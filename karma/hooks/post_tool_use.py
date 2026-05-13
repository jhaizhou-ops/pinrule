"""post_tool_use hook — 跟踪 session 状态（Read 历史 / Bash 测试输出 / Edit 累积）。

时机：Agent tool 调用完成后。
输入：stdin JSON {tool_name, tool_input, tool_response, session_id}
输出：(无 — 仅写 session_state 文件)

性能预算：< 30ms（写小 JSON 文件）
"""

from __future__ import annotations

import json
import sys

from karma import session_state


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"karma post_tool_use: 输入 JSON 解析失败 ({e})", file=sys.stderr)
        return 0  # fail open

    session_id = payload.get("session_id", "") or "default"
    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}
    tool_response = payload.get("tool_response", "") or payload.get("tool_output", "") or ""

    state = session_state.load(session_id)

    if tool_name == "Read":
        fp = tool_input.get("file_path", "")
        state.record_read(fp)
    elif tool_name in ("Edit", "Write", "NotebookEdit"):
        fp = tool_input.get("file_path", "") or tool_input.get("notebook_path", "")
        state.record_edit(fp)
    elif tool_name == "Bash":
        cmd = tool_input.get("command", "") or ""
        state.record_bash(cmd, str(tool_response))

    try:
        session_state.save(state)
    except OSError as e:
        print(f"karma post_tool_use: 保存 session_state 失败 ({e})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
