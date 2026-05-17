"""Cursor-native hook adapters (beforeShellExecution / beforeMCPExecution)."""

from __future__ import annotations

import json
from io import StringIO
from unittest.mock import patch

import pytest

from karma.hooks import before_mcp_execution, before_shell_execution


@pytest.fixture
def empty_rules(monkeypatch):
    monkeypatch.setattr("karma.hooks._tool_gate.load", lambda: [])


def test_before_shell_execution_adapts_command_to_shell_gate(empty_rules, monkeypatch):
    captured = {}

    def fake_gate(payload):
        captured.update(payload)
        return 0

    monkeypatch.setattr(
        "karma.hooks.before_shell_execution.run_tool_gate", fake_gate,
    )
    stdin = json.dumps({"command": "sleep 60", "cwd": "/tmp", "conversation_id": "c1"})
    with patch("sys.stdin", StringIO(stdin)):
        assert before_shell_execution.main() == 0
    assert captured["tool_name"] == "Shell"
    assert captured["tool_input"]["command"] == "sleep 60"


def test_before_mcp_execution_blocks_long_await(empty_rules, monkeypatch):
    monkeypatch.setattr("karma.hooks._tool_gate.load", lambda: [])
    stdin = json.dumps({
        "tool_name": "Await",
        "tool_input": {"task_id": "x", "block_until_ms": 60000},
        "conversation_id": "c1",
    })
    with patch("sys.stdin", StringIO(stdin)):
        rc = before_mcp_execution.main()
    assert rc == 0
