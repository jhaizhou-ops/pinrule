# karma v2 交接 — 2026-05-14（M3 六波结束）

> **⚠️ 这是 karma 内部开发的「Agent 接力文档」，不是最终用户文档。**
> 如果你是想用 karma 的 Claude Code 用户，请看 [README.md](README.md) /
> [PRD.md](PRD.md) / [ARCHITECTURE.md](ARCHITECTURE.md)。
> 本文档保留各 milestone 阶段未解 bug / 错误诊断教训 / 下次 session 的 TODO，
> 是给「接力开发的下一个 Agent」看的。

> 给下个 session 的快速接手指引。

## 当前状态：M3 第六波完成，karma 装到本机并经历完整 dogfooding

### 已交付里程碑

| 里程碑 | 内容 | 关键 commit |
|---|---|---|
| M0 | 项目初始化 + 4 核心文档 | 9cb460f |
| M1 | sticky.yaml 加载 + 2 hook 原型 + CLI 骨架 | e6f4466 |
| M1.5 | pre_tool_use 实时拦截 hook | bf29d73 |
| M2 | 6 条规则工程检测 + session_state | 484f267 |
| M2.1 | 适配 Claude Code 真实 hook 协议 | b61deee |
| M2.2 | long_term check 按 tool 分组 + 文档豁免 | 52af21b |
| **M3 第一波** | **降假阳 9 项**（has_recent_test_pass 新语义 / _FAIL_RE 精确化 / 描述上下文统一抽象 / 关键词层只扫 Bash / 字面量列表 hint / testset hash 上下文 / evidence 行为词 / non_blocking 剥引号 / background catchup 雏形） | 72065f9 |
| **M3 第二波** | **假阴对偶 7 项**（_FAIL_RE 加 ERROR/FATAL / 意图注释 pattern / 全大写常量名单 / gold 列表 hex / 间接 shell / Write→record_read / **background catchup 真根因 — tool_response 是 dict**） | 0c7af6a + 3b10325 |
| **M3 第三波** | **CLI 装机体验**（install-hooks 自动写 settings.json idempotent + 备份 + 保留他人 hook / uninstall-hooks 同步清理 / doctor hook 安装检测） | 3b10325 |
| **M3 第四波** | **长期质量 4 缺口**（session-state 30 天清理 / violations.jsonl rotation / save tmp 名 pid+ns / post_tool_use 跳过失败 tool） | 2938d91 |
| **M3 第五波** | **描述上下文完整化 2 项**（commit message 80 字位置约束 / heredoc 剥） | bf928bd |
| **M3 第六波** | **用户反馈担心放过真违反，对偶审计 + 加严**（heredoc 区分头部命令 bash/sh 内是真 shell / 关键词层 Write/Edit 加注释 + docstring 扫描 / 11 个对偶假阴回归测试） | 8f58bb9 |
| **M4 装机体验 + 反馈机制** | sticky.example → dev.example（场景化定位）+ 5 项 sticky 调整 / 桌面通知（macOS/Linux/Windows）/ 累积告警 / 配置系统 / doctor 显示配置 | 216f754 → 61a7c72 |
| **M4 turn 维度重构** | ⚠️ 标记 + 累积告警按 **turn 距离**（Agent 漂移按 turn 累积，不按人类时钟）+ Violation 加 turn 字段 + recent_turns / count_recent_turns | 42955ba |
| **M4 audit + 假阳根因修复** | karma audit 命令（自动标可疑假阳，触发词占 ≥ 50% 标 ⚠️）/ docs/yaml Edit 不推 last_edit_ts / conventional commit (docs/chore) 豁免 evidence / stats 加最近 5 turn 列 | 667f15c → 9429173 |
| **M4 reset 命令** | karma reset 清 session-state 漂移实验重启 | ffcbd07 |
| **M4 audit turn 维度** | audit 末尾段「本 session 最近 10 turn 漂移近况」+ 🔥 高频标记 | ca65116 |
| **M4 keep-pushing 工程层 + Stop hook 真干预** | keep_pushing check（问号 / 停顿语气词双信号）+ Stop hook decision=block 让 Agent 不真停继续生成 + safeguard `stop_block_max_per_turn` 防死循环 | 8502713 |
| **M4 keep-pushing 反转 + audit 改进建议** | 用户精准纠正：问号是合理决策应豁免，纯陈述完结无下一步才是真停下 → 反转检测方向（推进/问号豁免，停顿词/默认 → 命中）。stats / doctor 显示 stop_block_count；audit 末尾自动改进建议段；catchup 多 hook 跑（UserPromptSubmit+PreToolUse 都跑，task #8 剩余 case）；non_blocking 长任务列表收紧（移除 pytest 等测试命令，保留 docker/build/install）| 8502713 → 最新 |
| **M4 元层面监管 — 自身被绕过的检测**（用户反馈核心场景） | 回应「这就是一个典型的出现了问题，你绕过/忽略了问题拿了个短期结果」三层实施：① bypass_karma check（Bash 命令含 karma 内部敏感字面 + 写操作 → 命中）② Stop hook 累积强制 decision=block（同 sticky ≥ N 次必须 fix 根因不许继续绕）③ sticky #8 deep-fix-not-bypass 进默认开发模板（preference + 关键词 + 工程层）。strip_shell_quoted_literals 加 python/node/ruby -c flag + placeholder 保护内部引号字面（commit message 自指假阳豁免 + python -c 真执行代码保留扫）| 最新 |
| **M4 user_prompt_submit 强提醒 fallback** | 用户反馈「你又停下来了，自己加的 sticky 也没拦」根因：Claude Code Stop hook 在 user 立刻接 prompt 时**不跑**（user_prompt_submit 优先级覆盖 Stop hook idle 触发）。fallback：user_prompt_submit hook 读 transcript last assistant message 跑 keep_pushing.check，命中（纯陈述完结无推进）→ 注入「强提醒」段告诉本 turn Claude 上次停了，本 turn 必须立即推进。这是 karma 当前能做的最强 keep-pushing 干预（不依赖 Stop hook 协议层 limitation） | 最新 |
| **M4 Stop hook 不跑 → 撤回错误诊断**（重要错误教训） | 之前结论「Claude Code Stop hook 在 user-continuous 对话不跑」**错** — 用户质疑「stop hook 原理机制咱们没研究清楚」后重派 claude-code-guide 确认：**Stop hook 不支持 matcher 字段**，karma install-hooks 给所有 event 都加 `matcher: '*'` → Stop event 看到 matcher 会无声忽略整个 hook entry → Stop hook 根本没装上 → trace 0 条记录。**真根因**：karma 自身 install-hooks 配置 bug。修：_karma_event_entry 只对 PreToolUse/PostToolUse/UserPromptSubmit 加 matcher，Stop 不加。`karma install-hooks` 重装后修好。教训：单次 trace 0 条记录不能直接断言「协议 limitation」，要查配置先 | 52af21b → 最新 |
| **M4 dogfooding 三连 fix**（本 session 用户实战触发 force_block + 累积纠正驱动） | ① **violations.py turn=None fallback bug** — `recent_turns / count_recent_turns` 把无 turn 字段的老违反通过 `.get("turn", 0)` fallback 成 0 落入当前窗口造成假阳。dogfooding 实证：新对话 turn=1 window=3 → cutoff=-2 → 老违反 turn=0 被误数触发 force_block。修：`if turn_raw is None: continue` 直接跳过。② **stop.py force_block 跟「不阻塞 / 继续推进」语义自我矛盾** — 累积「停下太多」违反触发 force_block 要求 Agent「必须停下让用户介入」恰好再次违反规则本身。修：sticky schema 加 `force_block_exempt: bool` 字段（配置驱动去硬编码 sticky id 名）+ stop.py 从 sticky 列表读豁免集合；默认模板 + 作者 sticky.yaml 给 keep-pushing-no-stop / non-blocking-parallel 加 `force_block_exempt: true`。③ **doctor 显示 force_block 豁免名单** + README/ARCHITECTURE 同步字段说明 + 撤回 ARCHITECTURE 残留错诊断「Stop hook 在 user-continuous 不跑」（已实证 trace 5 条真 GUID session 触发）。测试 227 → 232。 | 最新 |
| **M5 多 backend 横向扩展**（v0.3.0 → v0.4.2，5 个 release） | 从「Claude Code 专用」升级「多 AI 编程客户端通用」。① **v0.3.0 Codex CLI backend**：抽 `karma/backends/` Backend Protocol；实测发现 Codex feature 真名 `hooks` 不是 vibe-island 写的 `codex_hooks`；exec 模式不触发 hook（[GitHub #17532](https://github.com/openai/codex/issues/17532)）。② **v0.4.0 Gemini CLI backend**：event 名完全不同（BeforeAgent/AfterAgent/BeforeTool/AfterTool）；Stop 字段 `prompt_response` 适配；karma 4 wrapper basename 跨 3 backend 复用。③ **v0.4.1 抽 `JsonHooksBackend` 通用基类**：从 vibe-island 实证 9 家清单（cursor/factory/qoder/copilot/codebuddy/kimi 等）学到多客户端同模式，让加新 backend 变 6 类属性「填表」+ 4 行 event 映射。④ **v0.4.2 bypass_karma `2>/dev/null` 假阳修**：dogfooding 实测发现的真 bug — stderr 转黑洞被误识别为 write_op。`karma/backends/HOWTO.md` 5 步走文档让社区贡献门槛低。**作者本机三家全装实测装机/卸装/hook 真触发 catch 违反全跑通**。测试 232 → 304，4 件套（ruff/mypy/vulture/pytest）+ CI 跨平台跨 Python 版本全绿。**未实测的 client 不预加 backend**（sticky #1）— 等装实际 client 真跑实测再加。| 125f361 → c417ed2 |

## 真验证盲区：codex / gemini TUI hook 调度从没在作者本机真触发

2026-05-14 同事即将首装时实测发现：vibe-island bridge.log 767 行全部
`source=claude`，**0 条 `source=codex`** / **0 条 `source=gemini`** —
作者本机 codex / gemini 装着 hook 但**从没真用过 TUI 跑过**。

这意味 karma v0.3.0 → v0.4.7 多 backend 横向扩展实测**全是模拟 payload
+ 装机文件验证**：
- ✓ karma 端 5/5（装机/wrapper 真处理 payload/sticky 注入/拦截/写入）
- ✓ codex 端 3/3（features.hooks / config.toml / wrappers 可执行）
- ❌ codex / gemini TUI 真启动 + 真完成一个 turn + 真触发 hook 调度 — **未验证**

`codex exec` / `codex debug prompt-input` / pipe stdin codex 都**不触发**
hook（codex 协议设计）。codex TUI 真启动用 `script -q` PTY 通过，但精确
按键时序 expect 难一行命令脚本化（codex ratatui prompt 字符识别复杂）。

**后续验证只能真用户 5 秒手动操作**：起 `codex` TUI 输入 `/hooks` 看
karma 4 hook 是否真注册 + 输入 prompt 看是否真触发。

不是 karma 的 bug — 是 codex / gemini 客户端调度行为只能在真 TUI 验证。

**2026-05-14 真根因找到**（用户挑战「这几天 vibe island 一直调 codex hook」
驱动深挖 — sub-agent 真起 codex CLI TUI 用 pty.fork() 跑通看到的）：

**codex 0.130 新加 hook approval gate** — 所有新装的 hook 默认 quarantined,
必须 TUI 内交互式 `/hooks` 审批后才执行。codex TUI 启动横幅显示
`⚠ 8 hooks need review before they can run. Open /hooks to review them.`
（karma 4 + vibe-island 4 = 8 个全在等审批）。

这是 codex 0.130 安全设计**不是 bug**，但需要用户手动审批一次才生效。
karma 装机层 + 5 个 wrapper + sticky 注入 + 协议适配全验证生效，**codex
不调度 wrapper 是 0.130 approval gate** 拦的，不是 Desktop App regression
（之前 issue #21639 是另一回事 — 仅 Desktop App 还有自己的 regression）。

sub-agent 附带发现：codex CLI 0.130 panic 真根因「byte index u64 wrap」
触发条件是逐字符 stdin 注入；用位置参数 `codex "<prompt>"` 绕过 panic 但
hook 仍被 approval gate 拦。

**用户体验影响**：karma 装完同事第一次跑 codex 会看到 `⚠ N hooks need
review` 横幅，必须 TUI 输 `/hooks` 逐条 approve karma 4 个 wrapper 才真
生效。README + 给同事 AI prompt 块已加这关键一步。

## ✅ Stop hook matcher fix 已实战验证生效 + 一条 karma 管不到的元认知盲区

**生效证据**：fix 后 Stop hook 真触发 decision=block 干预（用户在 UI 看到了
karma 强制干预 reason 文案），说明 matcher fix 真根因正确。

**karma 管不到的层面（用户纠正 Agent 元认知）**：

Stop hook 排查全过程暴露了一条 karma 工程检测**无法捕捉**的失败模式 ——
「Agent 过早下结论 + 根因没挖透」。具体路径：

1. trace 真实 session_id 0 条 → 我直接断言「Claude Code Stop hook 在
   user-continuous 对话不跑，是协议 limitation」并写进 HANDOFF / ARCHITECTURE
2. 用户质疑「stop hook 的原理和机制你好好研究下，我觉得不会是没有触发，
   更像是原理机制咱们没研究清楚」
3. 我才回头重派 claude-code-guide 查协议，发现真根因：**Stop event 不支持
   matcher 字段，karma install-hooks 给所有 event 加 matcher='\*' → Stop entry
   被 Claude Code 无声忽略**

用户原话：**「太容易下结论这个问题我估计 karma 管不到这么细节和深入的层面，
但这确实是个宝贵的经验值得咱们都吸取」**。指的是 Agent 自己根因挖没挖透
这种**元认知判断** —— karma 工程检测器（关键词 / 正则 / 计数 / pattern）
没法写出「Agent 这次思考是否收敛过早」的判定。这是 LLM 自身的元能力问题，
karma 不该假装能管。

附带的具体工程 bug + 修复（真根因就一条）：

**真根因**：老违反**无 turn 字段**，`d.get("turn", 0)` fallback 成 0 → 当前 turn=1
window=3 时 cutoff=-2 → 老违反 turn=0 ≥ -2 被数 → 触发 force_block 假阳。

**修法**：`recent_turns / count_recent_turns` 加 `if turn_raw is None: continue`,
无 turn 字段直接跳过（语义：未知 turn 距离），不要假装 turn=0。回归测试 2 条
（test_recent_turns_skips_legacy_no_turn_field / test_count_...）已守护。

**用户纠正的两条认知错误**（写下来给后任 Agent 别再踩）：

- 我曾说「session_id 跨 compact 不变 → count_recent_turns 按 session_id 过滤
  没用 → karma 管不到」。**两层都错**：
  - 同一 session 跨 compact 是**同一会话的延续**，违反计数持续累积**是正确行为**,
    不是要修的问题。所以 karma 不该「管」这事
  - 即便真要管，Claude Code 实际有 `PreCompact` hook event（看 `~/.claude/settings.json`
    PreCompact entry 就有，vibe-island 也在用），不是「没暴露 compact 信号」

**教训（自警，不进 check）**：
- 「单次观测 0 条」类的强结论永远先怀疑配置 / 装机 / 自身代码，再怀疑协议
- 写「协议 limitation / 平台 bug」前必须有正式文档 / 多次复现 / 排除自身实现
- 用户提出的「再研究下」「不太对劲」要严肃对待，那是元认知信号

### 真实工作证据 — 假阳治理后 audit 干净

完整 audit 工具链实证（本 session M4 末尾）：
1. audit 找问题 → 33 条历史，标 2 个假阳重灾区（evidence / non_blocking pytest）
2. 修 pattern → conventional commit 豁免 / docs Edit 不推 ts / pytest 移出长任务列表 / sleep 0 不算阻塞 / TODO 后缀要求 / 描述上下文 yaml/json 豁免 等
3. clear --trigger 治理历史 → 33 → 11 条剩真违反
4. 现状 audit：**「暂无明显假阳重灾区」** ✓

剩余 11 条都是真违反 / 边缘观察：
| sticky_id | 总 | 类型 |
|---|---|---|
| read-before-write | 6 | **真违反**（未 Read 就 Edit /Users/jhz/.claude/statusline.sh 等） |
| chinese-plain-no-jargon | 3 | 真违反（中文比例 34% / mutex 无中文解释） |
| no-testset-no-future-leakage | 2 | 边缘（描述 ML 概念） |

**全 7 个 sticky 都装好**（含 sticky #7 keep-pushing-no-stop 工程层 + Stop block 真干预）。

### 测试状态

`pytest tests/` → **275/275 passed**（M3+M4 + 2 轮评审 Agent 修复累积加 200 个新测试，含跨平台 locale 检测 17 条）
- `tests/test_false_negative_regression.py` — 23 个对偶假阴测试
- `tests/test_cli.py` — 10 个 CLI 测试
- `tests/test_description_context.py` — 9 个上下文测试
- `tests/test_session_state.py` — 22 个（含 background catchup / purge / unique tmp）
- 其他原有测试也加了新 case

## 装好的资产

### 仓库结构（已含 M3 新文件）

```
/Users/jhz/karma/
├── README / PRD / ARCHITECTURE / CLAUDE.md / HANDOFF.md
├── data/sticky.dev.example.yaml     # 7 条 sticky 模板 (软件开发场景)
├── karma/
│   ├── sticky.py                    # yaml 加载 + 校验
│   ├── session_state.py             # 跨 hook 状态 + background catchup
│   ├── violations.py                # 违反记录 + rotation
│   ├── cli.py                       # init / install-hooks / doctor / stats
│   ├── checks/
│   │   ├── common.py                # 共用 helpers (strip_shell_quoted_literals
│   │   │                              / strip_code_blocks / extract_natural_language)
│   │   ├── description_context.py   # 描述上下文统一豁免
│   │   ├── long_term.py             # 多 pattern + 描述上下文豁免
│   │   ├── non_blocking.py          # 间接 shell + 引号字面剥
│   │   ├── chinese_plain.py
│   │   ├── evidence.py              # 行为词上下文判定
│   │   ├── testset.py               # case_id / gold list 上下文约束
│   │   ├── read_first.py
│   │   ├── keep_pushing.py          # 推进信号 / 问号 / 停顿词检测
│   │   └── bypass_karma.py          # 元层监管 — 绕开 karma 的字面 + 写操作
│   ├── backends/                    # 3 家 AI 客户端装机抽象 (v0.4+)
│   │   ├── _base.py                 # Backend Protocol
│   │   ├── _json_hooks.py           # 通用 JSON hooks 基类（90% 共用实现）
│   │   ├── claude_code.py / codex.py / gemini_cli.py
│   │   └── HOWTO.md                 # 加新 backend 5 步走指南
│   └── hooks/                       # 4 个 hook 入口（跨 backend 复用）
│       ├── user_prompt_submit.py    # sticky 注入 + 每 turn purge + 强提醒 fallback
│       ├── pre_tool_use.py          # 实时拦截
│       ├── post_tool_use.py         # 跟踪状态 + catchup
│       └── stop.py                  # response 扫违反 + force_block + 豁免
└── tests/                           # 275 个测试
```

### 用户 home（`~/.claude/karma/`）

```
~/.claude/karma/
├── sticky.yaml                      # 用户 sticky（作者实例 8 条：默认 7 + keep-pushing-no-stop）
├── violations.jsonl                 # append-only + 5000 行自动 rotation
└── session-state/                   # 每 session 一 json，30 天自动清理
```

### AI 客户端 hook 配置（v0.4+ 三家通用）

karma backend 抽象支持 **3 家客户端**：

| Backend | 配置路径 | 启用方式 |
|---|---|---|
| Claude Code | `~/.claude/settings.json` | 默认 |
| Codex CLI | `~/.codex/hooks.json` | `karma install-hooks --backend codex`<br/>自动启用 `[features] hooks = true` |
| Gemini CLI | `~/.gemini/settings.json` | `karma install-hooks --backend gemini-cli` |

`--backend all` 一次装齐本机检测到的所有客户端。

详 [karma/backends/HOWTO.md](karma/backends/HOWTO.md) 加新 backend 5 步走。

### Claude Code hook 配置

`install-hooks` 自动写 `~/.claude/settings.json`（保留他人 hook，idempotent）。备份在 `~/.claude/settings.json.before-karma`。

## 关键设计 / 边界

### 描述上下文统一豁免（karma/checks/description_context.py）

多维度判定 tool 调用是否「描述」而非「执行意图」：
- file_path 是 `.md / .rst / .txt / .markdown / .adoc` → 文档
- path 含 `tests/` `test/` `__tests__` `spec` → 测试目录
- 文件名 `test_*.py` / `*_test.py` 等 → 测试代码
- 路径 `/tmp/` 或 `/var/tmp/` → 临时探针
- 文件名含 `probe / scratch / sample / playground / fixture` → 探针
- 命中即整段豁免工程层 long_term / testset + 关键词层

### shell 引号字面 + heredoc 智能剥（karma/checks/common.py）

`strip_shell_quoted_literals` 处理 commit message / echo / heredoc 等：
- `'...'` `"..."` 引号字面 → 剥（描述/数据）
- `bash -c '...'` → 保留内引号当真子命令
- `bash/sh/zsh <<EOF ... EOF` → 内容是真 shell 命令，保留
- `python/cat/grep <<EOF ... EOF` → 内容是数据，剥

### background 任务通过证据接入（task #8 真根因）

Claude Code 真实 `tool_response` 是 dict `{stdout, stderr, backgroundTaskId}` 不是字面。`record_bash` 接受 dict 并从 command 解析 `> /path` 重定向取真实输出文件。`catchup_pending_bg` 下次 hook 触发时读 log 接进 `last_test_pass_ts` — 解决了 background pytest 跑通后 evidence check 看不到证据的死结。

### 关键词层 Write/Edit 只扫注释 + docstring

避开 M2.2 时的「描述字面假阳」和 M3 第一波「全放又漏真违反」的两端 — 注释里写「先打个补丁」是真意图表达扫，代码主体字面赋值（数据）不扫。

### 已知 fix 过宽 limitation（2026-05-14 v0.4.22 自审后接受）

按用户视角真测发现部分 fix 仍有边界 case 过宽 — 工程难做，接受 limitation
作为长期持续观察对象。下个 session 接手时如果真实用户报漏拦 case，按对应
方向治理。

1. **v0.4.11 chinese-plain ML 真 jargon 豁免过宽** — `zero-shot learning` /
   `few-shot prompt-engineering` / `chain-of-thought reasoning` / `self-
   attention` / `multi-head attention` 等 ML 标准 jargon 是 kebab-case 形式
   但**实质是真 jargon**，被错豁免。
   - 真原因：v0.4.11 剥 kebab-case 是为豁免**项目自身标识符**（force_block /
     chinese-plain-no-jargon），跟 ML 真 jargon 形式相同语义不同
   - fix 方向：维护「常见 ML kebab jargon 黑名单」（zero-shot / few-shot /
     chain-of-thought / self-attention / multi-head / layer-norm 等）作为
     不剥例外。但黑名单总有遗漏 — 接受工程代价
   - 或者：调本机小模型语义判定（违反 v2 边界，不做）

2. **v0.4.12 keep-pushing 假数字攻击** — 「9999 测试通过」假数字骗 `_SUCCESS_
   REPORT_RE` 豁免。罕见 anti-pattern 接受 limitation。
   - 真 fix 难：karma 不知道实际测试数 — 除非接 pytest plugin 实时报告
   - 接受：用户 Agent 不会蓄意伪造测试数字（sticky #4「完成要有证据」前提下
     trust）

3. **v0.4.13 deep-fix `shutil.rmtree('~/.claude/karma')` 整目录漏拦** —
   `_KARMA_STATE_PATH_RE` 只匹配具体文件（session-state / violations.jsonl /
   sticky.yaml）不匹配整目录 `.claude/karma/`。
   - 真原因：v0.4.13 之前就有的 path regex limitation 不是本回合引入
   - 接受：用户极少 rmtree 整 karma 目录，且 sticky #4「数据销毁需 flag」用户层
     兜底

4. **v0.4.16 force_block 协议层 placeholder 漏洞** — Agent 蓄意当前 turn 给
   短回复 placeholder（如 `done.`）→ 不真触发该 sticky → 不 force_block →
   历史累积没真处理。
   - 接受：sticky #7 信任前提下不防 Agent 蓄意作弊。这种 placeholder 行为本
     身违反 sticky #7

5. **v0.4.17/21 audit timeline 粒度** — `check 文件最新 commit ts` 不区分
   「真根因 fix commit」vs「注释 / 重构 commit」。可能误标「修后 0」但实际是
   commit 之后没新触发不是 fix 真生效。
   - 接受：dev hint 工具不追求精准，dogfooding 数据观察靠人工判断

6. **v0.4.19 keep-pushing「下次 X 这事吧」推卸语气漏拦** — `(?!\s*[吧行])`
   负向前瞻只覆盖紧邻「吧」字，「下次治理这事吧」中「吧」前有「这事」隔开
   不在 0 字范围。
   - 接受：语义判断难做，记 HANDOFF

### Agent 在 karma 项目内汇报用词指南（2026-05-14 防 chinese-plain 38% 真违反复发）

**为什么需要**：dogfooding 实测 chinese-plain 38% 触发 4 次是 **真违反不是
check 假阳**。Agent（包括本人）写 release note / commit / 汇报响应时撒
「release note / code identifier / jargon token / commit message」类英文
复合词，没汉字解释 → 拉低中文比 < 40% 真违反 sticky #3。

**真原则**：karma 项目术语 / 字段名（kebab-case / snake_case / 版本号）已经
被 chinese-plain check v0.4.11/15 剥离豁免。但**英文复合词**（不含连字符）
没被识别为项目术语，需要 Agent 自己用汉字解释或替换。

**用词替换清单**（高频英文复合词 → 直白汉字）：

| 英文复合词 | 直白汉字 |
|---|---|
| release note | 发布说明 |
| code identifier | 代码标识符 / 标识符 |
| jargon token | 英文术语词 |
| commit message | 提交说明 |
| dogfooding | 自用验证 |
| timeline | 时间线 |
| markdown | 标记格式 / md |
| pattern | 模式 / 规则 |
| force_block | 强制干预（项目术语保留反引号引用） |
| sticky | 偏好规则 |
| check | 检测 / 规则 |

**例外（保留英文不强求汉字）**：
- 命令名 / CLI flag — `karma audit --with-fix-timeline`（反引号引用是引用不是话术）
- 版本号 — `v0.4.21`（已被 check 剥）
- URL / GitHub 链接 — 已被 check 剥
- 项目专有标识符 — `chinese-plain-no-jargon` / `_LANG_C_HEAD_RE`（已被 kebab/snake 剥）
- 表格 cell 内引用 — 已被 v0.4.15 jargon 扫描豁免

**自检**：写完 response 前看末尾段是否含 2+ 个**英文复合词**（连字符以外
的空格分隔英文）且没汉字解释 → 改成上面替换清单或加括号说明。

### karma 设计层 4 类深层矛盾（2026-05-14 dogfooding 深度自省）

本 session 6 个 release 治理（v0.4.11~16）触发的真深层问题清单。每条都有
真实假阳 case 跟设计思考，下个 session 接手时持续观察：

**矛盾 1：惩罚 vs 鼓励的哲学错位**
- 真触发：chinese-plain 累积 8 次 force_block → v0.4.15 修真根因 → 仍按
  最近 3 turn 累积重复 force_block，Agent 修了真根因没法解除卡死
- 真根因：karma 当前是纯惩罚系统，缺「修真根因后自动恢复」反馈环
- 部分 fix：v0.4.16 加「当前 turn 真触发」条件 + scripts/verify-installed.sh
  防 hook 跑旧字节码。本质闭环已实现（修 check → 重装 → 当前 turn 0
  触发 → force_block 自动解除）
- 残余待治理：更显式的 evolution log 记每次 fix 的真根因 + 时间，让 audit
  视图能区分 fix 前 / fix 后违反

**矛盾 2：karma 自指悖论**
- 真触发清单：`v0.4.11` 版本号字面 / `force_block` 项目标识符 / 表格 cell
  里的 `embedding` jargon / `python -c "...> cutoff..."` 比较运算符 /
  `pytest && git commit` 链式 — 都是 karma 项目自己讨论自己时撞到
- 真根因：sticky 设计 always-on 全局规则，没区分「karma 项目自身」vs
  「用户真业务」vs「文档 / 测试」场景
- 已做：v0.4.11/13/14/15 逐 check 内容层精化（剥版本号 / 标识符 / 表格 /
  python 比较 / 链式测试）
- **不该做**：「karma 项目自身场景识别」是给作者自用的局部 hack，违反
  CLAUDE.md「karma 默认必须跨用户合理」原则。逐 check 内容层精化才是
  真普适（任何用户讨论项目术语 / 写表格汇报 / 跑探针都受益）

**矛盾 3：字面检测 vs 语义意图根本不可调和**
- 真触发：`>` 字面 — shell 重定向 vs python 比较；`sleep` 字面 — shell
  真等待 vs python 字符串数据；jargon 字面 — 真术语堆砌 vs 表格 cell
  引用
- 真根因：karma v2 严格不用大模型（v1→v2 明确边界），regex 字面永远
  分不清「字面相同 / 语义不同」
- **接受的工程代价**：按 v2 边界**坚定不引入 LLM**（memory 里
  `feedback-karma-v2-no-llm-firm` 明确）。路径只能是不断扩剥离 +
  黑白名单，每个 fix 解决一类下一类还在等
- 不该做：调本机小模型语义层兜底（违反 v2 边界）

**矛盾 5：dogfooding 自我评估陷阱（2026-05-14 用户问触发的元层教训）**
- 真触发：本 session 修 5 类 check fix 后我用「audit 修前 N / 修后 0」当
  「完美闭环」证据。用户问「全修成 0 了会不会真阳被误判成假阳」 → 自审发
  现 5 个 fix 中 5 个真过宽，多个真阳被错豁免
- 真根因：karma 用「修后无新触发」当 fix 有效证据，但「修后 0 触发」可能只是
  fix 过宽把真阳吃了，不是真根因 fix 正确 — 经典 sticky #5「反喂思维」陷阱
- 真教训：
  - **不能用 audit 数据当 fix 有效证据** — 那是 confirmation bias
  - **对偶守护测试是「我能想到的真违反 case」** — 漏覆盖真实场景真阳
  - **真验证只能**：按用户视角构造真违反 case 跑现行 check（这次用户问触发
    的就是这流程） + 真用户跨场景使用报漏拦
  - karma 自审工具（audit timeline）不该当作 truth 而是 dogfooding **嫌疑提示**
- 长期方向：karma 协议层不该假设「audit 0 触发 = fix 正确」 — 应该加「召回率
  怀疑」启发：某 check 修后突然 0 触发 + sticky 仍启用 + 历史有真违反 → 标
  `? 召回率可疑` 让用户主动复查（跟现有 `⚠️ 可能假阳` 形成「假阳 vs 假阴」双
  标记 dogfooding 工具）

**矛盾 4：sticky 之间互相打架没冲突仲裁**
- 真冲突对：#8 不停下推进 vs #1 不范围蔓延 / #7 显式让用户介入 vs #8
  不停下问 / #4 完整证据（数字 / 表格） vs #3 直白中文（被拉低比例）
- 部分 fix：现有 `force_block_exempt` 字段给「行为反向」sticky 用（keep-
  pushing 越 force_block 越自相矛盾，所以 exempt）
- **不该做**：加 sticky priority 字段是预防性机制没真实 case 驱动，违反
  sticky #1 「不超出任务需要」。多数冲突是 Agent 自己读 sticky 时的判
  断问题，不是 check 触发后的仲裁问题

## 下个 session 接手指引

### 7+1 条 sticky 完整定位

| # | id | 作用 |
|---|---|---|
| 1 | long-term-fundamental | 用最根本方案不打补丁 |
| 2 | non-blocking-parallel | 测试 / 子 Agent 跑时并行推进 |
| 3 | chinese-plain-no-jargon | 直白中文不堆 jargon |
| 4 | loud-failure-with-evidence | 完成附测试证据 |
| 5 | no-testset-no-future-leakage | 不喂测试集 |
| 6 | read-before-write | 改代码前先读 |
| 7 | keep-pushing-no-stop | 完成后立即推下个不停（作者 / 全权委托型用户）|
| 8 | deep-fix-not-bypass | karma 拦截时深挖根因不绕（**元层监管**）|

sticky #7/#8 跟 #1-#6 不同维度 — #1-#6 是「开发场景行为规则」，#7 是「Agent 协作节奏」，#8 是「Agent 不绕 karma 自身」元层规则。

### 已知 bug / 待 fix 优先清单

- **task #8 catchup 多 hook fix 验证 OK** — catchup_pending_bg 加到 UserPromptSubmit / PreToolUse / PostToolUse 三个 hook 后实战验证 pending=0、last_test_pass_ts 自动接进。
- **task #8.1 catchup race condition（本 session 末尾发现）** — 当 pending_bg_tasks 有滞留 entry（log file 仍存在），每次 hook 调用 catchup 都重复处理 → 反复推 ltp 到 pytest log 时间。如果同时手动 update ltp 到 future，后续 hook 会用 `_next_ts()` floor = max(ltp, le) 覆盖。
  - **根因**：pending entry 没在 catchup 后被移除（看 catchup_pending_bg 代码 — 已经 still_pending list 应该 OK，但实战 ltp 仍被覆盖到旧值）
  - **下个 session 优先**：dump 一次 catchup 调用前后的 pending_bg_tasks + ltp 变化，看是否是 race 还是 catchup 重复读同一 log
- **历史假阳治理 workflow 验证** — 本 session 用 `karma violations clear --trigger <substring>` 选择性清掉 M4 fix 前累积的所有假阳：硬编码 / TODO / sleep 0 / quick fix 字面 / workaround / 先打个补丁 / 字面量列表 / 强制跳过验证 等。audit 从 33 → 11 条剩真违反，证明：
  1. fix 后立即清历史 = audit 视图干净
  2. 工具链完整：audit 找问题 → 修 pattern → clear 治理历史 → 进入纯 dogfooding 数据积累

### karma 自用持续观察 = 持续推进开发

用户原话「咱们继续推就是观察期」— 不要把「开发」和「观察」当二元选择。每次推进都是 dogfooding 数据点。

### 推进候选优先级

**已完成（2026-05-14 dogfooding 第二波）**：

1. ✅ **non-blocking-parallel python -c 字符串字面假阳** — v0.4.18 fix。复用
   v0.4.13 `_LANG_C_HEAD_RE` 模式。330 测试 + 5 向真测。audit timeline 真生效。
2. ✅ **keep-pushing 第 3 类假阳：未来规划 / 显式让用户介入** — v0.4.19 fix。
   `_PUSH_SIGNAL_RE` 扩 + `_STOP_HINT_RE` 收紧 + 新 `_EXPLICIT_USER_HANDOFF_RE`。
   333 测试 + 5 向真测对偶守护。audit timeline 真生效（修前 32 / 修后 0）。
3. ✅ **audit --with-fix-timeline dogfooding 闭环视图** — v0.4.17 feat。
   `_check_file_last_commit_ts` 用 `sticky.yaml.violation_checks` 反查 REGISTRY
   `.__module__` → check 文件 → `git log -1`。仅 karma 仓库 cwd + git 可用时
   启用，fail open。

**下个 session 可推进**（按价值排序）：

1. **chinese-plain 38% 真违反治理 — Agent 用词训练** — audit 显示 chinese-plain
   修后 0 触发但本回合早期有 4 次 38% 真违反（不是 check 假阳，是我用了
   release note / code identifier / jargon token 类英文复合词）。考虑写一份
   「karma 项目自身汇报用词手册」给 Agent 看：什么场景下英文复合词必须配中文
   解释，什么场景下豁免（commit message / 项目术语等）。这是用户层面引导
   而非 check 层 fix。
2. **long-term-fundamental SEED 阶段早期违反清理** — audit 显示 long-term 修前
   5 / 修后 3 是早期 turn 0/1/14 真违反（不是 check 假阳）。考虑 `karma
   violations clear --before-turn 5` 类清理早期 SEED 噪音，让 audit 视图更
   聚焦本 session 真行为分析。但这违反 sticky #5 「不能用测试集反喂训练数据」
   边界要谨慎。
3. **`karma audit --with-fix-timeline` 加 markdown 输出** — 当前是 plain text，
   加 `--format md` 输出可粘贴到 PR / issue 的 markdown 表格让 dogfooding
   分享更方便。
2. **触发词假阳性持续观察** — 实战可能还有未发现假阳
3. **sticky.yaml 模板扩** — 当前 7 条，模型支持 10
4. **README.md / PRD.md 同步最新现状**（每次重大改动后追）
5. **跨场景规则集** — 当前只有「软件开发」一个 dev.example.yaml，可加写作 / 研究等场景预设

已完成（历史候选已落地）：
- ✅ macOS / Linux / Windows 桌面通知（karma/notify.py）
- ✅ 违反累积升级告警（按 turn 距离 + force_block decision=block）
- ✅ Stop hook 真干预（matcher fix 后实战生效）

### 接手前必读

- 跑 `pytest tests/` 应看到 316 passed
- 跑 `karma doctor` 应看到 4 个 hook event 全 ✓
- 看 `karma stats` 累积违反作为持续数据点
- **每次发版后必跑 `scripts/verify-installed.sh --reinstall`** — hook
  shebang 指向 `.venv/bin/python`，pip pkg 不重装本机 hook 仍跑旧字节
  码。v0.4.9/10/11 三连发都没装到本机 → force_block 累积 6 次都没生
  效是这个真根因。

### 紧急关 karma

```
.venv/bin/karma uninstall-hooks         # 拆 wrapper + 清 settings.json
# 或恢复完整原 settings
cp ~/.claude/settings.json.before-karma ~/.claude/settings.json
```

## 仓库链接

- karma v2：https://github.com/jhaizhou-ops/karma
- karma v1（归档）：https://github.com/jhaizhou-ops/karma-v1
