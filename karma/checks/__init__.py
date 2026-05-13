"""violation_check 函数注册表。

每个 check 函数签名：
    def check(*, tool_name, tool_input, response, session_state, **_) -> CheckHit | None

返回 None = 无违反；CheckHit = 违反详情。

sticky.yaml 的 violation_checks 字段值对应 REGISTRY 的 key。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from karma.checks import (
    chinese_plain,
    evidence,
    long_term,
    non_blocking,
    read_first,
    testset,
)


@dataclass(frozen=True)
class CheckHit:
    """violation_check 函数的返回 — 一次违反命中。"""

    sticky_id: str
    trigger: str          # 描述什么触发的（"Bash sleep 30"）
    snippet: str          # 上下文片段
    suggested_fix: str    # 给 Agent 看的修复建议


class CheckFn(Protocol):
    def __call__(self, **kwargs) -> CheckHit | None: ...


REGISTRY: dict[str, CheckFn] = {
    "long_term_fundamental": long_term.check,
    "non_blocking_parallel": non_blocking.check,
    "chinese_plain_no_jargon": chinese_plain.check,
    "loud_failure_with_evidence": evidence.check,
    "no_testset_no_future_leakage": testset.check,
    "read_before_write": read_first.check,
}


def run_checks(
    check_names: tuple[str, ...] | list[str],
    *,
    tool_name: str = "",
    tool_input: dict | None = None,
    response: str = "",
    session_state=None,
    sticky_id: str = "",
) -> list[CheckHit]:
    """跑一组 check 函数，返回所有命中。

    缺失的 check 名静默跳过（防 sticky.yaml 写错名 deny 所有 tool）。
    """
    hits: list[CheckHit] = []
    for name in check_names:
        fn = REGISTRY.get(name)
        if fn is None:
            continue
        try:
            hit = fn(
                tool_name=tool_name,
                tool_input=tool_input or {},
                response=response,
                session_state=session_state,
                sticky_id=sticky_id,
            )
        except Exception:
            # check 函数自己崩了不该阻塞 hook
            continue
        if hit:
            hits.append(hit)
    return hits
