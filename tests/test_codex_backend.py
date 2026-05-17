"""Codex backend private protocol tests."""

from __future__ import annotations

import json
import tomllib

from pathlib import Path

from pinrule.backends import codex as codex_backend
from pinrule.backends._json_hooks import hook_command_str
from pinrule.backends.codex import CodexBackend, codex_hook_trusted_hash


def _fake_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


REAL_CODEX_SINGLE_FILE_ENVELOPE = (
    "*** Begin Patch\n"
    "*** Update File: /tmp/pinrule-codex-toy.py\n"
    "@@\n"
    "+# v0.9.16 test\n"
    "*** End Patch\n"
)

REAL_CODEX_SESSION_START_PAYLOAD = {
    "session_id": "019e2fcc-redacted-session",
    "transcript_path": "/Users/jhz/.codex/sessions/2026/05/16/rollout-redacted.jsonl",
    "cwd": "/Users/jhz/pinrule",
    "hook_event_name": "SessionStart",
    "model": "gpt-5.5",
    "permission_mode": "default",
    "source": "startup",
}


def _normalize(raw_tool_input):
    return CodexBackend().normalize_tool_input("exec_command", raw_tool_input, {})


def _normalize_bash(raw_tool_input):
    return CodexBackend().normalize_tool_input("Bash", raw_tool_input, {})


def test_exec_command_tail_command_key_extracts_read_file_path():
    out = _normalize({"command": "tail -n 20 /path/to/file.py"})
    assert out == {
        "command": "tail -n 20 /path/to/file.py",
        "read_file_paths": ["/path/to/file.py"],
    }


def test_native_bash_tail_extracts_read_file_path():
    """Codex hooks docs report shell calls as tool_name=Bash + tool_input.command."""
    out = _normalize_bash({"command": "tail -n 20 /path/to/file.py"})
    assert out == {
        "command": "tail -n 20 /path/to/file.py",
        "read_file_paths": ["/path/to/file.py"],
    }


def test_exec_command_sed_n_cmd_key_extracts_read_file_path_for_desktop_shape():
    out = _normalize({"cmd": "sed -n '1,200p' /Users/jhz/pinrule/pinrule/__init__.py"})
    assert out == {
        "cmd": "sed -n '1,200p' /Users/jhz/pinrule/pinrule/__init__.py",
        "command": "sed -n '1,200p' /Users/jhz/pinrule/pinrule/__init__.py",
        "read_file_paths": ["/Users/jhz/pinrule/pinrule/__init__.py"],
    }


def test_exec_command_cat_extracts_read_file_path():
    out = _normalize({"command": "cat relative/path.py"})
    assert out["read_file_paths"] == ["relative/path.py"]


def test_exec_command_sed_i_marks_write_and_emits_write_file_paths():
    out = _normalize({"command": "sed -i 's/foo/bar/' /workspace/x.py"})
    assert out == {
        "command": "sed -i 's/foo/bar/' /workspace/x.py",
        "is_write": True,
        "write_file_paths": ["/workspace/x.py"],
    }


def test_native_bash_sed_i_emits_write_file_paths():
    out = _normalize_bash({"command": "sed -i 's/foo/bar/' /workspace/x.py"})
    assert out == {
        "command": "sed -i 's/foo/bar/' /workspace/x.py",
        "is_write": True,
        "write_file_paths": ["/workspace/x.py"],
    }


def test_exec_command_tee_emits_write_file_paths():
    out = _normalize({"command": "tee -a /workspace/x.py"})
    assert out == {
        "command": "tee -a /workspace/x.py",
        "is_write": True,
        "write_file_paths": ["/workspace/x.py"],
    }


def test_exec_command_single_pipe_tee_emits_write_file_paths():
    command = "uv run python tests/distillation/run_eval_harness.py | tee /tmp/delivery4_eval_before.md"
    out = _normalize({"command": command})
    assert out == {
        "command": command,
        "is_write": True,
        "write_file_paths": ["/tmp/delivery4_eval_before.md"],
    }


