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
    """data/sticky.example.yaml 必须能加载，且是 6 条种子 sticky (M2 精简)。"""
    repo_root = Path(__file__).resolve().parents[1]
    example = repo_root / "data" / "sticky.example.yaml"
    sticky = load(example)
    assert len(sticky) == 6
    ids = {s.id for s in sticky}
    expected = {
        "long-term-fundamental",
        "non-blocking-parallel",
        "chinese-plain-no-jargon",
        "loud-failure-with-evidence",
        "no-testset-no-future-leakage",
        "read-before-write",
    }
    assert ids == expected
    # 每条都有对应 violation_checks
    for s in sticky:
        assert s.violation_checks, f"{s.id} 缺 violation_checks"


def test_format_for_injection_basic() -> None:
    sticky = [
        Sticky(id="r1", preference="方向 1\n  细节"),
        Sticky(id="r2", preference="方向 2"),
    ]
    out = format_for_injection(sticky)
    assert "[karma sticky" in out
    assert "1. 方向 1" in out
    assert "   细节" in out  # 多行缩进
    assert "2. 方向 2" in out


def test_format_for_injection_marks_recent_violation() -> None:
    sticky = [Sticky(id="r1", preference="方向 1")]
    out = format_for_injection(sticky, recent_violations={"r1": 12345})
    assert "⚠️" in out
    assert "上次违反" in out


def test_format_for_injection_empty_list() -> None:
    assert format_for_injection([]) == ""
