"""rule.format_for_injection / format_anchor_only 直接单测。

覆盖：
- 空规则列表 → 返回 ""（不注入任何文本）
- 单条规则 → 编号正确、preference 完整出现
- 多条规则 → 全部按编号顺序
- recent_violations 标记 → 偏离 marker 出现在违反过的规则行
- 未违反规则 → 无 marker
- 多行 preference → 续行缩进 3 空格（format_for_injection 专属）
- format_anchor_only → 只出首行 + rule id
- anchor 无多行缩进（只注首行 preference）
- zh locale 头部含中文（KARMA_LOCALE=zh 环境下）
"""

from __future__ import annotations

import pytest

from karma.rule import Rule, format_anchor_only, format_for_injection


# ---------------------------------------------------------------------------
# 辅助工厂
# ---------------------------------------------------------------------------

def _r(rid: str, pref: str, **kw) -> Rule:
    return Rule(id=rid, preference=pref, **kw)


# ---------------------------------------------------------------------------
# 1. 空规则列表 → ""
# ---------------------------------------------------------------------------

def test_format_injection_empty_rules():
    assert format_for_injection([]) == ""


def test_format_anchor_empty_rules():
    assert format_anchor_only([]) == ""


# ---------------------------------------------------------------------------
# 2. 单条规则：编号 + preference
# ---------------------------------------------------------------------------

def test_format_injection_single_rule():
    rules = [_r("my-rule", "保持长期方案")]
    out = format_for_injection(rules)
    assert "1. 保持长期方案" in out
    assert "my-rule" not in out  # 完整注入不显示 id（只 anchor 显示）


def test_format_anchor_single_rule():
    rules = [_r("my-rule", "保持长期方案")]
    out = format_anchor_only(rules)
    assert "[my-rule]" in out
    assert "保持长期方案" in out


# ---------------------------------------------------------------------------
# 3. 多条规则：编号 1..N 全部出现
# ---------------------------------------------------------------------------

def test_format_injection_multiple_rules_numbered():
    rules = [
        _r("rule-a", "方向 A"),
        _r("rule-b", "方向 B"),
        _r("rule-c", "方向 C"),
    ]
    out = format_for_injection(rules)
    assert "1. 方向 A" in out
    assert "2. 方向 B" in out
    assert "3. 方向 C" in out


def test_format_anchor_multiple_rules():
    rules = [
        _r("rule-a", "方向 A"),
        _r("rule-b", "方向 B"),
    ]
    out = format_anchor_only(rules)
    assert "1. [rule-a]" in out
    assert "2. [rule-b]" in out


# ---------------------------------------------------------------------------
# 4. recent_violations：违反过的规则加偏离 marker
# ---------------------------------------------------------------------------

def test_format_injection_drift_marker_on_violated_rule():
    rules = [
        _r("r1", "保持 A"),
        _r("r2", "保持 B"),
    ]
    recent = {"r1": 1234567890}  # r1 违反过
    out = format_for_injection(rules, recent_violations=recent)
    # r1 对应行应含偏离 marker，r2 不含
    lines = out.splitlines()
    r1_line = next(l for l in lines if "保持 A" in l)
    r2_line = next(l for l in lines if "保持 B" in l)
    # marker 在 zh locale 下含「偏离」字眼
    assert "偏离" in r1_line or "〔" in r1_line, "违反规则行应含偏离 marker"
    assert "偏离" not in r2_line and "〔" not in r2_line, "未违反规则行不含 marker"


def test_format_anchor_drift_marker_on_violated_rule():
    rules = [_r("r1", "保持 A"), _r("r2", "保持 B")]
    out = format_anchor_only(rules, recent_violations={"r1": 1})
    lines = out.splitlines()
    r1_line = next(l for l in lines if "[r1]" in l)
    r2_line = next(l for l in lines if "[r2]" in l)
    assert "〔" in r1_line or "偏离" in r1_line
    assert "〔" not in r2_line and "偏离" not in r2_line


# ---------------------------------------------------------------------------
# 5. recent_violations=None → 等价于 {}（不加 marker）
# ---------------------------------------------------------------------------

def test_format_injection_none_recent_violations_no_marker():
    rules = [_r("r1", "保持 A")]
    out = format_for_injection(rules, recent_violations=None)
    assert "偏离" not in out
    assert "〔" not in out


def test_format_anchor_none_recent_violations_no_marker():
    rules = [_r("r1", "保持 A")]
    out = format_anchor_only(rules, recent_violations=None)
    assert "〔" not in out


# ---------------------------------------------------------------------------
# 6. 多行 preference → 续行用 3 空格缩进（只 format_for_injection）
# ---------------------------------------------------------------------------

def test_format_injection_multiline_preference_indented():
    pref = "第一行核心方向\n第二行详细说明\n第三行补充"
    rules = [_r("r1", pref)]
    out = format_for_injection(rules)
    lines = out.splitlines()
    # 首行：1. 第一行核心方向
    first = next(l for l in lines if "第一行核心方向" in l)
    assert first.startswith("1. ")
    # 续行：以 3 空格开头
    second = next(l for l in lines if "第二行详细说明" in l)
    assert second.startswith("   ")
    third = next(l for l in lines if "第三行补充" in l)
    assert third.startswith("   ")


def test_format_anchor_multiline_preference_only_first_line():
    """anchor 只取 preference 首行，后续行不出现。"""
    pref = "首行方向\n不该出现的后续行"
    rules = [_r("r1", pref)]
    out = format_anchor_only(rules)
    assert "首行方向" in out
    assert "不该出现的后续行" not in out


# ---------------------------------------------------------------------------
# 7. zh locale 下头部含中文关键词
# ---------------------------------------------------------------------------

def test_format_injection_zh_header_present():
    """KARMA_LOCALE=zh 环境下头部含「默契」等中文标识词。"""
    rules = [_r("r1", "保持 A")]
    out = format_for_injection(rules)
    # zh locale：inject.header.title = "[karma — 你跟用户的长期默契]"
    assert "karma" in out
    assert "默契" in out


def test_format_anchor_zh_header_present():
    rules = [_r("r1", "保持 A")]
    out = format_anchor_only(rules)
    assert "karma" in out


# ---------------------------------------------------------------------------
# 8. 注入文本以换行结尾（便于拼接其他 context）
# ---------------------------------------------------------------------------

def test_format_injection_ends_with_newline():
    rules = [_r("r1", "x")]
    out = format_for_injection(rules)
    assert out.endswith("\n")


def test_format_anchor_ends_with_newline():
    rules = [_r("r1", "x")]
    out = format_anchor_only(rules)
    assert out.endswith("\n")


# ---------------------------------------------------------------------------
# 9. 10 条规则 → 全部编号到 10
# ---------------------------------------------------------------------------

def test_format_injection_ten_rules_all_numbered():
    rules = [_r(f"rule-{i:02d}", f"方向 {i}") for i in range(1, 11)]
    out = format_for_injection(rules)
    for i in range(1, 11):
        assert f"{i}. 方向 {i}" in out


# ---------------------------------------------------------------------------
# 10. force_block_exempt 字段不影响格式（格式只看 id + preference）
# ---------------------------------------------------------------------------

def test_format_injection_force_block_exempt_rule_included_normally():
    rules = [_r("r1", "不受 force_block 惩罚的规则", force_block_exempt=True)]
    out = format_for_injection(rules)
    assert "1. 不受 force_block 惩罚的规则" in out
