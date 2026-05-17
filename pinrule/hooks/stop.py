"""Stop hook — Agent 响应完成后扫违反。

跨 backend 协议（Claude Code / Codex 兼容）：
- Claude Code stdin: {session_id, transcript_path, cwd, ...}（没有 response 字段）
  → 反向读 transcript_path JSONL 取最后一条 assistant message
- Codex stdin: {session_id, cwd, hook_event_name, model, turn_id, stop_hook_active,
                last_assistant_message}
  → 直接用 last_assistant_message 字段（pinrule 不用读 transcript，性能更好）
- 共享 stdout: {"hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": "..."}}
  + 共享 decision/reason/continue 等 block 字段
"""

from __future__ import annotations

import json
import os
import sys
import time

from pinrule import session_state
from pinrule.checks import run_checks
from pinrule.i18n import tr
from pinrule.notify import notify
from pinrule.rule import RuleConfigError, load
from pinrule.violations import Violation, append, count_recent, count_recent_turns, detect

# 累积告警 default 阈值（fallback，实际从 pinrule.config 读）
# 优先用 turn 维度（更符合 Agent 漂移视角）；ts 维度保留为 fallback
_ESCALATE_WINDOW_TURNS = 3
_ESCALATE_THRESHOLD = 3


def _read_last_assistant_response(transcript_path: str) -> str:
    """读 transcript JSONL，取最后一条 assistant message 的所有 text content。"""
    from pinrule.hooks._transcript import read_last_message_text
    return read_last_message_text(transcript_path, "assistant")


def _read_last_user_prompt(transcript_path: str) -> str:
    """v0.4.41: 读 transcript JSONL，取最后一条 user message 的 text content
    让 keep_pushing.check 能识别用户上 turn 叫停字眼（HANDOFF v3 第三步候选）。
    """
    from pinrule.hooks._transcript import read_last_message_text
    return read_last_message_text(transcript_path, "user")


def _emit_notifications(
    check_hits: list,
    keyword_violations: list,
    seen_ids: set,
    hit_sticky_ids: set,
    state,
    session_id: str,
) -> None:
    """stderr + 桌面通知 + 累积告警升级。

    - stderr 每条违反详情（含 suggested_fix）
    - 桌面通知合并多条避免轰炸 (fail open)
    - 命中 + 窗口内已累积超阈值 → 升级 🚨 严重通知
    """
    notify_msgs: list[str] = []
    for h in check_hits:
        line = tr("hook.stop.violation_line", rule_id=h.rule_id, trigger=h.trigger)
        print(line, file=sys.stderr)
        notify_msgs.append(f"{h.rule_id} — {h.trigger}")
        if h.suggested_fix:
            print(tr("hook.stop.suggestion_line", fix=h.suggested_fix), file=sys.stderr)
    for v in keyword_violations:
        if v.rule_id in seen_ids:
            continue
        line = tr("hook.stop.keyword_line", rule_id=v.rule_id, trigger=v.trigger)
        print(line, file=sys.stderr)
        notify_msgs.append(f"{v.rule_id} — {v.trigger}")

    if not notify_msgs:
        return

    try:
        from pinrule.config import load as _load_config
        cfg = _load_config()
        window_turns = int(cfg.get("escalate_window_turns", _ESCALATE_WINDOW_TURNS))
        threshold = cfg["escalate_threshold"]
    except Exception:
        window_turns = _ESCALATE_WINDOW_TURNS
        threshold = _ESCALATE_THRESHOLD
    # 按 turn 距离统计（不是人类时钟）— Agent 漂移按 turn 累积
    if state.turn_count > 0:
        counts = count_recent_turns(session_id, state.turn_count, window_turns=window_turns)
    else:
        counts = count_recent(window_sec=1800)  # 早期 fallback
    escalated_ids = [sid for sid in hit_sticky_ids if counts.get(sid, 0) >= threshold]
    if escalated_ids:
        notify(
            f"🚨 pinrule 严重 — 累积违反 {len(escalated_ids)} 条",
            " / ".join(f"{sid} (×{counts[sid]})" for sid in escalated_ids[:3]),
        )
    else:
        notify("pinrule 检测违反", " / ".join(notify_msgs[:3]))


