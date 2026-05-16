"""Codex backend private protocol tests."""

from __future__ import annotations

import json

from karma.backends.codex import CodexBackend


REAL_CODEX_SINGLE_FILE_ENVELOPE = (
    "*** Begin Patch\n"
    "*** Update File: /tmp/karma-codex-toy.py\n"
    "@@\n"
    "+# v0.9.16 test\n"
    "*** End Patch\n"
)


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
