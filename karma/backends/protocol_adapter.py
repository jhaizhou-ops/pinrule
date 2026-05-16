"""Cross-backend hook protocol adapter — input normalization + output shape.

v0.9.15 background: karma 之前假设 Claude Code / Codex CLI / Gemini CLI 三家
hook 协议「靠 payload 字段同名兼容」（见 `karma/backends/__init__.py:9-10`），
但 codex GPT-5.5 cross-model audit + WebFetch 官方文档双验证发现 2 个 critical
cross-backend bug：

1. **Gemini BeforeTool output shape 跟 Claude/Codex 不同**：
   - Claude/Codex 用 `{hookSpecificOutput: {permissionDecision: "deny", ...}}`
   - Gemini 官方文档要求顶层 `{decision: "deny" | "block", reason: "..."}`
   - 影响：Gemini 下 karma 拦截 0 生效（karma 写 violation + stderr 但危险 tool 真执行）

2. **Gemini tool_name + Codex apply_patch 不在 karma checks 比较列表**：
   - karma checks 用 Claude 风格 `Bash`/`Read`/`Edit`/`Write` 比较
   - Gemini 用 `run_shell_command`/`read_file`/`write_file`/`replace`
   - Codex 编辑用 `apply_patch`（hook stdin 真 tool_name）
   - 影响：Gemini 下 0 check 触发；Codex 用户 apply_patch 漏所有编辑型 check（绕 evidence/read_first/long_term）

这个模块是 v0.9.15 phase 1 修复 — 统一 input normalize + output shape adapter。
v0.9.16 phase 2 完成：`normalize_tool_input` + `parse_apply_patch_envelope` 真
解 codex apply_patch envelope（基于本机捕获的 codex 0.130.0 + GPT-5.5 真 session
rollout 真 tool_call 字面），支持 multi-file 让 read_first / record_edit 真覆盖
所有路径。

Sources:
- Gemini hooks reference: https://geminicli.com/docs/hooks/reference/
- Codex hooks docs: https://developers.openai.com/codex/hooks
- Claude Code hooks docs: https://code.claude.com/docs/en/hooks

## 为什么 stop hook / post_tool_use 输出不需要 adapter

Claude Code 把 hook decision 分两种 pattern (verified by WebFetch on
code.claude.com/docs/en/hooks)：

1. **顶层 `decision`**: 用于 UserPromptSubmit / PostToolUse / Stop / SubagentStop /
   PreCompact / ConfigChange 等 — `{decision: "block", reason: "..."}`
2. **`hookSpecificOutput.permissionDecision`**: 仅 PreToolUse — Claude 在这个
   特殊事件有独立 decision schema

karma stop.py 已用顶层 `{decision: "block", reason: ...}` — 跟 Claude Stop 协议
+ Gemini AfterAgent 协议**同时一致**（两家恰巧都用顶层）。所以 stop hook
不需要 adapter 转换。

只有 PreToolUse 是真跨 backend 协议差异点（Claude/Codex 用 hookSpecificOutput，
Gemini BeforeTool 用顶层 decision），所以 protocol_adapter 主要服务 PreToolUse。
"""

from __future__ import annotations

import json
import re
from typing import Any, Literal

# karma 内部 canonical tool_name — 跟 Claude Code 原生命名对齐（历史原因 +
# karma checks 已用这套名比较，归一化 target 是「不改 check 逻辑」最稳）
Backend = Literal["claude", "codex", "gemini"]

# Gemini → karma canonical 映射
# Sources: Gemini hooks reference 文档 + Gemini CLI 内建 tool 名清单
_GEMINI_TOOL_MAP: dict[str, str] = {
    "run_shell_command": "Bash",
    "read_file": "Read",
    "read_many_files": "Read",  # 多文件读：当 Read 处理（read_first check 取 file_path 第一个）
    "write_file": "Write",
    "replace": "Edit",
    "edit": "Edit",
    "edit_file": "Edit",
    # Gemini 其他 tool（save_memory / search 等）karma 不关心，保持原 tool_name
}

# Codex → karma canonical 映射
# Source: Codex hooks docs — apply_patch 是编辑入口，hook stdin 真 tool_name=apply_patch
_CODEX_TOOL_MAP: dict[str, str] = {
    "apply_patch": "Edit",  # Codex 主要编辑方式 — 归一化让 long_term / testset / bypass_karma 扫 tool_input.command 触发
    # Codex Bash 已用 canonical "Bash" 不需映射
    # Codex Read/Write 是否原生存在文档未明 — 暂不映射，让原 tool_name 透传
}

# Gemini event 名 — 用于 backend detection（stdin payload 含 `hook_event_name`）
_GEMINI_EVENT_NAMES = frozenset({"BeforeAgent", "BeforeTool", "AfterTool", "AfterAgent"})


def detect_backend(payload: dict) -> Backend:
    """从 stdin payload 检测当前 hook 跑在哪个 backend。

    Detection 顺序：
    1. payload 的 `hook_event_name` 是 Gemini event 名 → "gemini"
    2. payload 的 `hook_event_name` 是 Claude/Codex event 名（PreToolUse / Stop 等）
       → fallback "claude"（Codex 也接受 Claude output shape，不需要区分）

    karma checks / hooks 实际行为只对「Gemini vs not-Gemini」分流（output shape 差异
    只在 Gemini）。所以 detection 二分够用。
    """
    event = payload.get("hook_event_name", "") or ""
    if event in _GEMINI_EVENT_NAMES:
        return "gemini"
    return "claude"  # Claude + Codex 共用 (Codex 也接受 Claude output shape)


