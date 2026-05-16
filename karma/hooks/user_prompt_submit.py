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
from karma.rule import RuleConfigError, format_anchor_only, load
from karma.violations import recent, recent_turns


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
        from karma.model_threshold import model_from_payload
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
        from karma.checks import run_checks
        tp = _Path(transcript_path)
        if not tp.exists():
            return ""
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
            from karma.violations import Violation as _V, append as _v_append
            # v0.9.12 bug fix: 之前漏传 trigger_key 让 engine check 命中被错归
            # 「keyword-only」桶（v0.9.11 audit --by-check 暴露了这个数据归类
            # bug — 86% violation 被错归 keyword-only，实际大部分是 engine
            # check 真触发只是字段缺失）。trigger_key 来自 CheckHit，跟
            # pre_tool_use.py / stop.py 写 Violation 一致传递。
            recs = [_V(
                ts=int(_time.time()), session_id=session_id,
                rule_id=h.rule_id, trigger=h.trigger,
                snippet=h.snippet, turn=current_turn,
                trigger_key=h.trigger_key,  # v0.5.7: locale-agnostic 分组 key
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
        return "\n".join(reminder_lines)
    except Exception:
        return ""


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
    current_turn, state = _advance_turn_state(session_id, payload)

    # 偏离回顾标记 — 按 turn 距离查最近违反（不是人类时钟）
    # 默认 5 turn 内违反过的规则标偏离回顾。窗口可配。
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
    # v0.9.0: 每 turn 注入**精简 anchor**（id + 第一行 + 偏离回顾标记），
    # 完整 preference 由 SessionStart baseline 一次注入进 history 持续可见。
    # 长 session 累积达模型阈值（Opus 60K / Sonnet 40K / Haiku 30K）后
    # PostToolUse 中段全量补一次抗稀释。
    additional_context = format_anchor_only(sticky_list, recent_v)

    # 强提醒 fallback：跑上一 response 通过所有规则的 violation_checks (拆 helper: v0.8.3)
    transcript_path = payload.get("transcript_path", "")
    if state is not None:
        additional_context += _build_strong_reminder(
            transcript_path, sticky_list, state, session_id, current_turn,
        )

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": additional_context,
        }
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
