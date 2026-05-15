# karma 技术架构（M3 现状）

## 总览

```
┌───────────────────────────────────────────────────────────┐
│  ~/.claude/karma/                                         │
│  ├── sticky.yaml             ← 用户手工维护核心方向        │
│  ├── violations.jsonl        ← 违反历史（5000 行自动 rotation）│
│  └── session-state/          ← 每 session 一 json (30 天自动清理)│
│      └── {session_id}.json   ← read_files / edit_files /  │
│                                  recent_bash / last_test_pass_ts / │
│                                  pending_bg_tasks ...     │
└───────────────────────────────────────────────────────────┘
                       │ 读 / 写
                       ▼
┌───────────────────────────────────────────────────────────┐
│  Claude Code hooks (~/.claude/hooks/)                     │
│  ├── karma_user_prompt_submit.py   ← 每条消息前注入 sticky │
│  ├── karma_pre_tool_use.py         ← 实时拦截违反 tool 调用│
│  ├── karma_post_tool_use.py        ← 跟踪状态 + catchup    │
│  └── karma_stop.py                 ← 扫 response 违反      │
└───────────────────────────────────────────────────────────┘
                       │
                       │ additionalContext / permissionDecision
                       ▼
              ┌─────────────────────┐
              │   Claude Code       │
              │   (Agent loop)      │
              └─────────────────────┘
```

## 数据模型

### sticky.yaml（用户手工维护）

```yaml
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
- `violation_checks` — `karma/checks/__init__.py:REGISTRY` 里的函数名

软上限 10 条，硬上限 12 条（超过 hook 拒绝加载，避免注意力稀释）。

### violations.jsonl

```jsonl
{"ts":1715617200,"session_id":"abc","sticky_id":"long-term-fundamental","trigger":"硬编码","snippet":"...先 硬编码 这个值..."}
{"ts":1715617250,"session_id":"abc","sticky_id":"non-blocking-parallel","trigger":"Bash sleep 命令: 'sleep 30'","snippet":"sleep 30 && echo done"}
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

## 4 个 Hook（Claude Code 标准协议）

### UserPromptSubmit hook

时机：用户发消息 → 模型看到消息前。

输入 stdin payload（Claude Code 协议）：
```json
{"prompt": "...", "session_id": "abc", "transcript_path": "...", "cwd": "..."}
```

输出 stdout：
```json
{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "...sticky 注入..."}}
```

实现：`karma/hooks/user_prompt_submit.py`
- 加载 sticky.yaml
- 读 violations.jsonl 按 turn 距离取最近违反过的 sticky_id（标 ⚠️）
- 格式化 `[karma sticky — 用户最高优先级方向，请始终遵守]` + 编号规则
- 顺带跑 `purge_old_states` + `catchup_pending_bg`（异常吞掉不阻塞）
- **强提醒 fallback**（关键机制）：读 transcript 取上一 assistant message
  → 跑所有 sticky 的 violation_checks → 命中的违反 + suggested_fix 注入「强提醒」段
  覆盖 keep-pushing / chinese-plain / evidence 等所有 response 类 check
  这是「Stop hook 在 user 立刻接 prompt 时不一定跑」场景的事后兜底
  （Stop hook 装机正确时实战会跑 — matcher fix 后 trace 已实证 5 条实际 session 触发）

性能：< 50ms。

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

实现：`karma/hooks/pre_tool_use.py`

两层检测：
1. **工程层** — 跑 sticky 配的 `violation_checks` 函数集（精确 regex pattern）
2. **关键词层（兜底）** — 扫 Bash command 骨架（剥引号字面 + heredoc 智能剥）+ Write/Edit 注释 + docstring

优先工程层（更精确），命中即 deny。Fail open 原则（配置错 / payload 解析失败 → allow，不卡 Agent）。

性能：< 100ms。

### PostToolUse hook（状态跟踪 + catchup）

时机：tool 调用完成后。

输入 stdin payload：
```json
{"tool_name": "Bash", "tool_input": {...}, "tool_response": {"stdout": "...", "stderr": "...", "backgroundTaskId": "..."}, "session_id": "abc"}
```

