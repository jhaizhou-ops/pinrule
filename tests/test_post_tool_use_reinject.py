"""PostToolUse 中段 sticky reinject 真单元测试（v0.4.32 token 启发式）。

设计意图（v0.4.32 用户决策）：
1. 中段注入是「抵御长 turn context 累积导致 sticky attention 衰减」补丁
2. 累积 token 达阈值（默认 8000）后下个 PostToolUse 注入一次「重新锚定」
3. 注入只取最近触发过的 sticky，不是全 sticky
4. 注入后重置 last_reinject_byte_seq 节流
5. 每 turn 起手 user_prompt_submit 重置 tool_byte_seq + last_reinject_byte_seq 归零
"""

from __future__ import annotations

from unittest.mock import patch

from karma.hooks.post_tool_use import _estimate_tokens, _build_smart_reinject
from karma.session_state import SessionState
from karma.sticky import Sticky


def _make_sticky(sid: str) -> Sticky:
    return Sticky(
        id=sid, preference=f"测试 sticky {sid} 第一行\n第二行不该注入",
        violation_keywords=[], violation_checks=[],
    )


def _make_state(turn=5, byte_seq=0, last_reinject=0) -> SessionState:
    s = SessionState(session_id="test")
    s.turn_count = turn
    s.tool_byte_seq = byte_seq
    s.last_reinject_byte_seq = last_reinject
    return s


def test_estimate_tokens_simple_bash():
    """简单 Bash 真按字节数 // 3 估算。"""
    tool_input = {"command": "ls"}  # ~15 字节
    tool_response = "a.txt\nb.txt\n"  # ~12 字节
    est = _estimate_tokens(tool_input, tool_response)
    # 实际 (len(str(dict))=22 + len(str)=12) // 3 ≈ 11 token
    assert 5 < est < 30


def test_estimate_tokens_subagent_only_counts_main_visible():
    """sub-agent (Task) 也按主 Agent 看到的最终 tool_response 算 — 子 Agent
    内部 thinking + 中间 tool 是子 Agent 自己 context 不算主 Agent 衰减。
    用户 v0.4.32 决策真核心：主 Agent context 衰减只看主 Agent 真看到的。
    """
    # 模拟 sub-agent 最终回报 ~3KB
    tool_input = {"prompt": "x" * 200}
    tool_response = "x" * 3000
    est = _estimate_tokens(tool_input, tool_response)
    # 真大约 (3000+200) // 3 ≈ 1066 token — 不是 30K（不算子 Agent 内部）
    assert 900 < est < 1200


def test_no_reinject_when_below_threshold():
    """累积 token 未达阈值 → 不注入 + state 不动。"""
    state = _make_state(byte_seq=5000, last_reinject=0)  # 累积 5K < 8K 默认
    with patch("karma.hooks.post_tool_use._load_sticky", create=True), \
         patch("karma.sticky.load", return_value=[_make_sticky("r1")]), \
         patch("karma.violations.recent_turns", return_value={"r1": 2}):
        result = _build_smart_reinject("test", state)
    assert result == ""
    assert state.last_reinject_byte_seq == 0  # 未达阈值不更新


def test_reinject_when_threshold_reached_and_sticky_triggered():
    """累积达阈值 + 有最近触发 sticky → 注入 + 重置 last_reinject_byte_seq。"""
    state = _make_state(byte_seq=10000, last_reinject=0)  # 累积 10K > 8K
    with patch("karma.sticky.load", return_value=[_make_sticky("r1"), _make_sticky("r2")]), \
         patch("karma.violations.recent_turns", return_value={"r1": 2}):
        result = _build_smart_reinject("test", state)
    assert "[karma 中段提醒" in result
    assert "r1" in result
    assert "r2" not in result  # 没触发 r2 不该注入
    # 注入后 last_reinject_byte_seq 真重置为当前 tool_byte_seq
    assert state.last_reinject_byte_seq == 10000


def test_threshold_resets_after_reinject():
    """注入后再积累必须从 0 起算 — last_reinject_byte_seq 真节流测试。"""
    state = _make_state(byte_seq=10000, last_reinject=0)
    with patch("karma.sticky.load", return_value=[_make_sticky("r1")]), \
         patch("karma.violations.recent_turns", return_value={"r1": 1}):
        # 第一次注入达阈值
        r1 = _build_smart_reinject("test", state)
    assert r1 != ""
    # 模拟下个 tool 累积 5K（10000+5000=15000，距 last_reinject=10000 差 5K < 8K）
    state.tool_byte_seq = 15000
    with patch("karma.sticky.load", return_value=[_make_sticky("r1")]), \
         patch("karma.violations.recent_turns", return_value={"r1": 1}):
        r2 = _build_smart_reinject("test", state)
    assert r2 == ""  # 未再达阈值不重复注入


def test_no_recent_violations_throttles_last_reinject_anyway():
    """累积达阈值但无最近触发 sticky → 不注入但仍更新 last_reinject_byte_seq
    防止下个 PostToolUse 立刻再判定（节流）。"""
    state = _make_state(byte_seq=10000, last_reinject=0)
    with patch("karma.sticky.load", return_value=[_make_sticky("r1")]), \
         patch("karma.violations.recent_turns", return_value={}):
        result = _build_smart_reinject("test", state)
    assert result == ""
    # 节流：即使没注入内容也更新位置防止下次立即重判
    assert state.last_reinject_byte_seq == 10000


def test_zero_turn_returns_empty():
    """turn=0 (session 起手未提 prompt) → 不注入。"""
    state = _make_state(turn=0, byte_seq=10000)
    with patch("karma.sticky.load", return_value=[_make_sticky("r1")]):
        assert _build_smart_reinject("test", state) == ""
