"""UserPromptSubmit hook — 给 Claude 注入 sticky 提示作为 additionalContext。

Claude Code 实际协议（2026-05）：
- stdin payload 字段: prompt (不是 user_text), session_id, transcript_path, cwd, ...
- stdout 输出: {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "..."}}
- additionalContext 作为 system message context 给 Claude 看（不修改 user_text 本身）

性能预算：< 50ms
"""

from __future__ import annotations

import json
import sys

from pinrule import session_state
from pinrule.session_state import purge_old_states
from pinrule.rule import RuleConfigError, format_anchor_only, load


def _output_passthrough() -> None:
    """没规则 / 配置错 → 不输出 additionalContext，passthrough。"""
    print(json.dumps({}))


def _advance_turn_state(session_id: str, payload: dict):
    """每 turn 推进 session state — turn_count + 1，干预计数清 0，model 探测。

    v0.4.32 中段注入 token 启发式：每 turn 起手 token 累积归零 + 上次注入
    位置归零，让 turn 内累积达阈值才中段注入第一次（每 turn 起手 sticky
    已全量注入过 — 中段注入是「衰减后重新锚定」补丁）。

    v0.4.39 用 transcript_path 路径探 model（user_prompt_submit payload
    没 model 字段，需读 transcript jsonl 找最后一条 assistant model 字面）。

    v0.9.8: 用 update_state 让 load → modify → save 整段对同 session atomic
    （多 hook 同时跑时不丢更新）。

    返回 (current_turn, state) — 失败时 (0, None) 让调用方 fallback。
    """
    def _advance(state):
        state.catchup_pending_bg()
        state.turn_count += 1
        state.stop_block_count = 0
        # v0.9.0: tool_byte_seq / last_reinject_byte_seq **不再每 turn 重置** —
        # 改成 session 全局累积，让中段全量 reinject 按 session 视角触发。
        # 旧 v0.4.32 设计每 turn 重置是因为「每 turn 起手已全量注入」假设，
        # v0.9.0 改成 SessionStart 一次全量 + 每 turn 精简 anchor，全量注入
        # 是稀疏事件 — 累积视角必须跨 turn 才能正确按 60K Opus 阈值触发。
        #
        # v0.10.4: 用统一 model_from_payload — Codex 每个 UserPromptSubmit hook
        # payload 都含 active model slug (含中途 /model 切换后的新值), 不依赖
        # transcript 格式稳定性. Claude payload 没 model 时仍走 transcript fallback.
        from pinrule.model_threshold import model_from_payload
        new_model = model_from_payload(payload)
        if new_model:
            state.model = new_model

    try:
        state, _ = session_state.update_state(session_id, _advance)
        return state.turn_count, state
    except Exception:
        return 0, None


def _build_strong_reminder(
    transcript_path: str,
    sticky_list,
    state,
    session_id: str,
    current_turn: int,
) -> str:
    """跑上一 assistant response 的 violation_checks → 拼合作回顾强提醒文本。

    这是 Stop hook 在 user 立刻接 prompt 时不跑的协议 limitation 完整 fallback —
    覆盖 keep-pushing / chinese-plain / evidence 等所有 response 类 check。

    返回拼好的强提醒文本（含 i18n 头尾）；无命中或读 transcript 失败时返回 ""。
    """
    if not transcript_path:
        return ""
    try:
        from pathlib import Path as _Path
        from pinrule.checks import run_checks
        tp = _Path(transcript_path)
        if not tp.exists():
            return ""
        from pinrule.hooks._transcript import read_last_message_text
        last_text = read_last_message_text(str(tp), "assistant")
        if not last_text:
            return ""
        # 跑所有规则的 violation_checks 看上一 response
        all_hits = []
        for s in sticky_list:
            if not s.violation_checks:
                continue
            hits = run_checks(
                s.violation_checks,
                response=last_text,
                session_state=state,
                rule_id=s.id,
            )
            all_hits.extend(hits)
        if not all_hits:
            return ""
        # 写到 violations.jsonl 让 stats/audit 反映实战触发（fallback for
        # Stop hook 实战不跑导致违反没记录）
        try:
            import time as _time
            from pinrule.violations import Violation as _V, append as _v_append
            # v0.9.12 bug fix: 之前漏传 trigger_key 让 engine check 命中被错归
            # 「keyword-only」桶（v0.9.11 audit --by-check 暴露了这个数据归类
            # bug — 86% violation 被错归 keyword-only，实际大部分是 engine
            # check 真触发只是字段缺失）。trigger_key 来自 CheckHit，跟
            # pre_tool_use.py / stop.py 写 Violation 一致传递。
            # v0.10.5 (Agent 1 F1.3 fix): _advance_turn_state 已经把 turn_count
            # 推 N → N+1, 但 strong_reminder 扫的是**上一 turn** (N) 的 assistant
            # response. Violation 应该归属于产生它的 turn (N) 不是 user 新输入
            # 创建的 turn (N+1). 用 max(0, current_turn - 1) 修正 turn 归属让
            # recent_turns / force_block 窗口数学正确. 同 v0.9.13 B1 off-by-one 族.
            prev_turn = max(0, current_turn - 1)
            recs = [_V(
                ts=int(_time.time()), session_id=session_id,
                rule_id=h.rule_id, trigger=h.trigger,
                snippet=h.snippet, turn=prev_turn,
                trigger_key=h.trigger_key,  # v0.5.7: locale-agnostic 分组 key
            ) for h in all_hits]
            _v_append(recs)
        except Exception:
            pass
        # v0.5.2 i18n: 合作回顾语气强提醒切 locale (en/zh)
        from pinrule.i18n import tr
        reminder_lines = [
            tr("strong_reminder.header.title"),
            tr("strong_reminder.header.line"),
        ]
        for h in all_hits[:5]:  # 最多 5 条避免淹没
            reminder_lines.append(f"\n  ▸ {h.rule_id}")
            reminder_lines.append(f"    {h.trigger}")
            if h.suggested_fix:
                reminder_lines.append(f"    {h.suggested_fix}")
        reminder_lines.append(tr("strong_reminder.footer"))
        return "\n".join(reminder_lines)
    except Exception:
        return ""


