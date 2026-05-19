"""Per-backend native hook surfaces — pinrule 能力如何挂到各客户端原生事件上.

Claude: PascalCase events + hookSpecificOutput (baseline reference).
Codex: nested hooks + payload.model + trusted_hash (see codex.py).
Cursor: camelCase events + permission/followup_message + Rules .mdc (本模块).

设计原则: **同一套 checks/rules/session_state**, **不同 native 触达点**.
不追求 event 名一一对应; 追求 **能力覆盖** (注入 / 拦截 / 审计 / 续推).
"""

from __future__ import annotations

from typing import TypedDict


class NativeHookSpec(TypedDict):
    event: str
    wrapper: str
    role: str  # inject | gate | audit | lifecycle


# Cursor — https://cursor.com/docs/hooks (2026-05)
CURSOR_NATIVE_HOOKS: list[NativeHookSpec] = [
    {"event": "beforeSubmitPrompt", "wrapper": "user_prompt_submit", "role": "inject"},
    {"event": "sessionStart", "wrapper": "session_start", "role": "inject"},
    {"event": "postToolUse", "wrapper": "post_tool_use", "role": "inject"},
    {"event": "preToolUse", "wrapper": "pre_tool_use", "role": "gate"},
    {"event": "beforeShellExecution", "wrapper": "before_shell_execution", "role": "gate"},
    {"event": "beforeMCPExecution", "wrapper": "before_mcp_execution", "role": "gate"},
    {"event": "beforeReadFile", "wrapper": "before_read_file", "role": "gate"},
    {"event": "afterAgentResponse", "wrapper": "after_agent_response", "role": "audit"},
    {"event": "stop", "wrapper": "stop", "role": "audit"},
    {"event": "preCompact", "wrapper": "pre_compact", "role": "lifecycle"},
    {"event": "subagentStart", "wrapper": "subagent_start", "role": "lifecycle"},
    {"event": "subagentStop", "wrapper": "subagent_stop", "role": "lifecycle"},
]

# Codex — https://developers.openai.com/codex/hooks
CODEX_NATIVE_HOOKS: list[NativeHookSpec] = [
    {"event": "SessionStart", "wrapper": "session_start", "role": "inject"},
    {"event": "UserPromptSubmit", "wrapper": "user_prompt_submit", "role": "inject"},
    {"event": "PreToolUse", "wrapper": "pre_tool_use", "role": "gate"},
    {"event": "PermissionRequest", "wrapper": "pre_tool_use", "role": "gate"},
    {"event": "PostToolUse", "wrapper": "post_tool_use", "role": "inject"},
    {"event": "Stop", "wrapper": "stop", "role": "audit"},
]

CURSOR_HOOK_EVENTS: dict[str, str] = {
    spec["event"]: spec["wrapper"] for spec in CURSOR_NATIVE_HOOKS
}

CODEX_HOOK_EVENTS: dict[str, str] = {
    spec["event"]: spec["wrapper"] for spec in CODEX_NATIVE_HOOKS
}


# Hermes Agent — https://hermes-agent.nousresearch.com/docs/user-guide/features/hooks (2026-05)
# NousResearch Hermes Agent v0.14.0+ — persistent memory + multi-platform CLI agent.
# Plugin hooks (CLI + Gateway), 真 stdin JSON payload with session_id / tool_name /
# tool_input / cwd / extra. Output shape: {"decision": "block"} or {"action": "block"}
# normalized; pre_llm_call accepts top-level {"context": "..."}.
HERMES_NATIVE_HOOKS: list[NativeHookSpec] = [
    {"event": "pre_llm_call", "wrapper": "user_prompt_submit", "role": "inject"},
    {"event": "on_session_start", "wrapper": "session_start", "role": "inject"},
    {"event": "post_tool_call", "wrapper": "post_tool_use", "role": "inject"},
    {"event": "pre_tool_call", "wrapper": "pre_tool_use", "role": "gate"},
    {"event": "agent:end", "wrapper": "stop", "role": "audit"},
    {"event": "on_session_end", "wrapper": "session_end", "role": "lifecycle"},
]

HERMES_HOOK_EVENTS: dict[str, str] = {
    spec["event"]: spec["wrapper"] for spec in HERMES_NATIVE_HOOKS
}
