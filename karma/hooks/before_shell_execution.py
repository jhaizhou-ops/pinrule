"""Cursor beforeShellExecution — native shell command gate (not preToolUse clone).

https://cursor.com/docs/hooks — fires on the actual shell command string before
execution. karma routes through shared tool gate with Shell/Bash semantics.
"""

from __future__ import annotations

import json
import sys

from karma.hooks._tool_gate import run_tool_gate


def main() -> int:
    try:
        raw = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        from karma.backends.protocol_adapter import emit_allow
        print(f"karma beforeShellExecution: JSON 解析失败 ({e})", file=sys.stderr)
        print(emit_allow({}))
        return 0

    payload = dict(raw)
    payload.setdefault("hook_event_name", "beforeShellExecution")
    payload["tool_name"] = "Shell"
    payload["tool_input"] = {
        "command": raw.get("command", ""),
        "cwd": raw.get("cwd", ""),
        "sandbox": raw.get("sandbox", False),
    }
    return run_tool_gate(payload)


if __name__ == "__main__":
    sys.exit(main())