def main() -> int:
    try:
        return _main_inner()
    except Exception as e:
        # v0.16.6 fail-open: 任何异常 → passthrough, 不卡客户端 UserPromptSubmit
        # (Cursor 协议下 beforeSubmitPrompt 非 0 = block prompt, 等于输入框失灵).
        try:
            _output_passthrough()
        except Exception:
            print(json.dumps({}))
        print(f"pinrule UserPromptSubmit fail-open: {type(e).__name__}: {e}", file=sys.stderr)
        return 0


def _main_inner() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"pinrule UserPromptSubmit: 输入 JSON 解析失败 ({e})", file=sys.stderr)
        _output_passthrough()
        return 0

    # 实际 prompt 在 'prompt' 字段
    _ = payload.get("prompt", "")  # 不需要 — 我们只注入 additionalContext

    # 每 turn 清理一次老 session-state 文件（清理周期从 config 读，默认 30 天）。
    # 异常不该阻塞 sticky 注入。
    try:
        from pinrule.config import load as _load_config
        cfg = _load_config()
        purge_old_states(max_age_days=cfg["session_state_max_age_days"])
    except Exception:
        try:
            purge_old_states(max_age_days=30)
        except Exception:
            pass

    # 每 turn 给 session_state.turn_count + 1 — 给后续按 turn 距离的违反统计
    # 同时重置 stop_block_count（新 user prompt = 新 turn，干预计数清 0）
    # 顺便 catchup pending background 任务（task #8：catchup 之前只在 PostToolUse
    # 跑，bg 完成后第一个触发的 hook 可能是这里 / pre_tool_use，要多 hook 都跑）
    #
    # v0.11.2 fix: turn / model telemetry 早于 rules.json 加载. pinrule 系统级
    # 状态 (turn_count / model / pending_bg_tasks) 跟用户有没有装 rules 无关 —
    # 即使 rules 为空也要推进, 否则空 rules 用户的所有 model-aware reinject 阈值 +
    # turn-based 违反窗口都失效. 上一版顺序错: 没 rules 就早 return, model 永远
    # 没写进 state. CI clean home 永远捕不到 model.
    from pinrule.hooks._payload import extract_session_id
    session_id = extract_session_id(payload)
    current_turn, state = _advance_turn_state(session_id, payload)

    try:
        sticky_list = load()
    except RuleConfigError as e:
        print(f"pinrule: {e}", file=sys.stderr)
        _output_passthrough()
        return 0

    if not sticky_list:
        _output_passthrough()
        return 0

    from pinrule.backends.protocol_adapter import detect_backend
    from pinrule.rule import format_for_injection, format_rule_id_catalog
    from pinrule.violations import session_violations as _session_violations

    violated = _session_violations(session_id)
    is_cursor = detect_backend(payload) == "cursor"
    if is_cursor:
        # Cursor: sessionStart 注入常进不了模型上下文; v0.13.0 anchor-only
        # passthrough 让新会话 beforeSubmitPrompt 输出 {"continue":true} 零规则可见.
        parts = [format_rule_id_catalog(sticky_list)]
        if current_turn <= 1:
            parts.append(format_for_injection(sticky_list))
        else:
            anchor = format_anchor_only(sticky_list, violated)
            if anchor:
                parts.append(anchor)
        additional_context = "\n\n".join(p for p in parts if p.strip())
    else:
        # Claude/Codex: v0.13.0 anchor 只列本 session 违反过的 rule.
        additional_context = format_anchor_only(sticky_list, violated)

    # 强提醒 fallback：跑上一 response 通过所有规则的 violation_checks (拆 helper: v0.8.3)
    transcript_path = payload.get("transcript_path", "")
    if state is not None:
        additional_context += _build_strong_reminder(
            transcript_path, sticky_list, state, session_id, current_turn,
        )

    # v0.10.6: 走 protocol_adapter — backend 决定 output shape.
    # v0.12.2 Cursor: hook_event_name=beforeSubmitPrompt, 同一 main().
    from pinrule.backends.protocol_adapter import emit_context_injection
    event_name = payload.get("hook_event_name") or "UserPromptSubmit"
    print(emit_context_injection(event_name, additional_context, payload))
    return 0


if __name__ == "__main__":
    sys.exit(main())
