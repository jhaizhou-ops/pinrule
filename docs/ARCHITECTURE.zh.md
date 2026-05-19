# pinrule 技术架构

**[🇬🇧 English](./ARCHITECTURE.md) · [🇨🇳 中文（当前）](./ARCHITECTURE.zh.md)**

## 总览

```
┌───────────────────────────────────────────────────────────┐
│  ~/.pinrule/                                         │
│  ├── rules.json              ← 用户手工维护核心方向        │
│  ├── violations.jsonl        ← 违反历史（5000 行自动 rotation）│
│  └── session-state/          ← 每 session 一 json (30 天自动清理)│
│      └── {session_id}.json   ← read_files / edit_files /  │
│                                  recent_bash / last_test_pass_ts / │
│                                  pending_bg_tasks ...     │
└───────────────────────────────────────────────────────────┘
                       │ 读 / 写
                       ▼
┌───────────────────────────────────────────────────────────┐
│  Claude hooks (~/.claude/hooks/)                     │
│  ├── pinrule_user_prompt_submit.py   ← 每条消息前注入规则   │
│  ├── pinrule_pre_tool_use.py         ← 实时拦截违反 tool 调用│
│  ├── pinrule_post_tool_use.py        ← 跟踪状态 + catchup    │
│  └── pinrule_stop.py                 ← 扫 response 违反      │
└───────────────────────────────────────────────────────────┘
                       │
                       │ additionalContext / permissionDecision
                       ▼
              ┌─────────────────────┐
              │   Claude            │
              │   (Agent loop)      │
              └─────────────────────┘
```

## 数据模型

### rules.json（用户手工维护）

```json
- id: long-term-fundamental         # kebab-case slug，CLI 用
  preference: |                     # 多行允许，注入 Claude 看到的就是这个
    用最根本、最长期、最普适、最优雅的方案。
    不打补丁、不硬编码、不为追短期 KPI 牺牲长期质量。
  violation_keywords:               # 关键词数组（任一匹配算违反）
    - 先打个补丁
    - 硬编码
    - 临时方案
  violation_checks:                 # 工程层 check 函数名（精确 pattern）
    - long_term_fundamental
```

字段：
- `id` — kebab-case 短 slug，唯一
- `preference` — 一句或多行的方向描述
- `violation_keywords` — 关键词数组（不区分大小写，子串匹配）
- `violation_checks` — `pinrule/checks/__init__.py:REGISTRY` 里的函数名

软上限 10 条，硬上限 12 条（超过 hook 拒绝加载，避免注意力稀释）。

### violations.jsonl

```jsonl
{"ts":1715617200,"session_id":"abc","rule_id":"long-term-fundamental","trigger":"硬编码","snippet":"...先 硬编码 这个值..."}
{"ts":1715617250,"session_id":"abc","rule_id":"non-blocking-parallel","trigger":"Bash sleep 命令: 'sleep 30'","snippet":"sleep 30 && echo done"}
```

append-only，行数超 5000 自动 rotation（`.1` `.2` `.3` 保留 3 个历史，最老的删）。

### session-state/{session_id}.json

```json
{
  "session_id": "abc",
  "read_files": ["/x/a.py", "/x/b.py"],
  "edit_files": ["/x/a.py"],
  "recent_bash": [
    {"ts":..., "command_summary":"pytest tests/", "is_test_cmd":true, "output_passed":true, "output_failed":false},
    ...
  ],
  "last_test_pass_ts": 1715617200.5,
  "last_edit_ts": 1715617100.3,
  "pending_bg_tasks": [
    {"cmd":"pytest > log.txt 2>&1","output_file":"/tmp/log.txt","started_ts":...}
  ]
}
```

跨 hook 共享状态：
- `read_files / edit_files` — read_first 检测用（Write/NotebookEdit 后自动 record_read）
- `recent_bash` — Bash 历史摘要（PASS/FAIL 信号 + 是否测试命令）
- `last_test_pass_ts vs last_edit_ts` — `has_recent_test_pass()` 用：「自最近代码改动以来跑过测试且通过」
- `pending_bg_tasks` — background 任务启动时 record，下次 hook 触发 `catchup_pending_bg` 读 output_file 接进通过证据

文件 30 天没动自动清理（user_prompt_submit hook 每 turn 跑 purge）。
保存用 `{stem}.{pid}.{ns}.json.tmp` + atomic rename，并发写不冲突。

## 4 个 Hook（Claude 标准协议）

### UserPromptSubmit hook

时机：用户发消息 → 模型看到消息前。

输入 stdin payload（Claude 协议）：
```json
{"prompt": "...", "session_id": "abc", "transcript_path": "...", "cwd": "..."}
```

输出 stdout：
```json
{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "...规则注入..."}}
```

实现：`pinrule/hooks/user_prompt_submit.py`
- 加载 `rules.json`
- 读 `violations.jsonl` 按 turn 距离取最近偏离过的 `rule_id`（标〔...偏离... 看看对齐〕回顾标记）
- 格式化 `[pinrule — 你跟用户的长期默契]` + 编号规则
- 顺带跑 `purge_old_states` + `catchup_pending_bg`（异常吞掉不阻塞）
- **协作回顾 fallback**（关键机制）：读 transcript 取上一 assistant message
  → 跑所有规则的 `violation_checks` → 命中的违反 + `suggested_fix` 注入「回顾」段
  覆盖 keep-pushing / chinese-plain / evidence 等所有 response 类 check
  这是「Stop hook 在 user 立刻接 prompt 时不一定跑」场景的事后兜底
  （Stop hook 装机正确时实战会跑 — matcher fix 后 trace 已实证 5 条实际 session 触发）

性能：< 60ms。

### PreToolUse hook（实时拦截，最关键的干预层）

时机：Agent 决定调 tool 但**还没执行**前。

输入 stdin payload：
```json
{"tool_name": "Bash", "tool_input": {"command": "sleep 30"}, "session_id": "abc", ...}
```

输出 stdout（允许）：
```json
{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}}
```

输出 stdout（拦截）：
```json
{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "..."}}
```

实现：`pinrule/hooks/pre_tool_use.py`

两层检测：
1. **工程层** — 跑规则配的 `violation_checks` 函数集（精确 regex pattern）
2. **关键词层（兜底）** — 扫 Bash command 骨架（剥引号字面 + heredoc 智能剥）+ Write/Edit 注释 + docstring

优先工程层（更精确），命中即 deny。Fail open 原则（配置错 / payload 解析失败 → allow，不卡 Agent）。

性能：< 100ms。

### PostToolUse hook（状态跟踪 + catchup）

时机：tool 调用完成后。

输入 stdin payload：
```json
{"tool_name": "Bash", "tool_input": {...}, "tool_response": {"stdout": "...", "stderr": "...", "backgroundTaskId": "..."}, "session_id": "abc"}
```

实现：`pinrule/hooks/post_tool_use.py`

主要逻辑：
1. 先跑 `state.catchup_pending_bg()` — 读上轮 background 任务 log 接通过证据
2. 判 `_tool_failed(tool_response)`（dict `isError`/`interrupted` 或 string 前缀）
3. 成功的 Read → `record_read`；成功的 Write/NotebookEdit → `record_edit + record_read`；成功的 Edit → `record_edit`；Bash 总是 record（PASS/FAIL 内部判）
4. 失败 tool 不 record（防 Read 失败也 record_read 让 read_first 被绕过）

性能：< 30ms。

### Stop hook（response 扫违反 + 实时干预）

时机：Agent 响应完成（这条 turn 结束）。

输入 stdin payload（**没有** response 字段，要读 transcript）：
```json
{"session_id": "abc", "transcript_path": "/path/to/transcript.jsonl", "cwd": "..."}
```

实现：`pinrule/hooks/stop.py`
1. 读 transcript_path JSONL，找最后一条 `type=assistant` 取所有 text content
2. 扫 violation_keywords 关键词层 + 工程层 violation_checks（chinese_plain / evidence / keep_pushing / **long_term_fundamental response-level** 主要在这层 — v0.11.0+ 加了 response-level 短期意图话术检测）
3. 命中违反写 `violations.jsonl` + stderr 通知 + 桌面通知 + 累积告警
4. **keep-pushing-no-stop 命中 → 输出 `{"decision": "block", "reason": "..."}`** 让 Agent
   不立即停下继续生成（干预规则 #7「不主动停」）。Safeguard：单 turn 内累积 block ≥ N
   次（config `stop_block_max_per_turn` 默认 2）后让 Agent 停下，防死循环
5. 否则输出 `additionalContext` 给下次 UserPromptSubmit 看

性能：< 200ms。

**⚠️ Stop hook 配置注意**：Stop / SessionStart / SessionEnd 等 event **不支持
`matcher` 字段** — Claude 看到 matcher 会无声忽略整个 hook entry。
`pinrule install-hooks` 已修：Stop entry 不加 matcher，PreToolUse/PostToolUse/
UserPromptSubmit 才加。如果你看 `/tmp/pinrule_stop_trace.log` 实际 session 0 条，
先检查 `~/.claude/settings.json` 的 Stop entry 是否含 matcher 字段。

## 四端能力对照

每家 backend native event 触达面 — 四端共用 pinrule 核心逻辑, 但每家挑该平台原生协议最强的触达点 (Cursor 4 个独立 gate / Codex PermissionRequest / Claude PreCompact 落盘), 不互相套别家协议形状.

| 能力 | Claude | Codex | Cursor | Hermes |
|---|---|---|---|---|
| Native hook 数 | 8 | 6 | 12 | 5 |
| 起手注入规则 | ✓ SessionStart | ✓ SessionStart | ✓ sessionStart | ✓ on_session_start |
| 工具调用前实时拦截 | ✓ PreToolUse | ✓ PreToolUse + PermissionRequest | ✓ preToolUse + 4 个独立 gate (Shell / MCP / Read / File) | ✓ pre_tool_call |
| Stop 干预 | ✓ block 决策 | ✓ block 决策 | ✓ followup_message (自动续推) | — (on_session_end 真 fire 但无 transcript) |
| compact 后续命 | ✓ PreCompact 落盘 | — | ✓ preCompact 落盘 | — (持久 memory 模型) |
| 子 Agent 覆盖 | ✓ SubagentStart/Stop | — | ✓ subagentStart/Stop | — |
| `/pinrule <NL>` 加规则 | ✓ home 全局 | ✓ home 全局 | ⚠ 只 project-scoped | ✓ home 全局 (`~/.hermes/skills/`) |
| 可见性兜底 | — | trusted_hash 自动信任 | `.mdc` Rules `alwaysApply` | — (`--accept-hooks` flag 同意) |

