"""pre_tool_use hook — Agent 调 tool **之前**拦截违反。

时机：Agent 决定调 tool（Bash / Write / Edit / ...）但还没执行。
输入：stdin JSON payload，含 tool_name + tool_input + session_id。
输出：stdout JSON 决策 {"decision": "allow" | "deny", "reason": "..."}

跟 post_response 的差别：
- post_response 是事后通知（Agent 已经做完违反动作）
- pre_tool_use 是事前拦截（Agent 还没执行就被打回）

性能预算：< 100ms（影响每次 tool 调用响应）
"""

from __future__ import annotations

import json
import sys
from typing import Any

from karma.sticky import StickyConfigError, load
from karma.violations import append, detect


def _extract_scan_text(tool_name: str, tool_input: dict[str, Any]) -> str:
    """从 tool_input 提取要扫违反的文本。

    不同 tool 不同字段:
    - Bash: command
    - Write: content
    - Edit: new_string + old_string (新写入的内容才是 Agent 加的)
    - 其他: json dump 整个 input
    """
    if tool_name == "Bash":
        return tool_input.get("command", "") or ""
    if tool_name == "Write":
        return tool_input.get("content", "") or ""
    if tool_name == "Edit":
        # 优先扫 new_string（Agent 写的新内容）；old_string 是用户已有代码不算违反
        return tool_input.get("new_string", "") or ""
    if tool_name == "NotebookEdit":
        return tool_input.get("new_source", "") or ""
    # 其他 tool 全量序列化（保守）
    try:
        return json.dumps(tool_input, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(tool_input)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"karma pre_tool_use: 输入 JSON 解析失败 ({e})", file=sys.stderr)
        # 解析失败 → 不阻塞 tool（fail open，避免坏 karma 卡 Agent）
        print(json.dumps({"decision": "allow"}))
        return 0

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}
    session_id = payload.get("session_id", "unknown")

    try:
        sticky_list = load()
    except StickyConfigError as e:
        print(f"karma: {e}", file=sys.stderr)
        print(json.dumps({"decision": "allow"}))
        return 0

    if not sticky_list:
        print(json.dumps({"decision": "allow"}))
        return 0

    scan_text = _extract_scan_text(tool_name, tool_input)
    if not scan_text.strip():
        print(json.dumps({"decision": "allow"}))
        return 0

    violations = detect(scan_text, sticky_list, session_id=session_id)
    if not violations:
        print(json.dumps({"decision": "allow"}))
        return 0

    # 写违反记录（让 stats / recent 命令看得到 pre-tool 拦截历史）
    append(violations)

    # 拒绝 tool 调用 + 把违反原因返给 Agent（Agent 看了会重新规划）
    top = violations[0]
    sticky_pref = next((s.preference for s in sticky_list if s.id == top.sticky_id), "")
    reason = (
        f"karma sticky 拦截：违反 {top.sticky_id!r}（触发 {top.trigger!r}）。\n"
        f"方向：{sticky_pref.strip()}\n"
        f"请重新设计这步，不要用 {top.trigger!r} 这种方式。"
    )
    print(json.dumps({"decision": "deny", "reason": reason}, ensure_ascii=False))
    # 同时 stderr 通知用户
    print(
        f"🛑 karma 拦截：{top.sticky_id} (tool={tool_name}, 触发 {top.trigger!r})",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
