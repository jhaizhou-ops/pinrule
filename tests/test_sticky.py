"""sticky.json 加载 + schema 验证 + 注入渲染。"""

from __future__ import annotations

from pathlib import Path

import pytest
import json

from pinrule.rule import (
    HARD_MAX,
    Rule,
    RuleConfigError,
    format_for_injection,
    load,
)


def _write_yaml(tmp_path: Path, items: list[dict]) -> Path:
    p = tmp_path / "sticky.json"
    p.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def test_load_missing_file_returns_empty(tmp_path: Path) -> None:
    """文件不存在返回 [] — hook 静默 passthrough。"""
    assert load(tmp_path / "no-such.yaml") == []


def test_load_valid_minimal(tmp_path: Path) -> None:
    p = _write_yaml(tmp_path, [
        {"id": "test-rule", "preference": "do X not Y"},
    ])
    sticky = load(p)
    assert len(sticky) == 1
    assert sticky[0].id == "test-rule"
    assert sticky[0].preference == "do X not Y"
    assert sticky[0].violation_keywords == ()


def test_load_with_violation_keywords(tmp_path: Path) -> None:
    p = _write_yaml(tmp_path, [
        {
            "id": "long-term",
            "preference": "用长期方案",
            "violation_keywords": ["先打个补丁", "硬编码"],
        },
    ])
    sticky = load(p)
    assert sticky[0].violation_keywords == ("先打个补丁", "硬编码")


def test_load_rejects_invalid_id(tmp_path: Path) -> None:
    """id 必须是 kebab-case slug。"""
    p = _write_yaml(tmp_path, [
        {"id": "Bad_ID", "preference": "x"},
    ])
    with pytest.raises(RuleConfigError, match="id="):
        load(p)


def test_load_rejects_duplicate_id(tmp_path: Path) -> None:
    p = _write_yaml(tmp_path, [
        {"id": "rule-a", "preference": "x"},
        {"id": "rule-a", "preference": "y"},
    ])
    with pytest.raises(RuleConfigError, match="重复 id"):
        load(p)


def test_load_rejects_missing_preference(tmp_path: Path) -> None:
    p = _write_yaml(tmp_path, [
        {"id": "rule-a"},
    ])
    with pytest.raises(RuleConfigError, match="缺 preference"):
        load(p)


def test_load_rejects_over_hard_max(tmp_path: Path) -> None:
    """超过 HARD_MAX 拒绝加载（fail loud）。"""
    items = [{"id": f"r-{i}", "preference": f"p{i}"} for i in range(HARD_MAX + 1)]
    p = _write_yaml(tmp_path, items)
    with pytest.raises(RuleConfigError, match="硬上限"):
        load(p)


def test_load_real_example() -> None:
    """data/rules.dev.example.json 必须能加载，且是 7 条种子 sticky（开发场景预设）。"""
    repo_root = Path(__file__).resolve().parents[1]
    example = repo_root / "data" / "rules.dev.example.json"
    sticky = load(example)
    assert len(sticky) == 7
    ids = {s.id for s in sticky}
    expected = {
        "long-term-fundamental",
        "non-blocking-parallel",
        # v0.16.8: EN 模板 chinese-plain → plain-language (英文化 "reduce jargon,
        # first-use example" 等价 rule, 不再要求英文用户 remove). ZH 模板仍叫 chinese-plain.
        "plain-language-no-jargon",
        "loud-failure-with-evidence",
        "no-testset-no-future-leakage",
        "deep-fix-not-bypass",  # M4 末加 — 监管 Agent 绕开 pinrule 的元层规则
        "read-before-write",
    }
    assert ids == expected
    # 每条原则上都有对应 violation_checks，例外见下
    # plain-language-no-jargon (v0.16.8) 工程监督层用户授权撤掉 —
    # 保留 preference 文本提醒，不强制工程检测 (memory feedback-language-preference-no-engine)
    soft_only = {"plain-language-no-jargon"}
    for s in sticky:
        if s.id in soft_only:
            continue
        assert s.violation_checks, f"{s.id} 缺 violation_checks"


def test_load_real_minimal_example() -> None:
    """data/rules.dev.minimal.example.json 5 条跨用户中性核心 — 砍场景化两条。

    评审 C Agent 痛点：默认 7 条含 chinese-plain（中文用户偏好）+
    no-testset（ML 场景）违反 CLAUDE.md「不针对当前用户作弊」原则。这个
    精简版让英文母语 / 非 ML 用户拿到中性默认。
    """
    repo_root = Path(__file__).resolve().parents[1]
    example = repo_root / "data" / "rules.dev.minimal.example.json"
    sticky = load(example)
    assert len(sticky) == 5
    ids = {s.id for s in sticky}
    expected = {
        "long-term-fundamental",
        "non-blocking-parallel",
        "loud-failure-with-evidence",
        "deep-fix-not-bypass",
        "read-before-write",
    }
    assert ids == expected
    # chinese-plain 和 no-testset-no-future-leakage 不在精简版
    assert "chinese-plain-no-jargon" not in ids
    assert "no-testset-no-future-leakage" not in ids
    # non-blocking-parallel 必须设 force_block_exempt: true（避免语义自相矛盾）
    nb = next(s for s in sticky if s.id == "non-blocking-parallel")
    assert nb.force_block_exempt is True