def test_exec_command_with_pipe_does_not_extract_read_file_paths():
    out = _normalize({"command": "cat /path/to/file.py | sed -n '1,20p'"})
    assert out == {"command": "cat /path/to/file.py | sed -n '1,20p'"}


def test_simple_pipe_head_tail_recognized():
    cases = {
        "head -n 40 /path/to/file.py | tail -n 10": "/path/to/file.py",
        "cat /path/to/file.py | head -n 20": "/path/to/file.py",
        "cat /path/to/file.py | tail -n 20": "/path/to/file.py",
        "tail -n 80 /path/to/file.py | head -n 20": "/path/to/file.py",
    }

    for command, path in cases.items():
        out = _normalize({"command": command})
        assert out == {"command": command, "read_file_paths": [path]}


def test_xargs_cat_not_recognized_documented_skip():
    """find/xargs reads many unknown files; read_first needs exact file paths."""
    command = "find tests -name '*.py' -print0 | xargs -0 cat"
    out = _normalize({"command": command})
    assert out == {"command": command}


def test_recursive_grep_not_recognized_documented_skip():
    """recursive grep reads a tree; directory prefixes do not satisfy read_first."""
    command = "grep -R needle pinrule"
    out = _normalize({"command": command})
    assert out == {"command": command}


def test_exec_command_with_wildcard_does_not_extract_read_file_paths():
    out = _normalize({"command": "tail -n 20 pinrule/*.py"})
    assert out == {"command": "tail -n 20 pinrule/*.py"}


def test_codex_apply_patch_envelope_still_synthesizes_edit_shape():
    out = CodexBackend().normalize_tool_input("apply_patch", REAL_CODEX_SINGLE_FILE_ENVELOPE, {})
    assert out == {
        "file_path": "/tmp/pinrule-codex-toy.py",
        "new_string": REAL_CODEX_SINGLE_FILE_ENVELOPE,
        "multi_file_targets": [{"op": "Update", "path": "/tmp/pinrule-codex-toy.py"}],
    }


def test_codex_apply_patch_native_command_field_synthesizes_edit_shape_without_warning(capsys):
    """Codex hooks docs: apply_patch uses tool_input.command in native hook payload."""
    out = CodexBackend().normalize_tool_input(
        "apply_patch",
        {"command": REAL_CODEX_SINGLE_FILE_ENVELOPE},
        {},
    )
    assert out == {
        "file_path": "/tmp/pinrule-codex-toy.py",
        "new_string": REAL_CODEX_SINGLE_FILE_ENVELOPE,
        "multi_file_targets": [{"op": "Update", "path": "/tmp/pinrule-codex-toy.py"}],
    }
    captured = capsys.readouterr()
    assert captured.err == ""


def test_codex_emit_allow_returns_empty_dict_not_claude_shape():
    out = CodexBackend().emit_allow({})
    assert out == "{}"
    assert json.loads(out) == {}


def test_codex_emit_deny_permission_request_shape():
    out = CodexBackend().emit_deny(
        "blocked by pinrule",
        {"hook_event_name": "PermissionRequest"},
    )
    assert json.loads(out) == {
        "hookSpecificOutput": {
            "hookEventName": "PermissionRequest",
            "decision": {
                "behavior": "deny",
                "message": "blocked by pinrule",
            },
        }
    }


def test_codex_emit_deny_pre_tool_use_shape_stays_permission_decision():
    out = CodexBackend().emit_deny(
        "blocked by pinrule",
        {"hook_event_name": "PreToolUse"},
    )
    assert json.loads(out) == {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": "blocked by pinrule",
        }
    }


def test_codex_emit_context_injection_shape_is_native_hook_specific_output():
    out = CodexBackend().emit_context_injection("SessionStart", "pinrule context", {})
    assert json.loads(out) == {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": "pinrule context",
        }
    }


def test_codex_emit_context_injection_empty_returns_empty_dict():
    out = CodexBackend().emit_context_injection("UserPromptSubmit", "", {})
    assert json.loads(out) == {}


