"""violations.jsonl 读写 + 违反检测。"""

from __future__ import annotations

from pathlib import Path

from karma.sticky import Sticky
from karma.violations import Violation, append, detect, load_all, recent


def _make_sticky() -> list[Sticky]:
    return [
        Sticky(
            id="long-term",
            preference="用长期方案",
            violation_keywords=("先打个补丁", "硬编码"),
        ),
        Sticky(
            id="chinese-only",
            preference="用中文",
            violation_keywords=("F1", "precision"),
        ),
    ]


def test_detect_finds_violation() -> None:
    response = "让我先打个补丁快速解决"
    out = detect(response, _make_sticky(), session_id="s1", now=1000)
    assert len(out) == 1
    assert out[0].sticky_id == "long-term"
    assert out[0].trigger == "先打个补丁"
    assert "先打个补丁" in out[0].snippet


def test_detect_multiple_stickies() -> None:
    response = "用 F1 看，先硬编码一下"
    out = detect(response, _make_sticky(), now=1000)
    sids = {v.sticky_id for v in out}
    assert sids == {"long-term", "chinese-only"}


def test_detect_same_sticky_multiple_keywords_records_first() -> None:
    """同一 sticky 多关键词命中只记第一个。"""
    response = "先打个补丁，再硬编码一个"
    out = detect(response, _make_sticky(), now=1000)
    assert len(out) == 1
    assert out[0].sticky_id == "long-term"


def test_detect_case_insensitive() -> None:
    response = "用 f1 score"
    out = detect(response, _make_sticky(), now=1000)
    assert len(out) == 1
    assert out[0].sticky_id == "chinese-only"


def test_detect_empty_response() -> None:
    assert detect("", _make_sticky()) == []


def test_detect_no_violation() -> None:
    response = "好的，开始干活了"
    assert detect(response, _make_sticky()) == []


def test_append_and_load_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "violations.jsonl"
    items = [
        Violation(ts=1000, session_id="s1", sticky_id="r1", trigger="x", snippet="..."),
        Violation(ts=2000, session_id="s1", sticky_id="r2", trigger="y", snippet="..."),
    ]
    append(items, path=p)
    loaded = load_all(p)
    assert len(loaded) == 2
    assert loaded[0].ts == 1000
    assert loaded[1].sticky_id == "r2"


def test_recent_filters_old(tmp_path: Path) -> None:
    p = tmp_path / "violations.jsonl"
    # 一条 25h 前，一条 1h 前
    items = [
        Violation(ts=1000, session_id="s", sticky_id="old-rule", trigger="x", snippet="."),
        Violation(ts=1000 + 24 * 3600, session_id="s", sticky_id="new-rule", trigger="y", snippet="."),
    ]
    append(items, path=p)
    out = recent(p, window_sec=24 * 3600, now=1000 + 25 * 3600)
    assert "new-rule" in out
    assert "old-rule" not in out


def test_recent_takes_latest_ts_per_sticky(tmp_path: Path) -> None:
    p = tmp_path / "violations.jsonl"
    items = [
        Violation(ts=1000, session_id="s", sticky_id="r1", trigger="x", snippet="."),
        Violation(ts=2000, session_id="s", sticky_id="r1", trigger="x", snippet="."),
        Violation(ts=1500, session_id="s", sticky_id="r1", trigger="x", snippet="."),
    ]
    append(items, path=p)
    out = recent(p, window_sec=10000, now=3000)
    assert out["r1"] == 2000


def test_recent_no_file(tmp_path: Path) -> None:
    assert recent(tmp_path / "no.jsonl") == {}


def test_append_empty_list_noop(tmp_path: Path) -> None:
    p = tmp_path / "violations.jsonl"
    append([], path=p)
    assert not p.exists()


# ---- 缺口 #4 violations.jsonl rotation ----

def test_rotation_triggers_when_over_max_lines(tmp_path: Path) -> None:
    """append 后行数超 max_lines → rotate（重命名 + 新文件）。"""
    from karma.violations import rotate_if_needed
    p = tmp_path / "violations.jsonl"
    # 写 11 行（max_lines=10 让测试简洁）
    items = [
        Violation(ts=i, session_id="s", sticky_id=f"r{i}", trigger="x", snippet=".")
        for i in range(11)
    ]
    append(items, path=p)
    rotated = rotate_if_needed(p, max_lines=10, keep=3)
    assert rotated, "超 max_lines 应该触发 rotation"
    # 原文件应该不存在或为空，.1 应该有内容
    if p.exists():
        assert p.read_text(encoding="utf-8") == ""
    assert (tmp_path / "violations.jsonl.1").exists()
    assert "r5" in (tmp_path / "violations.jsonl.1").read_text(encoding="utf-8")