def test_format_for_injection_basic() -> None:
    sticky = [
        Rule(id="r1", preference="方向 1\n  细节"),
        Rule(id="r2", preference="方向 2"),
    ]
    out = format_for_injection(sticky)
    # 2026-05-15 重写：合作默契语气取代「规则系统」包装
    assert "[pinrule" in out
    assert "默契" in out  # 头部合作语气关键字
    assert "1. [r1] 方向 1" in out
    assert "   细节" in out  # 多行缩进
    assert "2. [r2] 方向 2" in out


def test_format_for_injection_marks_recent_violation() -> None:
    sticky = [Rule(id="r1", preference="方向 1")]
    out = format_for_injection(sticky, recent_violations={"r1": 12345})
    # 2026-05-15 重写：合作回顾标记取代红警示词 ⚠️ / 「上次违反」
    assert "偏离" in out
    assert "对齐" in out  # 合作回顾语气关键字


def test_format_for_injection_empty_list() -> None:
    assert format_for_injection([]) == ""


# -------- v0.9.0 format_anchor_only tests --------


def test_format_anchor_only_basic() -> None:
    """v0.13.0: anchor 只列 violated rule (id + 第一行 preference, 无 marker 自动加)."""
    from pinrule.rule import format_anchor_only
    rules = [
        Rule(id="r1", preference="方向 1 的核心一句\n  详细说明 (anchor 不该含此行)"),
        Rule(id="r2", preference="方向 2 的核心"),
    ]
    # v0.13.0: 必须传 violated_rule_ids 才有 anchor 输出
    out = format_anchor_only(rules, violated_rule_ids={"r1", "r2"})
    assert "[pinrule" in out
    assert "精简版" in out  # anchor 头部含「精简版」说明
    # 含规则 id (跟 format_for_injection 不同 — anchor 必须带 id)
    assert "[r1]" in out
    assert "[r2]" in out
    # 第一行 preference 进 anchor
    assert "方向 1 的核心一句" in out
    assert "方向 2 的核心" in out
    # 详细说明**不**进 anchor (精简 anchor 的核心特点)
    assert "详细说明" not in out


def test_format_anchor_only_marks_recent_violation() -> None:
    """v0.13.0: anchor 里全是 violated rule 自动加 drift marker."""
    from pinrule.rule import format_anchor_only
    rules = [Rule(id="r1", preference="方向 1")]
    out = format_anchor_only(rules, violated_rule_ids={"r1": 12345})
    assert "偏离" in out
    assert "对齐" in out


def test_format_anchor_only_token_savings_vs_full() -> None:
    """v0.9.0 设计意图: anchor 精简版应比 format_for_injection 全量版 token 少很多。"""
    from pinrule.rule import format_anchor_only
    rules = [
        Rule(id=f"r{i}", preference=f"方向 {i} 的核心\n   详细说明 1\n   详细说明 2\n   详细说明 3")
        for i in range(10)
    ]
    anchor = format_anchor_only(rules)
    full = format_for_injection(rules)
    # 精简版字符数应该至少节省 30% (实际 v0.9.0 设计预期节省 ~80%)
    assert len(anchor) < len(full) * 0.7, f"anchor 应远短于 full: {len(anchor)} vs {len(full)}"


def test_format_anchor_only_empty_list() -> None:
    """空规则列表 → 空 anchor。"""
    from pinrule.rule import format_anchor_only
    assert format_anchor_only([]) == ""


# -------- v0.6.0 deletion-lock tests --------

def test_v0600_pinrule_sticky_module_removed():
    """v0.6.0: import pinrule.sticky 应该抛 ModuleNotFoundError (整个 shim module 删了)."""
    import pytest
    with pytest.raises(ModuleNotFoundError):
        import pinrule.sticky  # noqa: F401


def test_v0600_violation_sticky_id_attribute_removed():
    """v0.6.0: Violation.sticky_id @property 删了 (用 .rule_id)."""
    import pytest
    from pinrule.violations import Violation
    v = Violation(ts=1, session_id="s", rule_id="r", trigger="x", snippet=".", turn=1)
    assert v.rule_id == "r"  # 新属性仍工作
    with pytest.raises(AttributeError):
        v.sticky_id  # noqa: B018


def test_v0600_check_hit_sticky_id_attribute_removed():
    """v0.6.0: CheckHit.sticky_id @property 删了 (用 .rule_id)."""
    import pytest
    from pinrule.checks._types import CheckHit
    h = CheckHit(rule_id="r", trigger="x", snippet=".", suggested_fix="y")
    assert h.rule_id == "r"
    with pytest.raises(AttributeError):
        h.sticky_id  # noqa: B018


def test_v0600_rule_module_aliases_removed():
    """v0.6.0: pinrule.rule 里 Sticky / MAX_STICKY / StickyConfigError aliases 删了."""
    import pinrule.rule as r
    assert not hasattr(r, "Sticky")
    assert not hasattr(r, "MAX_STICKY")
    assert not hasattr(r, "StickyConfigError")


def test_v0600_pinrule_sticky_cli_returns_unknown():
    """v0.6.0: `pinrule sticky` CLI 子命令删了, 返 1 带「你是不是想用 pinrule rule」hint."""
    import subprocess
    import sys
    # Windows default text= mode reads child output with cp1252, can't decode
    # the deprecation message's Chinese chars → stderr=None. Force UTF-8 to
    # match the child's force_utf8_stdio() output encoding (v0.16.18 fix).
    result = subprocess.run(
        [sys.executable, "-m", "pinrule.cli", "sticky", "list"],
        capture_output=True, text=True, encoding="utf-8"
    )
    assert result.returncode == 1
    assert "pinrule rule" in result.stderr
