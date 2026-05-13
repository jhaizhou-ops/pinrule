"""post_response hook — 扫违反，写 violations.jsonl，通知用户。

时机：Agent 响应完成后。
输入：stdin JSON payload，含 agent_response + session_id。
输出：stderr 通知，violations.jsonl 写入。

检测两层：
1. 工程层 violation_checks（如 chinese_plain / evidence + session_state）
2. 关键词层 violation_keywords（兜底）
"""

from __future__ import annotations

import json
import sys
import time

from karma import session_state
from karma.checks import run_checks
from karma.sticky import StickyConfigError, load
from karma.violations import Violation, append, detect


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"karma post_response: 输入 JSON 解析失败 ({e})", file=sys.stderr)
        return 1
    response = payload.get("agent_response", "")
    session_id = payload.get("session_id", "") or "default"

    try:
        sticky_list = load()
    except StickyConfigError as e:
        print(f"karma: {e}", file=sys.stderr)
        return 0

    if not sticky_list or not response:
        return 0

    state = session_state.load(session_id)

    # 工程层 violation_checks
    check_hits = []
    for s in sticky_list:
        if not s.violation_checks:
            continue
        hits = run_checks(
            s.violation_checks,
            response=response,
            session_state=state,
            sticky_id=s.id,
        )
        check_hits.extend(hits)

    # 关键词层
    keyword_violations = detect(response, sticky_list, session_id=session_id)

    if not check_hits and not keyword_violations:
        return 0

    # 写入 + 通知
    all_records: list[Violation] = []
    for h in check_hits:
        all_records.append(Violation(
            ts=int(time.time()),
            session_id=session_id,
            sticky_id=h.sticky_id,
            trigger=h.trigger,
            snippet=h.snippet,
        ))
    # 去重：工程层已命中的 sticky_id 不再加关键词记录（避免重复）
    seen_ids = {h.sticky_id for h in check_hits}
    for v in keyword_violations:
        if v.sticky_id not in seen_ids:
            all_records.append(v)

    if all_records:
        append(all_records)

    # stderr 通知用户
    for h in check_hits:
        print(
            f"⚠️ karma: Agent 违反 {h.sticky_id!r} — {h.trigger}",
            file=sys.stderr,
        )
        if h.suggested_fix:
            print(f"   建议：{h.suggested_fix}", file=sys.stderr)
    for v in keyword_violations:
        if v.sticky_id in seen_ids:
            continue
        print(
            f"⚠️ karma: Agent 触发关键词 {v.sticky_id!r} (词 {v.trigger!r})",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
