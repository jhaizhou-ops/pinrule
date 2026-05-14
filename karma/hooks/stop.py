"""Stop hook — Agent 响应完成后扫违反。

Claude Code 实际协议:
- stdin payload: {session_id, transcript_path, cwd, ...}（没有 response 字段）
- 要扫 response 需要读 transcript_path JSONL 文件取最后一条 assistant message
- stdout: {"hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": "..."}}
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
    if not transcript_path:
        return ""
    p = Path(transcript_path)
    if not p.exists():
        return ""
    try:
        # 反向找最后一条 type=assistant
        lines = p.read_text(encoding="utf-8").splitlines()
        for ln in reversed(lines):
            ln = ln.strip()
            if not ln:
                continue
            try:
                d = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if d.get("type") != "assistant":
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
    transcript_path = payload.get("transcript_path", "")
    response = _read_last_assistant_response(transcript_path)

    try:
        sticky_list = load()
    except StickyConfigError as e:
        print(f"karma: {e}", file=sys.stderr)
        print(json.dumps({}))
        return 0

    if not sticky_list or not response:
        print(json.dumps({}))
        return 0

    state = session_state.load(session_id)

    check_hits = []
    for s in sticky_list:
        if not s.violation_checks:
            continue
        hits = run_checks(
            s.violation_checks,
            response=response,
            session_state=state,
            sticky_id=s.id,
        )
        check_hits.extend(hits)

    keyword_violations = detect(response, sticky_list, session_id=session_id, turn=state.turn_count)

    if not check_hits and not keyword_violations:
        print(json.dumps({}))
        return 0

    # 写违反
    all_records: list[Violation] = []
    for h in check_hits:
        all_records.append(Violation(
            ts=int(time.time()), session_id=session_id, sticky_id=h.sticky_id,
            trigger=h.trigger, snippet=h.snippet, turn=state.turn_count,
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
        hit_sticky_ids = {h.sticky_id for h in check_hits} | {
            v.sticky_id for v in keyword_violations if v.sticky_id not in seen_ids
        }
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
            block_max = int(_cfg.get("stop_block_max_per_turn", 3))
        except Exception:
            force_threshold = 5
            force_window = 3
            block_max = 3
        if force_threshold > 0 and state.turn_count > 0:
            counts_force = count_recent_turns(session_id, state.turn_count, window_turns=force_window)
            # force_block 豁免从 sticky.yaml 的 force_block_exempt 字段读
            # 「应该继续推进」类规则不该被「累积太多必须停下让用户介入」处罚
            # （否则语义自我矛盾 — 用户实战发现 keep-pushing-no-stop 触发该 bug）
            exempt_ids = {s.id for s in sticky_list if s.force_block_exempt}
            over_threshold = [
                sid for sid, n in counts_force.items()
                if n >= force_threshold and sid not in exempt_ids
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
            block_max = int(_load_config().get("stop_block_max_per_turn", 3))
        except Exception:
            block_max = 3
        if block_max > 0 and state.stop_block_count < block_max:
            # 干预 — 让 Agent 继续推进
            state.stop_block_count += 1
            try:
                session_state.save(state)
            except OSError:
                pass
            reason = (
                f"karma 拦截 stop：sticky #7 keep-pushing-no-stop 命中。"
                f"立即选下个推进点继续做 — 不要停下等用户决定。"
                f"（本 turn 已干预 {state.stop_block_count}/{block_max} 次）"
            )
            print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
            return 0

    # 也可以通过 additionalContext 让 Claude 看到 — 但 Stop 后 Claude 已停，
    # 主要给下次 UserPromptSubmit 的 sticky 注入加 RECENT_VIOLATION 标记
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "Stop",
            "additionalContext": "\n".join(summary_lines) if summary_lines else "",
        }
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
