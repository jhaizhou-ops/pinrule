"""CLI install-hooks / uninstall-hooks / doctor 集成测试。

关键：必须保留其他人的 hook（vibe-island / rtk / codex-review 等）+ idempotent。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from karma import cli


# ---- 通用 fixtures ----

@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    """指向 tmp 的伪 home — 让 cli 写到 tmp 不污染真实 home。"""
    monkeypatch.setenv("HOME", str(tmp_path))
    # cli 模块里的 KARMA_DIR 是 module-level Path.home() 缓存，需重 patch
    monkeypatch.setattr(cli, "KARMA_DIR", tmp_path / ".claude" / "karma")
    return tmp_path


def _write_settings(home: Path, content: dict) -> Path:
    p = home / ".claude" / "settings.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(content, ensure_ascii=False, indent=2))
    return p


def _read_settings(home: Path) -> dict:
    return json.loads((home / ".claude" / "settings.json").read_text())


# ---- install-hooks ----

def test_install_hooks_creates_wrappers(fake_home, capsys):
    rc = cli.cmd_install_hooks()
    assert rc == 0
    hooks_dir = fake_home / ".claude" / "hooks"
    for name in ("user_prompt_submit", "pre_tool_use", "post_tool_use", "stop"):
        wrapper = hooks_dir / f"karma_{name}.py"
        assert wrapper.exists(), f"{wrapper} 应该被创建"
        assert os.access(wrapper, os.X_OK), f"{wrapper} 应该可执行"


def test_install_hooks_writes_settings_when_missing(fake_home, capsys):
    """settings.json 不存在 → 创建并写入 4 条 karma entry。"""
    cli.cmd_install_hooks()
    settings = _read_settings(fake_home)
    hooks = settings.get("hooks", {})
    for event in ("UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop"):
        assert event in hooks, f"hooks.{event} 应该被创建"
        cmds = [h["command"] for m in hooks[event] for h in m.get("hooks", [])]
        assert any("karma_" in c for c in cmds), f"{event} 应含 karma wrapper"


def test_install_hooks_preserves_other_hooks(fake_home):
    """settings.json 已有别人的 hook（vibe-island/rtk）→ install 后保留。"""
    existing = {
        "env": {},
        "permissions": {"allow": [], "deny": []},
        "model": "opus",
        "hooks": {
            "PostToolUse": [
                {
                    "matcher": "*",
                    "hooks": [
                        {"type": "command", "command": "/path/to/vibe-island-bridge"},
                    ],
                },
            ],
            "PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "rtk hook claude"}]},
            ],
        },
        "theme": "dark",
    }
    _write_settings(fake_home, existing)

    cli.cmd_install_hooks()
    settings = _read_settings(fake_home)

    # 顶层非 hooks 字段保留
    assert settings["model"] == "opus"
    assert settings["theme"] == "dark"

    # 别人的 hook 仍在
    post_cmds = [h["command"] for m in settings["hooks"]["PostToolUse"] for h in m.get("hooks", [])]
    assert any("vibe-island-bridge" in c for c in post_cmds), "vibe-island 不能被覆盖"
    pre_cmds = [h["command"] for m in settings["hooks"]["PreToolUse"] for h in m.get("hooks", [])]
    assert any("rtk hook claude" in c for c in pre_cmds), "rtk 不能被覆盖"

    # karma 也加进去了
    assert any("karma_post_tool_use" in c for c in post_cmds)
    assert any("karma_pre_tool_use" in c for c in pre_cmds)


def test_install_hooks_idempotent(fake_home):
    """跑两次 install 结果一致，不重复添加 karma entry。"""
    cli.cmd_install_hooks()
    settings_first = _read_settings(fake_home)
    karma_cmds_first = sorted(
        h["command"]
        for event in settings_first["hooks"].values()
        for m in event
        for h in m.get("hooks", [])
        if "karma_" in h["command"]
    )

    cli.cmd_install_hooks()
    settings_second = _read_settings(fake_home)
    karma_cmds_second = sorted(
        h["command"]
        for event in settings_second["hooks"].values()
        for m in event
        for h in m.get("hooks", [])
        if "karma_" in h["command"]
    )

    assert karma_cmds_first == karma_cmds_second
    # 4 个 karma 命令，每个一次
    assert len(karma_cmds_first) == 4


def test_install_hooks_stop_entry_has_no_matcher(fake_home):
    """Stop hook 不支持 matcher 字段 — Claude Code 会无声忽略整个 entry。

    这是真实踩过的坑（详 HANDOFF.md「Stop hook 不跑 → 撤回错误诊断」）：
    之前给所有 event 都加 matcher='*' 导致 Stop entry 被 Claude Code 忽略，
    Stop hook 整个 session 都没装上。这条测试守护这个反向约束。
    """
    cli.cmd_install_hooks()
    settings = _read_settings(fake_home)
    stop_entries = [e for e in settings["hooks"].get("Stop", []) if cli._is_karma_entry(e)]
    assert len(stop_entries) == 1, "Stop 应该有恰好 1 条 karma entry"
    assert "matcher" not in stop_entries[0], (
        "Stop entry 不能含 matcher 字段 — 否则 Claude Code 无声忽略整个 entry"
    )


def test_install_hooks_tool_events_keep_matcher(fake_home):
    """PreToolUse / PostToolUse / UserPromptSubmit 必须有 matcher='*'。

    与 Stop 形成对偶 — 工具相关 event 不加 matcher 也会让 Claude Code 不知道
    针对哪些 tool 跑（PreToolUse / PostToolUse 至少需要）。
    """
    cli.cmd_install_hooks()
    settings = _read_settings(fake_home)
    for event in ("PreToolUse", "PostToolUse", "UserPromptSubmit"):
        karma_entries = [e for e in settings["hooks"][event] if cli._is_karma_entry(e)]
        assert len(karma_entries) == 1
        assert karma_entries[0].get("matcher") == "*", f"{event} 必须 matcher='*'"


def test_install_hooks_backs_up_first_time(fake_home):
    """第一次运行 → 创建 settings.json.before-karma 备份。"""
    original = {"model": "opus", "hooks": {}}
    _write_settings(fake_home, original)

    cli.cmd_install_hooks()
    backup = fake_home / ".claude" / "settings.json.before-karma"
    assert backup.exists(), "第一次 install 应该备份原 settings"
    assert json.loads(backup.read_text()) == original


def test_install_hooks_does_not_overwrite_backup(fake_home):
    """已有备份 → 不要覆盖（保护原始备份）。"""
    original = {"model": "first", "hooks": {}}
    _write_settings(fake_home, original)
    cli.cmd_install_hooks()
    backup_first = (fake_home / ".claude" / "settings.json.before-karma").read_text()

    # 用户改 settings 后重 install — 备份不该被新 settings 覆盖
    _write_settings(fake_home, {"model": "changed", "hooks": {}})
    cli.cmd_install_hooks()
    backup_second = (fake_home / ".claude" / "settings.json.before-karma").read_text()
    assert backup_first == backup_second, "备份应保留最初版本"


# ---- uninstall-hooks ----

def test_uninstall_removes_wrappers_and_settings_entries(fake_home):
    cli.cmd_install_hooks()
    # verify install 后 karma entry 存在
    settings = _read_settings(fake_home)
    karma_cmds = [
        h["command"]
        for event in settings["hooks"].values()
        for m in event
        for h in m.get("hooks", [])
        if "karma_" in h["command"]
    ]
    assert len(karma_cmds) == 4

    cli.cmd_uninstall_hooks()
    settings_after = _read_settings(fake_home)
    karma_cmds_after = [
        h["command"]
        for event in settings_after["hooks"].values()
        for m in event
        for h in m.get("hooks", [])
        if "karma_" in h["command"]
    ]
    assert karma_cmds_after == [], "uninstall 后 settings 里不应有 karma entry"

    # wrapper 也被删
    hooks_dir = fake_home / ".claude" / "hooks"
    for name in ("user_prompt_submit", "pre_tool_use", "post_tool_use", "stop"):
        assert not (hooks_dir / f"karma_{name}.py").exists()


def test_uninstall_preserves_other_hooks(fake_home):
    """uninstall 不应破坏其他人的 hook entry。"""
    _write_settings(fake_home, {
        "hooks": {
            "PostToolUse": [
                {"matcher": "*", "hooks": [{"type": "command", "command": "/path/vibe"}]},
            ],
        },
    })
    cli.cmd_install_hooks()
    cli.cmd_uninstall_hooks()

    settings = _read_settings(fake_home)
    post = settings.get("hooks", {}).get("PostToolUse", [])
    cmds = [h["command"] for m in post for h in m.get("hooks", [])]
    assert any("vibe" in c for c in cmds), "vibe hook 应保留"
    assert not any("karma_" in c for c in cmds), "karma 应清掉"


# ---- doctor ----

def test_doctor_reports_missing_wrappers(fake_home, capsys):
    """没装 hook → doctor 报告缺失。"""
    # 准备最小 sticky 让 doctor 跑下去
    sticky_path = fake_home / ".claude" / "karma" / "sticky.yaml"
    sticky_path.parent.mkdir(parents=True, exist_ok=True)
    sticky_path.write_text("- id: test\n  preference: x\n")
    import karma.sticky
    import karma.violations
    import unittest.mock
    with unittest.mock.patch.object(karma.sticky, "DEFAULT_PATH", sticky_path):
        with unittest.mock.patch.object(cli, "STICKY_PATH", sticky_path):
            with unittest.mock.patch.object(karma.violations, "DEFAULT_PATH", fake_home / "v.jsonl"):
                with unittest.mock.patch.object(cli, "VIOLATIONS_PATH", fake_home / "v.jsonl"):
                    rc = cli.cmd_doctor()
    out = capsys.readouterr().out
    assert "✗" in out or "缺失" in out or "未安装" in out, f"doctor 应明确报告 hook 缺失: {out}"


def test_doctor_reports_fully_installed(fake_home, capsys):
    """install 后 doctor 应报告全部 ✓。"""
    sticky_path = fake_home / ".claude" / "karma" / "sticky.yaml"
    sticky_path.parent.mkdir(parents=True, exist_ok=True)
    sticky_path.write_text("- id: test\n  preference: x\n")
    import karma.sticky
    import karma.violations
    import unittest.mock
    cli.cmd_install_hooks()
    with unittest.mock.patch.object(karma.sticky, "DEFAULT_PATH", sticky_path):
        with unittest.mock.patch.object(cli, "STICKY_PATH", sticky_path):
            with unittest.mock.patch.object(karma.violations, "DEFAULT_PATH", fake_home / "v.jsonl"):
                with unittest.mock.patch.object(cli, "VIOLATIONS_PATH", fake_home / "v.jsonl"):
                    rc = cli.cmd_doctor()
    out = capsys.readouterr().out
    assert rc == 0
    # 4 个 hook event 都应该报告 ✓
    for event in ("UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop"):
        assert event in out, f"doctor 应列出 {event} 状态"
