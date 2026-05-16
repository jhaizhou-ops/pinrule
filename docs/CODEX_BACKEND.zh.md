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

## 6 个契约 method

Codex backend (`CodexBackend` 在 `karma/backends/codex.py`) 必须实现这 6 个方法. `JsonHooksBackend` 基类提供 Claude-shape 默认实现; override 来匹配 codex 协议.

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

## 已知 TODO 列表（codex 议程）

这些是 karma 维护者识别但**推迟给 codex backend owner** 的 gap,因为需要 codex 端协议知识：

| # | 问题 | 建议方法 |
|---|---|---|
| 1 | **shell-as-Read** — `exec_command` 跑 `tail`/`sed`/`cat` 应该算 Read 给 `record_read` 用,让 `read_first` 不假阳拦 | 新 `karma/utils/shell_read.py` 含 `extract_read_paths_from_shell(command) -> list[str]`. `codex.normalize_tool_input` 写 `read_file_paths` 字段. `post_tool_use` 通用 handler record 每条. codex 应该对真 codex CLI session 测试避免复杂 pipeline 上假阳（xargs, find, ls -la）. |
| 2 | **真 hook-level payload 捕获** — 当前推断自 session rollout (`response_item.payload.input` 字段) 但实际 hook stdin shape（codex 包装后）没直接捕获. `_extract_codex_patch_text` 防御式 unwrap 几种候选 shape; 知道真 payload 后可以收紧. | 真交互式 codex session（`/hooks` 审批后）加 `KARMA_DEBUG_DUMP_PAYLOAD` env，dump payload 锁字面到测试 fixture. |
| 3 | **Codex feature-flag 检测** — `_is_hooks_feature_enabled` 手解 `~/.codex/config.toml`. codex 可能有更干净 API. | 如果 codex CLI 有 `codex features list --json` 或 status 文件，换掉 toml parser. |
| 4 | **其他 codex tool_name 没映射** — `exec_command` 应该映射到 `Bash`（codex 等价）. `update_plan` 大概应该透传. | Audit codex tool 注册表，更新 `_CODEX_TOOL_MAP`. |
| 5 | **审批状态检测** — `karma doctor` 当前打印手工 reminder. 如果 codex 暴露 approved-hook 列表（sqlite? 文件? API?），`doctor` 可以程序化验证每个 wrapper. | 调研 codex 内部; 如果没 API 给 OpenAI codex 团队提 issue. |

## 如何贡献（codex PR 流程）

1. **只改** `karma/backends/codex.py`（如果新建 `tests/test_codex_backend.py` 也可以）
2. **跑** 现有测试还过: `.venv/bin/python -m pytest tests/test_protocol_adapter.py tests/test_backends.py -q`
3. **加测试** for any new method behavior — 至少用硬编码期望输出锁新 shape
4. **真 codex CLI 证据捕获** （rollout 文件路径 / session id / 版本）在 commit message — 避免 v0.9.15「Claude 猜错」模式
5. **不破 6-method 契约** — 要加新方法先提 issue 让 karma 维护者同步更新 `_base.py` Protocol 和所有 backend
6. **PR description 必须含**:
   - 测试用的 codex CLI 版本 (e.g., `codex 0.130.0`)
   - 真实测试 transcript (e.g., 用户 prompt → karma 响应截图)
   - 任何新捕获的 tool_name / payload shape（session rollout 文件路径）

## 契约测试（计划中，未实现）

karma 维护者会加 `tests/test_backend_contract.py` 跑同一套抽象契约测试对 `REGISTRY` 里每个 backend — codex 的 PR 不应破这套. 预期覆盖:
- 6 个方法 在最小 payload 上能 callable 不崩
- `emit_allow` 和 `emit_deny` 返回有效 JSON
- `normalize_tool_name` 保留 canonical 名（幂等）
- `pre_install_setup` 和 `post_install_message` 返回 list

## 沟通渠道

- **架构问题**: 提 GitHub issue 加标签 `backend:codex`，@ `@jhaizhou-ops`
- **PR review**: karma 维护者 1-2 天内 review; 推荐窄而专注的 PR（一 PR 一 TODO 项）
- **破坏性变更**: 必须先在 issue 讨论; codex backend 可以申请 `_base.py` 契约调整如果真 codex 协议需要