def test_rotation_under_threshold_no_op(tmp_path: Path) -> None:
    """行数未超阈值 → 不 rotate。"""
    from karma.violations import rotate_if_needed
    p = tmp_path / "violations.jsonl"
    items = [
        Violation(ts=i, session_id="s", sticky_id=f"r{i}", trigger="x", snippet=".")
        for i in range(5)
    ]
    append(items, path=p)
    rotated = rotate_if_needed(p, max_lines=10, keep=3)
    assert not rotated
    assert p.exists()
    assert not (tmp_path / "violations.jsonl.1").exists()


def test_rotation_keep_history_count(tmp_path: Path) -> None:
    """多次 rotate 后保留最多 keep 个历史文件（最老的删）。"""
    from karma.violations import rotate_if_needed
    p = tmp_path / "violations.jsonl"
    # 模拟 5 次 rotate（每次行数超阈值）
    for round_idx in range(5):
        items = [
            Violation(ts=round_idx * 100 + i, session_id="s", sticky_id=f"r{i}", trigger="x", snippet=".")
            for i in range(11)
        ]
        append(items, path=p)
        rotate_if_needed(p, max_lines=10, keep=3)
    # 应只保留 .1 .2 .3，没有 .4 .5
    assert (tmp_path / "violations.jsonl.1").exists()
    assert (tmp_path / "violations.jsonl.2").exists()
    assert (tmp_path / "violations.jsonl.3").exists()
    assert not (tmp_path / "violations.jsonl.4").exists()
    assert not (tmp_path / "violations.jsonl.5").exists()


def test_append_triggers_rotation_automatically(tmp_path: Path, monkeypatch) -> None:
    """append() 末尾自动调 rotate_if_needed — 超阈值时自动 rotate。"""
    import karma.violations as v
    monkeypatch.setattr(v, "MAX_LINES", 10)
    monkeypatch.setattr(v, "KEEP_HISTORY", 3)
    p = tmp_path / "violations.jsonl"
    items = [
        Violation(ts=i, session_id="s", sticky_id=f"r{i}", trigger="x", snippet=".")
        for i in range(15)
    ]
    append(items, path=p)
    # 应已自动 rotate
    assert (tmp_path / "violations.jsonl.1").exists(), "append 应自动触发 rotation"


# ---- count_recent — 累积警报基础 ----

def test_count_recent_returns_count_per_sticky(tmp_path: Path) -> None:
    """count_recent 返回 window_sec 内每个 sticky_id 的违反次数（不是最新 ts）。"""
    from karma.violations import count_recent
    p = tmp_path / "violations.jsonl"
    items = [
        Violation(ts=1000, session_id="s", sticky_id="r1", trigger="x", snippet="."),
        Violation(ts=1100, session_id="s", sticky_id="r1", trigger="x", snippet="."),
        Violation(ts=1200, session_id="s", sticky_id="r1", trigger="x", snippet="."),
        Violation(ts=1300, session_id="s", sticky_id="r2", trigger="x", snippet="."),
    ]
    append(items, path=p)
    out = count_recent(p, window_sec=1000, now=2000)
    assert out["r1"] == 3
    assert out["r2"] == 1


def test_count_recent_filters_outside_window(tmp_path: Path) -> None:
    """超出 window_sec 的违反不算。"""
    from karma.violations import count_recent
    p = tmp_path / "violations.jsonl"
    items = [
        Violation(ts=1000, session_id="s", sticky_id="r1", trigger="x", snippet="."),  # 25 min 前
        Violation(ts=2000, session_id="s", sticky_id="r1", trigger="x", snippet="."),  # 当前窗口内
    ]
    append(items, path=p)
    # 窗口 500 秒，now=2200 → 只数 ts >= 1700 的
    out = count_recent(p, window_sec=500, now=2200)
    assert out["r1"] == 1


def test_count_recent_no_file(tmp_path: Path) -> None:
    """文件不存在 → 返回空 dict。"""
    from karma.violations import count_recent
    out = count_recent(tmp_path / "no.jsonl")
    assert out == {}
