"""多 backend 装机抽象测试 — Claude Code / Codex / 抽象接口。"""

from __future__ import annotations


import pytest

from karma.backends import (
    REGISTRY,
    ClaudeCodeBackend,
    CodexBackend,
    CursorBackend,
    detect_installed_backends,
)
from karma.backends._base import SettingsParseError


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    """让 Path.home() 指向 tmp，让 backend 写到 tmp 不污染真 home。"""
    monkeypatch.setenv("HOME", str(tmp_path))
    # Path.home() 实际读 HOME 环境变量
    return tmp_path


def test_registry_has_three_backends():
    assert "claude-code" in REGISTRY
    assert "codex" in REGISTRY
    assert "cursor" in REGISTRY
    assert "gemini-cli" not in REGISTRY  # v0.13.2 砍 Gemini
    assert isinstance(REGISTRY["claude-code"], ClaudeCodeBackend)
    assert isinstance(REGISTRY["codex"], CodexBackend)
    assert isinstance(REGISTRY["cursor"], CursorBackend)


def test_backends_all_have_common_karma_wrappers():
    """3 个 backend 都有 pre_tool_use / post_tool_use / stop 通用 wrapper.

    Cursor v0.12.2+ 用 beforeSubmitPrompt → user_prompt_submit 作每 turn 注入;
    session_start 是 session 起手 baseline. 用 {pre, post, stop} 作跨 backend 最小集.
    """
    minimum_commons = {"pre_tool_use", "post_tool_use", "stop"}
    for name in ("claude-code", "codex", "cursor"):
        wrappers = set(REGISTRY[name].hook_events().values())
        assert minimum_commons.issubset(wrappers), (
            f"{name} 缺通用 wrapper: 缺 {minimum_commons - wrappers}"
        )


def test_claude_code_has_session_start_wrapper():
    """v0.4.28: Claude Code 多加 SessionStart 注入 sticky baseline 特别处理 compact 后.
    Codex 协议没对应 event, Cursor 自己有 sessionStart (v0.12.0).
    """
    cc_wrappers = set(REGISTRY["claude-code"].hook_events().values())
    assert "session_start" in cc_wrappers


# ---- Claude Code backend ----


def test_claude_code_paths(fake_home):
    b = ClaudeCodeBackend()
    assert b.hooks_dir() == fake_home / ".claude" / "hooks"
    assert b.settings_path() == fake_home / ".claude" / "settings.json"
    assert b.settings_backup_path() == fake_home / ".claude" / "settings.json.before-karma"


def test_claude_code_event_entry_matcher(fake_home):
    """Stop event 不加 matcher（Claude Code 协议特性）；其他 3 个加 matcher='*'。"""
    b = ClaudeCodeBackend()
    pre = b.build_event_entry("pre_tool_use", "PreToolUse")
    assert pre.get("matcher") == "*"
    stop = b.build_event_entry("stop", "Stop")
    assert "matcher" not in stop


def test_claude_code_atomic_save(fake_home):
    """save_settings 用 tmp + os.replace，不留 .karma-tmp.* 残留。"""
    b = ClaudeCodeBackend()
    b.save_settings({"hooks": {}, "model": "opus"})
    assert b.settings_path().exists()
    tmp_files = list(b.settings_path().parent.glob("*karma-tmp*"))
    assert not tmp_files


def test_claude_code_load_corrupted_raises(fake_home):
    """损坏的 settings.json 抛 SettingsParseError 不静默返回 {}。"""
    b = ClaudeCodeBackend()
    p = b.settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(SettingsParseError):
        b.load_settings()


# ---- Codex backend ----


def test_codex_paths(fake_home):
    b = CodexBackend()
    assert b.hooks_dir() == fake_home / ".codex" / "hooks"
    assert b.settings_path() == fake_home / ".codex" / "hooks.json"


def test_codex_event_entry_no_matcher(fake_home):
    """Codex hook entry 不需要 matcher 字段（协议没该概念）。"""
    b = CodexBackend()
    entry = b.build_event_entry("user_prompt_submit", "UserPromptSubmit")
    assert "matcher" not in entry
    hooks = entry["hooks"]
    assert len(hooks) == 1
    assert hooks[0]["type"] == "command"
    assert "karma_user_prompt_submit.py" in hooks[0]["command"]
    assert hooks[0].get("timeout") == 30


def test_codex_load_save_roundtrip(fake_home):
    b = CodexBackend()
    data = {"hooks": {"UserPromptSubmit": [{"hooks": [{"command": "/x", "type": "command"}]}]}}
    b.save_settings(data)
    loaded = b.load_settings()
    assert loaded == data


def test_codex_pre_install_setup_no_codex_bin(monkeypatch):
    """codex 不在 PATH → pre_install_setup 输出警告而不是 crash。"""
    monkeypatch.setattr("shutil.which", lambda x: None)
    b = CodexBackend()
    steps = b.pre_install_setup()
    assert any("codex" in s.lower() for s in steps)


