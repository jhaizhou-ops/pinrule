"""violation_check 函数注册表。

每个 check 函数签名：
    def check(*, tool_name, tool_input, response, session_state, **_) -> CheckHit | None

返回 None = 无违反；CheckHit = 违反详情。

sticky.yaml 的 violation_checks 字段值对应 REGISTRY 的 key。
"""

from __future__ import annotations

from pinrule.checks._types import CheckFn, CheckHit  # 公共类型，子模块也直接从这里 import
from pinrule.checks import (
    bypass_pinrule,
    chinese_plain,
    evidence,
    keep_pushing,
    long_term,
    non_blocking,
    read_first,
    testset,
)

__all__ = ["CheckHit", "CheckFn", "REGISTRY", "run_checks"]


REGISTRY: dict[str, CheckFn] = {
    "long_term_fundamental": long_term.check,
    "non_blocking_parallel": non_blocking.check,
    "chinese_plain_no_jargon": chinese_plain.check,
    "loud_failure_with_evidence": evidence.check,
    "no_testset_no_future_leakage": testset.check,
    "read_before_write": read_first.check,
    "keep_pushing_no_stop": keep_pushing.check,
    "bypass_pinrule_detection": bypass_pinrule.check,
}


def run_checks(
    check_names: tuple[str, ...] | list[str],
    *,
    tool_name: str = "",
    tool_input: dict | None = None,
    response: str = "",
    user_prompt: str = "",
    session_state=None,
    rule_id: str = "",
) -> list[CheckHit]:
    """跑一组 check 函数，返回所有命中。

    缺失的 check 名静默跳过（防 rules.yaml 写错名 deny 所有 tool）。
    check 函数自己崩了静默吞错（不阻塞 hook），但 `PINRULE_DEBUG=1` 时往
    stderr 打 traceback 让用户能调试自定义 check / 内部 bug。
    """
    import os
    import sys
    import traceback as _tb
    debug = bool(os.environ.get("PINRULE_DEBUG"))

    hits: list[CheckHit] = []
    for name in check_names:
        fn = REGISTRY.get(name)
        if fn is None:
            if debug:
                print(f"pinrule[debug]: 跳过未知 check {name!r}", file=sys.stderr)
            continue
        try:
            hit = fn(
                tool_name=tool_name,
                tool_input=tool_input or {},
                response=response,
                user_prompt=user_prompt,
                session_state=session_state,
                rule_id=rule_id,
            )
        except Exception as e:
            # check 函数自己崩了不该阻塞 hook（fail open）
            if debug:
                print(
                    f"pinrule[debug]: check {name!r} 抛异常 {type(e).__name__}: {e}\n"
                    f"{_tb.format_exc()}",
                    file=sys.stderr,
                )
            continue
        if hit:
            hits.append(hit)
    return hits
