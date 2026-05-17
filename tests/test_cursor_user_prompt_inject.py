"""Cursor beforeSubmitPrompt must inject rule ids (not passthrough on turn 1)."""

from __future__ import annotations

import io
import json

from karma.hooks import user_prompt_submit

from tests.test_hooks import _patch_paths


def test_cursor_before_submit_injects_rule_id_catalog(monkeypatch, tmp_path, capsys):
    _patch_paths(monkeypatch, tmp_path, sticky_items=[
        {"id": "dogfood-marker-cursor-v12", "preference": "marker", "violation_keywords": []},
    ])
    payload = json.dumps({
        "prompt": "列出 karma 规则 id",
        "conversation_id": "cursor-vis-1",
        "hook_event_name": "beforeSubmitPrompt",
    })
    monkeypatch.setattr("sys.stdin", io.StringIO(payload))
    assert user_prompt_submit.main() == 0
    out = json.loads(capsys.readouterr().out)
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert "dogfood-marker-cursor-v12" in ctx
    assert "`dogfood-marker-cursor-v12`" in ctx