def test_codex_features_hooks_enabled_detection(fake_home):
    """读 ~/.codex/config.toml 看 [features] hooks 是否已 true（避免重复 enable）。"""
    b = CodexBackend()
    config_path = fake_home / ".codex" / "config.toml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        "model = \"foo\"\n[features]\nhooks = true\ngoals = false\n",
        encoding="utf-8",
    )
    assert b._is_hooks_feature_enabled() is True

    # disabled 状态
    config_path.write_text(
        "[features]\nhooks = false\n", encoding="utf-8",
    )
    assert b._is_hooks_feature_enabled() is False

    # 无 [features] 段
    config_path.write_text("model = \"foo\"\n", encoding="utf-8")
    assert b._is_hooks_feature_enabled() is False


def test_codex_is_karma_entry_recognizes_wrapper(fake_home):
    """karma 装的 hook entry（路径含 karma_ 前缀）被识别。"""
    b = CodexBackend()
    karma_entry = {"hooks": [{"type": "command", "command": "/x/karma_stop.py"}]}
    other_entry = {"hooks": [{"type": "command", "command": "/x/vibe-island"}]}
    assert b.is_karma_entry(karma_entry) is True
    assert b.is_karma_entry(other_entry) is False


# ---- detect_installed_backends ----


def test_detect_installed_returns_list_of_names():
    installed = detect_installed_backends()
    assert isinstance(installed, list)
    for name in installed:
        assert name in REGISTRY


def test_detect_installed_picks_up_each_backend(monkeypatch):
    """3 个 backend 都「装了」→ detect 返回 3 个（顺序按 REGISTRY）。"""
    monkeypatch.setattr(ClaudeCodeBackend, "client_installed", lambda self: True)
    monkeypatch.setattr(CodexBackend, "client_installed", lambda self: True)
    monkeypatch.setattr(CursorBackend, "client_installed", lambda self: True)
    assert detect_installed_backends() == ["claude-code", "codex", "cursor"]


def test_detect_installed_skips_uninstalled_backend(monkeypatch):
    """只装一个 → detect 只返回那个。"""
    monkeypatch.setattr(ClaudeCodeBackend, "client_installed", lambda self: False)
    monkeypatch.setattr(CodexBackend, "client_installed", lambda self: True)
    monkeypatch.setattr(CursorBackend, "client_installed", lambda self: False)
    assert detect_installed_backends() == ["codex"]


# ---- Cursor backend (v0.12.0) ----


def test_cursor_paths(fake_home):
    b = CursorBackend()
    assert b.hooks_dir() == fake_home / ".cursor" / "hooks"
    assert b.settings_path() == fake_home / ".cursor" / "hooks.json"
    assert b.settings_backup_path() == fake_home / ".cursor" / "hooks.json.before-karma"


def test_cursor_event_names_are_camelcase(fake_home):
    """Cursor event 名是 camelCase 小开头 — preToolUse 而非 PreToolUse.

    跟 Claude Code PascalCase 大开头不同, 写进 hooks.json 时大小写敏感.
    """
    b = CursorBackend()
    events = b.hook_events()
    assert "preToolUse" in events
    assert "postToolUse" in events
    assert "sessionStart" in events
    assert "stop" in events
    # 没有 PascalCase 形式 (Claude 是)
    assert "PreToolUse" not in events
    assert "SessionStart" not in events


def test_cursor_maps_before_submit_to_user_prompt_submit(fake_home):
    """v0.12.2: beforeSubmitPrompt 复用 user_prompt_submit wrapper (每 turn 注入)."""
    b = CursorBackend()
    events = b.hook_events()
    assert events.get("beforeSubmitPrompt") == "user_prompt_submit"
    assert "session_start" in events.values()


def test_cursor_event_entry_native_flat_command(fake_home):
    """Cursor hook entry 用 native flat `{command}` + stop 带 loop_limit."""
    b = CursorBackend()
    entry = b.build_event_entry("pre_tool_use", "preToolUse")
    assert "matcher" not in entry
    assert "hooks" not in entry
    assert "karma_pre_tool_use.py" in entry["command"]
    assert "type" not in entry
    stop_entry = b.build_event_entry("stop", "stop")
    assert stop_entry.get("loop_limit") == 10


def test_cursor_normalize_tool_name_shell_to_bash():
    """Cursor Shell tool == Claude Bash — 归一化."""
    b = CursorBackend()
    assert b.normalize_tool_name("Shell", {}) == "Bash"
    assert b.normalize_tool_name("Read", {}) == "Read"
    assert b.normalize_tool_name("Write", {}) == "Write"


