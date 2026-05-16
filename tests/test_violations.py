"""violations.jsonl 读写 + 违反检测。"""

from __future__ import annotations

from pathlib import Path

from karma.rule import Rule as Sticky
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
    assert out[0].rule_id == "long-term"
    assert out[0].trigger == "先打个补丁"
    assert "先打个补丁" in out[0].snippet


def test_detect_multiple_stickies() -> None:
    response = "用 F1 看，先硬编码一下"
    out = detect(response, _make_sticky(), now=1000)
    sids = {v.rule_id for v in out}
    assert sids == {"long-term", "chinese-only"}


def test_detect_same_sticky_multiple_keywords_records_first() -> None:
    """同一 sticky 多关键词命中只记第一个。"""
    response = "先打个补丁，再硬编码一个"
    out = detect(response, _make_sticky(), now=1000)
    assert len(out) == 1
    assert out[0].rule_id == "long-term"


def test_detect_case_insensitive() -> None:
    response = "用 f1 score"
    out = detect(response, _make_sticky(), now=1000)
    assert len(out) == 1
    assert out[0].rule_id == "chinese-only"


def test_detect_empty_response() -> None:
    assert detect("", _make_sticky()) == []


def test_detect_no_violation() -> None:
    response = "好的，开始干活了"
    assert detect(response, _make_sticky()) == []


def test_append_and_load_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "violations.jsonl"
    items = [
        Violation(ts=1000, session_id="s1", rule_id="r1", trigger="x", snippet="..."),
        Violation(ts=2000, session_id="s1", rule_id="r2", trigger="y", snippet="..."),
    ]
    append(items, path=p)
    loaded = load_all(p)
    assert len(loaded) == 2
    assert loaded[0].ts == 1000
    assert loaded[1].rule_id == "r2"


def test_recent_filters_old(tmp_path: Path) -> None:
    p = tmp_path / "violations.jsonl"
    # 一条 25h 前，一条 1h 前
    items = [
        Violation(ts=1000, session_id="s", rule_id="old-rule", trigger="x", snippet="."),
        Violation(ts=1000 + 24 * 3600, session_id="s", rule_id="new-rule", trigger="y", snippet="."),
    ]
    append(items, path=p)
    out = recent(p, window_sec=24 * 3600, now=1000 + 25 * 3600)
    assert "new-rule" in out
    assert "old-rule" not in out