def test_codex_emit_stop_block_shape_is_native_decision_block():
    out = CodexBackend().emit_stop_block("keep going", {})
    assert json.loads(out) == {"decision": "block", "reason": "keep going"}


def test_module_docstring_contains_adr_001():
    assert codex_backend.__doc__
    assert "ADR-001" in codex_backend.__doc__
    assert "PermissionRequest event 改为接入" in codex_backend.__doc__


def test_exec_command_grep_without_recursive_flag_extracts_single_file_path():
    out = _normalize({"command": "grep -n 'needle' pinrule/backends/codex.py"})
    assert out["read_file_paths"] == ["pinrule/backends/codex.py"]


def test_exec_command_find_xargs_combo_does_not_extract_read_file_paths():
    out = _normalize({"command": "find pinrule -name '*.py' -print0 | xargs -0 grep needle"})
    assert out == {"command": "find pinrule -name '*.py' -print0 | xargs -0 grep needle"}


def test_exec_command_sed_print_delete_extracts_read_file_path():
    out = _normalize({"command": "sed '1,120p;d' pinrule/backends/codex.py"})
    assert out["read_file_paths"] == ["pinrule/backends/codex.py"]


def test_exec_command_awk_default_read_extracts_single_file_path():
    out = _normalize({"command": "awk '{print $1}' pinrule/backends/codex.py"})
    assert out["read_file_paths"] == ["pinrule/backends/codex.py"]


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
        "/Users/jhz/.codex/hooks/pinrule_post_tool_use.py",
        timeout=30,
    ) == "sha256:e33e88d486a7d25d1a210fc6dfe548bb65e57a330031a494f1b623679c537c15"


def test_codex_save_settings_pretrusts_only_pinrule_hooks(tmp_path, monkeypatch):
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
    session_cmd = hook_command_str(Path(f"{fake_home}/.codex/hooks/pinrule_session_start.py"))
    prompt_cmd = hook_command_str(Path(f"{fake_home}/.codex/hooks/pinrule_user_prompt_submit.py"))
    assert state[session_key] == {
        "enabled": True,
        "trusted_hash": codex_hook_trusted_hash("session_start", session_cmd, timeout=30),
    }
    assert state[prompt_key] == {
        "enabled": True,
        "trusted_hash": codex_hook_trusted_hash("user_prompt_submit", prompt_cmd, timeout=30),
    }
    assert not any("vibe-island" in key for key in state)


def test_codex_save_settings_pretrusts_all_native_events(tmp_path, monkeypatch):
    """Codex native surface install must auto-trust every event, including
    PermissionRequest, or users are back to one-by-one `/hooks` approval.
    """
    fake_home = _fake_home(tmp_path, monkeypatch)
    b = CodexBackend()
    settings = {
        "hooks": {
            event: [b.build_event_entry(wrapper, event)]
            for event, wrapper in b.hook_events().items()
        }
    }

    b.save_settings(settings)

    config = tomllib.loads((fake_home / ".codex" / "config.toml").read_text(encoding="utf-8"))
    state = config["hooks"]["state"]
    assert len(state) == len(b.hook_events())
    event_keys = {key.split(":")[-3] for key in state}
    assert event_keys == {
        "session_start",
        "user_prompt_submit",
        "pre_tool_use",
        "permission_request",
        "post_tool_use",
        "stop",
    }
    assert all(entry["enabled"] is True for entry in state.values())
    assert all(entry["trusted_hash"].startswith("sha256:") for entry in state.values())


def test_codex_hook_events_preserve_full_native_surface_with_shared_wrapper():
    """hook_events() is a native event map; installer handles wrapper de-dupe."""
    events = CodexBackend().hook_events()
    assert len(events) == 6
    assert len(list(events.items())) == 6
    values = list(events.values())
    assert len(values) == 6
    assert values.count("pre_tool_use") == 2
    assert events["PreToolUse"] == "pre_tool_use"
    assert events["PermissionRequest"] == "pre_tool_use"


