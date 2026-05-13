"""Stop hook — Agent 响应完成后扫违反。

Claude Code 实际协议:
- stdin payload: {session_id, transcript_path, cwd, ...}（没有 response 字段）
- 要扫 response 需要读 transcript_path JSONL 文件取最后一条 assistant message
- stdout: {"hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": "..."}}
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from karma import session_state
from karma.checks import run_checks
from karma.sticky import StickyConfigError, load
from karma.violations import Violation, append, detect


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

    keyword_violations = detect(response, sticky_list, session_id=session_id)

    if not check_hits and not keyword_violations:
        print(json.dumps({}))
        return 0

    # 写违反
    all_records: list[Violation] = []
    for h in check_hits:
        all_records.append(Violation(
            ts=int(time.time()), session_id=session_id, sticky_id=h.sticky_id,
            trigger=h.trigger, snippet=h.snippet,
        ))
    seen_ids = {h.sticky_id for h in check_hits}
    for v in keyword_violations:
        if v.sticky_id not in seen_ids:
            all_records.append(v)
    if all_records:
        append(all_records)

    # stderr 通知
    summary_lines = []
    for h in check_hits:
        line = f"⚠️ karma: Agent 违反 {h.sticky_id!r} — {h.trigger}"
        print(line, file=sys.stderr)
        summary_lines.append(line)
        if h.suggested_fix:
            print(f"   建议：{h.suggested_fix}", file=sys.stderr)
    for v in keyword_violations:
        if v.sticky_id in seen_ids:
            continue
        line = f"⚠️ karma: Agent 触发关键词 {v.sticky_id!r} (词 {v.trigger!r})"
        print(line, file=sys.stderr)
        summary_lines.append(line)

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
