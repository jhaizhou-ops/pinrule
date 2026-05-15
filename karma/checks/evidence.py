"""#4 loud-failure-with-evidence — 完成要有证据。

检测的行为模式（post_response + session_state）：
1. response 含完成词（完成/搞定/done/fix了）但 session 最近无测试通过证据
2. response 用「应该」「可能」做硬声明 + 没测试证据
3. 同时也兼顾 pre_tool_use git commit 前查证据（独立 hook 已能拦截）
"""

from __future__ import annotations

import re

from karma.checks._types import CheckHit
from karma.i18n import tr

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
# conventional commit 前缀 — 非代码 commit 不需要测试证据
# docs/chore/style/refactor 等不改业务行为，不该被 evidence check 拦
# v0.4.14：放宽匹配让 heredoc / $(cat <<EOF\nchore: ...) 包裹也识别（不要求紧邻引号）
_NON_CODE_COMMIT_PREFIX_RE = re.compile(
    r"""git\s+commit[\s\S]*?(?:^|[\s'"\n])(docs|chore|style|build|ci|test|refactor)\s*"""
    r"""(?:\([^)]*\))?\s*:""",
    re.IGNORECASE,
)
# v0.4.14：链式 chained 测试命令（pytest && git commit 类） — 用户在同一 Bash
# 调用里先跑测试再 commit，pre_tool_use 时 pytest 还没执行 has_recent_test=False
# 误拦。strip 后命令骨架含测试命令 → 视为「即时证据」豁免。
_CHAINED_TEST_RE = re.compile(
    r"\b(pytest|npm\s+test|jest|cargo\s+test|go\s+test|mvn\s+test|gradle\s+test|"
    r"pnpm\s+test|yarn\s+test|tox)\b",
    re.IGNORECASE,
)
# v0.4.22：pytest 假证据 flag — 跑了 pytest 但没跑测试用例。v0.4.14 过宽漏拦。
# --collect-only / --no-collect-only / --co 都是不跑 case 模式。
_FAKE_TEST_FLAG_RE = re.compile(
    r"--collect-only|--no-collect-only|--co\b|--setup-only|--setup-plan|"
    r"--fixtures-per-test|--help|-h\b|--version|-V\b",
    re.IGNORECASE,
)


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

    has_recent_test = bool(session_state and session_state.has_recent_test_pass())

    # === pre_tool_use 场景: git commit 前 ===
    if tool_name == "Bash":
        cmd = (tool_input or {}).get("command", "") or ""
        if _GIT_COMMIT_RE.search(cmd) and not has_recent_test:
            # 豁免 1：conventional commit 非代码类型（docs/chore/style 等）
            if _NON_CODE_COMMIT_PREFIX_RE.search(cmd):
                return None
            # 豁免 2（v0.4.14）：cmd 同行含 chained 测试命令（pytest && git commit）—
            # 用户在一个 Bash 调用里先测后 commit 是合法 workflow。strip 引号字面后
            # 扫骨架，避免 commit message 里字面提到 pytest 误豁免。
            # v0.4.22：但要排除 pytest --collect-only / --help 等假证据 flag。
            from karma.checks.common import strip_shell_quoted_literals
            cmd_stripped = strip_shell_quoted_literals(cmd)
            if _CHAINED_TEST_RE.search(cmd_stripped) and not _FAKE_TEST_FLAG_RE.search(cmd_stripped):
                return None
            return CheckHit(
                rule_id=_STICKY_ID,
                trigger=tr("check.evidence.commit.trigger"),
                trigger_key="check.evidence.commit.trigger",
                snippet=cmd[:200],
                suggested_fix=tr("check.evidence.commit.fix"),
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
                    rule_id=_STICKY_ID,
                    trigger=tr("check.evidence.completion.trigger", word=m_done.group()),
                    trigger_key="check.evidence.completion.trigger",
                    snippet=response[max(0, m_done.start()-30): m_done.end()+50],
                    suggested_fix=tr("check.evidence.completion.fix"),
                )
            break  # 命中一次足够
        for m_weak in _WEAK_CLAIM_RE.finditer(response):
            if not _in_code_task_context(response, m_weak):
                continue
            if not has_recent_test:
                return CheckHit(
                    rule_id=_STICKY_ID,
                    trigger=tr("check.evidence.weak_claim.trigger", word=m_weak.group()),
                    trigger_key="check.evidence.weak_claim.trigger",
                    snippet=response[max(0, m_weak.start()-30): m_weak.end()+50],
                    suggested_fix=tr("check.evidence.weak_claim.fix"),
                )
            break

    return None