def test_recent_takes_latest_ts_per_sticky(tmp_path: Path) -> None:
    p = tmp_path / "violations.jsonl"
    items = [
        Violation(ts=1000, session_id="s", rule_id="r1", trigger="x", snippet="."),
        Violation(ts=2000, session_id="s", rule_id="r1", trigger="x", snippet="."),
        Violation(ts=1500, session_id="s", rule_id="r1", trigger="x", snippet="."),
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
        Violation(ts=i, session_id="s", rule_id=f"r{i}", trigger="x", snippet=".")
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
        Violation(ts=i, session_id="s", rule_id=f"r{i}", trigger="x", snippet=".")
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
            Violation(ts=round_idx * 100 + i, session_id="s", rule_id=f"r{i}", trigger="x", snippet=".")
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
    """append() 末尾自动调 rotate_if_needed — 超阈值时自动 rotate。
    阈值从 karma.config 读，测试 monkeypatch config.load 返回低阈值。"""
    import karma.config as cfg_mod
    monkeypatch.setattr(
        cfg_mod, "load",
        lambda path=None: {**cfg_mod.DEFAULTS, "violations_max_lines": 10, "violations_keep_history": 3},
    )
    p = tmp_path / "violations.jsonl"
    items = [
        Violation(ts=i, session_id="s", rule_id=f"r{i}", trigger="x", snippet=".")
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
        Violation(ts=1000, session_id="s", rule_id="r1", trigger="x", snippet="."),
        Violation(ts=1100, session_id="s", rule_id="r1", trigger="x", snippet="."),
        Violation(ts=1200, session_id="s", rule_id="r1", trigger="x", snippet="."),
        Violation(ts=1300, session_id="s", rule_id="r2", trigger="x", snippet="."),
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
        Violation(ts=1000, session_id="s", rule_id="r1", trigger="x", snippet="."),  # 25 min 前
        Violation(ts=2000, session_id="s", rule_id="r1", trigger="x", snippet="."),  # 当前窗口内
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


# ---- turn-based recent / count ----

def test_recent_turns_filters_by_session_and_turn_window(tmp_path: Path) -> None:
    """recent_turns 只统计本 session 最近 N turn 内的违反。

    v0.9.13 cutoff 收紧（off-by-one fix）：window=N 真匹配 N 个 turn 不是 N+1。
    session a, current_turn=6, window_turns=3 → 匹配 [cur-(N-1), cur] = [4, 6] 共 3 个 turn。
    """
    from karma.violations import recent_turns
    p = tmp_path / "violations.jsonl"
    # 不同 session + 不同 turn
    items = [
        Violation(ts=1000, session_id="a", rule_id="r1", trigger="x", snippet=".", turn=1),
        Violation(ts=1100, session_id="a", rule_id="r1", trigger="x", snippet=".", turn=2),
        Violation(ts=1200, session_id="a", rule_id="r2", trigger="x", snippet=".", turn=5),
        Violation(ts=1300, session_id="b", rule_id="r3", trigger="x", snippet=".", turn=3),  # 别的 session
    ]
    append(items, path=p)
    # session a，当前 turn=6，窗口 3 → 真 3 turn 匹配 [4, 5, 6]
    out = recent_turns("a", current_turn=6, window_turns=3, path=p)
    assert "r2" in out
    assert out["r2"] == 5
    assert "r1" not in out  # turn 1/2 在窗口外
    assert "r3" not in out  # 别的 session


def test_count_recent_turns_by_session(tmp_path: Path) -> None:
    """count_recent_turns 数本 session 内 N turn 内违反次数。

    v0.9.13 cutoff 收紧（off-by-one fix）：window=N 真匹配 N 个 turn。
    current=7, window=3 → 匹配 [5, 6, 7] 共 3 个 turn。
    """
    from karma.violations import count_recent_turns
    p = tmp_path / "violations.jsonl"
    items = [
        Violation(ts=1000, session_id="a", rule_id="r1", trigger="x", snippet=".", turn=5),
        Violation(ts=1100, session_id="a", rule_id="r1", trigger="x", snippet=".", turn=6),
        Violation(ts=1200, session_id="a", rule_id="r1", trigger="x", snippet=".", turn=7),
        Violation(ts=1300, session_id="a", rule_id="r1", trigger="x", snippet=".", turn=2),  # 窗口外
        Violation(ts=1400, session_id="b", rule_id="r1", trigger="x", snippet=".", turn=7),  # 别 session
    ]
    append(items, path=p)
    # session a, current_turn=7, window=3 → 真 3 turn [5,6,7]
    out = count_recent_turns("a", current_turn=7, window_turns=3, path=p)
    assert out["r1"] == 3  # turn 5/6/7


def test_recent_turns_window_lockdown_v0913(tmp_path: Path) -> None:
    """v0.9.13 off-by-one lockdown：window=N 真匹配 N 个 turn 不是 N+1。

    场景：current=10, window=3 → 期望匹配 [8, 9, 10] 共 3 个 turn。
    旧 cutoff = current - window = 7 → 匹配 [7, 8, 9, 10] 共 4 个 turn (off-by-one)
    新 cutoff = current - (window - 1) = 8 → 匹配 [8, 9, 10] 共 3 个 turn ✓

    锁 force_block / escalation 阈值不被旧实现多算 1 turn 历史误算。
    """
    from karma.violations import recent_turns, count_recent_turns
    p = tmp_path / "violations.jsonl"
    items = [
        Violation(ts=t, session_id="s", rule_id="r", trigger="x", snippet=".", turn=t)
        for t in [6, 7, 8, 9, 10]
    ]
    append(items, path=p)

    # window=3 真匹配 3 个 turn ([8,9,10])
    out = recent_turns("s", current_turn=10, window_turns=3, path=p)
    assert "r" in out
    assert out["r"] == 10
    # 关键 assert: turn=7 不该被算进 window=3 窗口
    counts = count_recent_turns("s", current_turn=10, window_turns=3, path=p)
    assert counts["r"] == 3, f"window=3 应匹配 [8,9,10] 共 3 turn, 实际 {counts['r']}"
    # window=1 真匹配 1 个 turn (current 自己)
    counts1 = count_recent_turns("s", current_turn=10, window_turns=1, path=p)
    assert counts1["r"] == 1, f"window=1 应只匹配 current turn=10, 实际 {counts1['r']}"


def test_recent_turns_skips_legacy_no_turn_field(tmp_path: Path) -> None:
    """老格式没 turn 字段 → 跳过，不要 fallback 成 0 落入当前窗口造成假阳。

    场景：Claude Code session compact 不换 session_id，turn 维度引入前的
    老违反沿用到「新对话」开头 turn_count=1 时，window=3 → cutoff=-2 →
    fallback 0 落入窗口 → 触发 force_block 假阳（dogfooding 实际踩过）。
    """
    import json
    from karma.violations import recent_turns
    p = tmp_path / "violations.jsonl"
    # 手写老格式（无 turn 字段，模拟 turn 维度引入前的历史）
    legacy = {"ts": 1000, "session_id": "a", "sticky_id": "r1",
              "trigger": "x", "snippet": "."}
    p.write_text(json.dumps(legacy) + "\n", encoding="utf-8")
    # current_turn=1, window=3, cutoff=-2 — 如果 fallback 0 会被数到
    out = recent_turns("a", current_turn=1, window_turns=3, path=p)
    assert "r1" not in out, "无 turn 字段的老违反不应被当前窗口数到"


def test_count_recent_turns_skips_legacy_no_turn_field(tmp_path: Path) -> None:
    """同上 — count_recent_turns 也要跳过无 turn 字段的老违反。"""
    import json
    from karma.violations import count_recent_turns
    p = tmp_path / "violations.jsonl"
    # 模拟 6 条老违反（force_block 阈值 5）
    legacy_lines = [
        json.dumps({"ts": 1000 + i, "session_id": "a", "sticky_id": "r1",
                    "trigger": "x", "snippet": "."}) for i in range(6)
    ]
    p.write_text("\n".join(legacy_lines) + "\n", encoding="utf-8")
    out = count_recent_turns("a", current_turn=1, window_turns=3, path=p)
    assert out.get("r1", 0) == 0, (
        "6 条老违反（无 turn 字段）不应数到 → 不应触发 force_block 假阳"
    )


def test_violation_dataclass_has_turn_field():
    """Violation 加 turn 字段，default 0 兼容旧记录。"""
    v = Violation(ts=1, session_id="s", rule_id="r", trigger="x", snippet=".")
    assert v.turn == 0
    v2 = Violation(ts=1, session_id="s", rule_id="r", trigger="x", snippet=".", turn=42)
    assert v2.turn == 42


def test_violation_to_json_includes_turn():
    import json as _json
    v = Violation(ts=1, session_id="s", rule_id="r", trigger="x", snippet=".", turn=7)
    d = _json.loads(v.to_json())
    assert d["turn"] == 7


def test_load_all_handles_missing_turn_field(tmp_path: Path):
    """旧 jsonl 没 turn 字段 → 读取时 default 0。"""
    p = tmp_path / "violations.jsonl"
    p.write_text('{"ts":1,"session_id":"s","sticky_id":"r","trigger":"x","snippet":"."}\n')
    out = load_all(p)
    assert len(out) == 1
    assert out[0].turn == 0


def test_load_all_reads_agent_id_field(tmp_path: Path):
    """v0.9.13 fix: load_all() 之前漏读 agent_id 字段（to_json 写了但 load 不读）—
    audit / stats 视图无法真按主/子 Agent 分组。Now properly round-trips。
    """
    p = tmp_path / "violations.jsonl"
    items = [
        Violation(ts=1, session_id="s", rule_id="r", trigger="x", snippet=".",
                  turn=1, agent_id="sub-uuid-123"),  # 子 Agent 违反
        Violation(ts=2, session_id="s", rule_id="r", trigger="x", snippet=".",
                  turn=2),  # 主 Agent（agent_id=None）
    ]
    append(items, path=p)
    out = load_all(p)
    assert len(out) == 2
    # 子 Agent agent_id 反序列化回来
    assert out[0].agent_id == "sub-uuid-123"
    # 主 Agent agent_id 是 None（不在 to_json，load 也得 None）
    assert out[1].agent_id is None


def test_weak_claims_zh_en_coverage_parity():
    """v0.9.13 fix: 中文 weak_claims 字眼数过去 8 vs 英文 23，中文 evidence
    check 召回率严重不足。补齐后两语言字眼覆盖差距应 < 30% 让中文用户也能
    可靠检测 hedge 字眼。

    数差距阈值：30% 给字眼性质有自然语言差异留余地（不强求 1:1）。
    """
    from pathlib import Path

    def _count_entries(path: Path) -> int:
        return sum(
            1 for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        )

    root = Path(__file__).resolve().parent.parent
    zh = _count_entries(root / "data" / "signals" / "weak_claims" / "zh.txt")
    en = _count_entries(root / "data" / "signals" / "weak_claims" / "en.txt")
    assert zh > 0 and en > 0, f"两语言 weak_claims 字眼都必须非空: zh={zh}, en={en}"
    smaller, larger = min(zh, en), max(zh, en)
    diff_ratio = (larger - smaller) / larger
    assert diff_ratio < 0.3, (
        f"weak_claims zh/en 字眼数差距 {diff_ratio*100:.0f}% 超过 30% 阈值: "
        f"zh={zh}, en={en}. 补字眼让中文 evidence check 召回率对齐英文。"
    )