def normalize_tool_name(raw_tool_name: str, payload: dict) -> str:
    """归一化 tool_name 到 karma 内部 canonical（Claude 风格）。

    返回 mapping 命中后的 canonical 名；不在 mapping 表中的 tool_name 原样透传
    （让 karma checks 自己决定要不要处理 — 多数 check 用 `if tool_name not in
    (...): return None` 早期 return，未知 tool_name 自然 no-op，不会误拦）。

    Examples:
        normalize_tool_name("run_shell_command", {...}) → "Bash"
        normalize_tool_name("apply_patch", {...}) → "Edit"
        normalize_tool_name("Bash", {...}) → "Bash"  # 已是 canonical
        normalize_tool_name("unknown_mcp_tool", {...}) → "unknown_mcp_tool"  # 透传
    """
    backend = detect_backend(payload)
    if backend == "gemini":
        return _GEMINI_TOOL_MAP.get(raw_tool_name, raw_tool_name)
    if backend == "claude":
        # Codex 跟 Claude 共用 canonical 大部分名，唯一例外是 apply_patch
        return _CODEX_TOOL_MAP.get(raw_tool_name, raw_tool_name)
    return raw_tool_name


def emit_deny(reason: str, payload: dict) -> str:
    """生成 backend-specific deny output JSON string，hook 直接 print() 出去。

    - **Gemini**: 顶层 `{decision: "deny", reason: ...}`（官方文档要求）
    - **Claude/Codex**: 新格式 `{hookSpecificOutput: {hookEventName, permissionDecision, permissionDecisionReason}}`
      （Codex 文档明确说支持这个新格式 + legacy decision 格式两种）
    """
    backend = detect_backend(payload)
    if backend == "gemini":
        return json.dumps({"decision": "deny", "reason": reason}, ensure_ascii=False)
    # Claude + Codex
    return json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }, ensure_ascii=False)


def emit_allow(payload: dict) -> str:
    """生成 backend-specific allow output JSON string。

    - **Gemini**: passthrough 空对象 `{}`（Gemini 默认允许，不需要显式 allow）
    - **Claude/Codex**: `{hookSpecificOutput: {hookEventName, permissionDecision: "allow"}}`
    """
    backend = detect_backend(payload)
    if backend == "gemini":
        return json.dumps({})  # Gemini 默认 allow
    return json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
        }
    })


# v0.9.16 Codex apply_patch envelope parser
# Real captured shape (codex 0.130.0 + GPT-5.5, 2026-05-16 session rollout):
#     "*** Begin Patch\n*** Update File: <path>\n@@\n+...\n*** End Patch\n"
# Multi-file supported via repeated "*** Update File:" / "*** Add File:" /
# "*** Delete File:" blocks within one envelope. Paths may have leading
# whitespace; strip them.
_APPLY_PATCH_OP_RE = re.compile(
    r"^\*\*\*\s+(Update|Add|Delete)\s+File:\s*(.+?)\s*$",
    re.MULTILINE,
)
_APPLY_PATCH_BEGIN = "*** Begin Patch"


def parse_apply_patch_envelope(envelope: str) -> list[dict[str, str]]:
    """Parse codex apply_patch envelope → list of {"op", "path"}.

    op ∈ {"Update", "Add", "Delete"}.

    Returns [] for non-envelope input (malformed / empty / unrelated string).
    Honest scope: handles standard codex envelope grammar; doesn't validate
    @@ hunks or +/- line content (karma only needs file paths for state
    tracking).
    """
    if not envelope or _APPLY_PATCH_BEGIN not in envelope:
        return []
    return [
        {"op": m.group(1), "path": m.group(2).strip()}
        for m in _APPLY_PATCH_OP_RE.finditer(envelope)
    ]


def _extract_codex_patch_text(raw_tool_input: Any) -> str:
    """codex hook payload 里 apply_patch 的 tool_input 可能是裸字符串或 wrap dict.

    Real codex session rollout (custom_tool_call) 显示 `input` 字段是字符串.
    Hook payload 里 codex 可能 wrap 成 `{"input": "..."}` 或 `{"command": "..."}` —
    暂未捕获真 hook payload（codex exec mode 没 fire hook），这是文档+rollout
    推断的兜底.
    """
    if isinstance(raw_tool_input, str):
        return raw_tool_input
    if isinstance(raw_tool_input, dict):
        for key in ("input", "patch", "command", "diff"):
            v = raw_tool_input.get(key)
            if isinstance(v, str) and v.strip():
                return v
    return ""


def normalize_tool_input(raw_tool_name: str, raw_tool_input: Any, payload: dict) -> Any:
    """Codex apply_patch → karma canonical Edit-shape dict.

    For non-codex / non-apply_patch tool calls: returns raw_tool_input unchanged.

    Returns dict shape:
        {
            "file_path": <primary Update/Add path>,    # read_first single-path check
            "new_string": <full envelope>,             # keyword scan visibility
            "_codex_patch_files": [{"op", "path"}...], # post-hook record_edit per file
        }

    Multi-file patches: file_path is the first Update/Add. _codex_patch_files
    carries the full list so post_tool_use can record_edit each. read_first
    check internally iterates this list when present.
    """
    if raw_tool_name != "apply_patch":
        return raw_tool_input
    # Only codex uses apply_patch in karma's known backends.
    backend = detect_backend(payload)
    if backend == "gemini":
        return raw_tool_input  # not a Gemini tool — passthrough
    envelope = _extract_codex_patch_text(raw_tool_input)
    files = parse_apply_patch_envelope(envelope)
    if not files:
        return raw_tool_input  # not a parseable envelope — passthrough
    primary = next(
        (f["path"] for f in files if f["op"] in ("Update", "Add")),
        files[0]["path"],
    )
    return {
        "file_path": primary,
        "new_string": envelope,
        "_codex_patch_files": files,
    }
