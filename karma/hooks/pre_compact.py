"""PreCompact hook — compact 前落盘 sticky 完整状态（karma v3 第五步）。

Claude Code 协议:
- stdin payload: {trigger: "manual"|"auto", session_id, transcript_path, ...}
- stdout: {"hookSpecificOutput": {"hookEventName": "PreCompact", "additionalContext": "..."}}

设计（v0.4.29 升级 — 早期 stub 用 continue:false 想阻止 compact，错。compact 是
Claude Code 保护机制，karma 不该干扰。改成纯落盘 + 注入 reminder）：

- 落盘 sticky 完整状态到 `~/.claude/karma/pre_compact_snapshot.md`
  保存：完整 sticky.yaml + 最近 5 turn 违反清单 + compact 触发时间 + session_id
- 注入 additionalContext 让 Claude 看到「即将 compact，sticky 已落盘」
- SessionStart(source=compact) 重起后会读这个 snapshot 加强提醒

两端夹击 compact 失忆：PreCompact 落盘 + SessionStart 读盘。
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from karma.paths import karma_home
from karma.rule import load as load_sticky
from karma.violations import recent_turns


SNAPSHOT_FILENAME = "pre_compact_snapshot.md"


def _snapshot_path() -> Path:
    return karma_home() / SNAPSHOT_FILENAME


def _passthrough() -> None:
    print(json.dumps({}))


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"karma PreCompact: 输入 JSON 解析失败 ({e})", file=sys.stderr)
        _passthrough()
        return 0

    trigger = payload.get("trigger", "")  # manual / auto
    from karma.hooks._payload import extract_session_id
    session_id = extract_session_id(payload)

    try:
        rule_list = load_sticky()
    except Exception as e:
        print(f"karma PreCompact: 规则加载失败 ({e})", file=sys.stderr)
        _passthrough()
        return 0

    if not rule_list:
        _passthrough()
        return 0

    # 落盘 snapshot — 让 SessionStart(source=compact) 重起后读得到
    lines = [
        "# karma compact 前快照",
        "",
        f"- compact 触发: {trigger or 'unknown'}",
        f"- session_id: {session_id}",
        f"- 时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}",
        "",
        "## sticky 完整清单",
        "",
    ]
    for s in rule_list:
        lines.append(f"### {s.id}")
        lines.append("")
        for pref_line in s.preference.strip().split("\n"):
            lines.append(f"> {pref_line}")
        lines.append("")

    # 最近 5 turn 违反清单 — 让 compact 后 Agent 知道之前撞过哪些 sticky
    try:
        # v0.10.5 (Agent 1 F1.1 fix): 之前 fallback 用 current_turn=999999 想让
        # recent_turns 「看全部」, 但 v0.9.13 把 cutoff 改成 cur-(window-1) 后这条
        # fallback 数学错 — cutoff=999995 让窗口 [999995, 999999] 不命中真实
        # turn 1-100 的 violations, recent_v 永远空, compact 失忆兜底关键路径失效.
        # 修法: turn_count=0 的 fallback 路径改读 ts 维度最近 24h, 不依赖 turn 窗口.
        from karma import session_state as _ss
        state = _ss.load(session_id)
        if state.turn_count > 0:
            recent_v = recent_turns(session_id, state.turn_count, window_turns=5)
        else:
            from karma.violations import recent as _recent_ts
            recent_v = _recent_ts(window_sec=24 * 3600)
    except Exception:
        recent_v = {}
    if recent_v:
        lines.append("## compact 前最近 5 turn 违反过的 sticky")
        lines.append("")
        for sid, n in recent_v.items():
            lines.append(f"- {sid}: {n} 次")
        lines.append("")

    snapshot = "\n".join(lines)
    try:
        sp = _snapshot_path()
        sp.parent.mkdir(parents=True, exist_ok=True)
        sp.write_text(snapshot, encoding="utf-8")
    except OSError as e:
        print(f"karma PreCompact: 落盘失败 ({e})", file=sys.stderr)
        _passthrough()
        return 0

    # Claude: PreCompact 不支持 additionalContext — snapshot + SessionStart(compact) 路径.
    # Cursor: 官方 preCompact 支持 `user_message` 提醒用户 compact 前已落盘.
    from karma.backends.protocol_adapter import detect_backend, emit_context_injection
    if detect_backend(payload) == "cursor":
        from karma.i18n import tr
        print(emit_context_injection(
            "preCompact",
            tr("pre_compact.cursor_notice"),
            payload,
        ))
    else:
        _passthrough()
    return 0


if __name__ == "__main__":
    sys.exit(main())
