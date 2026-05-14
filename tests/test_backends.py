"""多 backend 装机抽象测试 — Claude Code / Codex / 抽象接口。"""

from __future__ import annotations


import pytest

from karma.backends import REGISTRY, ClaudeCodeBackend, CodexBackend, detect_installed_backends
from karma.backends._base import SettingsParseError


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    """让 Path.home() 指向 tmp，让 backend 写到 tmp 不污染真 home。"""
    monkeypatch.setenv("HOME", str(tmp_path))
    # Path.home() 实际读 HOME 环境变量
    return tmp_path


def test_registry_has_both_backends():
    assert "claude-code" in REGISTRY
    assert "codex" in REGISTRY
    assert isinstance(REGISTRY["claude-code"], ClaudeCodeBackend)
    assert isinstance(REGISTRY["codex"], CodexBackend)


def test_backends_have_4_overlap_events():
    """两个 backend 都支持 4 个核心 event（UserPromptSubmit / PreToolUse /
    PostToolUse / Stop） — karma hook 入口可跨 backend 复用。"""
    expected = {"UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop"}
    assert set(REGISTRY["claude-code"].hook_events().keys()) == expected
    assert set(REGISTRY["codex"].hook_events().keys()) == expected


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
    """两个 backend 都「装了」→ detect 返回两个。"""
    monkeypatch.setattr(ClaudeCodeBackend, "client_installed", lambda self: True)
    monkeypatch.setattr(CodexBackend, "client_installed", lambda self: True)
    assert detect_installed_backends() == ["claude-code", "codex"]


def test_detect_installed_skips_uninstalled_backend(monkeypatch):
    """只装一个 → detect 只返回那个。"""
    monkeypatch.setattr(ClaudeCodeBackend, "client_installed", lambda self: False)
    monkeypatch.setattr(CodexBackend, "client_installed", lambda self: True)
    assert detect_installed_backends() == ["codex"]
