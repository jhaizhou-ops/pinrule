"""Codex backend private protocol tests."""

from __future__ import annotations

import json
import tomllib

from karma.backends.codex import CodexBackend, codex_hook_trusted_hash


def _fake_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


REAL_CODEX_SINGLE_FILE_ENVELOPE = (
    "*** Begin Patch\n"
    "*** Update File: /tmp/karma-codex-toy.py\n"
    "@@\n"
    "+# v0.9.16 test\n"
    "*** End Patch\n"
)

REAL_CODEX_SESSION_START_PAYLOAD = {
    "session_id": "019e2fcc-redacted-session",
    "transcript_path": "/Users/jhz/.codex/sessions/2026/05/16/rollout-redacted.jsonl",
    "cwd": "/Users/jhz/karma",
    "hook_event_name": "SessionStart",
    "model": "gpt-5.5",
    "permission_mode": "default",
    "source": "startup",
}


def _normalize(raw_tool_input):
    return CodexBackend().normalize_tool_input("exec_command", raw_tool_input, {})


def test_exec_command_tail_command_key_extracts_read_file_path():
    out = _normalize({"command": "tail -n 20 /path/to/file.py"})
    assert out == {
        "command": "tail -n 20 /path/to/file.py",
        "read_file_paths": ["/path/to/file.py"],
    }


def test_exec_command_sed_n_cmd_key_extracts_read_file_path_for_desktop_shape():
    out = _normalize({"cmd": "sed -n '1,200p' /Users/jhz/karma/karma/__init__.py"})
    assert out == {
        "cmd": "sed -n '1,200p' /Users/jhz/karma/karma/__init__.py",
        "command": "sed -n '1,200p' /Users/jhz/karma/karma/__init__.py",
        "read_file_paths": ["/Users/jhz/karma/karma/__init__.py"],
    }


def test_exec_command_cat_extracts_read_file_path():
    out = _normalize({"command": "cat relative/path.py"})
    assert out["read_file_paths"] == ["relative/path.py"]


def test_exec_command_sed_i_marks_write_and_does_not_extract_path():
    out = _normalize({"command": "sed -i '' 's/old/new/' /path/to/file.py"})
    assert out == {
        "command": "sed -i '' 's/old/new/' /path/to/file.py",
        "is_write": True,
    }


def test_exec_command_with_pipe_does_not_extract_read_file_paths():
    out = _normalize({"command": "cat /path/to/file.py | sed -n '1,20p'"})
    assert out == {"command": "cat /path/to/file.py | sed -n '1,20p'"}


def test_exec_command_with_wildcard_does_not_extract_read_file_paths():
    out = _normalize({"command": "tail -n 20 karma/*.py"})
    assert out == {"command": "tail -n 20 karma/*.py"}


def test_codex_apply_patch_envelope_still_synthesizes_edit_shape():
    out = CodexBackend().normalize_tool_input("apply_patch", REAL_CODEX_SINGLE_FILE_ENVELOPE, {})
    assert out == {
        "file_path": "/tmp/karma-codex-toy.py",
        "new_string": REAL_CODEX_SINGLE_FILE_ENVELOPE,
        "multi_file_targets": [{"op": "Update", "path": "/tmp/karma-codex-toy.py"}],
    }


def test_codex_emit_allow_returns_empty_dict_not_claude_shape():
    out = CodexBackend().emit_allow({})
    assert out == "{}"
    assert json.loads(out) == {}


def test_exec_command_grep_without_recursive_flag_extracts_single_file_path():
    out = _normalize({"command": "grep -n 'needle' karma/backends/codex.py"})
    assert out["read_file_paths"] == ["karma/backends/codex.py"]


def test_exec_command_find_xargs_combo_does_not_extract_read_file_paths():
    out = _normalize({"command": "find karma -name '*.py' -print0 | xargs -0 grep needle"})
    assert out == {"command": "find karma -name '*.py' -print0 | xargs -0 grep needle"}


def test_exec_command_sed_print_delete_extracts_read_file_path():
    out = _normalize({"command": "sed '1,120p;d' karma/backends/codex.py"})
    assert out["read_file_paths"] == ["karma/backends/codex.py"]


def test_exec_command_awk_default_read_extracts_single_file_path():
    out = _normalize({"command": "awk '{print $1}' karma/backends/codex.py"})
    assert out["read_file_paths"] == ["karma/backends/codex.py"]


def test_exec_command_stdin_operand_does_not_extract_read_file_paths():
    out = _normalize({"command": "cat -"})
    assert out == {"command": "cat -"}


def test_session_start_in_hook_events():
    assert CodexBackend().hook_events()["SessionStart"] == "session_start"


