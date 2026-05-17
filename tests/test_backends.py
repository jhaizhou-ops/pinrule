"""多 backend 装机抽象测试 — Claude Code / Codex / 抽象接口。"""

from __future__ import annotations


import pytest

from pinrule.backends import (
    REGISTRY,
    ClaudeCodeBackend,
    CodexBackend,
    CursorBackend,
    detect_installed_backends,
)
from pinrule.backends._base import SettingsParseError


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    """让 Path.home() / pinrule_install_root() 指向 tmp, backend 写 tmp 不污染真 home.

    跨平台细节:
    - Unix: Path.home() 读 $HOME
    - Windows: Path.home() 读 $USERPROFILE (有时回退到 $HOMEDRIVE+$HOMEPATH)
    - PINRULE_HOME (v0.16.11+ install_root sandbox 真路径): 优先级最高,
      所有 backend 装机路径都走它, 设了就稳跨平台.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("PINRULE_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def cursor_test_config_dir(fake_home, monkeypatch):
    """Cursor backend 测试用非 `.cursor` 目录名 — 部分沙箱禁止 mkdir `.cursor`."""
    dir_name = "cursor-pinrule-test"
    monkeypatch.setattr(CursorBackend, "_CONFIG_DIR_NAME", dir_name)
    return fake_home / dir_name


def test_registry_has_three_backends():
    assert "claude-code" in REGISTRY
    assert "codex" in REGISTRY
    assert "cursor" in REGISTRY
    assert "gemini-cli" not in REGISTRY  # v0.13.2 砍 Gemini
    assert isinstance(REGISTRY["claude-code"], ClaudeCodeBackend)
    assert isinstance(REGISTRY["codex"], CodexBackend)
    assert isinstance(REGISTRY["cursor"], CursorBackend)


def test_backends_all_have_common_pinrule_wrappers():
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
    assert b.settings_backup_path() == fake_home / ".claude" / "settings.json.before-pinrule"


def test_claude_code_event_entry_matcher(fake_home):
    """Stop event 不加 matcher（Claude Code 协议特性）；其他 3 个加 matcher='*'。"""
    b = ClaudeCodeBackend()
    pre = b.build_event_entry("pre_tool_use", "PreToolUse")
    assert pre.get("matcher") == "*"
    stop = b.build_event_entry("stop", "Stop")
    assert "matcher" not in stop


def test_claude_code_atomic_save(fake_home):
    """save_settings 用 tmp + os.replace，不留 .pinrule-tmp.* 残留。"""
    b = ClaudeCodeBackend()
    b.save_settings({"hooks": {}, "model": "opus"})
    assert b.settings_path().exists()
    tmp_files = list(b.settings_path().parent.glob("*pinrule-tmp*"))
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
    assert "pinrule_user_prompt_submit.py" in hooks[0]["command"]
    assert hooks[0].get("timeout") == 30


def test_codex_native_hook_surface_matches_docs_full_list(fake_home):
    """Codex hooks docs list 6 PascalCase native events; pinrule installs all 6.

    Reality check 2026-05-17: https://developers.openai.com/codex/hooks lists
    SessionStart / PreToolUse / PermissionRequest / PostToolUse /
    UserPromptSubmit / Stop as the released hook events. Generated schema links
    may contain future pre/post compact files, but the docs event table is the
    install surface.
    """
    from pinrule.backends.native_capabilities import CODEX_HOOK_EVENTS, CODEX_NATIVE_HOOKS

    docs_events = {
        "SessionStart",
        "PreToolUse",
        "PermissionRequest",
        "PostToolUse",
        "UserPromptSubmit",
        "Stop",
    }
    assert {spec["event"] for spec in CODEX_NATIVE_HOOKS} == docs_events
    assert set(CodexBackend().hook_events()) == docs_events
    assert CodexBackend().hook_events() == CODEX_HOOK_EVENTS
    assert all(event[:1].isupper() for event in CodexBackend().hook_events())


def test_codex_permission_request_maps_to_tool_gate_wrapper(fake_home):
    """PermissionRequest is a native codex gate and reuses pinrule's pre tool gate.

    v0.15.0 changes the old ADR-001 decision: native-first means the event is
    installed, but no new check engine is invented; it routes to the same
    pre_tool_use wrapper as PreToolUse.
    """
    events = CodexBackend().hook_events()
    assert events["PreToolUse"] == "pre_tool_use"
    assert events["PermissionRequest"] == "pre_tool_use"


def test_codex_install_writes_permission_request_entry(fake_home):
    """install-style settings include PermissionRequest with the shared wrapper."""
    b = CodexBackend()
    entry = b.build_event_entry(
        b.hook_events()["PermissionRequest"],
        "PermissionRequest",
    )
    hook = entry["hooks"][0]
    assert hook["type"] == "command"
    assert hook["timeout"] == 30
    assert "pinrule_pre_tool_use.py" in hook["command"]


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


def test_codex_is_pinrule_entry_recognizes_wrapper(fake_home):
    """pinrule 装的 hook entry（路径含 pinrule_ 前缀）被识别。"""
    b = CodexBackend()
    pinrule_entry = {"hooks": [{"type": "command", "command": "/x/pinrule_stop.py"}]}
    other_entry = {"hooks": [{"type": "command", "command": "/x/vibe-island"}]}
    assert b.is_pinrule_entry(pinrule_entry) is True
    assert b.is_pinrule_entry(other_entry) is False


def test_codex_trust_state_covers_permission_request(fake_home):
    """auto-trust state must include the newly installed PermissionRequest event."""
    b = CodexBackend()
    command = str(b.hooks_dir() / "pinrule_pre_tool_use.py")
    settings = {
        "hooks": {
            "PermissionRequest": [{
                "hooks": [{
                    "type": "command",
                    "command": command,
                    "timeout": 30,
                }]
            }]
        }
    }
    states = b.codex_hook_state_entries(settings)
    assert len(states) == 1
    key, value = next(iter(states.items()))
    assert ":permission_request:" in key
    assert value["enabled"] is True
    assert isinstance(value["trusted_hash"], str)
    assert value["trusted_hash"].startswith("sha256:")


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
    assert b.settings_backup_path() == fake_home / ".cursor" / "hooks.json.before-pinrule"


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


def test_cursor_native_hook_surface_superset_of_claude_wrappers(fake_home):
    """Cursor native surface covers all Claude wrappers plus IDE-only gates."""
    claude = set(ClaudeCodeBackend().hook_events().values())
    cursor = set(CursorBackend().hook_events().values())
    assert claude <= cursor
    assert "before_shell_execution" in cursor
    assert "before_mcp_execution" in cursor
    assert "after_agent_response" in cursor
    assert len(CursorBackend().hook_events()) == 12


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
    assert "pinrule_pre_tool_use.py" in entry["command"]
    assert "type" not in entry
    stop_entry = b.build_event_entry("stop", "stop")
    assert stop_entry.get("loop_limit") == 10


def test_cursor_normalize_tool_name_shell_to_bash():
    """Cursor Shell tool == Claude Bash — 归一化."""
    b = CursorBackend()
    assert b.normalize_tool_name("Shell", {}) == "Bash"
    assert b.normalize_tool_name("Read", {}) == "Read"
    assert b.normalize_tool_name("Write", {}) == "Write"
    assert b.normalize_tool_name("Task", {}) == "Agent"


def test_cursor_emit_pre_compact_user_message():
    """Cursor preCompact 用 user_message (observational); Claude 仍 passthrough."""
    import json as _json
    b = CursorBackend()
    out = _json.loads(b.emit_context_injection("preCompact", "saved rules", {}))
    assert out == {"user_message": "saved rules"}
    empty = _json.loads(b.emit_context_injection("preCompact", "", {}))
    assert empty == {}


def test_cursor_subagent_start_additional_context():
    """subagentStart 跟 sessionStart 一样走 snake_case additional_context."""
    import json as _json
    b = CursorBackend()
    out = _json.loads(b.emit_context_injection(
        "subagentStart", "sticky baseline", {},
    ))
    assert out == {"additional_context": "sticky baseline"}


def test_cursor_subagent_stop_loop_limit(fake_home):
    """subagentStop 跟 stop 一样带 loop_limit."""
    b = CursorBackend()
    entry = b.build_event_entry("subagent_stop", "subagentStop")
    assert entry.get("loop_limit") == 10


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

    这正映射 pinrule keep-pushing 「stop 时塞反思 prompt 让继续」语义,
    比 Gemini AfterAgent 强制返 {} fail-open 更适配 pinrule 干预模型.
    """
    import json as _json
    b = CursorBackend()
    out = _json.loads(b.emit_stop_block("keep thinking about root cause", {}))
    assert out == {"followup_message": "keep thinking about root cause"}
    # 必须不含 Claude 的 decision:block (协议不接受)
    assert "decision" not in out