def _handle_force_block(
    state,
    sticky_list,
    hit_sticky_ids: set,
    session_id: str,
    payload: dict | None = None,
) -> bool:
    """累积强制 block — 同规则累积违反超阈值 → 输出 decision=block 强制查根因。

    返回 True 表示已 print decision=block，调用方应 return 0。

    v0.4.16 原因 fix：只惩罚「当前 turn 触发 + 历史累积超阈值」的规则，
    不惩罚「已修原因不再触发但历史在窗口内」的规则（否则 fix 后仍卡死循环）。
    `force_block_exempt: true` 的规则（如 keep-pushing-no-stop）整条豁免。
    """
    try:
        from pinrule.config import load as _load_config
        _cfg = _load_config()
        force_threshold = int(_cfg.get("force_block_threshold", 5))
        force_window = int(_cfg.get("escalate_window_turns", 3))
        block_max = int(_cfg.get("stop_block_max_per_turn", 2))
    except Exception:
        force_threshold = 5
        force_window = 3
        block_max = 2

    if force_threshold <= 0 or state.turn_count <= 0:
        return False

    counts_force = count_recent_turns(session_id, state.turn_count, window_turns=force_window)
    exempt_ids = {s.id for s in sticky_list if s.force_block_exempt}
    over_threshold = [
        sid for sid, n in counts_force.items()
        if n >= force_threshold and sid not in exempt_ids
        and sid in hit_sticky_ids  # 当前 turn 触发该规则才 force_block
    ]
    # 短路 (优化): 没超阈值的 rule 就不进 atomic check
    if not over_threshold:
        return False

    # v0.16.6 TOCTOU fix: 原子 check + bump 在 update_state lock 内. 之前
    # `state.stop_block_count >= block_max` 在 lock 外, 多个 Stop hook 并发
    # 时两个进程都各自读 count=1 → 都通过 check → 各 bump → 真 count=3 超 max=2.
    # 修法: check + bump 合并 fn, fn 内 atomic, caller 看 count 真涨没决定是否打印 block.
    old_count = state.stop_block_count
    def _check_and_bump(s):
        if s.stop_block_count < block_max:
            s.stop_block_count += 1
        # else: 已超 max, no-op (let caller see count didn't change)
    try:
        updated_state, _ = session_state.update_state(
            state.session_id, _check_and_bump, agent_id=state.agent_id,
        )
        state.stop_block_count = updated_state.stop_block_count
    except OSError:
        # update_state save 失败 fallback 内存自增 (race 风险但比卡用户好)
        if state.stop_block_count < block_max:
            state.stop_block_count += 1
    # 真 bump 才打印 block; race 中其他进程已先 bump 到 max → 这次 no-op
    if state.stop_block_count == old_count:
        return False
    reason = (
        f"pinrule 强制干预：累积违反 {over_threshold} 共 {sum(counts_force[s] for s in over_threshold)} 次。"
        f"必须 fix 原因（深挖 pattern / 工程 bug / 协议）或显式让用户介入。"
        f"禁止继续绕（手动改 pinrule 状态 / 临时改 rules.yaml）。"
    )
    # v0.10.6 (Agent 2 F3 fix): 走 protocol_adapter.emit_stop_block —
    # Cursor stop 用 followup_message; backend 自己决定 fail-open shape.
    from pinrule.backends.protocol_adapter import emit_stop_block
    print(emit_stop_block(reason, payload or {}))
    return True


def _handle_keep_pushing_block(
    check_hits: list,
    keyword_violations: list,
    state,
    payload: dict | None = None,
) -> bool:
    """keep-pushing 干预 — Agent 沉默式停下时让继续生成。

    返回 True 表示已 print decision=block，调用方应 return 0。
    """
    keep_pushing_hit = any(h.rule_id == "keep-pushing-no-stop" for h in check_hits) or \
        any(v.rule_id == "keep-pushing-no-stop" for v in keyword_violations)
    if not keep_pushing_hit:
        return False

    try:
        from pinrule.config import load as _load_config
        block_max = int(_load_config().get("stop_block_max_per_turn", 2))
    except Exception:
        block_max = 2

    if block_max <= 0:
        return False

    # v0.16.6 TOCTOU fix (same pattern as _handle_force_block): atomic
    # check + bump in update_state lock to prevent concurrent Stop hooks
    # bumping past block_max.
    old_count = state.stop_block_count
    def _check_and_bump(s):
        if s.stop_block_count < block_max:
            s.stop_block_count += 1
    try:
        updated_state, _ = session_state.update_state(
            state.session_id, _check_and_bump, agent_id=state.agent_id,
        )
        state.stop_block_count = updated_state.stop_block_count
    except OSError:
        if state.stop_block_count < block_max:
            state.stop_block_count += 1
    if state.stop_block_count == old_count:
        return False
    from pinrule.i18n import tr
    reason = tr(
        "stop.reason",
        count=state.stop_block_count,
        max=block_max,
    )
    from pinrule.backends.protocol_adapter import emit_stop_block
    print(emit_stop_block(reason, payload or {}))
    return True