实现：`karma/hooks/post_tool_use.py`

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

实现：`karma/hooks/stop.py`
1. 读 transcript_path JSONL，找最后一条 `type=assistant` 取所有 text content
2. 扫 violation_keywords 关键词层 + 工程层 violation_checks（chinese_plain / evidence / keep_pushing 主要在这层）
3. 命中违反写 `violations.jsonl` + stderr 通知 + 桌面通知 + 累积告警
4. **keep-pushing-no-stop 命中 → 输出 `{"decision": "block", "reason": "..."}`** 让 Agent
   不立即停下继续生成（干预 sticky #7「不主动停」）。Safeguard：单 turn 内累积 block ≥ N
   次（config `stop_block_max_per_turn` 默认 2）后让 Agent 停下，防死循环
5. 否则输出 `additionalContext` 给下次 UserPromptSubmit 看

性能：< 200ms。

**⚠️ Stop hook 配置注意**：Stop / SessionStart / SessionEnd 等 event **不支持
`matcher` 字段** — Claude Code 看到 matcher 会无声忽略整个 hook entry。
`karma install-hooks` 已修：Stop entry 不加 matcher，PreToolUse/PostToolUse/
UserPromptSubmit 才加。如果你看 `/tmp/karma_stop_trace.log` 实际 session 0 条，
先检查 `~/.claude/settings.json` 的 Stop entry 是否含 matcher 字段。

## 8 个 violation_check 函数（工程层精准检测）

`karma/checks/__init__.py:REGISTRY` 映射 sticky.yaml 的 `violation_checks` 字符串 → 函数：

| check 名 | sticky | 检测内容 |
|---|---|---|
| `long_term_fundamental` | 长期方案 | 长 hash if 分支 / 黑白名单字面 / 全大写常量名单 / TODO 实际注释 / 意图字面注释 / commit message 主语 hack 词 |
| `non_blocking_parallel` | 不阻塞 | sleep / wait / 长任务无 background / 间接 shell 执行 |
| `chinese_plain_no_jargon` | 中文 | 中文占比（分母剥含点号工程标识符 / 路径字面 / commit message 引号块）+ jargon 检测（剥 code block / inline code）+ 同前缀字 ≥ 5 次/response 触发自审（白名单豁免一/不/是/有/没/我/你/他/这/那/在）|
| `loud_failure_with_evidence` | 完成证据 | 完成词 / weak claim 在代码任务上下文 + 无测试证据 |
| `no_testset_no_future_leakage` | 不喂测试集 | gold_cases 反喂 / 跨 split 复制 / 长 hash 在比较或赋值位置 |
| `read_before_write` | 先读再写 | Edit/Write 前未 Read 该 file_path（Write 新文件豁免） |
| `keep_pushing_no_stop` | 不主动停 | 优先级判：0) **user prompt 上文含叫停字眼**（不用了 / 休息吧 / 明天再说 / 先到这 / 算了 / 晚安 / 够了 等 sticky #8 例外清单）→ 整 turn 豁免（最高优先级）1) response 末尾 80 字含推进信号（我现在/接下来 + 动词）→ 豁免 2) 含问号 → 豁免（合理询问决策应鼓励）3) 含停顿语气词（下次 / 先到这 / 告一段落）→ 命中 4) 默认命中（纯陈述完结无推进无问号）|
| `bypass_karma_detection` | 不绕检测 | Bash 命令含 karma 内部字面（last_test_pass_ts / pending_bg_tasks / session-state json 路径）+ 写操作 → 命中「绕开 karma」。豁免：karma 官方 CLI / 只读 inspection / commit message 引号字面（剥后骨架不含敏感字面） |

每个 check 函数签名：`def check(*, tool_name, tool_input, response, session_state, **_) -> CheckHit | None`。

返回 `None` = 无违反，返回 `CheckHit(sticky_id, trigger, snippet, suggested_fix)` = 违反命中。

## 共用 helpers（`karma/checks/common.py`）

跨 check 函数 + hook 共用：