def test_cursor_emit_deny_top_level_permission_shape():
    """Cursor preToolUse deny: 顶层 `permission` + `user_message` + `agent_message`.

    跟 Claude `hookSpecificOutput.permissionDecision` / Gemini `decision` 都不同.
    """
    import json as _json
    b = CursorBackend()
    out = _json.loads(b.emit_deny("triggered rule X", {}))
    assert out == {
        "permission": "deny",
        "user_message": "triggered rule X",
        "agent_message": "triggered rule X",
    }
    # 必须不含 hookSpecificOutput (Claude 形态)
    assert "hookSpecificOutput" not in out
    # 必须不含 decision (Gemini 形态)
    assert "decision" not in out


def test_cursor_emit_allow_top_level_permission_shape():
    """Cursor allow: 顶层 `permission: "allow"`."""
    import json as _json
    b = CursorBackend()
    out = _json.loads(b.emit_allow({}))
    assert out == {"permission": "allow"}


def test_cursor_emit_context_injection_snake_case_key():
    """Cursor sessionStart / postToolUse 用 snake_case `additional_context`."""
    import json as _json
    b = CursorBackend()
    out = _json.loads(b.emit_context_injection(
        "sessionStart", "you are sticky baseline", {},
    ))
    assert out == {"additional_context": "you are sticky baseline"}
    assert "additionalContext" not in out
    assert "hookSpecificOutput" not in out


def test_cursor_emit_context_injection_before_submit_nested():
    """beforeSubmitPrompt 走 third-party nested additionalContext; 空则 continue."""
    import json as _json
    b = CursorBackend()
    empty = _json.loads(b.emit_context_injection("beforeSubmitPrompt", "", {}))
    assert empty == {"continue": True}
    nested = _json.loads(b.emit_context_injection(
        "beforeSubmitPrompt", "anchor text", {},
    ))
    assert nested["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    assert nested["hookSpecificOutput"]["additionalContext"] == "anchor text"


def test_cursor_emit_stop_followup_message_not_decision_block():
    """Cursor stop 没 block 概念 — 用 `followup_message` auto-continue.

    这正映射 karma keep-pushing 「stop 时塞反思 prompt 让继续」语义,
    比 Gemini AfterAgent 强制返 {} fail-open 更适配 karma 干预模型.
    """
    import json as _json
    b = CursorBackend()
    out = _json.loads(b.emit_stop_block("keep thinking about root cause", {}))
    assert out == {"followup_message": "keep thinking about root cause"}
    # 必须不含 Claude 的 decision:block (协议不接受)
    assert "decision" not in out


def test_cursor_client_installed_falls_back_to_config_dir(fake_home, monkeypatch):
    """Cursor IDE 通常没 PATH 命令 (`cursor` 是可选 shell shim) — fallback
    检测 ~/.cursor 目录存在.
    """
    monkeypatch.setattr("shutil.which", lambda x: None)
    b = CursorBackend()
    # 默认 fake_home 下没 .cursor 目录 → False
    assert b.client_installed() is False
    # 创建后 → True
    (fake_home / ".cursor").mkdir()
    assert b.client_installed() is True


def test_cursor_is_karma_entry_recognizes_wrapper(fake_home):
    """karma 装的 hook entry (路径含 karma_ 前缀) 被识别."""
    b = CursorBackend()
    karma_entry = {"hooks": [{"type": "command", "command": "/x/karma_stop.py"}]}
    other_entry = {"hooks": [{"type": "command", "command": "/x/vibe-island"}]}
    assert b.is_karma_entry(karma_entry) is True
    assert b.is_karma_entry(other_entry) is False


def test_cursor_load_save_roundtrip(fake_home):
    b = CursorBackend()
    data = {"hooks": {"preToolUse": [{"hooks": [{"command": "/x", "type": "command"}]}]}}
    b.save_settings(data)
    loaded = b.load_settings()
    assert loaded == data


def test_cursor_load_corrupted_raises(fake_home):
    """损坏的 hooks.json 抛 SettingsParseError 不静默返回 {}."""
    b = CursorBackend()
    p = b.settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(SettingsParseError):
        b.load_settings()


# ---- detect_backend cursor routing (v0.12.0) ----


def test_detect_backend_routes_cursor_by_event_name():
    """payload.hook_event_name 含 Cursor camelCase event → 路由到 cursor."""
    from karma.backends.protocol_adapter import detect_backend
    assert detect_backend({"hook_event_name": "preToolUse"}) == "cursor"
    assert detect_backend({"hook_event_name": "sessionStart"}) == "cursor"
    assert detect_backend({"hook_event_name": "postToolUse"}) == "cursor"
    assert detect_backend({"hook_event_name": "stop"}) == "cursor"


def test_detect_backend_routes_cursor_by_path_fallback(monkeypatch):
    """sys.argv[0] 含 /.cursor/ → 路由到 cursor (event name 缺失兜底)."""
    from karma.backends import protocol_adapter
    monkeypatch.setattr(
        protocol_adapter.sys, "argv",
        ["/Users/x/.cursor/hooks/karma_pre_tool_use.py"],
    )
    assert protocol_adapter.detect_backend({}) == "cursor"
