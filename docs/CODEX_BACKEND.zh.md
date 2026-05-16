# Codex Backend — 接手指南

**[🇬🇧 English](./CODEX_BACKEND.md) · [🇨🇳 中文（当前）](./CODEX_BACKEND.zh.md)**

本文档是 karma `codex` backend 的**接口契约 + 所有权边界**。v0.10.0 起 codex backend 由 **Codex CLI 自身**维护（通过 Codex session 发 PR 进来），karma 主仓只提供契约层 + 审 PR.

## 为什么这样分工

karma v0.9.15 cross-model audit 和 v0.9.16 codex envelope parser 都撞到同一类失败模式：**Claude 猜 codex 协议细节就会猜错**。已记录的事件：

- **v0.9.15** 假设 Codex 接受 `hookSpecificOutput.permissionDecision:"allow"` shape — 2026-05-16 真测试 codex 0.130 CLI 报错 `unsupported permissionDecision:allow`。正确 shape 是裸 `{}`（[codex hooks docs](https://developers.openai.com/codex/hooks) 原文）。karma 这条错了 1 个 release.
- **shell-as-Read 适配缺口** — codex CLI 没独立 `Read` tool，靠 `exec_command` 跑 `tail` / `sed` / `cat` 等 shell 读文件。karma `record_read` 只认 `tool_name == "Read"`，看不到 codex 的 shell 读 → 任何 codex 编辑都被 `read_first` 假阳拦。修法需要在 codex backend 内识别 shell-read 模式，Claude 不在最佳位置设计这个.
- Codex feature flag 一直变 — `codex_hooks` 被弃用换成 `hooks`（~2026-04），`features.hooks=true` 现在必须，`/hooks` TUI 逐个 wrapper 审批（v0.130+）。karma 主仓总落后 1-2 周.

**结论**：codex 协议细节所有权属于「对 codex 平台变更信号最快的一方」。那就是 Codex CLI 自己，通过本仓 PR session 维护.

## 所有权边界

| 文件 | Owner | Codex 能改？ |
|---|---|---|
| `karma/backends/codex.py` | **Codex** | ✅ 可以，主要文件 |
| `tests/test_codex_backend.py`（新建，可选） | **Codex** | ✅ 可以，codex 私有测试 |
| `karma/backends/_base.py` Protocol | karma 维护者 | ❌ 契约层，要改先提 issue |
| `karma/backends/_json_hooks.py` 基类 | karma 维护者 | ❌ Claude-shape 默认行为 |
| `karma/backends/protocol_adapter.py` 调度 | karma 维护者 | ❌ 纯路由 |
| `karma/hooks/*.py` 主逻辑 | karma 维护者 | ❌ backend-neutral |
| `karma/checks/*.py` engine check | karma 维护者 | ❌ backend-neutral |
| `tests/test_protocol_adapter.py` 跨 backend 测试 | karma 维护者 | ❌ 契约测试 |

## 8 个契约 method

Codex backend (`CodexBackend` 在 `karma/backends/codex.py`) 必须实现这 8 个方法. `JsonHooksBackend` 基类提供 Claude-shape 默认实现; override 来匹配 codex 协议.

方法 1-6 是 v0.10.0 拆分时定义的; 方法 7-8 在 v0.10.6 加, 去掉 ContextInjection + Stop hook 上 4 个 hook 直 print Claude shape 的隐式假设 (跟 v0.9.15 同款 drift pattern).

### 1. `pre_install_setup(self) -> list[str]`

karma 写 hooks.json 前调用. 当前跑 `codex features enable hooks` 翻 feature flag. 返回 per-line 用户可见日志.

**当前状态**: ✅ 已实现. codex 可 review 这条 feature 命令.

### 2. `post_install_message(self) -> list[str]`

karma 写完 hooks.json 后调用. 返回响亮警示行打印到 stdout. 用于告诉用户 `/hooks` TUI 审批要求.

**当前状态**: ✅ 已实现（占位文本）. codex 可调措辞 / 加 tutorial 链接 / 如果 codex 暴露 approval state API 就检测.

### 3. `normalize_tool_name(self, raw_tool_name: str, payload: dict) -> str`

把 codex 原生 tool_name 映射到 karma canonical（Claude 风格: `Bash` / `Read` / `Edit` / `Write` / `NotebookEdit`).

**当前状态**: `apply_patch → Edit`. **大概率不完整** — codex 可能还有别的 tool_name (`exec_command`, `update_plan`, plugin tools) karma 该归一化.

**为什么重要**: karma engine check 用 `tool_name in ("Edit", "Write")` 比较. 没映射的 raw_tool_name 让 check 早 return `None` → 0 强制力.

### 4. `normalize_tool_input(self, raw_tool_name, raw_tool_input, payload) -> Any`

把 codex tool_input 转 karma canonical dict. `apply_patch` 解 envelope 字符串成 `{file_path, new_string, multi_file_targets}`.