- `extract_tool_text(tool_name, tool_input)` — 不同 tool 不同字段提取（Bash.command / Write.content / Edit.new_string）
- `strip_code_blocks(text)` — 剥 markdown ` ``` ` 代码块 + ` ` ` inline code
- `strip_shell_quoted_literals(cmd)` — 剥 shell `'...'` `"..."` 引号字面 + heredoc 智能剥（区分头部命令 bash/sh 保留扫 vs python/cat 剥）+ 间接 shell（`bash -c '...'` 内保留扫）
- `extract_natural_language(content, file_path)` — 抽出代码注释行（# / // / --）+ docstring（""" ''' /* */）

## 描述上下文统一豁免（`karma/checks/description_context.py`）

`is_description_context(tool_name, tool_input) → (bool, reason)`：

| 维度 | 判定 |
|---|---|
| 文档后缀 | `.md` / `.rst` / `.txt` / `.markdown` / `.adoc` |
| 测试目录 | path 含 `tests/` `test/` `__tests__` `spec` |
| 测试文件名 | `test_*.py` / `*_test.py` / `*_test.go` 等 |
| 临时探针 | `/tmp/` / `/var/tmp/` 路径 |
| 探针/样本命名 | 文件名含 `probe / scratch / sample / playground / fixture` |

命中即整段豁免工程层 `long_term` / `testset` + 关键词层（关键词层对 Write/Edit 也调此判定）。

## CLI 工具（`karma/cli.py`）

```bash
# 初始化
karma init                       # 创建 ~/.claude/karma/ + 复制 sticky 模板

# sticky 管理
karma sticky list                # 列出所有 sticky
karma sticky edit                # $EDITOR 打开 sticky.yaml 编辑
karma sticky remove <id>         # 移除某条

# 观察
karma stats                      # 每条规则违反统计
karma violations recent [N]      # 最近 N 条违反详情
karma violations clear           # 清违反历史（需确认）

# 装机
karma install-hooks              # 生成 wrapper + 自动写 settings.json (Claude Code 8 个 event)
karma uninstall-hooks            # 删 wrapper + 清 settings.json 里 karma entry
karma doctor                     # 检查环境 + 全部 hook 安装状态（Claude Code 8 个）
```

`install-hooks` 关键特性：
- idempotent — 多次运行结果一致
- 首次运行备份 `settings.json` 到 `settings.json.before-karma`
- 保留所有非 karma hook（vibe-island / rtk / codex-review 等共存）
- 用 wrapper 路径含 `karma_` 前缀识别 karma entry

## 配置

`~/.claude/karma/config.yaml` 调阈值不用改代码。`karma doctor` 看当前生效值。
所有字段缺失走 `karma/config.py:DEFAULTS`（fail open），可只配关心的几条。

| 字段 | 默认 | 含义 |
|---|---|---|
| `notify_enabled` | `true` | 桌面通知开关（也可用 `KARMA_NO_NOTIFY=1` 环境变量关） |
| `recent_violation_turns` | `5` | ⚠️ 标记窗口 — 最近 N turn 内违反过的 sticky 下次注入时标红 |
| `escalate_window_turns` | `3` | 累积告警窗口（按 turn 距离） |
| `escalate_threshold` | `3` | 累积告警次数阈值 — 窗口内同 sticky 命中 ≥ N 次升级 🚨 严重通知 |
| `stop_block_max_per_turn` | `2` | Stop hook 单 turn 内 `decision=block` 上限（防 keep-pushing 干预死循环）。`0` 完全关闭干预 |
| `force_block_threshold` | `5` | 累积强制 block 阈值 — 同 sticky 窗口内违反 ≥ N 次 Stop hook 输出 `decision=block` 强制 fix 根因。`0` 完全关闭。可在 sticky.yaml 单条规则用 `force_block_exempt: true` 豁免 |
| `violations_max_lines` | `5000` | `violations.jsonl` 行数上限触发 rotation |
| `violations_keep_history` | `3` | rotation 保留几个历史 `.jsonl.{N}` |
| `session_state_max_age_days` | `30` | `session-state/*.json` 自动清理周期（天） |
| `max_recent_bash` | `15` | `SessionState` 保留最近 Bash 数量 |

