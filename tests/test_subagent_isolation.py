"""v0.4.34 子 Agent 独立 karma 监控架构守护测试。

设计意图（用户决策）：子 Agent 跟主 Agent 是两个不同进程彼此互不干扰，
子 Agent 应有临时独立 state，子 Agent 结束自动销毁。

协议依据：Claude Code PreToolUse/PostToolUse/Stop hook payload 含 agent_id
字段（主 Agent 字段缺失，子 Agent 含 uuid）。session_id 设计就是子 Agent
共享主 session_id，所以区分主/子的唯一信号是 agent_id 字段。
"""

from __future__ import annotations

from karma import session_state
from karma.violations import Violation


def test_main_agent_state_path_unchanged(tmp_path):
    """主 Agent (agent_id=None) state 文件路径保持向后兼容 = <session_id>.json。"""
    p = session_state._state_path("abc123", base_dir=tmp_path)
    assert p.name == "abc123.json"


def test_subagent_state_path_includes_agent_id(tmp_path):
    """子 Agent state 文件路径含 __<agent_id> 后缀 — 跟主 Agent state 隔离。"""
    p = session_state._state_path("abc123", base_dir=tmp_path, agent_id="explore-uuid-1")
    assert p.name == "abc123__explore-uuid-1.json"


def test_subagent_load_save_independent_from_main(tmp_path):
    """子 Agent state load / save 跟主 Agent 完全独立 — 互不污染。"""
    # 主 Agent 写一个 state
    main_state = session_state.SessionState(session_id="sess1")
    main_state.turn_count = 5
    main_state.tool_byte_seq = 1000
    session_state.save(main_state, base_dir=tmp_path)

    # 子 Agent 写另一个 state（同 session_id 不同 agent_id）
    sub_state = session_state.SessionState(session_id="sess1", agent_id="sub-1")
    sub_state.turn_count = 99  # 故意不同值证明真隔离
    sub_state.tool_byte_seq = 9999
    session_state.save(sub_state, base_dir=tmp_path)

    # load 主 Agent 拿到主 state
    loaded_main = session_state.load("sess1", base_dir=tmp_path)
    assert loaded_main.turn_count == 5
    assert loaded_main.tool_byte_seq == 1000
    assert loaded_main.agent_id is None

    # load 子 Agent 拿到子 state
    loaded_sub = session_state.load("sess1", base_dir=tmp_path, agent_id="sub-1")
    assert loaded_sub.turn_count == 99
    assert loaded_sub.tool_byte_seq == 9999
    assert loaded_sub.agent_id == "sub-1"


def test_purge_subagent_state_deletes_file(tmp_path):
    """SubagentStop 时调用 purge_subagent_state 删子 Agent state 文件。"""
    sub_state = session_state.SessionState(session_id="sess1", agent_id="sub-1")
    sub_state.turn_count = 1
    session_state.save(sub_state, base_dir=tmp_path)
    sub_path = session_state._state_path("sess1", base_dir=tmp_path, agent_id="sub-1")
    assert sub_path.exists()  # 真创建了

    # 销毁
    deleted = session_state.purge_subagent_state("sess1", "sub-1", base_dir=tmp_path)
    assert deleted is True
    assert not sub_path.exists()  # 删了


def test_purge_subagent_state_main_path_unaffected(tmp_path):
    """purge_subagent_state 销毁子 Agent state 不应影响主 Agent state。"""
    main_state = session_state.SessionState(session_id="sess1")
    main_state.turn_count = 5
    session_state.save(main_state, base_dir=tmp_path)
    sub_state = session_state.SessionState(session_id="sess1", agent_id="sub-1")
    session_state.save(sub_state, base_dir=tmp_path)

    session_state.purge_subagent_state("sess1", "sub-1", base_dir=tmp_path)

    # 主 Agent state 真还在
    main_path = session_state._state_path("sess1", base_dir=tmp_path)
    assert main_path.exists()
    loaded = session_state.load("sess1", base_dir=tmp_path)
    assert loaded.turn_count == 5


def test_pending_subagent_models_fifo_queue(tmp_path):
    """v0.4.37: 主 Agent 派多个子 Agent 时 pending_subagent_models 按 FIFO 入队。
    主 PreToolUse(Agent, model=X) 入队 → SubagentStart pop 队首写子 state。
    """
    main_state = session_state.SessionState(session_id="sess1")
    # 模拟主 Agent 派 3 个并行子 Agent (Opus / Sonnet / Haiku)
    main_state.pending_subagent_models = ["opus", "sonnet", "haiku"]
    session_state.save(main_state, base_dir=tmp_path)

    # 第一次 SubagentStart pop "opus"
    loaded = session_state.load("sess1", base_dir=tmp_path)
    first = loaded.pending_subagent_models.pop(0)
    session_state.save(loaded, base_dir=tmp_path)
    assert first == "opus"

    # 第二次 pop "sonnet"
    loaded = session_state.load("sess1", base_dir=tmp_path)
    second = loaded.pending_subagent_models.pop(0)
    assert second == "sonnet"
    assert loaded.pending_subagent_models == ["haiku"]


def test_subagent_state_model_drives_threshold(tmp_path):
    """v0.4.37 闭环：主 PreToolUse 入队 → SubagentStart pop → 子 state.model
    写入 → 后续子 Agent 内 PostToolUse 用 threshold_for_model(state.model)。
    """
    from karma.model_threshold import threshold_for_model

    # 模拟 SubagentStart 写完子 Agent state.model
    sub_state = session_state.SessionState(session_id="sess1", agent_id="sub-1")
    sub_state.model = "haiku"
    session_state.save(sub_state, base_dir=tmp_path)

    # 后续子 Agent 内 PostToolUse load 子 state → 用 model 算阈值
    loaded = session_state.load("sess1", base_dir=tmp_path, agent_id="sub-1")
    assert loaded.model == "haiku"
    assert threshold_for_model(loaded.model) == 30_000  # haiku 真阈值

    # 对偶：主 Agent 是 opus，子 Agent 是 sonnet — 真各自独立阈值
    main = session_state.SessionState(session_id="sess1")
    main.model = "claude-opus-4-7"
    session_state.save(main, base_dir=tmp_path)
    sub2 = session_state.SessionState(session_id="sess1", agent_id="sub-2")
    sub2.model = "claude-sonnet-4-6"
    session_state.save(sub2, base_dir=tmp_path)

    main_loaded = session_state.load("sess1", base_dir=tmp_path)
    sub2_loaded = session_state.load("sess1", base_dir=tmp_path, agent_id="sub-2")
    assert threshold_for_model(main_loaded.model) == 80_000  # opus
    assert threshold_for_model(sub2_loaded.model) == 60_000  # sonnet


def test_violation_agent_id_serialized_when_subagent():
    """Violation 含 agent_id 时 to_json 写字段；agent_id=None 时不写省体积。"""
    import json
    v_main = Violation(ts=1, session_id="s", rule_id="r", trigger="t", snippet="x", turn=1)
    d_main = json.loads(v_main.to_json())
    assert "agent_id" not in d_main  # 主 Agent 不写 agent_id 字段省体积 + 向后兼容

    v_sub = Violation(
        ts=1, session_id="s", rule_id="r", trigger="t", snippet="x", turn=1,
        agent_id="sub-uuid",
    )
    d_sub = json.loads(v_sub.to_json())
    assert d_sub.get("agent_id") == "sub-uuid"  # 子 Agent 写 agent_id 字段
