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

from pinrule.hooks.post_tool_use import _estimate_tokens, _build_smart_reinject
from pinrule.session_state import SessionState
from pinrule.rule import Rule as Sticky


def _make_sticky(sid: str) -> Sticky:
    return Sticky(
        id=sid, preference=f"测试 sticky {sid} 第一行\n第二行不该注入",
        violation_keywords=(), violation_checks=(),
    )


def _make_state(turn=5, byte_seq=0, last_reinject=0, model="claude-sonnet-4-6") -> SessionState:
    """v0.4.35: 默认 model=sonnet (阈值 60K) — 测试用 70K byte_seq 触发实际注入逻辑。
    旧测试用 model=claude-instant 时 8K 阈值，跟之前 v0.4.32 行为一致。
    """
    s = SessionState(session_id="test", model=model)
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
    用户 v0.4.32 决策真核心：主 Agent context 衰减只看主 Agent 看到的。
    """
    # 模拟 sub-agent 最终回报 ~3KB
    tool_input = {"prompt": "x" * 200}
    tool_response = "x" * 3000
    est = _estimate_tokens(tool_input, tool_response)
    # 挺大约 (3000+200) // 3 ≈ 1066 token — 不是 30K（不算子 Agent 内部）
    assert 900 < est < 1200


def test_no_reinject_when_below_threshold():
    """累积 token 未达阈值 → 不注入 + state 不动 (v0.9.0: sonnet 默认 40K)。"""
    state = _make_state(byte_seq=5000, last_reinject=0)  # 累积 5K < 40K sonnet 阈值
    with patch("pinrule.hooks.post_tool_use._load_sticky", create=True), \
         patch("pinrule.rule.load", return_value=[_make_sticky("r1")]), \
         patch("pinrule.violations.recent_turns", return_value={"r1": 2}):
        result = _build_smart_reinject("test", state)
    assert result == ""
    assert state.last_reinject_byte_seq == 0  # 未达阈值不更新


def test_reinject_when_threshold_reached_and_sticky_triggered():
    """v0.9.0: 累积达阈值 → 全量 reinject (含所有规则) + 重置 last_reinject_byte_seq。

    跟 v0.8.x 区别: v0.8.x 只 reinject 最近触发的 sticky 精简版；v0.9.0 全量
    注入 format_for_injection（含每条 preference 全文）抗稀释。
    """
    state = _make_state(byte_seq=50000, last_reinject=0)  # sonnet 40K 阈值，累积 50K 触发
    with patch("pinrule.rule.load", return_value=[_make_sticky("r1"), _make_sticky("r2")]), \
         patch("pinrule.violations.recent_turns", return_value={"r1": 2}):
        result = _build_smart_reinject("test", state)
    # v0.9.0: 全量注入 format_for_injection 输出 — 含 inject.header.title
    assert "[pinrule" in result and "长期默契" in result
    # 所有规则都在 (v0.9.0 全量) — r2 也应该出现
    assert "r1" in result
    assert "r2" in result
    # 注入后 last_reinject_byte_seq 重置为当前 tool_byte_seq
    assert state.last_reinject_byte_seq == 50000


def test_threshold_resets_after_reinject():
    """注入后再积累必须从 0 起算 — last_reinject_byte_seq 节流测试。
    v0.9.0: sonnet 40K 阈值，累积 50K 触发首次，再加 5K 不再触发。
    """
    state = _make_state(byte_seq=50000, last_reinject=0)
    with patch("pinrule.rule.load", return_value=[_make_sticky("r1")]), \
         patch("pinrule.violations.recent_turns", return_value={"r1": 1}):
        r1 = _build_smart_reinject("test", state)
    assert r1 != ""
    # 模拟下个 tool 累积 5K（55000-50000=5K < 40K sonnet 阈值）
    state.tool_byte_seq = 55000
    with patch("pinrule.rule.load", return_value=[_make_sticky("r1")]), \
         patch("pinrule.violations.recent_turns", return_value={"r1": 1}):
        r2 = _build_smart_reinject("test", state)
    assert r2 == ""  # 未再达阈值不重复注入


def test_no_recent_violations_still_injects_full_baseline():
    """v0.9.0: 累积达阈值且无最近违反 → 仍全量注入 baseline 抗稀释。

    跟 v0.8.x 区别: v0.8.x 「无 recent → 不注入只更 last_reinject 节流」；
    v0.9.0 累积达阈值就全量注入（设计意图：抗稀释不依赖违反触发）。
    """
    state = _make_state(byte_seq=50000, last_reinject=0)  # sonnet 40K，50K 触发
    with patch("pinrule.rule.load", return_value=[_make_sticky("r1")]), \
         patch("pinrule.violations.recent_turns", return_value={}):
        result = _build_smart_reinject("test", state)
    # v0.9.0: 累积达阈值就全量注入，不管有没有最近违反
    assert result != ""
    assert "[pinrule" in result and "长期默契" in result
    # 节流：注入后更新位置防止下次立即重判
    assert state.last_reinject_byte_seq == 50000


def test_zero_turn_returns_empty():
    """turn=0 (session 起手未提 prompt) → 不注入。"""
    state = _make_state(turn=0, byte_seq=70000)
    with patch("pinrule.rule.load", return_value=[_make_sticky("r1")]):
        assert _build_smart_reinject("test", state) == ""


def test_threshold_adapts_to_opus_model():
    """v0.9.0: opus 阈值 60K（v0.4.35 是 80K），50K byte_seq 不触发，65K 触发。"""
    state = _make_state(byte_seq=50000, last_reinject=0, model="claude-opus-4-7")
    with patch("pinrule.rule.load", return_value=[_make_sticky("r1")]), \
         patch("pinrule.violations.recent_turns", return_value={"r1": 1}):
        result = _build_smart_reinject("test", state)
    assert result == ""  # opus 阈值 60K，累积 50K 不触发
    state.tool_byte_seq = 65000
    with patch("pinrule.rule.load", return_value=[_make_sticky("r1")]), \
         patch("pinrule.violations.recent_turns", return_value={"r1": 1}):
        result = _build_smart_reinject("test", state)
    assert "[pinrule" in result and "长期默契" in result  # opus 累积 65K 触发


def test_threshold_adapts_to_haiku_model():
    """haiku 模型阈值 30K（不变），35K byte_seq 触发。"""
    state = _make_state(byte_seq=35000, last_reinject=0, model="claude-haiku-4-5")
    with patch("pinrule.rule.load", return_value=[_make_sticky("r1")]), \
         patch("pinrule.violations.recent_turns", return_value={"r1": 1}):
        result = _build_smart_reinject("test", state)
    assert "[pinrule" in result and "长期默契" in result  # haiku 30K 阈值，35K 触发
