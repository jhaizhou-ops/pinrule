"""#4 loud-failure-with-evidence — 完成要有证据。

检测的行为模式（post_response + session_state）：
1. response 含完成词（完成/搞定/done/fix了）但 session 最近无测试通过证据
2. response 用「应该」「可能」做硬声明 + 没测试证据
3. 同时也兼顾 pre_tool_use git commit 前查证据（独立 hook 已能拦截）
"""

from __future__ import annotations

import re

_STICKY_ID = "loud-failure-with-evidence"

_COMPLETION_RE = re.compile(
    r"(完成了?|搞定了?|搞好了|做完了?|fix\s*了?|fixed|done\b|all set|搞好啦|修复完成|搞好了)",
    re.IGNORECASE,
)
_WEAK_CLAIM_RE = re.compile(
    r"(应该可以|应该没问题|应该是\w{0,3}的?|大概率|我猜\w{0,2}|可能可以|应该能)",
)
# pre_tool_use git commit 前的检查（共用此 check）
_GIT_COMMIT_RE = re.compile(r"\bgit\s+commit\b", re.IGNORECASE)


def check(
    *,
    tool_name: str = "",
    tool_input: dict | None = None,
    response: str = "",
    session_state=None,
    **_,
):
    from karma.checks import CheckHit

    has_recent_test = bool(session_state and session_state.has_recent_test_pass())

    # === pre_tool_use 场景: git commit 前 ===
    if tool_name == "Bash":
        cmd = (tool_input or {}).get("command", "") or ""
        if _GIT_COMMIT_RE.search(cmd) and not has_recent_test:
            return CheckHit(
                sticky_id=_STICKY_ID,
                trigger="git commit 前最近 session 内无测试通过证据",
                snippet=cmd[:200],
                suggested_fix="commit 前跑测试（pytest / npm test 等）确认通过，再 commit。",
            )

    # === post_response 场景 ===
    if response and response.strip():
        m_done = _COMPLETION_RE.search(response)
        if m_done and not has_recent_test:
            return CheckHit(
                sticky_id=_STICKY_ID,
                trigger=f"声称{m_done.group()!r} 但 session 最近无测试通过证据",
                snippet=response[max(0, m_done.start()-30): m_done.end()+50],
                suggested_fix="给出测试证据 — 跑 pytest / build 看到 PASS 后再说完成。",
            )
        m_weak = _WEAK_CLAIM_RE.search(response)
        if m_weak and not has_recent_test:
            return CheckHit(
                sticky_id=_STICKY_ID,
                trigger=f"用『{m_weak.group()}』做硬声明且无测试证据",
                snippet=response[max(0, m_weak.start()-30): m_weak.end()+50],
                suggested_fix="不要用『应该』掩盖不确定。明说不知道，或者跑测试确认。",
            )

    return None
