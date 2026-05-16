"""Stop hook — Agent 响应完成后扫违反。

跨 backend 协议（Claude Code / Codex 兼容）：
- Claude Code stdin: {session_id, transcript_path, cwd, ...}（没有 response 字段）
  → 反向读 transcript_path JSONL 取最后一条 assistant message
- Codex stdin: {session_id, cwd, hook_event_name, model, turn_id, stop_hook_active,
                last_assistant_message}
  → 直接用 last_assistant_message 字段（karma 不用读 transcript，性能更好）
- 共享 stdout: {"hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": "..."}}
  + 共享 decision/reason/continue 等 block 字段
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from karma import session_state
from karma.checks import run_checks
from karma.notify import notify
from karma.rule import RuleConfigError, load
from karma.violations import Violation, append, count_recent, count_recent_turns, detect

# 累积告警 default 阈值（fallback，实际从 karma.config 读）
# 优先用 turn 维度（更符合 Agent 漂移视角）；ts 维度保留为 fallback
_ESCALATE_WINDOW_TURNS = 3
_ESCALATE_THRESHOLD = 3


def _read_last_assistant_response(transcript_path: str) -> str:
    """读 transcript JSONL，取最后一条 assistant message 的所有 text content。"""
    return _read_last_message_text(transcript_path, msg_type="assistant")


def _read_last_user_prompt(transcript_path: str) -> str:
    """v0.4.41: 读 transcript JSONL，取最后一条 user message 的 text content
    让 keep_pushing.check 能识别用户上 turn 叫停字眼（HANDOFF v3 第三步候选）。
    """
    return _read_last_message_text(transcript_path, msg_type="user")


def _read_last_message_text(transcript_path: str, msg_type: str) -> str:
    """通用反向 scan transcript JSONL 找最后一条指定 type message 的 text content。"""
    if not transcript_path:
        return ""
    p = Path(transcript_path)
    if not p.exists():
        return ""
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
        for ln in reversed(lines):
            ln = ln.strip()
            if not ln:
                continue
            try:
                d = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if d.get("type") != msg_type:
                continue
            msg = d.get("message", {})
            content = msg.get("content")
            if isinstance(content, list):
                text_parts = []
                for c in content:
                    if isinstance(c, dict) and c.get("type") == "text":
                        text_parts.append(c.get("text", ""))
                return "\n".join(text_parts)
            if isinstance(content, str):
                return content
            return ""
    except OSError:
        return ""
    return ""


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
        line = f"⚠️ karma: Agent 违反 {h.rule_id!r} — {h.trigger}"
        print(line, file=sys.stderr)
        notify_msgs.append(f"{h.rule_id} — {h.trigger}")
        if h.suggested_fix:
            print(f"   建议：{h.suggested_fix}", file=sys.stderr)
    for v in keyword_violations:
        if v.rule_id in seen_ids:
            continue
        line = f"⚠️ karma: Agent 触发关键词 {v.rule_id!r} (词 {v.trigger!r})"
        print(line, file=sys.stderr)
        notify_msgs.append(f"{v.rule_id} — {v.trigger}")

    if not notify_msgs:
        return

    try:
        from karma.config import load as _load_config
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
            f"🚨 karma 严重 — 累积违反 {len(escalated_ids)} 条",
            " / ".join(f"{sid} (×{counts[sid]})" for sid in escalated_ids[:3]),
        )
    else:
        notify("karma 检测违反", " / ".join(notify_msgs[:3]))


def _handle_force_block(
    state,
    sticky_list,
    hit_sticky_ids: set,
    session_id: str,
) -> bool:
    """累积强制 block — 同规则累积违反超阈值 → 输出 decision=block 强制查根因。

    返回 True 表示已 print decision=block，调用方应 return 0。

    v0.4.16 原因 fix：只惩罚「当前 turn 触发 + 历史累积超阈值」的规则，
    不惩罚「已修原因不再触发但历史在窗口内」的规则（否则 fix 后仍卡死循环）。
    `force_block_exempt: true` 的规则（如 keep-pushing-no-stop）整条豁免。
    """
    try:
        from karma.config import load as _load_config
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
    if not over_threshold or state.stop_block_count >= block_max:
        return False

    # v0.9.8: update_state 让 stop_block_count + 1 跨进程原子（多个 Stop hook
    # 几乎同时跑时不丢 count 更新）。state 对象的 stop_block_count 会被 fn
    # 更新到内存反映。
    def _bump_block_count(s):
        s.stop_block_count += 1
    try:
        updated_state, _ = session_state.update_state(
            state.session_id, _bump_block_count, agent_id=state.agent_id,
        )
        # 同步 state 内存对象给后续 reason 字串用
        state.stop_block_count = updated_state.stop_block_count
    except OSError:
        # update_state 内部 save 失败 fallback 本地内存自增，不阻塞拦截
        state.stop_block_count += 1
    reason = (
        f"karma 强制干预：累积违反 {over_threshold} 共 {sum(counts_force[s] for s in over_threshold)} 次。"
        f"必须 fix 原因（深挖 pattern / 工程 bug / 协议）或显式让用户介入。"
        f"禁止继续绕（手动改 karma 状态 / 临时改 rules.yaml）。"
    )
    print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
    return True


def _handle_keep_pushing_block(
    check_hits: list,
    keyword_violations: list,
    state,
) -> bool:
    """keep-pushing 干预 — Agent 沉默式停下时让继续生成。

    返回 True 表示已 print decision=block，调用方应 return 0。
    """
    keep_pushing_hit = any(h.rule_id == "keep-pushing-no-stop" for h in check_hits) or \
        any(v.rule_id == "keep-pushing-no-stop" for v in keyword_violations)
    if not keep_pushing_hit:
        return False

    try:
        from karma.config import load as _load_config
        block_max = int(_load_config().get("stop_block_max_per_turn", 2))
    except Exception:
        block_max = 2

    if block_max <= 0 or state.stop_block_count >= block_max:
        return False

    # v0.9.8: update_state 让 stop_block_count + 1 跨进程原子
    def _bump_block_count(s):
        s.stop_block_count += 1
    try:
        updated_state, _ = session_state.update_state(
            state.session_id, _bump_block_count, agent_id=state.agent_id,
        )
        state.stop_block_count = updated_state.stop_block_count
    except OSError:
        # update_state 内部 save 失败 fallback 本地内存自增，不阻塞拦截
        state.stop_block_count += 1
    from karma.i18n import tr
    reason = tr(
        "stop.reason",
        count=state.stop_block_count,
        max=block_max,
    )
    print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
    return True


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"karma Stop: 输入 JSON 解析失败 ({e})", file=sys.stderr)
        print(json.dumps({}))
        return 0

    # 可选 debug trace — 仅当 KARMA_DEBUG_TRACE 环境变量指向可写路径时启用
    # 不写死 /tmp 路径（跨平台 / 多用户机器互相覆盖）。production 默认完全关。
    _trace_path = os.environ.get("KARMA_DEBUG_TRACE")
    if _trace_path:
        try:
            import time as _t
            from pathlib import Path as _P
            with _P(_trace_path).open("a", encoding="utf-8") as f:
                f.write(f"[{_t.strftime('%H:%M:%S')}] Stop hook fired, session={payload.get('session_id', '')!r}\n")
        except OSError:
            pass

    session_id = payload.get("session_id", "") or "default"
    # 跨 backend payload 字段适配 — 优先「直传 message」字段，fallback transcript
    # - Codex Stop: last_assistant_message
    # - Gemini AfterAgent: prompt_response
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

    try:
        sticky_list = load()
    except RuleConfigError as e:
        print(f"karma: {e}", file=sys.stderr)
        print(json.dumps({}))
        return 0

    if not sticky_list or not response:
        print(json.dumps({}))
        return 0

    # v0.4.34 子 Agent 独立架构：agent_id 路由到独立 state（Stop hook 也支持 agent_id）
    agent_id = payload.get("agent_id") or None
    # v0.10.5 (Agent 1 F1.2 fix): Stop hook 跟 Pre/PostToolUse / UserPromptSubmit
    # 一样要 catchup_pending_bg — 之前 stop.py 漏这一步, 让最后一个 PostToolUse
    # 之后才完成的 bg pytest (启动: `pytest tests/ > /tmp/log &`) last_test_pass_ts
    # 不推 → evidence check 看 has_recent_test_pass()=False → 完成词被错算
    # loud-failure 拦. 同 v0.9.13 C1 family (load+modify+save 路径).
    # 套 try/except 跟 pre_tool_use 一致, 失败 fallback 裸 load 不阻塞 Stop hook.
    try:
        state, _ = session_state.update_state(
            session_id,
            lambda s: s.catchup_pending_bg(),
            agent_id=agent_id,
        )
    except Exception as e:
        print(f"karma Stop: catchup_pending_bg 失败 fallback 裸 load ({e})", file=sys.stderr)
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
        print(json.dumps({}))
        return 0

    # 写违反
    all_records: list[Violation] = []
    for h in check_hits:
        all_records.append(Violation(
            ts=int(time.time()), session_id=session_id, rule_id=h.rule_id,
            trigger=h.trigger, snippet=h.snippet, turn=state.turn_count,
            agent_id=agent_id,
            trigger_key=h.trigger_key,  # v0.5.7: locale-agnostic 分组 key
        ))
    seen_ids = {h.rule_id for h in check_hits}
    for v in keyword_violations:
        if v.rule_id not in seen_ids:
            all_records.append(v)
    if all_records:
        append(all_records)

    # 当前 turn 触发的 rule_id 集合 — 用于 force_block 原因 fix:
    # 只惩罚「当前 turn 触发 + 历史累积超阈值」的规则；fix 原因后不再触发
    # 不该被历史累积反复 force_block (否则 Agent 没法靠「修根因」解除卡死)
    hit_sticky_ids = {h.rule_id for h in check_hits} | {
        v.rule_id for v in keyword_violations if v.rule_id not in seen_ids
    }

    # stderr ⚠️ 通知 + 桌面通知 + 累积告警升级 (拆 helper: v0.8.3)
    _emit_notifications(
        check_hits, keyword_violations, seen_ids, hit_sticky_ids, state, session_id,
    )

    # 机制 1: 累积强制 block — 累积违反超阈值 → decision=block 强制查根因
    if _handle_force_block(state, sticky_list, hit_sticky_ids, session_id):
        return 0

    # 机制 2: keep-pushing 干预 — Agent 沉默式停下时让继续生成
    if _handle_keep_pushing_block(check_hits, keyword_violations, state):
        return 0

    # 2026-05-15 原因 fix：Stop hook 协议**不支持 hookSpecificOutput**
    # （schema 仅 PreToolUse / UserPromptSubmit / PostToolUse / PostToolBatch 支持）
    # 之前 v0.4.x 输出 hookSpecificOutput.additionalContext → 被 Claude Code
    # 报「Expected schema」错误日志，且 Agent 看不到（Stop 后已停）。
    #
    # 摘要已通过 stderr ⚠️ 通知（第 178 行）+ violations.jsonl 落盘 + 桌面通知 +
    # 下次 UserPromptSubmit sticky 注入的偏离标记 — 不需要 Stop hook 再 echo
    # 一遍违反摘要。无干预原因 → passthrough。
    print(json.dumps({}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