def audit_agent_response(
    payload: dict,
    response: str,
    last_user_prompt: str = "",
    *,
    allow_stop_interventions: bool = True,
) -> bool:
    """Response-level checks — shared by Stop and Cursor afterAgentResponse.

    返 True = 已 print stop_block 干预 (main 不要再 print 兜底 {}),
    False = 没 print (caller 可兜底 print({})).
    """
    from pinrule.hooks._payload import extract_session_id, extract_subagent_id
    session_id = extract_session_id(payload)
    agent_id = extract_subagent_id(payload) or None

    try:
        sticky_list = load()
    except RuleConfigError as e:
        print(f"pinrule: {e}", file=sys.stderr)
        return False

    if not sticky_list or not (response or "").strip():
        return False

    try:
        state, _ = session_state.update_state(
            session_id,
            lambda s: s.catchup_pending_bg(),
            agent_id=agent_id,
        )
    except Exception as e:
        print(
            f"pinrule response audit: catchup_pending_bg 失败 fallback ({e})",
            file=sys.stderr,
        )
        state = session_state.load(session_id, agent_id=agent_id)

    check_hits = []
    for s in sticky_list:
        if not s.violation_checks:
            continue
        hits = run_checks(
            s.violation_checks,
            response=response,
            user_prompt=last_user_prompt,
            session_state=state,
            rule_id=s.id,
        )
        check_hits.extend(hits)

    keyword_violations = detect(
        response, sticky_list, session_id=session_id,
        turn=state.turn_count, agent_id=agent_id,
    )

    if not check_hits and not keyword_violations:
        return False

    all_records: list[Violation] = []
    for h in check_hits:
        all_records.append(Violation(
            ts=int(time.time()), session_id=session_id, rule_id=h.rule_id,
            trigger=h.trigger, snippet=h.snippet, turn=state.turn_count,
            agent_id=agent_id,
            trigger_key=h.trigger_key,
        ))
    seen_ids = {h.rule_id for h in check_hits}
    for v in keyword_violations:
        if v.rule_id not in seen_ids:
            all_records.append(v)
    if all_records:
        append(all_records)

    hit_sticky_ids = {h.rule_id for h in check_hits} | {
        v.rule_id for v in keyword_violations if v.rule_id not in seen_ids
    }

    _emit_notifications(
        check_hits, keyword_violations, seen_ids, hit_sticky_ids, state, session_id,
    )

    if not allow_stop_interventions:
        return False

    if _handle_force_block(state, sticky_list, hit_sticky_ids, session_id, payload):
        return True  # _handle 内部已 print emit_stop_block, main 不要再 print {}

    if _handle_keep_pushing_block(check_hits, keyword_violations, state, payload):
        return True

    return False


def main() -> int:
    try:
        return _main_inner()
    except Exception as e:
        # v0.16.6 fail-open: 任何异常 → 输出空 passthrough, 不卡客户端 Stop event
        # (Cursor 协议下 Stop 非 0 会 retry, Claude Code 不阻塞但 UI 噪声).
        try:
            print(json.dumps({}))
        except Exception:
            pass
        print(f"pinrule Stop fail-open: {type(e).__name__}: {e}", file=sys.stderr)
        return 0


def _main_inner() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"pinrule Stop: 输入 JSON 解析失败 ({e})", file=sys.stderr)
        print(json.dumps({}))
        return 0

    # 可选 debug trace — 仅当 PINRULE_DEBUG_TRACE 环境变量指向可写路径时启用
    # 不写死 /tmp 路径（跨平台 / 多用户机器互相覆盖）。production 默认完全关。
    _trace_path = os.environ.get("PINRULE_DEBUG_TRACE")
    if _trace_path:
        try:
            import time as _t
            from pathlib import Path as _P
            with _P(_trace_path).open("a", encoding="utf-8") as f:
                f.write(f"[{_t.strftime('%H:%M:%S')}] Stop hook fired, session={payload.get('session_id', '')!r}\n")
        except OSError:
            pass

    # session_id 在 line 220 已通过 extract_session_id 定义, 这里不重复.
    # 跨 backend payload 字段适配 — 优先「直传 message」字段，fallback transcript
    # - Codex Stop: last_assistant_message
    # (历史: Gemini AfterAgent 用 prompt_response, v0.13.2 砍掉)
    # - Claude Code Stop: 没直传，要 transcript_path 反向读最后 assistant message
    response = (
        payload.get("last_assistant_message", "")
        or payload.get("prompt_response", "")
        or _read_last_assistant_response(payload.get("transcript_path", ""))
    )

    # v0.4.41: 拿用户上 turn prompt 让 keep_pushing.check 识别叫停字眼
    # 原因：HANDOFF v3 第三步候选 — keep_pushing 只看 Agent response 末尾，
    # 看不到 user 上文「不用啦 / 休息吧 / 明天再说」叫停字面 → 反思 hook
    # 反复触发即使用户已明确叫停（sticky #8 例外条件命中但 check 不知道）。
    last_user_prompt = (
        payload.get("user_prompt", "")
        or payload.get("prompt", "")
        or _read_last_user_prompt(payload.get("transcript_path", ""))
    )

    if not response:
        print(json.dumps({}))
        return 0

    intervened = audit_agent_response(
        payload, response, last_user_prompt, allow_stop_interventions=True,
    )
    if not intervened:
        # audit 没 print 干预 → 兜底 print {} 让 hook 协议有合法 stdout
        print(json.dumps({}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