**当前状态** — **占位实现，codex 应该改进**:
- `parse_apply_patch_envelope()` 用正则解 `*** Begin Patch / *** Update File: / @@ / *** End Patch` 块. 锁的是 2026-05-16 13:51:47 一条真捕获 envelope. 可能漏边界 case（escaped path / binary patch 等）.
- `_extract_codex_patch_text()` 防御式处理裸字符串和 dict-wrap 输入形式. 真 hook-level payload schema 没捕获到（codex `exec` 模式不 fire hook; 交互式 codex hook payload 没 dump）. **codex 应该捕获真 hook payload shape 并锁字面**.
- **shell-as-Read 适配缺口未实现** — `raw_tool_name == "exec_command"` 且命令命中只读模式（`tail`, `sed -n`, `cat`, `head`, `less`, `more`, `wc`, `file`, `grep -l`）时,这个方法应该输出类似 `{"read_file_paths": [...]}`，post_tool_use 需要相应 handler. **codex 拥有这块设计** 因为 shell-read 模式检测假阳风险高,codex 对真实世界 `exec_command` 模式信号最快.

### 5. `emit_deny(self, reason: str, payload: dict) -> str`

返回「拒绝此 tool call」JSON string. Codex 接受 Claude 的 `hookSpecificOutput.permissionDecision:"deny"` shape（2026-05-16 真测试 case 1 验证）.

**当前状态**: ✅ shape 对（在基类基础上 override 了）.

### 6. `emit_allow(self, payload: dict) -> str`