def test_normalize_tool_name_exec_command_to_bash():
    assert CodexBackend().normalize_tool_name("exec_command", {}) == "Bash"


def test_real_codex_session_start_payload_shape_matches_session_start_hook_contract():
    payload = REAL_CODEX_SESSION_START_PAYLOAD
    assert list(payload) == [
        "session_id",
        "transcript_path",
        "cwd",
        "hook_event_name",
        "model",
        "permission_mode",
        "source",
    ]
    assert payload["hook_event_name"] == "SessionStart"
    assert isinstance(payload["session_id"], str) and payload["session_id"]
    assert isinstance(payload["cwd"], str) and payload["cwd"]
    assert isinstance(payload["model"], str) and payload["model"]
    assert isinstance(payload["permission_mode"], str) and payload["permission_mode"]
    assert isinstance(payload["transcript_path"], str) and payload["transcript_path"]
    assert payload.get("source") in {"startup", "resume", "clear", "compact"}


def test_codex_hook_trusted_hash_matches_codex_0130_source_algorithm():
    assert codex_hook_trusted_hash(
        "post_tool_use",
        "/Users/jhz/.codex/hooks/karma_post_tool_use.py",
        timeout=30,
    ) == "sha256:f6f66e9020480b0d5f6cb44e0e9d8ab33774a5ea02933e3b98c1835090055126"


def test_codex_save_settings_pretrusts_only_karma_hooks(tmp_path, monkeypatch):
    fake_home = _fake_home(tmp_path, monkeypatch)
    b = CodexBackend()
    settings = {
        "hooks": {
            "SessionStart": [
                {"hooks": [{
                    "type": "command",
                    "command": "/Users/jhz/.vibe-island/bin/vibe-island-bridge",
                    "timeout": 5,
                }]},
                b.build_event_entry("session_start", "SessionStart"),
            ],
            "UserPromptSubmit": [b.build_event_entry("user_prompt_submit", "UserPromptSubmit")],
        }
    }

    b.save_settings(settings)

    config = tomllib.loads((fake_home / ".codex" / "config.toml").read_text(encoding="utf-8"))
    state = config["hooks"]["state"]
    assert len(state) == 2

    session_key = f"{fake_home}/.codex/hooks.json:session_start:1:0"
    prompt_key = f"{fake_home}/.codex/hooks.json:user_prompt_submit:0:0"
    assert state[session_key] == {
        "enabled": True,
        "trusted_hash": codex_hook_trusted_hash(
            "session_start",
            f"{fake_home}/.codex/hooks/karma_session_start.py",
            timeout=30,
        ),
    }
    assert state[prompt_key] == {
        "enabled": True,
        "trusted_hash": codex_hook_trusted_hash(
            "user_prompt_submit",
            f"{fake_home}/.codex/hooks/karma_user_prompt_submit.py",
            timeout=30,
        ),
    }
    assert not any("vibe-island" in key for key in state)


def test_codex_hook_state_timeout_matches_codex_min_one_behavior(tmp_path, monkeypatch):
    fake_home = _fake_home(tmp_path, monkeypatch)
    b = CodexBackend()
    settings = {
        "hooks": {
            "PostToolUse": [{
                "hooks": [{
                    "type": "command",
                    "command": f"{fake_home}/.codex/hooks/karma_post_tool_use.py",
                    "timeout": 0,
                }]
            }],
        }
    }

    state = b.codex_hook_state_entries(settings)

    key = f"{fake_home}/.codex/hooks.json:post_tool_use:0:0"
    assert state[key]["trusted_hash"] == codex_hook_trusted_hash(
        "post_tool_use",
        f"{fake_home}/.codex/hooks/karma_post_tool_use.py",
        timeout=1,
    )


def test_codex_exec_command_pytest_records_bash_test_pass(tmp_path, monkeypatch):
    import io
    import sys

    from karma import session_state
    from karma.hooks import post_tool_use

    monkeypatch.setattr("karma.session_state.DEFAULT_DIR", tmp_path)
    state = session_state.SessionState(session_id="codex-bash-pytest")
    session_state.save(state, base_dir=tmp_path)

    payload = {
        "session_id": "codex-bash-pytest",
        "tool_name": "exec_command",
        "tool_input": {"cmd": "pytest tests/"},
        "tool_response": "===== 10 passed in 0.1s =====",
    }
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    monkeypatch.setattr(sys, "argv", ["/Users/jhz/.codex/hooks/karma_post_tool_use.py"])
    assert post_tool_use.main() == 0

    reloaded = session_state.load("codex-bash-pytest", base_dir=tmp_path)
    assert reloaded.has_recent_test_pass()
    assert reloaded.recent_bash[-1].command_summary == "pytest tests/"
    assert reloaded.recent_bash[-1].is_test_cmd
