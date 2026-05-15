"""PostToolUse hook — 跟踪 session 状态 + 智能 sticky reinject anchor。

Claude Code 实际协议:
- stdin payload: {tool_name, tool_input, tool_response, session_id, ...}
- stdout: {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": "..."}}
  或者 fail-loud {"decision": "block", "reason": "..."} (我们不用)

v0.4.24（proactive 锚定第一步）：智能 sticky reinject 解决「sticky 注入头部强
尾部弱」原因。当前 sticky 仅 UserPromptSubmit 注入 1 次/turn，长 response
中段 Agent 注意力漂移导致单 turn 累积违反（实测本回合 33 keep-pushing + 11
chinese-plain）。

策略：**不是每次都注入**（token 成本高），仅当最近 N turn 内**该 sticky 真
触发过**才 reinject 它的简化提醒。这样 sticky 跟违反检测闭环：
- 违反某 sticky → 下次 tool call 后 reinject 该 sticky anchor
- 多次违反 → 多次 reinject 直到 Agent 改行为
- 没违反的 sticky → 不注入省 token

性能预算：< 50ms
"""

from __future__ import annotations

import json
import sys

from karma import session_state
from karma.checks.description_context import is_description_context


# tool 失败的字符串前缀 — Claude Code Read/Edit 失败常见返回（启发式）
_FAILURE_STRING_PREFIXES = (
    "Error", "error:", "File does not exist", "does not exist",
    "<system-reminder>", "Tool execution failed",
)


def _tool_failed(tool_response) -> bool:
    """启发式判 tool 调用是否失败 — 失败时跳过 record_read/edit
    防止 Read 失败也 record_read → 后续 Edit 该文件被 read_first 绕过。

    dict 形式：isError / interrupted 标志，或 stderr 含明确错误。
    string 形式：以已知失败前缀开头。
    """
    if isinstance(tool_response, dict):
        if tool_response.get("isError") or tool_response.get("interrupted"):
            return True
        return False
    s = str(tool_response or "").lstrip()
    for prefix in _FAILURE_STRING_PREFIXES:
        if s.startswith(prefix):
            return True
    return False


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"karma PostToolUse: 输入 JSON 解析失败 ({e})", file=sys.stderr)
        print(json.dumps({}))
        return 0


    session_id = payload.get("session_id", "") or "default"
    # v0.4.34 子 Agent 独立架构：agent_id 路由到独立 state 文件
    agent_id = payload.get("agent_id") or None
    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}
    tool_response = payload.get("tool_response", "") or ""

    # v0.9.8: 整段 modify + smart_reinject 进 update_state fn，让跨进程原子。
    # fn 返回 additional_context 给 stdout 输出（_build_smart_reinject 在 lock
    # 内跑保证 last_reinject_byte_seq 节流也跨进程一致）。
    failed = _tool_failed(tool_response)

    def _do_post_tool_use(state):
        # v0.4.39 协议层路径：PostToolUse payload 没 model 字段（manual run 验证），
        # 但所有 hook payload 有 transcript_path → 读 jsonl 找最后一条 assistant
        # message 的 model 字面（每个 assistant message 都含 model 字段，跳合成）。
        transcript_path = payload.get("transcript_path")
        if transcript_path:
            from karma.model_threshold import extract_model_from_transcript
            new_model = extract_model_from_transcript(transcript_path)
            if new_model:
                state.model = new_model

        # 先 catchup pending background 任务输出（任务可能在中间完成了）
        # 这样能在后续 record 之前更新 last_test_pass_ts，保证 evidence check 看见
        state.catchup_pending_bg()

        # v0.4.32 累积 token 估算 — 主 Agent 看到的 tool_input + tool_response
        # 字节数 // 3 约为 token 数（中英文混合粗略估，sub-agent 也按主 Agent 真
        # 看到的最终 tool_response 算，子 Agent 内部 thinking 是子 Agent 自己
        # context 不算主 Agent 衰减）
        state.tool_byte_seq += _estimate_tokens(tool_input, tool_response)

        if tool_name == "Bash":
            # Bash 失败仍 record — has_recent_test_pass 由 _FAIL_RE 在 record_bash 内部判
            cmd = tool_input.get("command", "") or ""
            is_bg = bool(tool_input.get("run_in_background"))
            state.record_bash(cmd, tool_response, run_in_background=is_bg)
        elif not failed:
            # 非 Bash tool — 只在成功时 record，失败时不动 read_files/edit_files
            # 防 Read 失败也 record_read 让后续 Edit 绕过 read_first 检测
            if tool_name == "Read":
                fp = tool_input.get("file_path", "")
                state.record_read(fp)
            elif tool_name in ("Write", "NotebookEdit"):
                # Write / NotebookEdit 替换或创建整个文件
                # 描述上下文文件（.md / .yaml / tests/ 等）的改不算「代码改动」—
                # 不推 last_edit_ts（避免 docs / 配置 Edit 后 evidence check 误判
                # 「自最近代码改动以来未测试」）。仍 record_read（已知内容不被 read_first 拦）
                fp = tool_input.get("file_path", "") or tool_input.get("notebook_path", "")
                is_desc, _ = is_description_context(tool_name, tool_input)
                if not is_desc:
                    state.record_edit(fp)
                state.record_read(fp)
            elif tool_name == "Edit":
                # Edit 只改部分 — 仍要求事先 Read 全文
                # 描述上下文文件 Edit 不推 last_edit_ts（同 Write/NotebookEdit 逻辑）
                fp = tool_input.get("file_path", "")
                is_desc, _ = is_description_context(tool_name, tool_input)
                if not is_desc:
                    state.record_edit(fp)

        # v0.4.24+v0.4.32：智能 sticky reinject — 按 token 累积阈值决定。
        # 在 lock 内跑保证 last_reinject_byte_seq 节流跨进程一致（fn 返回该值
        # 给外面 stdout 输出）
        return _build_smart_reinject(session_id, state)

    try:
        _state, additional_context = session_state.update_state(
            session_id, _do_post_tool_use, agent_id=agent_id,
        )
    except OSError as e:
        print(f"karma PostToolUse: 保存 session_state 失败 ({e})", file=sys.stderr)
        additional_context = ""

    output = {}
    if additional_context:
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": additional_context,
            }
        }
    print(json.dumps(output, ensure_ascii=False))
    return 0


