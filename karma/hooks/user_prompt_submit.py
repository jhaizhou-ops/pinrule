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

from karma import session_state
from karma.session_state import purge_old_states
from karma.rule import RuleConfigError, format_for_injection, load
from karma.violations import recent, recent_turns


def _output_passthrough() -> None:
    """没 sticky / 配置错 → 不输出 additionalContext，passthrough。"""
    print(json.dumps({}))


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"karma UserPromptSubmit: 输入 JSON 解析失败 ({e})", file=sys.stderr)
        _output_passthrough()
        return 0

    # 实际 prompt 在 'prompt' 字段
    _ = payload.get("prompt", "")  # 不需要 — 我们只注入 additionalContext

    # 每 turn 清理一次老 session-state 文件（清理周期从 config 读，默认 30 天）。
    # 异常不该阻塞 sticky 注入。
    try:
        from karma.config import load as _load_config
        cfg = _load_config()
        purge_old_states(max_age_days=cfg["session_state_max_age_days"])
    except Exception:
        try:
            purge_old_states(max_age_days=30)
        except Exception:
            pass

    try:
        sticky_list = load()
    except RuleConfigError as e:
        print(f"karma: {e}", file=sys.stderr)
        _output_passthrough()
        return 0

    if not sticky_list:
        _output_passthrough()
        return 0

    # 每 turn 给 session_state.turn_count + 1 — 给后续按 turn 距离的违反统计
    # 同时重置 stop_block_count（新 user prompt = 新 turn，干预计数清 0）
    # 顺便 catchup pending background 任务（task #8：catchup 之前只在 PostToolUse
    # 跑，bg 完成后第一个触发的 hook 可能是这里 / pre_tool_use，要多 hook 都跑）
    session_id = payload.get("session_id", "") or "default"

    try:
        state = session_state.load(session_id)
        state.catchup_pending_bg()
        state.turn_count += 1
        state.stop_block_count = 0
        # v0.4.32 中段注入 token 启发式：每 turn 起手 token 累积归零 +
        # 上次注入位置归零，让 turn 内累积达阈值才中段注入第一次（每 turn
        # 起手 sticky 已全量注入过 — 中段注入是「衰减后重新锚定」补丁）
        state.tool_byte_seq = 0
        state.last_reinject_byte_seq = 0
        # v0.4.39 根本本路径：user_prompt_submit payload 没 model 字段（dogfooding
        # 验证 — 7 turn 跑下来 state.model 仍 None 证明 payload 没 model）。
        # 改用 transcript_path 路径 — 所有 hook payload 有 transcript_path，
        # 读 jsonl 找最后一条 assistant model 字面。这覆盖 SessionStart 后中途
        # /model 切换场景（v0.4.38 user_prompt_submit payload model 字段路径走
        # 不通的原因 fix）。
        transcript_path = payload.get("transcript_path")
        if transcript_path:
            from karma.model_threshold import extract_model_from_transcript
            new_model = extract_model_from_transcript(transcript_path)
            if new_model:
                state.model = new_model
        session_state.save(state)
        current_turn = state.turn_count
    except Exception:
        current_turn = 0

    # ⚠️ 标记 — 按 turn 距离查最近违反（不是人类时钟）
    # 默认 5 turn 内违反过的 sticky 标 ⚠️。窗口可配。
    try:
        from karma.config import load as _load_config
        cfg = _load_config()
        window_turns = int(cfg.get("recent_violation_turns", 5))
    except Exception:
        window_turns = 5
    if current_turn > 0:
        recent_v = recent_turns(session_id, current_turn, window_turns=window_turns)
    else:
        recent_v = recent()  # 早期 fallback 用人类时钟（首次 install 没 turn 计数）
    additional_context = format_for_injection(sticky_list, recent_v)

    # 额外检测：跑上一 response 通过所有 sticky 的 violation_checks，把命中的强提醒
    # 注入到本 turn。这是 Stop hook 在 user 立刻接 prompt 时不跑的协议 limitation
    # 的完整 fallback — 覆盖 keep-pushing / chinese-plain / evidence 等所有 response 类 check
    transcript_path = payload.get("transcript_path", "")
    if transcript_path:
        try:
            from pathlib import Path as _Path
            from karma.checks import run_checks
            tp = _Path(transcript_path)
            if tp.exists():
                # 反向找 last assistant message
                lines = tp.read_text(encoding="utf-8").splitlines()
                last_text = ""
                for ln in reversed(lines):
                    try:
                        d = json.loads(ln.strip())
                    except json.JSONDecodeError:
                        continue
                    if d.get("type") != "assistant":
                        continue
                    msg = d.get("message", {})
                    content = msg.get("content", [])
                    if isinstance(content, list):
                        parts = [c.get("text", "") for c in content
                                 if isinstance(c, dict) and c.get("type") == "text"]
                        last_text = "\n".join(parts)
                    elif isinstance(content, str):
                        last_text = content
                    break
                if last_text:
                    # 跑所有 sticky 的 violation_checks 看上一 response
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
                    if all_hits:
                        # 写到 violations.jsonl 让 stats/audit 反映实战触发（fallback for
                        # Stop hook 实战不跑导致违反没记录）
                        try:
                            import time as _time
                            from karma.violations import Violation as _V, append as _v_append
                            recs = [_V(
                                ts=int(_time.time()), session_id=session_id,
                                rule_id=h.rule_id, trigger=h.trigger,
                                snippet=h.snippet, turn=current_turn,
                            ) for h in all_hits]
                            _v_append(recs)
                        except Exception:
                            pass
                        # v0.5.2 i18n: 合作回顾语气强提醒切 locale (en/zh)
                        from karma.i18n import tr
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
                        additional_context += "\n".join(reminder_lines)
        except Exception:
            pass

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": additional_context,
        }
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