**Hermes config 已知 limit** (v0.19.0): pinrule 自带 YAML subset parser 真不接受 hermes 默认 `~/.hermes/config.yaml` (含 multi-line string 续行 + `agent.personalities` 段 unicode escape continuation). 临时 workaround: `pinrule install-hooks --backend hermes` 生成 wrapper 后, 手工 append `hooks:` 段到 config.yaml — 详见 HOWTO. 真 line-based surgical operator v0.19.1 真补.

## 8 个 violation_check 函数（工程层精准检测）

`pinrule/checks/__init__.py:REGISTRY` 映射 `rules.json` 的 `violation_checks` 字符串 → 函数：

| check 名 | 规则 | 检测内容 |
|---|---|---|
| `long_term_fundamental` | 长期方案 | **L1 tool_input 层**：长 hash if 分支 / 黑白名单字面 / 全大写常量名单 / TODO 实际注释 / 意图字面注释 / commit message 主语 hack 词。**L2 response-level 层 (v0.11.0+)**：第一人称意图前缀 (我/咱/这次/临时/目前/当前/让我) + 12 字内短期动作动词 (先打补丁/硬编码/临时方案/绕过验证/patch 一下) → combo pattern 命中；反思话语「短期补丁不行」仍干净通过 |
| `non_blocking_parallel` | 不阻塞 | sleep / wait / 长任务无 background / 间接 shell 执行 |
| `chinese_plain_no_jargon` | 中文 | 中文占比（分母剥含点号工程标识符 / 路径字面 / commit message 引号块）+ jargon 检测（剥 code block / inline code）+ 同前缀字 ≥ 5 次/response 触发自审（白名单豁免一/不/是/有/没/我/你/他/这/那/在）|
| `loud_failure_with_evidence` | 完成证据 | 完成词 / weak claim 在代码任务上下文 + 无测试证据 |
| `no_testset_no_future_leakage` | 不喂测试集 | gold_cases 反喂 / 跨 split 复制 / 长 hash 在比较或赋值位置 |
| `read_before_write` | 先读再写 | Edit/Write 前未 Read 该 file_path（Write 新文件豁免） |
| `keep_pushing_no_stop` | 不主动停 | 优先级判：0) **user prompt 上文含叫停字眼**（不用了 / 休息吧 / 明天再说 / 先到这 / 算了 / 晚安 / 够了 等规则 #8 例外清单）→ 整 turn 豁免（最高优先级）1) response 末尾 80 字含推进信号（我现在 / 接下来 + 动词）→ 豁免 2) 含问号 → 豁免（合理询问决策应鼓励）3) 含停顿语气词（下次 / 先到这 / 告一段落）→ 命中 4) 默认命中（纯陈述完结无推进无问号）|
| `bypass_pinrule_detection` | 不绕检测（rule #1 深挖根因） | **L1 字面层**：Bash 命令含 pinrule 内部字面 (last_test_pass_ts / pending_bg_tasks / session-state json 路径) + 写操作 → 命中「绕开 pinrule」。豁免：pinrule 官方 CLI / 只读 inspection / commit message 引号字面。**L3 时序层 (v0.11.1+)**：pre_tool_use Edit + 上一 Bash 是测试命令且失败 + 当前 file_path 本 session 未 Read → 命中「报错后没看源代码就改」草草了事 pattern。L4 (认知深度 — Agent 心里有没有真挖) 工程拦不到，靠 preference 注入 |

每个 check 函数签名：`def check(*, tool_name, tool_input, response, session_state, **_) -> CheckHit | None`。

返回 `None` = 无违反，返回 `CheckHit(rule_id, trigger, snippet, suggested_fix)` = 违反命中。

## 共用 helpers（`pinrule/checks/common.py`）

跨 check 函数 + hook 共用：

- `extract_tool_text(tool_name, tool_input)` — 不同 tool 不同字段提取（Bash.command / Write.content / Edit.new_string）
- `strip_code_blocks(text)` — 剥 markdown ` ``` ` 代码块 + ` ` ` inline code
- `strip_shell_quoted_literals(cmd)` — 剥 shell `'...'` `"..."` 引号字面 + heredoc 智能剥（区分头部命令 bash/sh 保留扫 vs python/cat 剥）+ 间接 shell（`bash -c '...'` 内保留扫）
- `extract_natural_language(content, file_path)` — 抽出代码注释行（# / // / --）+ docstring（""" ''' /* */）

## i18n 系统 — 双向

pinrule 有两个 i18n 面，都按「数据不写代码」哲学：

### 说话端：`pinrule/i18n.py` + `data/locales/{en,zh}.json`

pinrule **说给 Agent 听**的内容 — hook 注入文本、suggested_fix 字符串、audit 标签。`tr(key, **fmt)` lookup + `{placeholder}` 插值 + 缺 key fail-open。locale 解析链：

```
PINRULE_LOCALE env > config.json `locale` 字段 > 自动检测（中文比例）> en fallback
```

**注入生命周期（v0.9.0）** — 说话端跨 5 个 hook 注入点，token 成本差距大：

| Hook | 格式 | token | 频率 |
|---|---|---|---|
| SessionStart | `format_for_injection`（全量，~1817）| ~1817 | 每 session 一次（含 compact 重起）|
| UserPromptSubmit | `format_anchor_only`（id + 第一行，~490）| ~490 | 每 turn |
| PostToolUse 中段 reinject | `format_for_injection`（全量）| ~1817 | session byte_seq 累积达模型阈值（Opus 60K / Sonnet 40K / Haiku 30K）|
| Stop hook 强提醒 | 违反 + suggested_fix | ~135 / 条 | 违反时 |
| SubagentStart | 子 Agent 精简规则 | ~383 | 起子 Agent 时 |

分层注入: UserPromptSubmit anchor 只列本 session 违反过的规则（median 1 条 ≈ 60 token; 干净 session = 0 anchor passthrough）. **真 dogfood 实测: 占对话约 2%**（30 sessions, 60% 工作 session 完全 0 anchor token）. SessionStart 跟 PostToolUse 中段 reinject 各承担一次全量, 把规则信号集中在 Agent 注意力高点 + 衰减拐点.

### 听话端：`pinrule/signals.py` + `data/signals/<name>/{zh,en}.{txt,py}`（v0.8.0 → v0.8.2；v0.17.0 起 yaml → Python 模块）

pinrule **从对话里听**的内容 — `keep_pushing` / `evidence` check 用的检测字眼。两种存储格式：

- **`.txt` 平面字眼**（一行一个，`#` 注释）：`user_stop_hints` / `agent_saturation` / `stop_hints` / `explicit_handoff` / `weak_claims` / `completion_words`
- **`.py` 模块 cartesian DSL**：`push_signals` — `DATA` dict 含 `templates`（`{subject}` / `{verb}` 占位符）+ 词集 + 不需 cartesian 的 `phrases`

7 个检测信号全部外部化。loader（`compile_alternation()`）扫信号目录所有语言文件，去重 + union + 编译成单 regex（长字眼优先；`.txt` 字面走 `re.escape`；`.py` 模板保 raw regex）。跨语言字符集不重叠 → 无误命中。

**加新语言**：每个 signal 目录扔一个 `xx.txt` / `xx.py`。零 Python 代码（数据模块除外），零 LLM 在循环里。

## 描述上下文统一豁免（`pinrule/checks/description_context.py`）

`is_description_context(tool_name, tool_input) → (bool, reason)`：

| 维度 | 判定 |
|---|---|
| 文档后缀 | `.md` / `.rst` / `.txt` / `.markdown` / `.adoc` |
| 测试目录 | path 含 `tests/` `test/` `__tests__` `spec` |
| 测试文件名 | `test_*.py` / `*_test.py` / `*_test.go` 等 |
| 临时探针 | `/tmp/` / `/var/tmp/` 路径 |
| 探针/样本命名 | 文件名含 `probe / scratch / sample / playground / fixture` |

命中即整段豁免工程层 `long_term` / `testset` + 关键词层（关键词层对 Write/Edit 也调此判定）。

## CLI 工具（`pinrule/cli.py`）

```bash
# 初始化
pinrule init                       # 创建 ~/.pinrule/ + 复制规则模板 + 装 skill

# 规则管理
pinrule rule list                  # 列出所有规则
pinrule rule edit                  # $EDITOR 打开 rules.json 编辑
pinrule rule remove <id>           # 移除某条
pinrule rule add --from-json <f>   # 程序化加规则（schema + REGISTRY 校验）
pinrule rule preview --from-json <f>  # dry-run 校验 + 注入预览

# 观察
pinrule stats                      # 每条规则违反统计
pinrule violations recent [N]      # 最近 N 条违反详情
pinrule violations clear           # 清违反历史（需确认）
pinrule audit                      # 每条规则 top 触发词频次 + 跨 locale 稳定分组

# 装机
pinrule install-hooks              # 生成 wrapper + 自动写 settings.json
pinrule install-skill [--force]    # 装 / 升级 /pinrule 自然语言 skill（多 backend）
pinrule uninstall-hooks            # 删 wrapper + 清 settings.json 里 pinrule entry
pinrule doctor                     # 检查环境 + 全部 hook / skill 装机状态
```

`install-hooks` 关键特性：
- idempotent — 多次运行结果一致
- 首次运行备份 `settings.json` 到 `settings.json.before-pinrule`
- 保留所有非 pinrule hook（rtk / codex-review 等共存）
- 用 wrapper 路径含 `pinrule_` 前缀识别 pinrule entry

## 配置

