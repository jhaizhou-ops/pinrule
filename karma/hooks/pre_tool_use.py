"""pre_tool_use hook — Agent 调 tool **之前**拦截违反。

时机：Agent 决定调 tool 但还没执行。
输入：stdin JSON {tool_name, tool_input, session_id}
输出：stdout JSON {decision: "allow"|"deny", reason?}

检测两层：
1. 关键词层（violation_keywords）— 扫 tool_input 文本中关键词出现
2. 工程层（violation_checks）— 调 karma.checks 函数库（结构化模式 + session 状态）

性能预算：< 100ms
Fail open：配置坏 / 异常 → allow (不卡 Agent)
"""

from __future__ import annotations

import json
import sys

from karma import session_state
from karma.checks import run_checks
from karma.checks.common import extract_tool_text
from karma.sticky import StickyConfigError, load
from karma.violations import Violation, append, detect


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"karma pre_tool_use: 输入 JSON 解析失败 ({e})", file=sys.stderr)
        print(json.dumps({"decision": "allow"}))
        return 0

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}
    session_id = payload.get("session_id", "") or "default"

    try:
        sticky_list = load()
    except StickyConfigError as e:
        print(f"karma: {e}", file=sys.stderr)
        print(json.dumps({"decision": "allow"}))
        return 0

    if not sticky_list:
        print(json.dumps({"decision": "allow"}))
        return 0

    state = session_state.load(session_id)

    # 工程层 violation_checks
    check_hits = []
    for s in sticky_list:
        if not s.violation_checks:
            continue
        hits = run_checks(
            s.violation_checks,
            tool_name=tool_name,
            tool_input=tool_input,
            session_state=state,
            sticky_id=s.id,
        )
        check_hits.extend(hits)

    # 关键词层（兜底）
    keyword_violations: list[Violation] = []
    scan_text = extract_tool_text(tool_name, tool_input)
    if scan_text.strip():
        keyword_violations = detect(scan_text, sticky_list, session_id=session_id)

    if not check_hits and not keyword_violations:
        print(json.dumps({"decision": "allow"}))
        return 0

    # 优先工程层结果（更精准），关键词作 fallback
    if check_hits:
        top = check_hits[0]
        # 同时写违反记录（让 stats 看得到）
        append([Violation(
            ts=__import__("time").__dict__["time"]().__int__() if False else int(__import__("time").time()),
            session_id=session_id,
            sticky_id=top.sticky_id,
            trigger=top.trigger,
            snippet=top.snippet,
        )])
        sticky_pref = next((s.preference for s in sticky_list if s.id == top.sticky_id), "")
        reason = (
            f"karma 拦截：违反 {top.sticky_id!r}。\n"
            f"检测到：{top.trigger}\n"
            f"方向：{sticky_pref.strip()}\n"
            f"建议：{top.suggested_fix}"
        )
        print(json.dumps({"decision": "deny", "reason": reason}, ensure_ascii=False))
        print(
            f"🛑 karma: {top.sticky_id} (tool={tool_name}) — {top.trigger}",
            file=sys.stderr,
        )
        return 0

    # 仅关键词命中
    top_kw = keyword_violations[0]
    append([top_kw])
    sticky_pref = next((s.preference for s in sticky_list if s.id == top_kw.sticky_id), "")
    reason = (
        f"karma 拦截：违反 {top_kw.sticky_id!r}（触发词 {top_kw.trigger!r}）。\n"
        f"方向：{sticky_pref.strip()}\n"
        f"请改写，不要用 {top_kw.trigger!r} 这种方式。"
    )
    print(json.dumps({"decision": "deny", "reason": reason}, ensure_ascii=False))
    print(
        f"🛑 karma: {top_kw.sticky_id} (tool={tool_name}, 关键词 {top_kw.trigger!r})",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
