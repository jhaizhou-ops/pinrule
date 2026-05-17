"""Cursor beforeMCPExecution — native MCP gate (covers IDE tools like Await when exposed).

https://cursor.com/docs/hooks — stdin {tool_name, tool_input, url|command}.
Agent-internal long-poll tools often appear here as MCP. pinrule blocks
long block_until_ms / Await-style waits that never go through Shell preToolUse.
"""

from __future__ import annotations

import json
import sys

from pinrule.backends.protocol_adapter import emit_allow, emit_deny
from pinrule.hooks._tool_gate import run_tool_gate
from pinrule.i18n import tr


def _parse_tool_input(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    return {}


def _block_long_mcp_wait(tool_name: str, tool_input: dict, payload: dict) -> str | None:
    name_lower = (tool_name or "").lower()
    if "await" in name_lower:
        block_ms = tool_input.get("block_until_ms") or tool_input.get("block_until")
        if isinstance(block_ms, (int, float)) and block_ms >= 30_000:
            return tr("check.non_blocking.mcp_await.fix")
    for key in ("block_until_ms", "block_until", "timeout"):
        val = tool_input.get(key)
        if isinstance(val, (int, float)) and val >= 30_000:
            return tr("check.non_blocking.mcp_long_poll.fix")
    return None


def main() -> int:
    try:
        raw = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"pinrule beforeMCPExecution: JSON 解析失败 ({e})", file=sys.stderr)
        print(emit_allow({}))
        return 0

    tool_name = raw.get("tool_name", "")
    tool_input = _parse_tool_input(raw.get("tool_input"))
    payload = dict(raw)
    payload.setdefault("hook_event_name", "beforeMCPExecution")
    payload["tool_name"] = tool_name
    payload["tool_input"] = tool_input

    block_reason = _block_long_mcp_wait(tool_name, tool_input, payload)
    if block_reason:
        reason = tr(
            "check.non_blocking.mcp_await.trigger",
            tool=tool_name,
        ) + " " + block_reason
        print(emit_deny(reason, payload))
        return 0

    return run_tool_gate(payload)


if __name__ == "__main__":
    sys.exit(main())
