"""Cursor beforeReadFile — native read gate (read-before-write at file access).

Uses read_first check via synthetic Read tool gate when path is known.
"""

from __future__ import annotations

import json
import sys

from karma.backends.protocol_adapter import emit_allow
from karma.hooks._tool_gate import run_tool_gate


def main() -> int:
    try:
        raw = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"karma beforeReadFile: JSON 解析失败 ({e})", file=sys.stderr)
        print(emit_allow({}))
        return 0

    path = raw.get("file_path", "")
    payload = dict(raw)
    payload.setdefault("hook_event_name", "beforeReadFile")
    payload["tool_name"] = "Read"
    payload["tool_input"] = {"file_path": path}
    return run_tool_gate(payload)


if __name__ == "__main__":
    sys.exit(main())
