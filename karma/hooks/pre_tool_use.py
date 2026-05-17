"""PreToolUse hook — Agent 调 tool 前拦截违反。

Claude Code 实际协议:
- stdin payload: {tool_name, tool_input, tool_use_id, session_id, transcript_path, ...}
- stdout 输出:
    allow: {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}}
    deny : {"hookSpecificOutput": {..., "permissionDecision": "deny", "permissionDecisionReason": "..."}}

检测两层：
1. 工程层 violation_checks (karma.checks 函数库)
2. 关键词层 violation_keywords (兜底)

性能预算：< 100ms
Fail open：配置坏 / 异常 → allow (不卡 Agent)
"""

from __future__ import annotations

import sys

from karma.backends.protocol_adapter import emit_allow, emit_deny


def _allow(payload: dict) -> None:
    """v0.9.15: 走 protocol_adapter — Cursor 用 `{permission: allow}`, Claude/Codex 用 hookSpecificOutput."""
    print(emit_allow(payload))


def _deny(reason: str, payload: dict) -> None:
    """v0.9.15: 走 protocol_adapter — Cursor 顶层 `{permission: deny, agent_message, user_message}`,
    Claude/Codex `hookSpecificOutput.permissionDecision`. 之前 karma 只输出
    Claude 风格让 Cursor 拦截可能失效."""
    print(emit_deny(reason, payload))


def main() -> int:
    from karma.hooks._tool_gate import main_stdin
    return main_stdin()


if __name__ == "__main__":
    sys.exit(main())
