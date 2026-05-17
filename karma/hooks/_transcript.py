"""Transcript JSONL helpers — Claude Code 用 `type`, Cursor 用 `role`.

Stop / UserPromptSubmit 的 response-level check 依赖读 transcript.
Cursor agent-transcripts 是 `{"role":"assistant","message":{...}}` shape;
Claude Code 是 `{"type":"assistant","message":{...}}`. 两套都要认.
"""

from __future__ import annotations

import json
from pathlib import Path


def message_kind(record: dict) -> str:
    """Return ``user`` / ``assistant`` or empty if unknown."""
    kind = record.get("type", "")
    if kind in ("user", "assistant"):
        return kind
    role = record.get("role", "")
    if role in ("user", "assistant"):
        return role
    return ""


def extract_message_text(record: dict) -> str:
    """Pull plain text from a transcript record's message.content."""
    msg = record.get("message", {})
    content = msg.get("content")
    if isinstance(content, list):
        parts = [
            c.get("text", "")
            for c in content
            if isinstance(c, dict) and c.get("type") == "text"
        ]
        return "\n".join(parts)
    if isinstance(content, str):
        return content
    return ""


def read_last_message_text(transcript_path: str, kind: str) -> str:
    """Reverse-scan JSONL for the last user/assistant message text."""
    if not transcript_path or kind not in ("user", "assistant"):
        return ""
    p = Path(transcript_path)
    if not p.exists():
        return ""
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    for ln in reversed(lines):
        ln = ln.strip()
        if not ln:
            continue
        try:
            record = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if message_kind(record) != kind:
            continue
        return extract_message_text(record)
    return ""