`~/.pinrule/config.json` 调阈值不用改代码。`pinrule doctor` 看当前生效值。
所有字段缺失走 `pinrule/config.py:DEFAULTS`（fail open），可只配关心的几条。

| 字段 | 默认 | 含义 |
|---|---|---|
| `notify_enabled` | `true` | 桌面通知开关（也可用 `PINRULE_NO_NOTIFY=1` 环境变量关） |
| `recent_violation_turns` | `5` | 偏离标记窗口 — 最近 N turn 内违反过的规则下次注入时标〔偏离〕回顾 |
| `escalate_window_turns` | `3` | 累积告警窗口（按 turn 距离） |
| `escalate_threshold` | `3` | 累积告警次数阈值 — 窗口内同规则命中 ≥ N 次升级 🚨 严重通知 |
| `stop_block_max_per_turn` | `2` | Stop hook 单 turn 内 `decision=block` 上限（防 keep-pushing 干预死循环）。`0` 完全关闭干预 |
| `force_block_threshold` | `5` | 累积强制 block 阈值 — 同规则窗口内违反 ≥ N 次 Stop hook 输出 `decision=block` 强制查根因。`0` 完全关闭。可在 `rules.json` 单条规则用 `force_block_exempt: true` 豁免 |
| `violations_max_lines` | `5000` | `violations.jsonl` 行数上限触发 rotation |
| `violations_keep_history` | `3` | rotation 保留几个历史 `.jsonl.{N}` |
| `session_state_max_age_days` | `30` | `session-state/*.json` 自动清理周期（天） |
| `max_recent_bash` | `15` | `SessionState` 保留最近 Bash 数量 |

`pinrule init` 复制 `data/config.example.json` 模板。

### 调试环境变量

- `PINRULE_NO_NOTIFY=1` — 关桌面通知（CI / 静音场景）
- `PINRULE_DEBUG=1` — `run_checks` 函数抛异常时 stderr 打 traceback（调试自定义 check）
- `PINRULE_DEBUG_TRACE=<path>` — Stop hook 触发时 append 一行 trace 到指定文件
  （验证 Stop hook 是否触发，production 默认完全关）

## 真 sandbox 隔离（`PINRULE_HOME` 环境变量）

v0.16.11 把 `PINRULE_HOME` 从「只管数据目录」扩成**真 install-root sandbox** — 所有锚点都跟着 env 路径走：

| 锚点 | 没设 `PINRULE_HOME` | `PINRULE_HOME=/tmp/foo` |
|---|---|---|
| 数据目录（rules.json / violations.jsonl / session-state/ / config.json） | `~/.pinrule/` | `/tmp/foo/.pinrule/`（走 `pinrule_home()`） |
| Hook wrapper 装机根 | `~/.claude/`, `~/.codex/`, `~/.cursor/`, `~/.hermes/` | `/tmp/foo/.claude/`, `/tmp/foo/.codex/`, `/tmp/foo/.cursor/`, `/tmp/foo/.hermes/`（走 `pinrule_install_root()`） |
| settings.json 入口 | 写 `~/.claude/settings.json` 等 | 写 `/tmp/foo/.claude/settings.json` 等 |
| Skill 文件（`SKILL.md`） | `~/.claude/skills/pinrule/`, `~/.codex/skills/pinrule/` | 镜像到 `/tmp/foo/...` |
| Cursor `.mdc` rules | `~/.cursor/rules/` | `/tmp/foo/.cursor/rules/` |

这就是「真 sandbox」路径 — `init` / `install-hooks` / `doctor` / `rule list` 全 confined。适用场景：朋友试用不动他主机，CI dry-run 完全隔离，多 profile 规则集（`PINRULE_HOME=~/work` vs `~/play`）。

```bash
PINRULE_HOME=/tmp/pinrule-trial pinrule init           # 全装到 /tmp/pinrule-trial
PINRULE_HOME=/tmp/pinrule-trial pinrule install-hooks  # Hook wrapper 也 sandbox
PINRULE_HOME=/tmp/pinrule-trial pinrule doctor         # 读同一 sandbox
rm -rf /tmp/pinrule-trial                              # 试完干净撤
```

**两个 source-of-truth helper**（都在 `pinrule/paths.py`）：
- `pinrule_home()` — 数据目录（rules.json 等）。所有 5 个 module（rule / violations / session_state / config / cli）都读这个。
- `pinrule_install_root()` — hook wrapper + settings.json + skill 的装机根。`_json_hooks.py` 的 4 个方法（`client_installed` / `hooks_dir` / `settings_path` / `settings_backup_path`）跟 Cursor backend 的 rules-dir 方法都读这个。

注：path 在 module-level 常量 import 时 freeze，所以 `PINRULE_HOME` 必须在启动 pinrule 进程**之前** set。Hook wrapper 调起的 pinrule 继承父进程 env，所以 sandbox 装完之后运行时 env 不用再保留（wrapper 路径本身已经是 sandbox 内部的了）。

## 跨平台支持