def _estimate_tokens(tool_input, tool_response) -> int:
    """启发式估算主 Agent 看到的 token 数（bytes // 3 粗略中英文混合）。

    sub-agent (Task) 也按主 Agent 看到的最终 tool_response 算 — 子 Agent
    内部 thinking + 中间 tool 是子 Agent 自己 context，不算主 Agent 衰减。
    """
    return (len(str(tool_input or "")) + len(str(tool_response or ""))) // 3


def _build_smart_reinject(session_id: str, state) -> str:
    """智能 sticky reinject — 按 token 累积维度决定是否注入（v0.4.32 升级）。

    设计意图（用户 v0.4.32 决策 + v0.4.34 叙事对齐）：
    1. 中段注入是「抵御长 turn context 累积导致 sticky attention 稀释」补丁
       （不是「抵御模型遗忘」 — 当代 Claude 在 8K 几乎没衰减，衰减拐点
       在 70K-200K。8K 阈值是抗稀释频率，不是抗遗忘频率。详 session_state.py
       tool_byte_seq 字段注释）
    2. 每 turn 起手 user_prompt_submit 已全量注入 sticky → 中段不该立即重复
    3. 发生违反时已在 PreToolUse / Stop hook 响亮提醒 → 中段不重复警告
    4. 累积 token 达阈值（默认 8000）后下个 PostToolUse 注入一次「锚定刷新」
    5. 注入只取最近触发过的 sticky（不是全 sticky）— 跟 v0.4.24 保持一致

    返回空字符串 → PostToolUse 不注入 additionalContext。
    """
    try:
        from karma.rule import load as _load_sticky
        from karma.violations import recent_turns
        from karma.config import load as _load_config
    except ImportError:
        return ""
    try:
        sticky_list = _load_sticky()
    except Exception:
        return ""
    if not sticky_list or state.turn_count <= 0:
        return ""

    try:
        cfg = _load_config()
        window_turns = int(cfg.get("recent_violation_turns", 5))
        # v0.4.35 阈值来源优先级：sticky.yaml 显式配置 > 按模型自适应 > DEFAULT 60K
        # 用户 sticky.yaml 给 reinject_every_n_tokens 数字 → 强制覆盖
        # 没给 → 按 state.model 模型阈值（model_threshold 表）
        configured = cfg.get("reinject_every_n_tokens")
        if configured is not None:
            reinject_threshold = int(configured)
        else:
            from karma.model_threshold import threshold_for_model
            reinject_threshold = threshold_for_model(state.model)
    except Exception:
        window_turns = 5
        from karma.model_threshold import threshold_for_model, DEFAULT_THRESHOLD
        try:
            reinject_threshold = threshold_for_model(state.model)
        except Exception:
            reinject_threshold = DEFAULT_THRESHOLD

    # token 启发式：累积 token 距上次注入未达阈值 → 不注入
    accumulated = state.tool_byte_seq - state.last_reinject_byte_seq
    if accumulated < reinject_threshold:
        return ""

    # v0.9.0: 中段 reinject 改成**累积达阈值就全量注入**（含每条 preference 全文）
    # 抗稀释，不再依赖「最近违反过的规则」才注入。
    #
    # 理由：v0.9.0 架构是 SessionStart 一次全量 baseline + 每 turn 精简 anchor
    # + 累积达阈值中段全量补。SessionStart baseline 在 history 顶部累积到模型
    # 阈值后 attention 被稀释，需要全量重锚定 — 不依赖违反触发（设计意图：
    # 抗稀释是周期性维护，不是反应式维护）。
    # recent_v 仍传入 format_for_injection 让偏离规则带回顾标记。
    recent_v = recent_turns(session_id, state.turn_count, window_turns=window_turns)
    from karma.rule import format_for_injection
    additional_context = format_for_injection(sticky_list, recent_v)

    # 注入后更新 last_reinject_byte_seq — 下次累积重新计算
    state.last_reinject_byte_seq = state.tool_byte_seq
    return additional_context


if __name__ == "__main__":
    sys.exit(main())
