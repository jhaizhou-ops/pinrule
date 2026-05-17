"""tests for karma.hooks._payload extract_session_id (v0.12.1).

跨 backend stdin payload 字段 fallback 链:
- Claude / Codex (Cursor 用 conversation_id): `session_id`
- Cursor 1.7+: `conversation_id`
- fail-open: `default`
"""

from __future__ import annotations

from karma.hooks._payload import extract_session_id


def test_session_id_primary_path():
    """Claude Code / Codex stdin 用 session_id."""
    assert extract_session_id({"session_id": "claude-abc-123"}) == "claude-abc-123"


def test_conversation_id_cursor_fallback():
    """Cursor 1.7+ stdin 用 conversation_id 而非 session_id."""
    assert extract_session_id({"conversation_id": "cursor-xyz-789"}) == "cursor-xyz-789"


def test_session_id_takes_priority_over_conversation_id():
    """两个都在时优先 session_id (除非 Cursor 真同时发, 实测 only conversation_id)."""
    assert extract_session_id({
        "session_id": "claude-id",
        "conversation_id": "cursor-id",
    }) == "claude-id"


def test_empty_payload_falls_back_to_default():
    """payload 没任何 session 字段 → 'default' fail-open, hook 跑通但归一桶."""
    assert extract_session_id({}) == "default"


def test_empty_string_falls_through_to_conversation_id():
    """session_id 是空 string 时, 仍 fallback 到 conversation_id (字面 '' falsy)."""
    assert extract_session_id({
        "session_id": "",
        "conversation_id": "cursor-id",
    }) == "cursor-id"


def test_both_empty_falls_to_default():
    """两个 key 都存在但都空 → 'default'."""
    assert extract_session_id({
        "session_id": "",
        "conversation_id": "",
    }) == "default"


def test_cursor_real_payload_shape():
    """模拟 Cursor 真 stdin payload (https://cursor.com/docs/hooks 文档 schema).

    Cursor payload 含 conversation_id / generation_id / model 等, 不含 session_id.
    karma 入口拿不到 session_id 时 fallback 到 conversation_id 让 session_state
    不归到 'default' 一锅粥.
    """
    cursor_payload = {
        "conversation_id": "abc-def-123",
        "generation_id": "gen-456",
        "hook_event_name": "preToolUse",
        "model": "claude-sonnet-4",
        "tool_name": "Shell",
        "tool_input": {"command": "ls"},
    }
    assert extract_session_id(cursor_payload) == "abc-def-123"