pinrule 真支持 Linux / macOS / Windows 三平台 — [CI 6 矩阵全绿](https://github.com/jhaizhou-ops/pinrule/actions/workflows/ci.yml)（ubuntu + macOS + Windows × Python 3.11 / 3.12）+ 朋友 Windows 真机 dogfood 确认能跑。平台实现细节：

- **hook 命令**在 `settings.json` / `hooks.json` 里用 `subprocess.list2cmdline([sys.executable, wrapper])` — 显式 `python.exe wrapper.py` 跨平台一致，含空格的路径自动加引号。
- **跨进程 file lock** Unix 上用 `fcntl.flock`（advisory，进程退出 kernel 自动释放）。Windows 上 no-op fallback — 真实使用一 session 一 AI 客户端不并发，单进程 pinrule 不受影响。N=20 并发压测只在 Unix 跑（验证 lock primitive，不验证真实用法）。
- **桌面通知**按 `sys.platform` 分发：macOS `osascript`、Linux `notify-send`、Windows `msg`（Pro/Enterprise 自带；Home 版静默 no-op）。
- **路径归一化** `_normalize_path` 用 `os.path.abspath(os.path.expanduser(...))` — stdlib 给出每平台正确行为；AI 客户端传 native 路径，真实场景跟期望一致。
- **stdio UTF-8** entry point 共享 `force_utf8_stdio()` helper —— `chcp 936` (zh-CN GBK default) Windows 控制台不会 crash 在 `▸` 等 CJK 符号。

## 性能预算

| 路径 | 预算 | 当前实测 |
|---|---|---|
| UserPromptSubmit | < 50ms | 5-15ms（rules.json 加载 + violations 读 200 行） |
| PreToolUse | < 100ms | 10-30ms（regex 扫 + check 函数集） |
| PostToolUse | < 30ms | 5-15ms（状态写 atomic rename） |
| Stop | < 200ms | 20-50ms（transcript 反向找 assistant + 扫违反） |

性能没成瓶颈 — 实测远低于预算。

## 安全 / 隐私

- 所有数据本地 `~/.pinrule/`
- 不上传任何数据
- 不调用 LLM（pinrule v2 全项目坚定不用 LLM，含 v1+ 也不引入）
- 用户随时 `rm -rf ~/.pinrule/` 清空状态
- `pinrule uninstall-hooks` 干净清理（删 wrapper + 清 settings.json）

## v0 边界（明确不做）

- ❌ 引入 LLM — 全工程化（regex / 计数 / 上下文判定）
- ❌ 数据库 — `violations.jsonl` + `session-state/*.json` 文本 IO 足够
- ❌ 自动蒸馏新 sticky — 用户掌控
- ❌ retrieval / cosine / scene 选规则 — 5-10 条 always-on
- ❌ Web UI / TUI — CLI + $EDITOR 足够

## 已交付里程碑

| 里程碑 | 状态 |
|---|---|
| M0 骨架 + 4 文档 | ✅ |
| M1 sticky 加载 + 2 hook 原型 + CLI 骨架 | ✅ |
| M1.5 PreToolUse 实时拦截 | ✅ |
| M2 6 个工程 check + session_state | ✅ |
| M2.1 适配 Claude Code 实际协议 | ✅ |
| M2.2 长 term check 按 tool 分组 + 文档豁免 | ✅ |
| M3 1-6 波 全面降假阳 + 假阴对偶 + 装机自动化 + 长期质量 + 描述上下文完整化 + 加严审计 | ✅ |
| v0.4.x v3 演化（中段注入 / SessionStart baseline / PreCompact dump / SubagentStart+Stop / 按模型自适应阈值 / 「协作默契」语气重写 / hook schema 严格合规）| ✅ |
| v0.5.0 sticky → rule 全代码库改名 + 向后兼容 alias 保留 | ✅ |
| v0.5.1 `pinrule rule add` / `rule preview` CLI + Claude Code skill 自然语言录入 | ✅ |
| v0.5.2 i18n MVP — `pinrule/i18n.py` + 5 个 hook 注入路径双语切换 | ✅ |
| v0.5.3 + v0.5.4 i18n 全覆盖 — 28 处 `suggested_fix` + 28 处 `CheckHit.trigger` 全 tr() | ✅ |
| v0.5.5 testset check `python -c` 字符串字面豁免（dogfooding 原因 fix）| ✅ |
| v0.5.6 `keep_pushing._PUSH_SIGNAL_RE` 补「下一推进点 / 下一步是」类未来规划短语 | ✅ |
| v0.5.7 `CheckHit` + `Violation` 加 `trigger_key` 字段 — `pinrule audit` 跨 locale 稳定分组 | ✅ |
| v0.5.8 + v0.5.9 Bash heredoc → 描述上下文路径豁免，从 testset.py 局部 helper 提到 `description_context.py` 共享层 | ✅ |
| v0.5.10 `pinrule --help` 顶部 docstring 列 `rule add/preview` 子命令（纯文档）| ✅ |
| v0.5.11 `skills/pinrule-rule.md` 清晰度 audit — 补 5 个 gap (anchor-vs-scope / overlap 决策表 / 内联草稿审阅 / locale-aware 语气 / 生效时机) | ✅ |
| v0.5.12 `pinrule init` 自动装 `pinrule-rule` skill + 新加 `pinrule install-skill [--force]` 命令 | ✅ |
| v0.5.13 audit 驱动 dedup — `is_python_c_command` helper 共享 + 34 处 `.sticky_id` callsite 清理 + `pinrule doctor` 报 skill 状态 | ✅ |
| v0.5.14 skill 教会 Agent 用 `remove + add` 现有命令组合做 modify（不加新 CLI；用户原则：不要为低频场景扩 CLI 表面）| ✅ |
| v0.5.15 v0.6.0 准备 — 计划稿 `docs/V0_6_0_PLAN.md` + 内部 11+4 处 `from pinrule.sticky` import 迁到 `from pinrule.rule` 让 v0.6.0 可以纯删除 commit | ✅ |
| v0.5.16 `/pinrule <自然语言>` skill 第一次可用 — 多 backend 装机（Claude Code / Codex / Gemini）含 Markdown → TOML 格式适配给 Gemini commands 路径；v0.5.1-15 诚实披露（装机路径错 → skill 从未触发）| ✅ |
| v0.5.17 README narrative 重写 — `/pinrule <NL>` skill 提升为顶级 section 而不是 patch 式提及；PRD F5 重写；ARCHITECTURE + HANDOFF 同步到 v0.5.16 现实 | ✅ |
| v0.5.18 `bypass_pinrule` false positive fix（dogfood 触发驱动）— redirect target 必须是 pinrule 路径才算绕过，不是「命令含 pinrule 路径 + 任何 write op」一刀切；`has_internal` field-name 维度对称收紧 | ✅ |
| v0.5.19 `keep_pushing` Agent 饱和声明豁免（dogfood 触发驱动）— 强饱和信号字眼 (`任务饱和` / `卡在 X` / `明天接力` 等) 豁免反思 hook，跟 v0.4.41 用户叫停豁免对偶；无强饱和信号的柔性停顿 (`今天到此为止` / `就这样吧`) 仍按 v0.4.22 拦 | ✅ |
| v0.5.20 rule 10 自审 follow-up — 同步 v0.5.19 漏的 ARCHITECTURE + HANDOFF（用户授权自审 catch，CHANGELOG 有条目但技术档案 doc 落后） | ✅ |
| **v0.6.0** ⚠️ BREAKING — 删除 `pinrule.sticky` 模块、`CheckHit`+`Violation` 的 `.sticky_id` @property、`pinrule sticky` CLI 子命令、`pinrule.rule`/`pinrule.cli` 内部 aliases（`Sticky` / `MAX_STICKY` / `StickyConfigError` / `EXAMPLE_STICKY*`）。数据兼容 shim（`rules.json`→`rules.json` 自动迁移、`violations.jsonl` `sticky_id` 字段兜底）永久保留。废弃周期：18 个 v0.5.x release。纯删除 commit — 得益于 v0.5.13/15 内部清理无需 refactor 逻辑。加 5 个 deletion-lock 测试。 | ✅ |
| v0.6.1 issue #1 用户 bug fix — `record_edit` 豁免非代码路径（README / CHANGELOG / docs/ / .gitignore 等）不推 `last_edit_ts`，所以 `docker pytest` 通过后改 README 再 git commit 不会被 `loud-failure-with-evidence` 误拦。实测复现根因是非代码 edit 后 `last_edit_ts > last_test_pass_ts`，不是 reporter 最初诊断的 regex 层。 | ✅ |
| v0.7.0 治根 refactor — 改写 pinrule 源规则文本里「真X」防御性前缀。用户抓到 Agent 从 pinrule 自身规则注入头部 in-context mimicry 出「真X」堆叠。撤销原计划的 `defensive_prefix_stacking` engine check（治表）改清源。规则模板 + locale + 用户面文档共 ~140 处重写。| ✅ |
| v0.7.1「真X」深度清理接力 — 用户指出 v0.7.0 同义词替换（`真→实际/确实`）不够，防御修饰本身大部分上下文里不必要。10 波 perl pipeline 覆盖 100 文件：767 → 120（84% 减少）。剩 120 处全是合理保留（named concept 真字狂魔 / eval 术语 真阳 / 工程对偶 真阻塞 / test fixture / 自然搭配 真心 真话）。修 doubled artifact `任务任务到饱和` bug。按用户「一次性修复完再提交」一次 commit。| ✅ |
| v0.7.2 撤掉 `chinese_plain` Check 3 reactive 监控 — v0.7.0+v0.7.1 治根后监控冗余。Check 3 是 v0.4.40 加的 reactive 治表对冲（代码注释自承「治症状不治根因」）。`pinrule audit` 确认治根后 168 条 violation 里 0 次触发。跟用户 v0.7.0 对 `defensive_prefix_stacking` 用过的同款逻辑；v0.7.2 闭环三个月前漏掉的同款思路。撤：`_check_repeated_prefix()` + 2 个 locale key + 2 个专用测试。| ✅ |
| v0.7.3 手工 audit 全部 GitHub 可见文档 — 用户指令逐个读不批处理（33 个 markdown 审过，22 个动了）。删营销话术（「≈ 0%」过度宣称 /「500+ 小时实战调优」）+ 清 v0.6.0 漏网的 `sticky` 老命令名 + 修正硬上限数字 14 → 12 + 砍冻结的「M3」「v0.5.x」milestone 标签 + 已落地 plan 文档标归档 + 重写过时 `HOOK_CONFIGURATION_GUIDE.md`（旧版列 9 hook 含不存在的 `PostCompact` → 改正为实际的 8 个）。净 −63 行。| ✅ |
| v0.7.4 `keep_pushing` 用户叫停字眼覆盖「满意 / 确认」类 — 当 turn dogfood：v0.7.3 ship 后用户说「感觉已经挺稳定了，不错不错」（满意叫停信号），但反思 hook 仍触发，因为 `_USER_STOP_HINT_RE` 只覆盖「累了 / 推卸」类（`休息吧 / 算了 / 够了`）。按 rule #7 治根：扩 regex 加第二类 — `不错不错 / 挺稳定 / 就这样吧 / 这就行 / 可以了 / OK 了` 等。两类都整 turn 豁免反思 hook。加 7 个新测试 fixture（含触发本版本的用户原话）。| ✅ |
| **v0.8.0 i18n 信号系统 — 检测字眼外部化到 `data/signals/<name>/{zh,en}.txt`**。用户洞察：之前 5 个检测 regex（`_USER_STOP_HINT_RE` / `_AGENT_SATURATION_RE` / `_STOP_HINT_RE` / `_EXPLICIT_USER_HANDOFF_RE` / `_WEAK_CLAIM_RE`）是中文硬编码；英文用户 `keep_pushing` 假阳烦人、`weak_claim` 漏拦。新 `pinrule/signals.py` loader 加载信号目录下所有语言文件，去重 union 编译（长字眼优先）。不同语言字符集不重叠 → 跨语言无误命中。**加新语言 = 0 Python 代码，每个 signal 目录提交一个 `.txt` 即可**。5 个信号的英文覆盖一次到位。`tests/test_signals.py` 加 13 个单元测试 + keep_pushing / evidence 加 4 个英文覆盖测试。`_PUSH_SIGNAL_RE`（cartesian 结构）留 v0.8.1。| ✅ |
| **v0.8.1 `push_signals` 用 YAML DSL i18n — cartesian 模板 + 词集 + 平面字眼**。v0.8.0 的 `.txt` 平面字眼格式跟 `_PUSH_SIGNAL_RE` 的「主语 + 副词 + 动词」cartesian 结构对不上。新 `.yaml` schema：`templates` 字段含 `{subject}` `{verb}` 占位符，`subjects` / `verbs` 词集做 cartesian 展开，加 `phrases` 整句平面字眼。`pinrule/signals.py` 加 `load_patterns()` + `_expand_yaml_signals()`（单数 → 复数占位符解析；yaml 模板保 raw regex 不 escape，`.txt` 字眼 `re.escape`）。1106 个展开 phrase（中英文合并）。历史 `(?!\s*[吧行])` lookahead 移出 regex 到 `check()` 后处理 `_PUSHBACK_TAIL_RE` — yaml 保持简洁。**6 个检测信号全 i18n 外部化**；加新语言 = ~6 个小文件，零 Python。6 个新 signals 测试 + 2 个英文推进测试。| ✅ |
| **v0.8.2 代码审查 — 死代码 + 命名一致 + bug fix**。用户要求 audit。工具扫干净（vulture / ruff）但手工 grep 找到 3 个死代码（注释自己说「v0.6.0 移除」但没真删 — `PINRULE_RULE_SKILL_SRC` / `_claude_skills_dir` / `_install_pinrule_rule_skill`）。v0.6.0 BREAKING 后大量 `sticky` → `rule` 命名残留也一并清：`cmd_sticky_*` → `cmd_rule_*`、`STICKY_PATH` → `RULES_PATH`（18 处）、`doctor` / `audit` / `violations clear` / `rule list` / 3 个 hook stderr 输出。audit 中发现真 bug：`cmd_violations_clear` 直接读 `d.get("sticky_id")` 绕过 v0.5.0+ rule_id/sticky_id 兼容垫层 — 改用 `extract_rule_id()` helper 修。i18n 一致性补：加 `completion_words` 信号（v0.8.0 跟 `weak_claims` 一起漏的）；**7 个检测信号全 i18n 外部化**。3 个新测试。| ✅ |
| **v0.8.3 内部 refactor — 长 hook main 拆 helper + cli.py import 去重**。`stop.py:main` 223→123（3 个 helper：`_emit_notifications`/`_handle_force_block`/`_handle_keep_pushing_block`），`user_prompt_submit.py:main` 159→68（2 个 helper：`_advance_turn_state`/`_build_strong_reminder`），`pre_tool_use.py:main` 128→90（2 个 helper 去重 parallel deny 逻辑）。cli.py：4 处函数级重复 import 删；module 顶部统一 alias `load as load_rules` + `format_for_injection`；3 处裸 `load()` 改 `load_rules()` 一致命名。455/455 通过，0 行为变化。| ✅ |
| **v0.8.4 v0.8.x 累积文档同步 + v0.8.2 audit 漏的 1 处死代码**。README / PRD / ARCHITECTURE 里过时的「6 个信号」数字（v0.8.0+v0.8.1 时期数字；v0.8.2 加 `completion_words` 后该是 7）全更新到 7。`pinrule/checks/__init__.py:run_checks()` 有个 `sticky_id` 参数注释自己写「v0.6.0 移除」但没真删 — 0 调用者，删参数 + 引用它的 `rule_id or sticky_id` fallback 行。是 v0.8.2「注释说移除但还活着」死代码 pattern 的第 4 例。455/455 通过。| ✅ |
| **v0.8.5 第 3 轮代码审查 — 2 处高价值清理 + 干净状态确认**。用户要求第 3 轮 audit。工具扫干净（vulture/ruff/455 测试）；手工 audit 找到 2 处高价值：`rule.py:format_for_injection` function-level `from pinrule.i18n import tr` 上提到 module 顶部（i18n 是 leaf module，无循环风险）；`chinese_plain.py:L179` inline magic `< 30` 抽 `_JARGON_PAREN_MAX_DIST = 30` 常量。诚实跳过中低价值 polish（cli.py 10 处 function-level import — 部分服务测试 mock 友好性；4 个 cli 长函数 — coordinator 无死代码）。文档一致性 audit：测试数 455 + 信号数 7 + 16 个关键文档 0 死链。v0.8.x 系列以「工具+手工+文档」三方一致干净状态收官。| ✅ |
| **v0.8.6 `agent_saturation` 裸字眼覆盖 — 当 turn dogfood**。v0.8.5 release notes 用了「真饱和」和「optimization for its own sake」— 都是合理饱和声明但 `agent_saturation` 信号漏命中。同 v0.7.4 user_stop_hints 覆盖漏 pattern。zh 加：裸 `真饱和` / `彻底饱和` / `系列收官` / `干净状态收官`；en 加：`genuinely saturated` / `truly saturated` / `diminishing returns` / `optimization for its own sake`。1 个新测试覆盖 6 个 fixture。456/456 通过。| ✅ |
| **v0.9.0 注入架构重设计 — 每 turn 节省 73% token**。v0.8.6 后用户洞察：「session 初始 + 不同模型默认锚定阈值就近注入 + 违规注入 + 压缩后注入 + 子 Agent 注入」— 每 turn 不需要重新全量注入（跟 conversation history 重复）。3 个协同改动：(1) SessionStart 改全量 baseline 覆盖 4 source；(2) UserPromptSubmit 每 turn 精简 anchor（id + 第一行 + 偏离标记，~490 tok vs 1817 —— 新 `format_anchor_only()` 函数）；(3) PostToolUse 中段 reinject 按 session 全局 byte 累积达模型阈值触发（不每 turn 重置），阈值收紧到 Opus 60K / Sonnet 40K / Haiku 30K。state 字段语义：`tool_byte_seq` 不再每 turn 重置。**460/460 通过**。1M Opus session 实测节省：18.4% → 8.2% (~100K token / 55% 减少)。| ✅ |
| **v0.9.1 v0.9.0 文档同步 follow-up**。用户在新 session dogfood v0.9.0 看到精简 anchor 格式生效后要求做 doc-sync follow-up。更新 `docs/PRD.md` / `docs/PRD.zh.md` F2 描述（精简 anchor）+ 加新 F2.5「注入架构 v0.9.0」5-hook 生命周期表；`docs/HOOK_CONFIGURATION_GUIDE.md` 各 hook 描述；`pinrule/hooks/session_start.py` docstring（之前描述方向反了，说「UserPromptSubmit 每 turn 全量，SessionStart 一次精简」— 跟 v0.9.0 实际相反）。纯文档 patch，0 行为变化。| ✅ |
| **v0.9.2 `test_compact_hooks.py` 硬编码 `/Users/jhz/pinrule` 路径 → 动态解析（issue #2）**。@fyn1320068837-source 第 2 次报。9 个测试共 20 处硬编码维护者本机路径 → 本机通过但其他机器（含 CI）全部 FileNotFoundError。issue 出来后才查：**GitHub Actions CI 从 v0.8.6 起 fail 3 个 release**（v0.8.6 / v0.9.0 / v0.9.1）。我每次说「pytest 460/460 通过」没看 CI — 同款 v0.6.1 第一次外部 dogfood 教训。按 reporter 建议 fix：`PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent` + `PYTHON = sys.executable`。本机 460/460 仍通过，现在可移植。| ✅ |
| **v0.9.3 真把 CI 修绿 — v0.9.2 不是全部根因**。v0.9.2 push 后按新 checklist 跑 `gh run list`：CI **仍然红**。不同根因：CI 跑 `vulture pinrule/ --min-confidence 60` 我本机一直跑 `--min-confidence 70`。60 confidence 找到 4 处真死代码本机看不到（cli.py 的 `EXAMPLE_RULES`/`EXAMPLE_RULES_MINIMAL` 别名、i18n.py 的 `current_locale()`/`reset_cache()`）+ 1 处 vulture 假阳（`signals.reset_cache` 被 tests 用但 vulture 只扫 `pinrule/`）。删 4 个真死，加 `whitelist.py` 引用 `signals.reset_cache`，改 `ci.yml` 喂 whitelist。本机-CI 质量门禁阈值不匹配是 v0.8.6 → v0.9.2 CI 红 streak 的深层根因。checklist 加：tag 前用 `--min-confidence 60`（匹配 CI）跑 vulture。| ✅ |
| **v0.9.4 CI 仍红 — 第 3 根因：`mypy` 严格模式抓 `signals.py` `Optional[list]` 类型收窄**。v0.9.3 push 后 CI **仍在 `mypy pinrule/` 上红**。CI 跑 mypy；我本机 checklist 从来没跑。`signals.py:_expand_yaml_signals` 的 `[v for _, v in resolved]` 出现在 `any(v is None for _, v in resolved): continue` 守护之后 — 运行时安全但 mypy 看不到守护、推断 `list[list \| None]` → `product(*word_lists)` 类型不兼容。fix：显式 `[v for _, v in resolved if v is not None]` 收窄到 `list[list]`。本机 checklist 补 `mypy pinrule/ && mypy tests/` 匹配 CI。| ✅ |
| **v0.9.5 CI 仍红 — 第 4 根因：测试假设 zh locale，CI 跑 en**。v0.9.4 push 后 CI **仍在 `pytest` 上红**（16 处 fail）。我本机 `LANG=zh_CN.UTF-8` → `pinrule.locale_detect.is_chinese_user()` True → i18n 选 zh → fixture 通过。CI runner 默认 `en_US.UTF-8` → False → en → 断言 `"默契"` / `"偏离"` / `"纯陈述"` 中文字面的 fixture 全 fail。fix：新建 `tests/conftest.py:pytest_configure` 在任何 pinrule import 之前 `os.environ.setdefault("PINRULE_LOCALE", "zh")`。测试现在总跑 zh 不管 host locale。本机 checklist 加 `LANG=en_US.UTF-8 pytest -q`（第 5 道门，抓 locale 耦合 bug）。v0.9.2 → v0.9.5 4 个 patch release 每个修一个独立 CI fail 根因，每次都被我本机 checklist 漏掉。| ✅ |
| **v0.9.6 CI 仍红 — 第 5 根因：v0.6.0 BREAKING 重命名在 `verify wheel` step 留的残留**。v0.9.5 push 后 CI **仍在 `Verify wheel contains yaml templates` 上红**，4 matrix job 全挂。CI verify 查 wheel 含 `data/sticky.dev.example.yaml` — 但 v0.6.0 BREAKING 把 `sticky.*` 改名 `rules.*`。**这步从 v0.6.0 起就一直在 fail（大概 9 个 release）** — 只是前面 (vulture/mypy/pytest) 一直挂在前头挡着。fix：`ci.yml` 的 expected 列表对齐 wheel 实际产物（`data/rules.dev.example.json` / `data/rules.dev.example.zh.json` / `data/locales/{en,zh}.json` / `data/config.example.json` / `skills/pinrule/SKILL.md`）。本机 checklist 加第 6 道门禁：`python -m build --wheel + verify` — 本机 checklist 现在是 CI step 顺序的真超集。元教训：我一直在「每一层都说『就是这个根因』」却没验证 CI 真到 terminal green 才停。真正最深的一层是本机 checklist 跟 CI pipeline 覆盖面不一致的结构性问题。| ✅ |
| **v0.9.7 PINRULE_HOME 隔离 mode 下 bypass 检测失效 + user-facing sticky 残留 + 加 regression 锁机制**。用户问 v0.9.6 子 Agent 报告里「合法保留」类是否真合法触发审计。确认子 Agent 对 CLI migration shim 判定对（那处不是字面硬编码），但**全仓 grep 后发现 2 个真 bug 子 Agent 漏报**：(1) `pinrule/checks/bypass_pinrule.py:_PINRULE_STATE_PATH_RE` 硬编码 `\.pinrule/...` 字面正则 — 用户跑 `PINRULE_HOME=/tmp/foo` 后 `rm /tmp/foo/session-state/*.json`（绕开尝试）**完全打不到**，正则只 match 默认路径。fix：`_build_state_path_re()` 工厂按 `pinrule_home()` 动态构造正则。文件名集合扩成同时拦 `rules.json` 跟 `rules.json`。(2) `pinrule/cli.py:257` 硬编码 `"vim ~/.pinrule/config.json"` 在 `PINRULE_HOME` mode 下把用户骗到不存在的文件 — fix：f-string 用 `config_path` 变量。加上 5 处 user-facing `sticky` 残留（`data/locales/zh.json` + `data/config.example.json` + 2 个 rules.dev example zh + 4 处 `violations.py` API docstring 谎称返回 `sticky_id`）。**Regression 锁机制**：新加 `tests/test_no_sticky_in_user_facing.py` 白名单方式锁 7 个 user-facing 文件 — 下次有人引入旧名 CI 直接 fail。白名单是「行字面精确匹配」非「文件级豁免」— 细粒度可审计。dev-facing 残留（cli/hook/notify module docstring + tests 变量名 ~10 处）留 v0.10.x 单独大扫，不进 v0.9.7 打补丁。`test_bypass_pinrule.py` 加 4 个 PINRULE_HOME 隔离 case。466/466 双 locale 都过。| ✅ |
| **v0.9.8 跨进程并发 race fix + API 强制原子性 `update_state(sid, fn)`**。给同事压测准备 audit 4 个可靠性怀疑点，3 个已 graceful，第 4 个真 bug — session_state.py 自己注释里就写着 TODO 加 file lock 但一直没加。实际 race 比 TODO 描述的更广：多 hook 同时 `load → modify → save` 第二个 save 覆盖第一个全部字段更新（不只 ltp 时序）。**反短期路线对齐时刻**：第一遍我选 contextmanager 方案 A（「v0.9.8 务实留 v0.10/v1 走 B」framing），用户拦下来「咱们要做长期方案，你忘了么？」— pinrule 检测层 pure-engineering regex 抓不到 design-intent 短期化（zero-LLM 原则已声明的边界）；人工监督就是兜底。回滚 + 重设计走方案 C 跟用户对齐：保留 `load`/`save` public（tests/ 58 处合理 lower-level 用户）；加 `update_state(sid, fn) -> tuple[state, T]` 作为 production API 打包 `_state_lock`（fcntl.flock advisory lock，Windows no-op fallback）；加 `read_state(sid)` 显式只读（`os.replace` 原子写让只读 lock-free）。6 个 hook 迁 `update_state`，`cli.py` 2 处只读迁 `read_state`。7 个新测试含 **N=20 subprocess 并发不丢更新真测**——race fix 真证据。473/473 双 locale 都过。**不变量（「同 session load → modify → save 必须原子」）在 API 形状而非调用约定** — 新加 hook 不可能漏套 lock。| ✅ |
| **v0.9.9 onboarding 反馈 — `pinrule init` 末尾展示默认启用规则简要列表**。用户驱动产品方向决策（v0.9.8 可靠性收官后）：「能不能给新安装的用户一个显式反馈，比如让 Agent 帮忙安装的话，最终会给用户一个默认启用的规则简要内容的列表展示？」加 `_print_default_rules_summary()` helper 在 `cmd_init` 末尾调用：每条 1 行（`id` + `preference` 首行），header 文字双语走 `init.summary.header` locale key。Agent 跑 `pinrule init` 看到这段 stdout 自然 paraphrase 给用户。**设计取舍 — 刻意不加「下一步: 跑 X 命令」tip**：第一版带了 `pinrule rule edit / list / remove` tip 块，用户反馈「我可能没说清楚，我不想让用户手动输一条指令」。删掉 tip。原则：Agent 转述完规则列表后，用户想改就跟 Agent 说「帮我去掉规则 X」/「改下规则 Y」 — Agent 知道用 `/pinrule` skill 或 `pinrule rule edit`，用户不需要敲命令语法。2 个新测试含一个锁定 invariant 的 regression test 确保未来 PR 不能重新引入命令 tip 到 summary 段。477/477 双 locale 都过。| ✅ |
| **v0.9.10 onboarding 打磨 — summary 首段替代首行 + footer (3% token 安心 + `/pinrule` 入口)**。v0.9.9 验收后用户提两点打磨：(1) `split("\n")[0]` 砍在 yaml visual wrap 处导致半句截断（`long-term-fundamental` 展示「...When facing hard problems」后面「they want you to pause...」全砍）。用户选方案 (b)：改成首段（`split("\n\n")[0]`），每条简介是完整意思单元。长度 tradeoff：zh full 7 ~33 行 / en minimal 5 ~37 行 — 仍在 Agent 转述合理量级。(2) 用户希望加 footer：「经测试，以上规则注入仅占 pinrule 每 session 会话 token 消耗总量的 3% 以内，请放心使用，体验下 Agent 长任务不飘逸的爽感。希望增改规则直接输入 /pinrule <自然语言你想增加的规则> 即可。」新 `init.summary.footer` 双语 locale key 走 `_resolve_locale()`（中文系统用户自动看中文 footer，英文系统看英文）。**`/pinrule` 不违反 v0.9.9「不加指令 tip」原则**：那是客户端对话框里输的 slash command，不是 shell 命令需要开 terminal，用户输 `/pinrule <意图>` 等于「跟 Agent 说想要什么规则」— in-chat 协作延续不是「去 shell 跑」friction。2 个新测试含 `test_init_summary_footer_matches_user_locale` 锁定双语 footer 跟用户 locale 一致 invariant。479/479 双 locale 都过。| ✅ |
| **v0.9.11 可观察性 — `pinrule audit --by-check` engine check 命中分布 + `/pinrule` 无参数默认展示该视图**。v0.9.10 打磨收官后问用户下一波方向 check 可观察性 vs 周报。**用户设计洞见**：「skill 的增加会造成额外的用户使用成本... 第一个方向是不是直接做成 /pinrule 指令不带内容时候的默认输出就比较好？」— 避开新 entry point；复用 `/pinrule`（用户已从 v0.9.10 footer 知道）做 in-chat 数据 dashboard handle。实施：(a) 新 `_cmd_audit_by_check()` 按 `Violation.trigger_key`（v0.5.7 已有 i18n key，格式 `check.<name>[.<sub>].trigger`）聚合 — top-level 每个 check 计数 + sub-variant 细分（`evidence.commit` vs `evidence.completion` 等）+ 独立 keyword-only 桶。**不需要 schema 变更**：复用 trigger_key，历史 jsonl 没该字段归 keyword-only。(b) `pinrule/cli.py` main dispatch 解析 `--by-check` flag，默认 audit 不变向后兼容。(c) `skills/pinrule/SKILL.md` 加 "No-argument flow" 段：`/pinrule` 空 `$ARGUMENTS` → Agent 跑 `pinrule audit --by-check` 转述给用户附简要解读（高命中 check / 高 keyword-only 占比 / sub-variant 假阳嫌疑），然后问「想调哪条？」。**闭合 dogfood 反馈闭环**不用发明新命令：violations.jsonl → audit → 用户看 pattern → 决定调整。真数据验证：作者本机 187 条 dogfood 数据 first-run 跑出有意义分布（`keep_pushing.default` 占 engine 命中 69%，86% 是 keyword-only 兜底）。2 个新测试含向后兼容 lockdown。481/481 双 locale 都过。⚠️ **v0.9.12 暴露的数据解读陷阱**：「86% keyword-only」是 instrumentation artifact（见 v0.9.12）。| ✅ |
| **v0.9.12 数据管道 bug 修复 — `_build_strong_reminder` hook fallback 漏传 `trigger_key`**。v0.9.11 first-run dogfood 跑出「86% keyword-only / 14% engine」我自信解读成用户行为信号。**用户 follow-up 问「只 1 次触发的 (`bypass_pinrule` / `evidence.completion` / `testset`) 是规则设计冗余还是漏监控」就是暴露 instrumentation bug 的 prompt**：read 真 jsonl 发现两条 violation 的 `trigger` 字面完全一样（都是 `check.keep_pushing.default.trigger` 的 i18n 输出）但一条有 `trigger_key` 字段一条没有。纯字段缺失差异。根因：`user_prompt_submit.py:_build_strong_reminder`（v0.4.41 fallback 路径 — 用户立刻接 prompt stop hook 来不及跑这条路径补写）构造 `Violation` 漏 `trigger_key=h.trigger_key`，`pre_tool_use.py` 跟 `stop.py` 都传了。经这条 fallback 路径的 engine 命中被错归 keyword-only。**应用修正后重新分析**：真 `keep_pushing` engine 命中 ≈ 99（不是 20）；真 `bypass_pinrule` ≈ 7（不是 1）；`evidence.completion` ≈ 10；`testset.*` ≈ 5 — **没一个「1 次触发」是真冗余**，都是被数据管道 bug 少数。fix：`_build_strong_reminder` 加 `trigger_key=h.trigger_key`。**Regression lockdown**：新 `test_all_hook_violation_writes_pass_trigger_key` 静态扫 `pinrule/hooks/*.py` 所有 `Violation(...)` 或 `_V(...)` 调用，含 `rule_id=...` 必须也有 `trigger_key=...` — 不变量进测试套件。**没回填历史 jsonl**（规则 5 [no-testset-no-future-leakage]：重写老 record 让 dashboard 数字好看是「修过去验证现在」的反喂 pattern 项目拒绝）。替代：`cmd_audit --by-check` footer 加 caveat 说 v0.9.12 前老数据可能错归类，只 v0.9.12+ 写入准确。**元教训**：规则 4 [loud-failure-with-evidence] 双向适用 — 声称结果后还要验证结果不是 instrument artifact。482/482 双 locale 都过。| ✅ |
| **v0.9.13 全面 instrumentation audit — 用 v0.9.12 pattern 作模板抓 4 个准确性 bug**。v0.9.12 后用户问「全面排查下，还有没有这种 bug，直接影响 pinrule 运行准确性和统计准确性的」。起综合 audit 覆盖 Type A（字段缺失）/ B（off-by-one）/ C（race）/ D（i18n 不一致）。子 Agent 报 5 个发现；按规则 4 逐个 hand-verify — 1 个子 Agent 误判（agent_id 编码在文件名不在 payload），4 个真 bug。**A1**：`load_all()` 读 jsonl 漏 `agent_id`（写侧 to_json 有写）；audit/stats 无法真按主/子 Agent 分组。fix：`agent_id=d.get("agent_id")` 加进 `load_all`。**B1**：turn 窗口 `cutoff = cur - window` 让 `[cur-window, cur]` 共 N+1 turn 不是 N。最严重影响 `stop.py:162 force_block`（`force_window=3, threshold=5`）— 用户 3 turn 前已修过原因仍可能因第 4 turn 旧违反算进 threshold 触发 force_block。config.json 注释字面说「最近 N turn 内」，N+1 是错的。fix：`cutoff = cur - (window - 1)` 同步改 `recent_turns` / `count_recent_turns` / `cli.py:836` 漂移视图。一个现有 fixture `test_stop_hook_force_blocks_on_accumulated_violations` 严丝合缝卡在旧 cutoff 才达 threshold=5 — fixture 加到 6 条（不是 5 条）含诚实注释说「fixture 调整反映 fix 正确性，不是为了让 test 过」。**C1**：`pre_tool_use.py:98-100` `load + catchup_pending_bg + no save`。我之前 v0.9.8 时 read 这块判 design choice（「PreToolUse 是决策端」）；子 Agent 拍我错 — `catchup_pending_bg()` 改 pending_bg_tasks / recent_bash 不持久化让下次 hook 重复 catchup 同任务。迁 `update_state(sid, lambda s: s.catchup_pending_bg(), agent_id=...)` 跟 v0.9.8 架构一致。**D1**：`data/signals/weak_claims/zh.txt` 只 8 个 hedge 字眼 vs en 23 个 — 中文用户 evidence check 召回率 ~35%。扩到 25 字眼覆盖「应该」家族 / 「大概率」/「可能/也许」/「推测/我猜/估计」/「看起来/似乎/好像」。3 个新 lockdown 含 `test_weak_claims_zh_en_coverage_parity`（锁 zh/en 字眼数差距 < 30%）跟 `test_recent_turns_window_lockdown_v0913`（显式 `window=N → N turn`）。485/485 双 locale 都过。**元 pattern 印证**：v0.9.12「86% keyword-only artifact」不是一次性 — 是「意图跟实现 instrumentation drift 多年沉淀」的症状。对自信解读的一个高质量 follow-up question 能暴露一群相关 peer bug 非孤立单个。| ✅ |

| **v0.9.14 多 Agent 交叉互审抓 v0.9.13 我自己引入回归 — `pre_tool_use` `update_state` 漏套 try/except**。用户：「每次多 Agent 交叉互审就能挖出很深的 bug 也是很有趣的一件事。再来一轮。」起 3 个并行 audit Agent **不同视角**（避开 v0.9.13 已扫 surface）：视角 1（8 engine check 逻辑 FP/FN）、视角 2（config defaults 漂移）、视角 3（fail-open 契约）。按规则 4 逐个 verify。**视角 1 大部分噪音**：6/8 是子 Agent 误判 design choice（chinese_plain 表格 jargon 计数 v0.4.22 by design；`_LONG_TASK_RE` 漏 `npm run` 是 by design user-script 时长不可预测）。**视角 2 干净** — DEFAULTS 跟所有 fallback 一致。**视角 3 抓到真 bug** — v0.9.13 C1 migration 我自己引入回归：把 `pre_tool_use.py:98-100` 从 `load + catchup + no save` 迁到 `update_state(sid, lambda s: s.catchup_pending_bg(), agent_id=...)` 时**漏套 try/except**。原 `load + catchup` 隐式 fail-safe，但 `update_state` 引入新失败路径（fcntl.flock acquire / save OSError）。任一抛异常 bubble → `pre_tool_use.main()` return 非 0 → Claude Code 看到 hook 失败 → **用户被卡不能调用 tool**（fail-closed 违反 pinrule 设计原则）。**fix**：套 try/except + 降级裸 `load()`（这一 turn 不持久化 catchup 但 PreToolUse 能用 stale state 决策不挂）。**视角 1 一个真 FN**：`_LONG_TASK_RE` 加 `pip install` pattern（pip install 总 ≥30s）。2 个新 regression test 含 PreToolUse fail-open lockdown。**Audit 信噪比对比**：v0.9.13 单 Agent 4 类 5 发现/4 真 bug（高信噪 — 多年沉淀 drift）；v0.9.14 3 Agent 并行不同视角 ~9 发现/2 真 bug（低信噪 — 已干净）。**边际价值递减确认**：后续 audit 主要 catch 上轮 fix 引入的回归。**规则 4 现在三方向适用**：forward（声称+evidence）/ backward（验证不是 artifact，v0.9.12 教训）/ **self-verify post-fix**（声称 fix 后验证 fix 没引入回归，v0.9.14 教训 — 多 Agent cross-audit 是一种方式）。487/487 双 locale 都过。| ✅ |

| **v0.9.15 cross-model audit (GPT-5.5) 抓 3 个 cross-backend 协议 bug + critical wheel 打包遗漏**. 用户：「再来一轮 cross-audit，本机配置了 codex cli，也配置好了 gpt 5.5 模型，你委派 codex cli 做一次多 Agent 交叉评审。」跑 `codex exec` GPT-5.5 xhigh reasoning 两次 — 高层 audit + 全仓 code review. **cross-model 视角暴露 Claude 端 audit 每轮都漏的 bug**：(1) Gemini BeforeTool 要求顶层 `{decision: "deny", reason}` 不是 Claude `hookSpecificOutput` — pinrule Gemini 拦截 no-op（写 violation + stderr 但危险 tool 真执行）。(2) Gemini tool_name 用 `run_shell_command`/`read_file` — pinrule checks 用 Claude `Bash`/`Read`/`Edit` 比较 → Gemini 下 0 check 触发。(3) Codex `apply_patch` 是 Codex 文档明确的编辑 tool_name 但 pinrule 0 处理 → `apply_patch` 编辑绕过 `read_first`/`evidence`/`long_term`/`testset`，`last_edit_ts` 不推进。**WebFetch Gemini/Codex/Claude Code 三家官方文档** 三重 verify 协议假设，catch 一处 codex audit 误判（Codex 实际接受新 `hookSpecificOutput` shape — pinrule Claude/Codex 端 OK，只缺 `apply_patch` 处理）。**Fix**：新 `pinrule/backends/protocol_adapter.py` 集中 `detect_backend()`（via `hook_event_name`）+ `normalize_tool_name()` + `emit_deny`/`emit_allow()`。pre_tool_use + post_tool_use 入口走 adapter。**第二轮 full-repo codex review 抓到独立 critical wheel 打包 bug**：`pyproject.toml` force-include 从来没列 `data/signals/`，pip install 的 wheel 缺 signal 词表树 → `compile_alternation()` never-match → evidence/keep_pushing/non_blocking keyword-fallback 静默失效 **影响所有 pip install 用户含 Claude Code 主流**。6 道本机门禁的 wheel verify 只锁 6 个 expected 文件，signals 子树漏 lockdown。Fix：force-include 整 `data/signals` 目录 + CI smoke test（build wheel + 干净 venv pip install + assert `compile_alternation()` non-empty regex）。真验证 fix 后：`weak_claims` 497 chars / `push_signals` 16653 chars / etc 全 functional。**用户拍我一次**（「你没有探查就下结论这很不好」）— 我打算 ask 用户拍方案前没真本地 verify。规则 6 read-before-write 也适用 doc — pull 真 `~/.codex/hooks.json` + `~/.gemini/settings.json` + WebFetch 官方文档。**元 pattern**：cross-model audit 价值在「在地模型有系统性盲区」是真的。Claude 写 pinrule + 本 session 已 review 12+ 轮，盲区是「假设 Claude 自己用的协议是通用的」。GPT-5.5 不同训练 exposure 拉官方 ref 精确指出。单模型轮次（v0.9.13/14）边际收益递减；cross-model 打开新 audit surface。这个 bug 在 pinrule「3-backend 支持」整个历史里都潜伏 — 每次 dogfooding 都 Claude Code。11 个新测试含 Gemini-style payload 集成 lockdown（pre_tool_use deny shape + post_tool_use state 推进）。498/498 通过。Phase 2（apply_patch multi-file diff parsing）留 v0.9.16+。| ✅ |

| **v0.9.16 codex apply_patch envelope 真 parser + config DEFAULTS 缺字段静默丢 + 测试断言收紧**. 关掉 v0.9.15 推迟的 phase 2 cross-backend 协议归一化。v0.9.15 只 normalize 了 `tool_name`，明确把 `tool_input` normalize 推到 phase 2 — 因为当时没捕获真 codex envelope 长什么样。v0.9.16 用真证据关掉 phase 2：parser 锁的是从一次新鲜 codex 0.130.0 + GPT-5.5 session rollout（`/Users/jhz/.codex/sessions/2026/05/16/rollout-2026-05-16T13-51-47-...jsonl`）真捕获的 `custom_tool_call.input` 字面。**Shape**：codex 把整个 `*** Begin Patch ... *** End Patch` envelope 当**单字符串**塞 `custom_tool_call.input`；多文件 patch 同一 envelope 里串多个 `*** Update File:` / `*** Add File:` / `*** Delete File:` 块。`pinrule/backends/protocol_adapter.py` 两个新函数：`parse_apply_patch_envelope()` 返回 `[{"op", "path"}, ...]`；`normalize_tool_input()` 合成 pinrule canonical `{file_path, new_string, _codex_patch_files}`（apply_patch 才合成，其他 passthrough）。接入 pre_tool_use + post_tool_use 入口；`pinrule/checks/read_first.py` 存在 `_codex_patch_files` 时遍历多文件覆盖（捕获「只 Read 了主文件」情况）。post_tool_use 遍历 Update/Add 路径 → 每条 `record_edit` + `record_read`，多文件 codex commit 时 `last_edit_ts` 真推进（关掉 v0.9.15 期 evidence/commit 门在 Codex 下被静默放过的 gap）。**调研脚注**：`codex exec` non-interactive 模式即便加 `--enable hooks` 也 NOT fire 用户 hook（通过 `PINRULE_DEBUG_DUMP_PAYLOAD` 注入工具 + `codex features list` 双向验证）。payload 改从 session rollout 捕获。交互式 codex（生产路径）正常 fire hook 是预期；防御式 `_extract_codex_patch_text()` 同时处理裸字符串（验证）和 dict-wrap shape。再加 **Minor #4**：`pinrule/config.py:load()` 用 `for key in DEFAULTS` 合并配置 — 任何不在 DEFAULTS 的可调字段在用户 config.json 里写了也被静默丢；`reinject_every_n_tokens` 是文档化可调字段但漏 DEFAULTS，加上（None → 「按模型自适应」语义保留）。再加 **Minor #5**：`tests/test_compact_hooks.py` 3 处 `if "hookSpecificOutput" in output:` 条件分支让 hook 万一退回老 shape 测试也静默通过 — 收紧成严格 `assert output == {}`。`test_protocol_adapter.py` 12 个新测试（共 22 个）+ config DEFAULTS 测试 + 收紧的 compact_hooks 断言。510/510 双 locale 都过（原 498）。全 6 道本地 gate 通过 + wheel smoke test 干净 venv install 下 parser 真工作。| ✅ |

| **v0.10.0 backend 架构分工: protocol_adapter 调度层 + 6 契约方法 + codex 所有权交接**. v0.9.16 真测试 codex 暴露 2 个新 bug (Codex 拒绝 `permissionDecision:"allow"` 按官方文档 — v0.9.15 假设错; codex shell-as-Read 适配缺口 — codex 没独立 Read tool, 靠 `exec_command`+`tail`/`sed`/`cat` 读, pinrule `record_read` 看不见 → `read_first` 假阳拦), 用户提议 backend 所有权分工: pinrule 维护者 owns hooks/checks/contract/base + claude_code + gemini_cli + GitHub 文档; **Codex CLI 自己 owns `pinrule/backends/codex.py` 通过 Codex session PR**. v0.10.0 形式化: `Backend` Protocol 声明 6 契约方法 (`pre_install_setup`, `post_install_message`, `normalize_tool_name`, `normalize_tool_input`, `emit_deny`, `emit_allow`), `_json_hooks.py` 提供 Claude-shape 默认. `protocol_adapter.py` 退化纯调度 — backend 私货 (`_GEMINI_TOOL_MAP`, `_CODEX_TOOL_MAP`, envelope parser) 全移各自 backend 文件. `detect_backend()` 通过 `hook_event_name` (Gemini) 或 `sys.argv[0]` 含 `/.codex/` (codex) 路由. `checks/read_first.py` 去 `_codex_patch_files` 字段 — 重命名 backend-neutral `multi_file_targets`. **Bug A 修**: `CodexBackend.emit_allow() → "{}"` 按 codex 官方文档; 锁定测试防回归. v0.9.17 工作集成: post_install_message 响亮 `/hooks` 审批提醒 + pinrule doctor codex-specific 段 + README codex alert box. 新 `docs/CODEX_BACKEND.zh.md` 定义所有权边界 + Codex backend owner 已知 TODO 议程 (shell-as-Read, 真 hook payload 捕获, 其他 tool_name 映射, 审批状态检测). 512/512 双 locale + 全 6 gate + wheel smoke. **元 pattern**: 在地模型猜别家平台协议系统性盲区 (v0.9.15 + v0.9.16 + v0.10.0 Bug A 同 pattern), 正确修法是贡献者所有权分工不是更多 cross-model audit. | ✅ |

| **v0.10.1 首个 codex 自提 PR 合并 (shell-as-Read) + pinrule 端通用层接入 + 跨 backend 契约测试**. v0.10.0 所有权分工几小时内就验证: Codex CLI 开 PR #3 实现 `CodexBackend.normalize_tool_input()` shell 读取识别只动 codex 拥有的文件, 边界纪律完美. pinrule 维护者做明确点出的配套: `pinrule/hooks/post_tool_use.py` 消费 canonical `tool_input["read_file_paths"]` 列表 — backend-neutral (任何后续 backend 输出该字段都生效). 新集成测试锁全链路. 端到端: codex agent shell 读取真注册为 pinrule Read → 同文件后续 `apply_patch` 不再被假阳拦. 另加 `tests/contract/test_backend_contract.py` 14 抽象契约 × N backend = 42 自动验证. CI vulture --min-confidence 60 误判 `shlex.shlex.whitespace_split` 加 `whitelist.py` 解决. 568/568 双 locale. **元 pattern 印证**: 所有权分工是正确答案 — Codex CLI 自己捕获真 session rollout 作证据 (比 Claude 任何 audit 信号都准), pinrule 维护者工作小且聚焦因边界事先清晰. | ✅ |

| **v0.10.2 第二个 codex 自提 PR (#4) 关掉对 Claude code 覆盖主要缺口**. Codex backend 现在覆盖 codex 0.130 的 6 个 event 中的 5 个 (SessionStart / UserPromptSubmit / Pre&PostToolUse / Stop). 三项: SessionStart event 注册 + 真捕获 payload 跟 Claude shape 完全兼容 (codex 在第一轮 prompt 前 fire 不是 TUI 启动 — 功能正确性保留); `exec_command → Bash` 映射 + `cmd → command` 字段拷贝让 `record_bash` / `is_test_cmd` / `last_test_pass_ts` 在 codex 下工作; **`trust_pinrule_hooks()` 装机时自动给 pinrule 自家 wrapper 写 `trusted_hash` 到 `~/.codex/config.toml`**, 消除手动 `/hooks` 审批 (pinrule v0.10.0 期最大 onboarding 痛点). 安全限定: 只 pinrule `is_pinrule_entry` 验证的 wrapper, hash 算法变了回落到 `/hooks` "modified" 不是静默漂移. pinrule 维护者配套: README alert box 翻成 "自动信任" + 双语文档 v0.10.2 段. 575/575 双 locale. **所有权分工连续 2 个 PR 验证** — codex 真证据 (真 session rollout) + 准时 + bonus 超预期. | ✅ |

| **v0.11.0 long-term-fundamental engine response-level pattern (真证据驱动 rule 重新设计)**. v0.10.x dogfood (217 违反 / 13 session) 发现 long-term engine 命中率 0% — engine 看工程层证据 (真用罕见), 真违反场景是话术. v0.11.0 加 response-level pattern: 第一人称 + 短期动作 combo (`我先打补丁` 风格); 承认但仍 ship (`知道不是长期方案 但先这样`). 假阳防御 (反思 / 字面讨论不拦). 5 新 lockdown, 611/611 双 locale. **元**: 第一个真证据驱动的 rule 重新设计 — 未来 v0.11.x 模板 (engine 命中率 < 20% = re-design 候选). | ✅ |

| **v0.10.6 关 v0.10.5 推迟 3 项: emit_context_injection + emit_stop_block backend 契约 + hook 集成测试**. Backend Protocol 从 6 扩到 8 契约方法. 4 ContextInjection hook + 2 Stop block 路径走 `protocol_adapter.emit_*` — codex SessionStart shape 未验证 (v0.9.15 类潜伏) 通过 backend dispatch 关; Gemini Stop fail-open 返 `{}`. 9 个新 lockdown (3 hook 集成 + 6 跨 backend 契约). 606/606 双 locale. **关闭 6-release v0.10.x 循环**: 架构分工 → codex 3 PR → pinrule parity → audit sweep → 结构性关闭. | ✅ |

| **v0.10.5 4 视角 cross-audit sweep — 10 修在 docs/functional/state/boundary 四类**. 3 个 Claude 并行 agent + dogfooding 视角浮现 18 finding, 17 hand-verified 真 (94% SNR). Critical 文档 (README FAQ + CODEX_BACKEND TODO 列表 stale), functional bug (`write_file_paths` canonical wiring 让 codex sed -i 真推 last_edit_ts), 边界 leak (protocol_adapter codex 字面删, 只走 sys.argv 路由), state/off-by-one (pre_compact fallback 数学, stop.py catchup, UserPromptSubmit turn 归属), regex/docstring polish (chinese_plain Unicode `\w` → ASCII, model_threshold docstring 同步), 信号词表 drift fix + parity lockdown (`agent_saturation` en+12, 新 `test_signals_zh_en_parity_within_30pct` 走所有 signals 抓任一方向 drift > 30%). 3 个结构性 finding 推迟 v0.10.6 (`emit_context_injection` / `emit_stop_block` backend 契约 + 3 hook 集成测试). 597/597 双 locale. **元 pattern**: 快速迭代让 drift 比 v0.9.14 边际递减预测快回来 — 多视角 audit value 正比于离上次 audit iteration 速度. | ✅ |

| **v0.10.4 优先用 codex payload.model + OpenAI/Codex 阈值表**. pinrule 中段 reinject 原来 Claude-only — `gpt-5.5` (1M context) fallback 到 DEFAULT 40K 太密. 新 `model_from_payload(payload)` 统一查找: payload.model 优先 (Codex 官方 hooks doc 明确说这是稳定 signal, transcript_path 不是), transcript fallback. 接入 3 个 hook. 加 11 个 OpenAI/Codex 阈值: `gpt-5.5/5.4 → 120K, gpt-5.3-codex/5.2-codex → 80K, mini/nano/spark → 40K-30K`. Claude 行为不变. Codex `/model` 中途切换立刻识别. **老实说不做**: PreCompact / SubagentStart/Stop / PermissionRequest 在 codex 上仍不可 hook (API limitation 不是 pinrule scope). 中段 reinject 是跨平台替代. 15 个新测试. 595/595 双 locale (原 580). | ✅ |

| **v0.10.3 codex 简单 pipe 读 (第三次 codex 贡献) + user_stop_hints 类 3「协作等候」 + 文档措辞修正**. codex commit `8c0e136` 扩展 shell-as-Read 识别 `head N | tail M` / `cat | head/tail` 简单 chain (单 pipe, 两侧都只读). pinrule 端: user_stop_hints 类 3 (中文 16 + 英文 18) 修本 session 100+ keep_pushing 假阳 — 真信号来自人-Agent-Agent 协作场景, 用户说「等」不是放弃也不是完成. v0.10.2 错措辞修正 (Codex 内部有 compaction / fanout feature flag, 只是 hook API 不暴露). 580/580 双 locale. | ✅ |

详见 [CHANGELOG.md](../CHANGELOG.md) 每版本的设计动机；[HANDOFF.md](./HANDOFF.md) 内部接力 context。

## 持续观察 = 持续开发

用户原话「咱们继续推就是观察期」— 每次推进都装着 pinrule 跑，每个 commit 都经历 hook 拦截。M3 累积 30+ 累积违反，全部 7-8 个 sticky 都触发过。

pinrule 不是「先开发完再观察」，是「开发即 dogfooding」。
