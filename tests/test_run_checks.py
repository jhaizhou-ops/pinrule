"""run_checks() 调度逻辑单测。

覆盖：
- 未知 check 名 → 静默跳过，不崩
- check 函数抛异常 → fail open（不崩、不命中）
- KARMA_DEBUG=1 → 两种情况都往 stderr 打诊断
- 多命中按顺序返回
- check_names 为空 → 立即返回 []
- tool_input=None → 默认 {}（不传 None 进 check 函数）
"""

from __future__ import annotations

import os
import sys

import pytest

from karma.checks import REGISTRY, CheckHit, run_checks
from karma.checks._types import CheckFn


# ---------------------------------------------------------------------------
# 辅助 fake checks
# ---------------------------------------------------------------------------

def _always_hit(**kwargs) -> CheckHit:
    return CheckHit(rule_id="r1", trigger="fake trigger", snippet="", suggested_fix="fix")


def _always_miss(**kwargs) -> CheckHit | None:
    return None


def _raises(**kwargs) -> CheckHit:
    raise RuntimeError("check 内部崩了")


# ---------------------------------------------------------------------------
# 1. 空 check 列表 → 立即 []
# ---------------------------------------------------------------------------

def test_run_checks_empty_list_returns_empty():
    result = run_checks([])
    assert result == []


# ---------------------------------------------------------------------------
# 2. 未知 check 名 → 静默跳过
# ---------------------------------------------------------------------------

def test_run_checks_unknown_name_silently_skipped(monkeypatch):
    monkeypatch.setitem(os.environ, "KARMA_DEBUG", "")
    result = run_checks(["non_existent_check_xyz"])
    assert result == []


def test_run_checks_unknown_name_debug_writes_stderr(monkeypatch, capsys):
    monkeypatch.setitem(os.environ, "KARMA_DEBUG", "1")
    run_checks(["totally_unknown_check"])
    err = capsys.readouterr().err
    assert "totally_unknown_check" in err


# ---------------------------------------------------------------------------
# 3. check 函数抛异常 → fail open（不崩、结果里不含该条）
# ---------------------------------------------------------------------------

def test_run_checks_exception_in_check_is_swallowed(monkeypatch):
    monkeypatch.setitem(REGISTRY, "_test_raises", _raises)
    monkeypatch.setitem(os.environ, "KARMA_DEBUG", "")
    result = run_checks(["_test_raises"])
    assert result == []


def test_run_checks_exception_debug_writes_stderr(monkeypatch, capsys):
    monkeypatch.setitem(REGISTRY, "_test_raises_dbg", _raises)
    monkeypatch.setitem(os.environ, "KARMA_DEBUG", "1")
    run_checks(["_test_raises_dbg"])
    err = capsys.readouterr().err
    assert "_test_raises_dbg" in err
    assert "RuntimeError" in err


# ---------------------------------------------------------------------------
# 4. 单命中返回单元素列表
# ---------------------------------------------------------------------------

def test_run_checks_single_hit(monkeypatch):
    monkeypatch.setitem(REGISTRY, "_test_hit", _always_hit)
    result = run_checks(["_test_hit"])
    assert len(result) == 1
    assert result[0].rule_id == "r1"


# ---------------------------------------------------------------------------
# 5. 多命中按传入顺序返回
# ---------------------------------------------------------------------------

def _make_hit(rule_id: str):
    def _fn(**kwargs) -> CheckHit:
        return CheckHit(rule_id=rule_id, trigger=f"t_{rule_id}", snippet="", suggested_fix="")
    return _fn


def test_run_checks_multiple_hits_in_order(monkeypatch):
    monkeypatch.setitem(REGISTRY, "_hit_a", _make_hit("rule-a"))
    monkeypatch.setitem(REGISTRY, "_hit_b", _make_hit("rule-b"))
    result = run_checks(["_hit_a", "_hit_b"])
    assert len(result) == 2
    assert result[0].rule_id == "rule-a"
    assert result[1].rule_id == "rule-b"


# ---------------------------------------------------------------------------
# 6. miss + hit 混合：只返回命中的
# ---------------------------------------------------------------------------

def test_run_checks_mixed_hit_and_miss(monkeypatch):
    monkeypatch.setitem(REGISTRY, "_miss_x", _always_miss)
    monkeypatch.setitem(REGISTRY, "_hit_x", _always_hit)
    result = run_checks(["_miss_x", "_hit_x", "_miss_x"])
    assert len(result) == 1
    assert result[0].rule_id == "r1"


# ---------------------------------------------------------------------------
# 7. tool_input=None → 内部默认 {}，check 不收到 None
# ---------------------------------------------------------------------------

def test_run_checks_none_tool_input_defaults_to_dict(monkeypatch):
    received: list[dict] = []

    def _capture(**kwargs) -> CheckHit | None:
        received.append(kwargs.get("tool_input"))
        return None

    monkeypatch.setitem(REGISTRY, "_capture_input", _capture)
    run_checks(["_capture_input"], tool_input=None)
    assert received == [{}]


# ---------------------------------------------------------------------------
# 8. 异常 check 不影响后续 check 的执行
# ---------------------------------------------------------------------------

def test_run_checks_exception_does_not_block_subsequent_checks(monkeypatch):
    monkeypatch.setitem(REGISTRY, "_crash_first", _raises)
    monkeypatch.setitem(REGISTRY, "_hit_after", _always_hit)
    monkeypatch.setitem(os.environ, "KARMA_DEBUG", "")
    result = run_checks(["_crash_first", "_hit_after"])
    assert len(result) == 1
    assert result[0].rule_id == "r1"


# ---------------------------------------------------------------------------
# 9. 真实内置 check 名都在 REGISTRY 里（注册表完整性）
# ---------------------------------------------------------------------------

_EXPECTED_CHECKS = [
    "long_term_fundamental",
    "non_blocking_parallel",
    "chinese_plain_no_jargon",
    "loud_failure_with_evidence",
    "no_testset_no_future_leakage",
    "read_before_write",
    "keep_pushing_no_stop",
    "bypass_karma_detection",
]


def test_registry_contains_all_builtin_checks():
    for name in _EXPECTED_CHECKS:
        assert name in REGISTRY, f"内置 check {name!r} 不在 REGISTRY"


# ---------------------------------------------------------------------------
# 10. run_checks 透传 kwargs 给 check 函数
# ---------------------------------------------------------------------------

def test_run_checks_passes_kwargs_through(monkeypatch):
    received: dict = {}

    def _record(**kwargs) -> CheckHit | None:
        received.update(kwargs)
        return None

    monkeypatch.setitem(REGISTRY, "_kw_check", _record)
    run_checks(
        ["_kw_check"],
        tool_name="Bash",
        tool_input={"command": "ls"},
        response="hello",
        rule_id="my-rule",
    )
    assert received["tool_name"] == "Bash"
    assert received["tool_input"] == {"command": "ls"}
    assert received["response"] == "hello"
    assert received["rule_id"] == "my-rule"