def test_codex_post_install_message_deduplicates_shared_wrapper_paths(tmp_path, monkeypatch):
    """PermissionRequest and PreToolUse share one wrapper; user approval UX must
    not ask people to inspect the same file twice.
    """
    fake_home = _fake_home(tmp_path, monkeypatch)
    lines = CodexBackend().post_install_message()
    wrapper_lines = [line for line in lines if str(fake_home / ".codex" / "hooks") in line]
    assert len(wrapper_lines) == len(set(wrapper_lines))
    assert sum("pinrule_pre_tool_use.py" in line for line in wrapper_lines) == 1


def test_codex_hook_state_timeout_matches_codex_min_one_behavior(tmp_path, monkeypatch):
    fake_home = _fake_home(tmp_path, monkeypatch)
    b = CodexBackend()
    settings = {
        "hooks": {
            "PostToolUse": [{
                "hooks": [{
                    "type": "command",
                    "command": f"{fake_home}/.codex/hooks/pinrule_post_tool_use.py",
                    "timeout": 0,
                }]
            }],
        }
    }

    state = b.codex_hook_state_entries(settings)

    key = f"{fake_home}/.codex/hooks.json:post_tool_use:0:0"
    assert state[key]["trusted_hash"] == codex_hook_trusted_hash(
        "post_tool_use",
        f"{fake_home}/.codex/hooks/pinrule_post_tool_use.py",
        timeout=1,
    )


def test_codex_exec_command_pytest_records_bash_test_pass(tmp_path, monkeypatch):
    import io
    import sys

    from pinrule import session_state
    from pinrule.hooks import post_tool_use

    monkeypatch.setattr("pinrule.session_state.DEFAULT_DIR", tmp_path)
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
    monkeypatch.setattr(sys, "argv", ["/Users/jhz/.codex/hooks/pinrule_post_tool_use.py"])
    assert post_tool_use.main() == 0

    reloaded = session_state.load("codex-bash-pytest", base_dir=tmp_path)
    assert reloaded.has_recent_test_pass()
    assert reloaded.recent_bash[-1].command_summary == "pytest tests/"
    assert reloaded.recent_bash[-1].is_test_cmd


def test_codex_exec_command_sed_i_records_canonical_write_path(tmp_path, monkeypatch):
    import io
    import sys

    from pinrule import session_state
    from pinrule.hooks import post_tool_use

    monkeypatch.setattr("pinrule.session_state.DEFAULT_DIR", tmp_path)
    state = session_state.SessionState(session_id="codex-sed-write")
    session_state.save(state, base_dir=tmp_path)

    payload = {
        "session_id": "codex-sed-write",
        "tool_name": "exec_command",
        "tool_input": {"cmd": "sed -i 's/foo/bar/' /workspace/x.py"},
        "tool_response": "",
    }
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    monkeypatch.setattr(sys, "argv", ["/Users/jhz/.codex/hooks/pinrule_post_tool_use.py"])
    assert post_tool_use.main() == 0

    reloaded = session_state.load("codex-sed-write", base_dir=tmp_path)
    assert "/workspace/x.py" in reloaded.edit_files
    assert reloaded.last_edit_ts > 0


def test_codex_native_bash_records_canonical_read_path(tmp_path, monkeypatch):
    import io
    import sys

    from pinrule import session_state
    from pinrule.hooks import post_tool_use

    monkeypatch.setattr("pinrule.session_state.DEFAULT_DIR", tmp_path)
    state = session_state.SessionState(session_id="codex-native-bash-read")
    session_state.save(state, base_dir=tmp_path)

    payload = {
        "session_id": "codex-native-bash-read",
        "hook_event_name": "PostToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "tail -n 20 /workspace/x.py"},
        "tool_response": "",
    }
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    monkeypatch.setattr(sys, "argv", ["/Users/jhz/.codex/hooks/pinrule_post_tool_use.py"])
    assert post_tool_use.main() == 0

    reloaded = session_state.load("codex-native-bash-read", base_dir=tmp_path)
    assert "/workspace/x.py" in reloaded.read_files
