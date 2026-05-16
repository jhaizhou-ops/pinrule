"""SubagentStart hook — 子 Agent 启动时注入 sticky baseline（karma v3 第六步）。

Claude Code 协议:
- stdin payload: {agent_id, agent_type, session_id, transcript_path, ...}
- stdout: {"hookSpecificOutput": {"hookEventName": "SubagentStart",
           "additionalContext": "..."}}
- additionalContext 注入到子 Agent 的上下文（不是主 Agent）— 让子 Agent 在
  隔离 context 中仍按 sticky 方向跑

设计（v0.4.30 first pass）：
- 简单序列化 sticky 摘要（id + 第一行 preference）传给子 Agent
- 用 ensure_ascii=False 输出utf-8 中文（早期 stub 没加，子 Agent 收到 `\\uXXXX`
  转义乱码看不懂）

Fail open：异常 / 配置坏 → passthrough 不阻塞子 Agent 启动。
"""

from __future__ import annotations

import json
import sys

from karma.rule import load as load_sticky


def _passthrough() -> None:
    print(json.dumps({}))


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"karma SubagentStart: 输入 JSON 解析失败 ({e})", file=sys.stderr)
        _passthrough()
        return 0

    # v0.4.37 子 Agent model 捕获到：主 Agent PreToolUse(Agent, model=X) 入队
    # pending_subagent_models，本 SubagentStart pop 队首写子 Agent state.model
    # 让按模型阈值（Opus 80K / Sonnet 60K / Haiku 30K）。FIFO 假设并行 Task
    # 触发顺序跟 PreToolUse 入队顺序一致（dogfooding 持续观察）。
    session_id = payload.get("session_id", "") or "default"
    agent_id = payload.get("agent_id") or None
    if agent_id:
        try:
            # v0.9.8: 用 update_state 让两段 load+save 都跨进程并发安全。
            # 主 state pop 跟子 state 写是不同 (session, agent_id) key，
            # 两把独立 lock 互不阻塞，但各自 load→modify→save 整段原子。
            from karma import session_state

            captured: dict = {}

            def _pop_sub_model(state):
                if state.pending_subagent_models:
                    captured["sub_model"] = state.pending_subagent_models.pop(0)

            session_state.update_state(session_id, _pop_sub_model)

            sub_model = captured.get("sub_model")
            if sub_model:
                def _set_sub_model(state):
                    state.model = sub_model
                session_state.update_state(session_id, _set_sub_model, agent_id=agent_id)
        except Exception as e:
            print(f"karma SubagentStart: pop 子 Agent model 失败 ({e})", file=sys.stderr)
            # 失败不阻塞 sticky baseline 注入

    try:
        rule_list = load_sticky()
    except Exception as e:
        print(f"karma SubagentStart: 规则加载失败 ({e})", file=sys.stderr)
        _passthrough()
        return 0

    if not rule_list:
        _passthrough()
        return 0

    # v0.5.2 i18n: 合作默契语气切 locale (en/zh)
    from karma.i18n import tr
    lines = [tr("subagent_start.title")]
    for s in rule_list:
        first_line = s.preference.strip().split("\n")[0]
        lines.append(f"  ▸ {s.id}: {first_line}")
    lines.append(tr("subagent_start.tail"))

    # v0.10.6 (Agent 2 F2.2 fix): 走 protocol_adapter.emit_context_injection
    from karma.backends.protocol_adapter import emit_context_injection
    print(emit_context_injection("SubagentStart", "\n".join(lines), payload))
    return 0


if __name__ == "__main__":
    sys.exit(main())