`karma init` 复制 `data/config.example.yaml` 模板。

### 调试环境变量

- `KARMA_NO_NOTIFY=1` — 关桌面通知（CI / 静音场景）
- `KARMA_DEBUG=1` — `run_checks` 函数抛异常时 stderr 打 traceback（调试自定义 check）
- `KARMA_DEBUG_TRACE=<path>` — Stop hook 触发时 append 一行 trace 到指定文件
  （验证 Stop hook 是否实际触发，production 默认完全关）

## 状态目录路径（`KARMA_HOME` 环境变量）

karma 状态默认存 `~/.claude/karma/`（含 `sticky.yaml` / `violations.jsonl` /
`session-state/` / `config.yaml`）。通过 `KARMA_HOME` 环境变量可改路径 — 用
于 dry-run / CI / 多 profile 隔离不污染默认 home：

```bash
KARMA_HOME=/tmp/karma-test karma init           # 不动 ~/.claude/karma/
KARMA_HOME=~/karma-profile-A karma sticky list  # 多 profile 隔离
```

注：path 在 module-level 常量 import 时 freeze，所以 `KARMA_HOME` 必须在
启动 karma 进程**前**set。已被 hook wrapper 调用的 karma 不会读这个 env
（wrapper 不传 env），实际使用以 `~/.claude/karma/` 为主。

实现单一来源：`karma/paths.py:karma_home()` — 所有 5 个 module（sticky /
violations / session_state / config / cli）都用它读 env。

## 性能预算

| 路径 | 预算 | 当前实测 |
|---|---|---|
| UserPromptSubmit | < 50ms | 5-15ms（yaml 加载 + violations 读 200 行） |
| PreToolUse | < 100ms | 10-30ms（regex 扫 + check 函数集） |
| PostToolUse | < 30ms | 5-15ms（状态写 atomic rename） |
| Stop | < 200ms | 20-50ms（transcript 反向找 assistant + 扫违反） |

性能没成瓶颈 — 实测远低于预算。

## 安全 / 隐私

- 所有数据本地 `~/.claude/karma/`
- 不上传任何数据
- 不调用 LLM（karma v2 全项目坚定不用 LLM，含 v1+ 也不引入）
- 用户随时 `rm -rf ~/.claude/karma/` 清空状态
- `karma uninstall-hooks` 干净清理（删 wrapper + 清 settings.json）

## v0 边界（明确不做）

- ❌ 引入 LLM — 全工程化（regex / 计数 / 上下文判定）
- ❌ 数据库 — `violations.jsonl` + `session-state/*.json` 文本 IO 足够
- ❌ 自动蒸馏新 sticky — 用户掌控
- ❌ retrieval / cosine / scene 选规则 — 5-10 条 always-on
- ❌ 跨平台支持 — 先 Claude Code only
- ❌ Web UI / TUI — CLI + $EDITOR 足够

## 已交付里程碑

| 里程碑 | 状态 |
|---|---|
| M0 骨架 + 4 文档 | ✅ |
| M1 sticky 加载 + 2 hook 原型 + CLI 骨架 | ✅ |
| M1.5 PreToolUse 实时拦截 | ✅ |
| M2 6 个工程 check + session_state | ✅ |
| M2.1 适配 Claude Code 真实协议 | ✅ |
| M2.2 长 term check 按 tool 分组 + 文档豁免 | ✅ |
| M3 1-6 波 全面降假阳 + 假阴对偶 + 装机自动化 + 长期质量 + 描述上下文完整化 + 加严审计 | ✅ |

详见 [HANDOFF.md](./HANDOFF.md)。

## 持续观察 = 持续开发

用户原话「咱们继续推就是观察期」— 每次推进都装着 karma 跑，每个 commit 都经历 hook 拦截。M3 累积 30+ 真实违反，全部 7-8 个 sticky 都触发过。

karma 不是「先开发完再观察」，是「开发即 dogfooding」。
