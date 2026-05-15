"""sticky.yaml 加载 + schema 验证 + 注入渲染。"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from karma.sticky import (
    HARD_MAX,
    Sticky,
    StickyConfigError,
    format_for_injection,
    load,
)


def _write_yaml(tmp_path: Path, items: list[dict]) -> Path:
    p = tmp_path / "sticky.yaml"
    p.write_text(yaml.safe_dump(items, allow_unicode=True), encoding="utf-8")
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
    with pytest.raises(StickyConfigError, match="id="):
        load(p)


def test_load_rejects_duplicate_id(tmp_path: Path) -> None:
    p = _write_yaml(tmp_path, [
        {"id": "rule-a", "preference": "x"},
        {"id": "rule-a", "preference": "y"},
    ])
    with pytest.raises(StickyConfigError, match="重复 id"):
        load(p)


def test_load_rejects_missing_preference(tmp_path: Path) -> None:
    p = _write_yaml(tmp_path, [
        {"id": "rule-a"},
    ])
    with pytest.raises(StickyConfigError, match="缺 preference"):
        load(p)


def test_load_rejects_over_hard_max(tmp_path: Path) -> None:
    """超过 HARD_MAX 拒绝加载（fail loud）。"""
    items = [{"id": f"r-{i}", "preference": f"p{i}"} for i in range(HARD_MAX + 1)]
    p = _write_yaml(tmp_path, items)
    with pytest.raises(StickyConfigError, match="硬上限"):
        load(p)


def test_load_real_example() -> None:
    """data/sticky.dev.example.yaml 必须能加载，且是 7 条种子 sticky（开发场景预设）。"""
    repo_root = Path(__file__).resolve().parents[1]
    example = repo_root / "data" / "sticky.dev.example.yaml"
    sticky = load(example)
    assert len(sticky) == 7
    ids = {s.id for s in sticky}
    expected = {
        "long-term-fundamental",
        "non-blocking-parallel",
        "chinese-plain-no-jargon",
        "loud-failure-with-evidence",
        "no-testset-no-future-leakage",
        "deep-fix-not-bypass",  # M4 末加 — 监管 Agent 绕开 karma 的元层规则
        "read-before-write",
    }
    assert ids == expected
    # 每条原则上都有对应 violation_checks，例外见下
    # chinese-plain-no-jargon (2026-05-15) 工程监督层用户授权撤掉 —
    # 保留 preference 文本提醒，不强制工程检测（容易执行 + 犯错代价小）
    soft_only = {"chinese-plain-no-jargon"}
    for s in sticky:
        if s.id in soft_only:
            continue
        assert s.violation_checks, f"{s.id} 缺 violation_checks"


def test_load_real_minimal_example() -> None:
    """data/sticky.dev.minimal.example.yaml 5 条真跨用户中性核心 — 砍场景化两条。

    评审 C Agent 真痛点：默认 7 条含 chinese-plain（中文用户偏好）+
    no-testset（ML 场景）违反 CLAUDE.md「不针对当前用户作弊」原则。这个
    精简版让英文母语 / 非 ML 用户拿到中性默认。
    """
    repo_root = Path(__file__).resolve().parents[1]
    example = repo_root / "data" / "sticky.dev.minimal.example.yaml"
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
        Sticky(id="r1", preference="方向 1\n  细节"),
        Sticky(id="r2", preference="方向 2"),
    ]
    out = format_for_injection(sticky)
    # 2026-05-15 重写：合作默契语气取代「规则系统」包装
    assert "[karma" in out
    assert "默契" in out  # 头部合作语气关键字
    assert "1. 方向 1" in out
    assert "   细节" in out  # 多行缩进
    assert "2. 方向 2" in out


def test_format_for_injection_marks_recent_violation() -> None:
    sticky = [Sticky(id="r1", preference="方向 1")]
    out = format_for_injection(sticky, recent_violations={"r1": 12345})
    # 2026-05-15 重写：合作回顾标记取代红警示词 ⚠️ / 「上次违反」
    assert "偏离" in out
    assert "对齐" in out  # 合作回顾语气关键字


def test_format_for_injection_empty_list() -> None:
    assert format_for_injection([]) == ""
