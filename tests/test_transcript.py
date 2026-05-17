"""Transcript JSONL parsing — Claude `type` vs Cursor `role`."""

from __future__ import annotations

import json

from pinrule.hooks._transcript import (
    message_kind,
    read_last_message_text,
)


def test_message_kind_claude_type():
    assert message_kind({"type": "assistant", "message": {}}) == "assistant"


def test_message_kind_cursor_role():
    assert message_kind({"role": "user", "message": {}}) == "user"


def test_read_last_assistant_cursor_shape(tmp_path):
    p = tmp_path / "t.jsonl"
    p.write_text(
        json.dumps({
            "role": "user",
            "message": {"content": [{"type": "text", "text": "hi"}]},
        }) + "\n"
        + json.dumps({
            "role": "assistant",
            "message": {"content": [{"type": "text", "text": "done with tests"}]},
        }) + "\n",
        encoding="utf-8",
    )
    assert read_last_message_text(str(p), "assistant") == "done with tests"
    assert read_last_message_text(str(p), "user") == "hi"


def test_read_last_claude_type_shape(tmp_path):
    p = tmp_path / "claude.jsonl"
    p.write_text(
        json.dumps({
            "type": "assistant",
            "message": {"content": [{"type": "text", "text": "claude reply"}]},
        }) + "\n",
        encoding="utf-8",
    )
    assert read_last_message_text(str(p), "assistant") == "claude reply"