返回「允许此 tool call」JSON string. **Codex 不接受 `hookSpecificOutput.permissionDecision:"allow"`** — [codex hooks 官方文档](https://developers.openai.com/codex/hooks) 原话：

> "permissionDecision: 'ask', legacy 'decision: 'approve', 'updatedInput', 'continue: false', 'stopReason', and 'suppressOutput' are parsed but not supported yet, so they fail open."
> "To permit a tool call, either return an empty JSON object (`{}`) or exit with code `0` and no output."

**当前状态**: ✅ 返回 `"{}"`. 有锁定回归测试（`test_codex_emit_allow_returns_empty_dict_not_claude_shape`）防止未来 PR 误退回 Claude shape.

### 7. `emit_context_injection(self, event_name: str, additional_context: str, payload: dict) -> str`

返回「向 Agent 注入 additionalContext」JSON string（SessionStart / UserPromptSubmit / PostToolUse / SubagentStart 都走这个）. Claude shape 是 `{hookSpecificOutput: {hookEventName: event_name, additionalContext: additional_context}}`.

**当前状态**: 继承 `JsonHooksBackend` 的 Claude-shape 默认. **codex 真接受度未验证** — 见剩余 TODO #8. 如果 codex 报错 / 静默丢, override 成 codex 真 shape.

### 8. `emit_stop_block(self, reason: str, payload: dict) -> str`

返回「拦下 Agent 停止」JSON string（Stop hook 的 force_block / keep_pushing_block 路径）. Claude shape 是 `{decision: "block", reason: reason}`. Gemini override 返 `{}` 因为 AfterAgent 没 block 概念 — 返空是 fail-open 不是静默拒.

**当前状态**: 继承 Claude-shape 默认. **codex 真接受度未验证** — 见剩余 TODO #8.

## 已完成 TODO (v0.10.x)

v0.10.0 定义的 TODO 在后续 codex-owned PR 里完成:

| # | 问题 | 状态 | 落地版本 |
|---|---|---|---|
| 1 | **shell-as-Read** — `exec_command` 跑 `tail`/`sed`/`cat` 算 Read | ✅ Done | v0.10.1 [PR #3](https://github.com/jhaizhou-ops/karma/pull/3) `extract_read_paths_from_exec_command()` |
| 1.5 | **简单 pipe 读** — `head N \| tail M` / `cat \| head/tail` chain | ✅ Done | v0.10.3 [PR #5](https://github.com/jhaizhou-ops/karma/pull/5) shell-as-Read 扩展 |
| 2 | **真 hook-level payload 捕获** for SessionStart | ✅ Done | v0.10.2 [PR #4](https://github.com/jhaizhou-ops/karma/pull/4) — codex SessionStart payload 捕获 + 锁定到测试 fixture |
| 4 | **其他 codex tool_name** — `exec_command → Bash` 等 | ✅ Done | v0.10.2 [PR #4](https://github.com/jhaizhou-ops/karma/pull/4) `_CODEX_TOOL_MAP` 扩展 |
| 5a | **审批状态 UX** — 手动 `/hooks` 审批瓶颈 | ✅ Done | v0.10.2 [PR #4](https://github.com/jhaizhou-ops/karma/pull/4) `trust_karma_hooks()` 自动写 `trusted_hash` |
| 7 | **`write_file_paths` canonical 写字段** — `sed -i` / `tee` / `producer \| tee file` 写命令同时输出 `write_file_paths` + `is_write=True`. 通用层 `karma/hooks/post_tool_use.py:124-155` 消费列表 (v0.10.5 karma 端 ready) 调 `state.record_edit(p)`. evidence check 现在看到 codex `sed -i` 等真代码改动. | ✅ Done | post-v0.11.2 [PR #6](https://github.com/jhaizhou-ops/karma/pull/6) `extract_read_write_paths_from_exec_command` 函数重命名返 `(read_paths, write_paths, is_write)` tuple |

## 剩余 TODO 列表（codex 议程）

| # | 问题 | 建议方法 |
|---|---|---|
| 2-follow-up | **真 hook-level payload 捕获 for PreToolUse / PostToolUse / Stop / UserPromptSubmit** — 只 SessionStart shape 捕获了. `_extract_codex_patch_text` 仍防御式 unwrap 多个候选 shape — 真 PreToolUse hook payload 捕获后可以收紧. | 真交互式 codex session（`/hooks` 审批后）加 `KARMA_DEBUG_DUMP_PAYLOAD` env, dump payload, 锁字面到 fixture, 把 `_extract_codex_patch_text` 收紧到验证过的 key. |
| 3 | **Codex feature-flag 检测清理** — `_is_hooks_feature_enabled` 手解 `~/.codex/config.toml`. codex 0.131+ 可能有更干净 API. | 如果 codex CLI 出 `codex features list --json` 或 status 文件, 换掉 toml parser. 低优先级 — toml parser 工作. |
| 5b | **程序化审批验证** — `trust_karma_hooks()` 写 `trusted_hash`; `karma doctor` 可以程序化验证每个 wrapper 当前是否仍 approved (vs. 让用户去 TUI 看). | 调研 `~/.codex/config.toml` `[hooks.state]` entry 是否能读回并 validate against 当前 wrapper hash. 如果可以, `karma doctor` 加 per-wrapper 绿红 check. |
| 6 | **更多 pipe 读 pattern** — `xargs cat` / recursive `grep -r` / `find` 故意不识别 (PR #5 保守 scope). 如果真 codex 使用显示这些 pattern 高假阴率, 设计组合-pattern 引擎. | 挖 `~/.codex/sessions/*/` rollout 看这些 pattern 真频率; 高就设计扩展. |
| 8 | **`emit_context_injection` / `emit_stop_block` codex shape 验证** — v0.10.6 加了 8-method Backend Protocol; codex.py 当前继承 Claude-shape 默认, 但 codex 是否真接受 `{hookSpecificOutput, additionalContext}` shape (SessionStart / UserPromptSubmit / PostToolUse / SubagentStart) + `{decision: "block", reason}` shape (Stop) 未验证. PR #6 明确推迟: "不 override, Claude shape 默认" 含锁定测试. | 真交互式 codex session fire 这些 hook 时捕获真 payload. 如果 codex 静默接受 Claude shape, 锁定测试保留. 如果 codex 报错 / 静默丢, override codex backend 的 `emit_context_injection` / `emit_stop_block`. |

## 如何贡献（codex PR 流程）

1. **只改** `karma/backends/codex.py`（如果新建 `tests/test_codex_backend.py` 也可以）
2. **跑** 现有测试还过: `.venv/bin/python -m pytest tests/test_protocol_adapter.py tests/test_backends.py -q`
3. **加测试** for any new method behavior — 至少用硬编码期望输出锁新 shape
4. **真 codex CLI 证据捕获** （rollout 文件路径 / session id / 版本）在 commit message — 避免 v0.9.15「Claude 猜错」模式
5. **不破 8-method 契约** — 要加新方法先提 issue 让 karma 维护者同步更新 `_base.py` Protocol 和所有 backend
6. **PR description 必须含**:
   - 测试用的 codex CLI 版本 (e.g., `codex 0.130.0`)
   - 真实测试 transcript (e.g., 用户 prompt → karma 响应截图)
   - 任何新捕获的 tool_name / payload shape（session rollout 文件路径）

## 契约测试 (v0.10.1 已实现)

`tests/contract/test_backend_contract.py` 用 `pytest.parametrize` 跑 14 个抽象契约测试对 `REGISTRY` 里每个 backend. 覆盖:
- 6 个方法在最小 payload 上能 callable 不崩
- `emit_allow` / `emit_deny` 返回有效 JSON string
- `normalize_tool_name` 返回 str + 透传未知 + canonical 幂等
- `hook_events()` 非空 dict + snake_case basename
- `settings_path()` 在 dotted config 目录下
- `build_event_entry()` 返回 dict 含 `hooks` key
- `is_karma_entry()` 识别自家 entry + 拒陌生 entry
- `name` / `display_name` 非空
- `skill_install_targets()` 返回 list 含合法 format string

任何 codex PR 破这些自动 CI fail. 加新 backend 自动通过 REGISTRY 注册拿到 14 个契约测试覆盖 — 无 per-backend boilerplate.

## 沟通渠道

- **架构问题**: 提 GitHub issue 加标签 `backend:codex`，@ `@jhaizhou-ops`
- **PR review**: karma 维护者 1-2 天内 review; 推荐窄而专注的 PR（一 PR 一 TODO 项）
- **破坏性变更**: 必须先在 issue 讨论; codex backend 可以申请 `_base.py` 契约调整如果真 codex 协议需要
