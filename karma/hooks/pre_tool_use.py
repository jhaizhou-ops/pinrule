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

import json
import sys
import time

from karma import session_state
from karma.checks import run_checks
from karma.checks.common import extract_tool_text
from karma.sticky import StickyConfigError, load
from karma.violations import Violation, append, detect


def _allow() -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
        }
    }))


def _deny(reason: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }, ensure_ascii=False))


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"karma PreToolUse: 输入 JSON 解析失败 ({e})", file=sys.stderr)
        _allow()
        return 0

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}
    session_id = payload.get("session_id", "") or "default"

    try:
        sticky_list = load()
    except StickyConfigError as e:
        print(f"karma: {e}", file=sys.stderr)
        _allow()
        return 0

    if not sticky_list:
        _allow()
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

    # 关键词层（兜底）— 只扫 Bash command（明确执行意图）。
    # Write/Edit 的代码内容里出现关键词几乎全是「描述/注释/字符串字面」假阳：
    #   - 代码注释讨论某个概念
    #   - docstring 介绍函数行为
    #   - 错误信息 / 帮助文本提到该词
    # 而 Bash command 是直接要执行的 shell — 关键词出现就是真执行意图。
    # Write/Edit 的真违反交给工程层 violation_checks（regex + 上下文判定）覆盖。
    keyword_violations: list[Violation] = []
    if tool_name == "Bash":
        scan_text = extract_tool_text(tool_name, tool_input)
        if scan_text.strip():
            keyword_violations = detect(scan_text, sticky_list, session_id=session_id)

    if not check_hits and not keyword_violations:
        _allow()
        return 0

    # 优先工程层
    if check_hits:
        top = check_hits[0]
        append([Violation(
            ts=int(time.time()),
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
        _deny(reason)
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
    _deny(reason)
    print(
        f"🛑 karma: {top_kw.sticky_id} (tool={tool_name}, 关键词 {top_kw.trigger!r})",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
