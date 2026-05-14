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
# 「代码任务行为词」— 完成词 / weak claim 必须在 40 字窗口内含至少一个，才算
# 「声称代码任务完成」而非日常闲聊「这个应该可以接受」之类
_ACTION_CONTEXT_RE = re.compile(
    r"(?:测试|test|代码|code|修复|fix|实现|实施|build|部署|deploy|commit|merge|"
    r"pull\s*request|\bPR\b|功能|feature|bug|崩|跑通|过了|跑过|装好|实施完)",
    re.IGNORECASE,
)
_CONTEXT_WINDOW = 40
# pre_tool_use git commit 前的检查（共用此 check）
_GIT_COMMIT_RE = re.compile(r"\bgit\s+commit\b", re.IGNORECASE)


def _in_code_task_context(response: str, match) -> bool:
    """完成词 / weak claim 周围 40 字内是否含代码任务行为词。"""
    window_start = max(0, match.start() - _CONTEXT_WINDOW)
    window_end = min(len(response), match.end() + _CONTEXT_WINDOW)
    window = response[window_start:window_end]
    return bool(_ACTION_CONTEXT_RE.search(window))


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
    # 完成词 / weak claim 必须出现在「代码任务行为词」附近 40 字内才算违反
    # 避免日常闲聊「这个方向应该可以」「先告一段落了」等被误判
    if response and response.strip():
        for m_done in _COMPLETION_RE.finditer(response):
            if not _in_code_task_context(response, m_done):
                continue
            if not has_recent_test:
                return CheckHit(
                    sticky_id=_STICKY_ID,
                    trigger=f"声称{m_done.group()!r} 但 session 最近无测试通过证据",
                    snippet=response[max(0, m_done.start()-30): m_done.end()+50],
                    suggested_fix="给出测试证据 — 跑 pytest / build 看到 PASS 后再说完成。",
                )
            break  # 命中一次足够
        for m_weak in _WEAK_CLAIM_RE.finditer(response):
            if not _in_code_task_context(response, m_weak):
                continue
            if not has_recent_test:
                return CheckHit(
                    sticky_id=_STICKY_ID,
                    trigger=f"用『{m_weak.group()}』做硬声明且无测试证据",
                    snippet=response[max(0, m_weak.start()-30): m_weak.end()+50],
                    suggested_fix="不要用『应该』掩盖不确定。明说不知道，或者跑测试确认。",
                )
            break

    return None
