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
from karma.sticky import StickyConfigError, load
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
    # 真根因：HANDOFF v3 第三步候选 — keep_pushing 只看 Agent response 末尾，
    # 看不到 user 上文「不用啦 / 休息吧 / 明天再说」叫停字面 → 反思 hook
    # 反复触发即使用户已明确叫停（sticky #8 例外条件命中但 check 不知道）。
    last_user_prompt = (
        payload.get("user_prompt", "")
        or payload.get("prompt", "")
        or _read_last_user_prompt(payload.get("transcript_path", ""))
    )

    try:
        sticky_list = load()
    except StickyConfigError as e:
        print(f"karma: {e}", file=sys.stderr)
        print(json.dumps({}))
        return 0

    if not sticky_list or not response:
        print(json.dumps({}))
        return 0

    # v0.4.34 子 Agent 独立架构：agent_id 路由到独立 state（Stop hook 也支持 agent_id）
    agent_id = payload.get("agent_id") or None
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
            ts=int(time.time()), session_id=session_id, rule_id=h.sticky_id,
            trigger=h.trigger, snippet=h.snippet, turn=state.turn_count,
            agent_id=agent_id,
        ))
    seen_ids = {h.sticky_id for h in check_hits}
    for v in keyword_violations:
        if v.sticky_id not in seen_ids:
            all_records.append(v)
    if all_records:
        append(all_records)

    # stderr 通知 + 桌面通知（用户离开 stderr 视野时的补充提示）
    summary_lines = []
    notify_msgs = []
    for h in check_hits:
        line = f"⚠️ karma: Agent 违反 {h.sticky_id!r} — {h.trigger}"
        print(line, file=sys.stderr)
        summary_lines.append(line)
        notify_msgs.append(f"{h.sticky_id} — {h.trigger}")
        if h.suggested_fix:
            print(f"   建议：{h.suggested_fix}", file=sys.stderr)
    for v in keyword_violations:
        if v.sticky_id in seen_ids:
            continue
        line = f"⚠️ karma: Agent 触发关键词 {v.sticky_id!r} (词 {v.trigger!r})"
        print(line, file=sys.stderr)
        summary_lines.append(line)
        notify_msgs.append(f"{v.sticky_id} — {v.trigger}")

    # 当前 turn 真触发的 sticky_id 集合 — 提到两个 if 块前共享
    # 用于 force_block 真根因 fix：只惩罚「当前 turn 真触发 + 历史累积超阈值」
    # 的 sticky；如果 Agent 修了真根因当前 turn 不再触发，不重复 force_block
    # 历史违反（否则 fix 后仍卡 force_block 形成死循环）
    hit_sticky_ids = {h.sticky_id for h in check_hits} | {
        v.sticky_id for v in keyword_violations if v.sticky_id not in seen_ids
    }

    # 桌面通知（合并多条违反到一条 notification 避免轰炸；fail open）
    # 累积告警：本次违反含窗口内已累积超阈值 → 升级严重度（阈值从 config 读）
    if notify_msgs:
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

    # 机制 2：累积强制 block — 同一 sticky 累积违反次数超阈值 → Stop hook 输出
    # decision=block，要求 Agent 修真根因或显式让用户介入，不允许继续绕
    if notify_msgs:
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
        if force_threshold > 0 and state.turn_count > 0:
            counts_force = count_recent_turns(session_id, state.turn_count, window_turns=force_window)
            # force_block 豁免从 sticky.yaml 的 force_block_exempt 字段读
            # 「应该继续推进」类规则不该被「累积太多必须停下让用户介入」处罚
            # （否则语义自我矛盾 — 用户实战发现 keep-pushing-no-stop 触发该 bug）
            exempt_ids = {s.id for s in sticky_list if s.force_block_exempt}
            # v0.4.16 真根因 fix：force_block 只惩罚「当前 turn 真触发 + 历史累积
            # 超阈值」的 sticky，不惩罚「已修了不再触发但历史在窗口内」的 sticky。
            # dogfooding 真触发：v0.4.15 修了 chinese-plain 真根因，但 force_block
            # 仍按最近 3 turn 累积 8 次重复 force_block，Agent 没法靠「修真根因」
            # 解除卡死。
            over_threshold = [
                sid for sid, n in counts_force.items()
                if n >= force_threshold and sid not in exempt_ids
                and sid in hit_sticky_ids  # 当前 turn 真触发了该 sticky 才 force_block
            ]
            if over_threshold and state.stop_block_count < block_max:
                state.stop_block_count += 1
                try:
                    session_state.save(state)
                except OSError:
                    pass
                reason = (
                    f"karma 强制干预：累积违反 {over_threshold} 共 {sum(counts_force[s] for s in over_threshold)} 次。"
                    f"必须 fix 真根因（深挖 pattern / 工程 bug / 协议）或显式让用户介入。"
                    f"禁止继续绕（手动改 karma 状态 / 临时改 sticky）。"
                )
                print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
                return 0

    # 机制：keep-pushing 干预 — Agent 沉默式停下时让继续生成
    keep_pushing_hit = any(h.sticky_id == "keep-pushing-no-stop" for h in check_hits) or \
        any(v.sticky_id == "keep-pushing-no-stop" for v in keyword_violations)
    if keep_pushing_hit:
        try:
            from karma.config import load as _load_config
            block_max = int(_load_config().get("stop_block_max_per_turn", 2))
        except Exception:
            block_max = 2
        if block_max > 0 and state.stop_block_count < block_max:
            # 干预 — 让 Agent 继续推进
            state.stop_block_count += 1
            try:
                session_state.save(state)
            except OSError:
                pass
            # v0.5.2 i18n: 合作回顾语气 reason 切 locale (en/zh)
            from karma.i18n import tr
            reason = tr(
                "stop.reason",
                count=state.stop_block_count,
                max=block_max,
            )
            print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
            return 0

    # 2026-05-15 真根因 fix：Stop hook 协议**不支持 hookSpecificOutput**
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