def test_cursor_client_installed_falls_back_to_config_dir(
    monkeypatch, cursor_test_config_dir,
):
    """Cursor IDE 通常没 PATH 命令 (`cursor` 是可选 shell shim) — fallback
    检测 ~/.cursor 目录存在.
    """
    monkeypatch.setattr("shutil.which", lambda x: None)
    b = CursorBackend()
    # 默认 fake_home 下没配置目录 → False
    assert b.client_installed() is False
    # 创建后 → True
    cursor_test_config_dir.mkdir(parents=True)
    assert b.client_installed() is True


def test_cursor_is_pinrule_entry_recognizes_wrapper(fake_home):
    """pinrule 装的 hook entry (路径含 pinrule_ 前缀) 被识别."""
    b = CursorBackend()
    pinrule_entry = {"hooks": [{"type": "command", "command": "/x/pinrule_stop.py"}]}
    other_entry = {"hooks": [{"type": "command", "command": "/x/vibe-island"}]}
    assert b.is_pinrule_entry(pinrule_entry) is True
    assert b.is_pinrule_entry(other_entry) is False


def test_cursor_load_save_roundtrip(cursor_test_config_dir):
    b = CursorBackend()
    data = {"hooks": {"preToolUse": [{"hooks": [{"command": "/x", "type": "command"}]}]}}
    b.save_settings(data)
    loaded = b.load_settings()
    assert loaded == data


def test_cursor_load_corrupted_raises(cursor_test_config_dir):
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
    from pinrule.backends.protocol_adapter import detect_backend
    assert detect_backend({"hook_event_name": "preToolUse"}) == "cursor"
    assert detect_backend({"hook_event_name": "sessionStart"}) == "cursor"
    assert detect_backend({"hook_event_name": "postToolUse"}) == "cursor"
    assert detect_backend({"hook_event_name": "stop"}) == "cursor"


def test_detect_backend_routes_cursor_by_path_fallback(monkeypatch):
    """sys.argv[0] 含 /.cursor/ → 路由到 cursor (event name 缺失兜底)."""
    from pinrule.backends import protocol_adapter
    monkeypatch.setattr(
        protocol_adapter.sys, "argv",
        ["/Users/x/.cursor/hooks/pinrule_pre_tool_use.py"],
    )
    assert protocol_adapter.detect_backend({}) == "cursor"
