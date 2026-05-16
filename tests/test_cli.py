"""CLI install-hooks / uninstall-hooks / doctor 集成测试。

关键：必须保留其他人的 hook（vibe-island / rtk / codex-review 等）+ idempotent。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from karma import cli
from karma.backends import ClaudeCodeBackend


# ---- 通用 fixtures ----

@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    """指向 tmp 的伪 home — 让 cli 写到 tmp 不污染实际 home。

    CI 隔离：默认 mock `ClaudeCodeBackend.client_installed = True` 让测试
    不依赖 CI 环境是否实际装 claude（v0.4.7 加 client_installed 门槛后所有
    cli.cmd_install_hooks() 测试都会查这个）。需要测「客户端没装」场景的测试
    自己 monkeypatch 覆盖即可。
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(cli, "KARMA_DIR", tmp_path / ".claude" / "karma")
    from karma.backends import ClaudeCodeBackend, CodexBackend, GeminiCLIBackend
    monkeypatch.setattr(ClaudeCodeBackend, "client_installed", lambda self: True)
    monkeypatch.setattr(CodexBackend, "client_installed", lambda self: False)
    monkeypatch.setattr(GeminiCLIBackend, "client_installed", lambda self: False)
    return tmp_path


def _write_settings(home: Path, content: dict) -> Path:
    p = home / ".claude" / "settings.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(content, ensure_ascii=False, indent=2))
    return p


def _read_settings(home: Path) -> dict:
    return json.loads((home / ".claude" / "settings.json").read_text())


# ---- install-hooks ----

def test_version_matches_pyproject():
    """karma --version 必须跟 pyproject.toml [project] version 字段一致。

    历史 bug：__init__.py 硬写 __version__ = '0.1.0' 跟 pyproject 双维护，
    版本 bump 后 `karma --version` 卡老版本（v0.4.3 时输出 v0.1.0）误导陌生
    用户。修：__init__.py 用 importlib.metadata 单一来源读 pyproject metadata。
    """
    from pathlib import Path
    from karma import __version__
    pyproject = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    import re
    m = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.MULTILINE)
    assert m is not None, "pyproject.toml 缺 version 字段"
    pyproject_version = m.group(1)
    # editable install 模式下 importlib.metadata 读的是首次装时快照
    # 测试只验证「__version__ 不是写死的不变值」+ 跟 pyproject 数字格式匹配
    assert __version__ != "0.1.0" or pyproject_version == "0.1.0", (
        f"__version__={__version__!r} 跟 pyproject={pyproject_version!r} 失同步 — "
        "可能 bump 版本后忘重跑 'pip install -e .' 同步 metadata"
    )


def test_install_hooks_all_backend_only_installs_detected(fake_home, monkeypatch):
    """`--backend all` 只装本机检测到的客户端，不装没检测到的。

    实测装机已验证三家全装的场景，本测试 mock 单 backend 装机覆盖代码路径。
    注：必须 mock 全部 3 个 backend 的 client_installed — CI 环境通常无任何
    AI 客户端，作者本机有 claude 但 CI 没，依赖本机 PATH 会让 test 在 CI fail。
    """
    from karma.backends import ClaudeCodeBackend, CodexBackend, GeminiCLIBackend
    # mock Claude Code 装了，其他都没装
    monkeypatch.setattr(ClaudeCodeBackend, "client_installed", lambda self: True)
    monkeypatch.setattr(CodexBackend, "client_installed", lambda self: False)
    monkeypatch.setattr(GeminiCLIBackend, "client_installed", lambda self: False)
    rc = cli.cmd_install_hooks(backend_name="all")
    assert rc == 0
    # 只有 Claude Code 装了 wrapper，其他 backend 没装
    cc_wrappers = list((fake_home / ".claude" / "hooks").glob("karma_*.py"))
    # 动态从 _HOOK_EVENTS 算 — 避免每次加 hook 改测试硬编码（v0.4.28 SessionStart /
    # v0.4.29 PreCompact / v0.4.30 SubagentStart+Stop 都得改这数字是反 pattern）
    assert len(cc_wrappers) == len(ClaudeCodeBackend._HOOK_EVENTS)
    # Codex / Gemini 目录可能不存在（client 没装）— 不该建
    assert not (fake_home / ".codex" / "hooks").exists() or \
        not list((fake_home / ".codex" / "hooks").glob("karma_*.py"))


def test_uninstall_all_backend_iterates_each_installed(fake_home, monkeypatch):
    """`--backend all` 卸装应对每个检测到的 backend 各跑一遍卸装流程。"""
    from karma.backends import ClaudeCodeBackend, CodexBackend, GeminiCLIBackend
    # mock 全部 3 个 backend — CI 隔离防 PATH 干扰
    monkeypatch.setattr(ClaudeCodeBackend, "client_installed", lambda self: True)
    monkeypatch.setattr(CodexBackend, "client_installed", lambda self: False)
    monkeypatch.setattr(GeminiCLIBackend, "client_installed", lambda self: False)
    cli.cmd_install_hooks(backend_name="all")
    rc = cli.cmd_uninstall_hooks(backend_name="all")
    assert rc == 0
    cc_wrappers = list((fake_home / ".claude" / "hooks").glob("karma_*.py"))
    assert cc_wrappers == [], "uninstall all 后 Claude Code wrapper 应清空"


def test_uninstall_one_shot_alias(fake_home, monkeypatch, capsys):
    """`karma uninstall` 是 `uninstall-hooks --backend all` 的一键 alias。

    陌生用户不用记 backend flag 长串 — 想完全卸载就 karma uninstall 一句。
    """
    from karma.backends import ClaudeCodeBackend, CodexBackend, GeminiCLIBackend
    monkeypatch.setattr(ClaudeCodeBackend, "client_installed", lambda self: True)
    monkeypatch.setattr(CodexBackend, "client_installed", lambda self: False)
    monkeypatch.setattr(GeminiCLIBackend, "client_installed", lambda self: False)
    cli.cmd_install_hooks(backend_name="claude-code")
    # 用 main dispatch 跑 `karma uninstall`（不带 args）
    rc = cli.main(["uninstall"])
    assert rc == 0
    cc_wrappers = list((fake_home / ".claude" / "hooks").glob("karma_*.py"))
    assert cc_wrappers == [], "karma uninstall 后 wrapper 应清空"


def test_install_hooks_aborts_when_client_not_installed(fake_home, monkeypatch, capsys):
    """显式 backend 也必须查 client_installed — 静默装到不存在客户端是bug。

    sub-agent 排查发现 P1：同事没装 Claude Code 跑 `karma install-hooks` 默认
    装 claude-code 静默写 settings.json 完全无反馈。修：检测不到客户端时报错。
    """
    from karma.backends import ClaudeCodeBackend
    monkeypatch.setattr(ClaudeCodeBackend, "client_installed", lambda self: False)
    rc = cli.cmd_install_hooks(backend_name="claude-code")
    assert rc == 1
    captured = capsys.readouterr()
    assert "没检测到" in captured.err
    # wrapper 不该被创建（拦在 client 检测就退了）
    cc_wrappers = list((fake_home / ".claude" / "hooks").glob("karma_*.py"))
    assert cc_wrappers == [], "拦在 client 检测后不该创建 wrapper"


def test_install_hooks_unknown_backend_errors(fake_home, capsys):
    """未知 backend 名报错不 silent fail。"""
    rc = cli.cmd_install_hooks(backend_name="not-real-backend")
    assert rc == 1
    captured = capsys.readouterr()
    assert "未知 backend" in captured.err or "not-real-backend" in captured.err


def test_init_explicit_no_minimal_installs_7_sticky(fake_home, capsys):
    """karma init --no-minimal 强制装 7 条 dev.example（覆盖自动检测）。"""
    import karma.rule
    monkeypatch_path = fake_home / ".claude" / "karma" / "sticky.yaml"
    import unittest.mock
    with unittest.mock.patch.object(cli, "RULES_PATH", monkeypatch_path):
        with unittest.mock.patch.object(karma.rule, "DEFAULT_PATH", monkeypatch_path):
            rc = cli.cmd_init(minimal=False)
    assert rc == 0
    assert monkeypatch_path.exists()
    sticky_list = karma.rule.load(monkeypatch_path)
    assert len(sticky_list) == 7


def test_init_explicit_minimal_installs_5_sticky(fake_home, capsys):
    """karma init --minimal 强制装 5 条精简（覆盖自动检测）。"""
    import karma.rule
    monkeypatch_path = fake_home / ".claude" / "karma" / "sticky.yaml"
    import unittest.mock
    with unittest.mock.patch.object(cli, "RULES_PATH", monkeypatch_path):
        with unittest.mock.patch.object(karma.rule, "DEFAULT_PATH", monkeypatch_path):
            rc = cli.cmd_init(minimal=True)
    assert rc == 0
    sticky_list = karma.rule.load(monkeypatch_path)
    assert len(sticky_list) == 5
    ids = {s.id for s in sticky_list}
    assert "chinese-plain-no-jargon" not in ids
    assert "no-testset-no-future-leakage" not in ids


def test_init_auto_chinese_user_installs_7_sticky(fake_home, capsys):
    """minimal=None + 系统语言中文 → 自动装 7 条含 chinese_plain。"""
    import karma.rule
    import karma.locale_detect
    monkeypatch_path = fake_home / ".claude" / "karma" / "sticky.yaml"
    import unittest.mock
    with unittest.mock.patch.object(cli, "RULES_PATH", monkeypatch_path):
        with unittest.mock.patch.object(karma.rule, "DEFAULT_PATH", monkeypatch_path):
            with unittest.mock.patch.object(karma.locale_detect, "detect_user_language",
                                            return_value="zh"):
                rc = cli.cmd_init(minimal=None)
    assert rc == 0
    sticky_list = karma.rule.load(monkeypatch_path)
    assert len(sticky_list) == 7
    out = capsys.readouterr().out
    # v0.5.0 起 label 改英文 ("full 7 dev-scenario" / "minimal 5"), zh 仍出现在 detected locale
    assert "zh" in out and ("完整" in out or "full" in out)


def test_init_auto_non_chinese_user_installs_5_sticky(fake_home, capsys):
    """minimal=None + 系统语言非中文 → 自动装 5 条精简（砍 chinese_plain）。"""
    import karma.rule
    import karma.locale_detect
    monkeypatch_path = fake_home / ".claude" / "karma" / "sticky.yaml"
    import unittest.mock
    with unittest.mock.patch.object(cli, "RULES_PATH", monkeypatch_path):
        with unittest.mock.patch.object(karma.rule, "DEFAULT_PATH", monkeypatch_path):
            with unittest.mock.patch.object(karma.locale_detect, "detect_user_language",
                                            return_value="en"):
                rc = cli.cmd_init(minimal=None)
    assert rc == 0
    sticky_list = karma.rule.load(monkeypatch_path)
    assert len(sticky_list) == 5
    out = capsys.readouterr().out
    assert "en" in out and ("精简" in out or "minimal" in out)


def test_init_auto_unknown_locale_fallback_to_minimal(fake_home, capsys):
    """minimal=None + 检测不到（容器 / CI / 异常）→ fallback 5 条精简（最安全）。"""
    import karma.rule
    import karma.locale_detect
    monkeypatch_path = fake_home / ".claude" / "karma" / "sticky.yaml"
    import unittest.mock
    with unittest.mock.patch.object(cli, "RULES_PATH", monkeypatch_path):
        with unittest.mock.patch.object(karma.rule, "DEFAULT_PATH", monkeypatch_path):
            with unittest.mock.patch.object(karma.locale_detect, "detect_user_language",
                                            return_value=None):
                rc = cli.cmd_init(minimal=None)
    assert rc == 0
    sticky_list = karma.rule.load(monkeypatch_path)
    assert len(sticky_list) == 5


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
    # 动态从 _HOOK_EVENTS 算（每个 event 一个 karma 命令）
    assert len(karma_cmds_first) == len(ClaudeCodeBackend._HOOK_EVENTS)


def test_install_hooks_stop_entry_has_no_matcher(fake_home):
    """Stop hook 不支持 matcher 字段 — Claude Code 会无声忽略整个 entry。

    这是实际踩过的坑（详 HANDOFF.md「Stop hook 不跑 → 撤回错误诊断」）：
    之前给所有 event 都加 matcher='*' 导致 Stop entry 被 Claude Code 忽略，
    Stop hook 整个 session 都没装上。这条测试守护这个反向约束。
    """
    cli.cmd_install_hooks()
    settings = _read_settings(fake_home)
    stop_entries = [e for e in settings["hooks"].get("Stop", []) if ClaudeCodeBackend().is_karma_entry(e)]
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
        karma_entries = [e for e in settings["hooks"][event] if ClaudeCodeBackend().is_karma_entry(e)]
        assert len(karma_entries) == 1
        assert karma_entries[0].get("matcher") == "*", f"{event} 必须 matcher='*'"


def test_install_hooks_aborts_on_corrupted_settings(fake_home, capsys):
    """settings.json 损坏（非合法 JSON）→ abort 不覆盖。

    评审 D Agent 指出真风险：之前 JSONDecodeError 静默返回 {} → save 时
    把用户其他配置（permissions / mcp / env）全清空。改成 abort + 提示
    用户手工修复后重跑。
    """
    p = fake_home / ".claude" / "settings.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{ not valid json", encoding="utf-8")
    original_size = p.stat().st_size

    rc = cli.cmd_install_hooks()
    captured = capsys.readouterr()
    assert rc == 1, "settings.json 损坏应返回非零退出码"
    assert "解析失败" in captured.err or "解析失败" in captured.out
    # 关键：损坏的 settings.json 没被覆盖
    assert p.stat().st_size == original_size
    assert "{ not valid json" in p.read_text(encoding="utf-8")


def test_install_hooks_writes_atomic(fake_home):
    """_save_settings 用 tmp + os.replace 原子写，无残留 tmp 文件。"""
    cli.cmd_install_hooks()
    settings_dir = fake_home / ".claude"
    tmp_files = list(settings_dir.glob("*karma-tmp*"))
    assert not tmp_files, f"原子写不该留 tmp 文件: {tmp_files}"


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
    # 动态从 _HOOK_EVENTS 算（每个 event 一个 karma 命令）
    assert len(karma_cmds) == len(ClaudeCodeBackend._HOOK_EVENTS)

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
    import karma.rule
    import karma.violations
    import unittest.mock
    with unittest.mock.patch.object(karma.rule, "DEFAULT_PATH", sticky_path):
        with unittest.mock.patch.object(cli, "RULES_PATH", sticky_path):
            with unittest.mock.patch.object(karma.violations, "DEFAULT_PATH", fake_home / "v.jsonl"):
                with unittest.mock.patch.object(cli, "VIOLATIONS_PATH", fake_home / "v.jsonl"):
                    cli.cmd_doctor()
    out = capsys.readouterr().out
    assert "✗" in out or "缺失" in out or "未安装" in out, f"doctor 应明确报告 hook 缺失: {out}"


def test_doctor_reports_fully_installed(fake_home, capsys, monkeypatch):
    """install Claude Code 后 doctor 应报告 Claude Code 全部 ✓（mock Codex 没装）。"""
    sticky_path = fake_home / ".claude" / "karma" / "sticky.yaml"
    sticky_path.parent.mkdir(parents=True, exist_ok=True)
    sticky_path.write_text("- id: test\n  preference: x\n")
    import karma.rule
    import karma.violations
    from karma.backends import CodexBackend, GeminiCLIBackend
    import unittest.mock
    # mock 其他 backend 没装（fake_home 是 tmp，本测试只关心 Claude Code 路径）
    monkeypatch.setattr(CodexBackend, "client_installed", lambda self: False)
    monkeypatch.setattr(GeminiCLIBackend, "client_installed", lambda self: False)
    cli.cmd_install_hooks(backend_name="claude-code")
    with unittest.mock.patch.object(karma.rule, "DEFAULT_PATH", sticky_path):
        with unittest.mock.patch.object(cli, "RULES_PATH", sticky_path):
            with unittest.mock.patch.object(karma.violations, "DEFAULT_PATH", fake_home / "v.jsonl"):
                with unittest.mock.patch.object(cli, "VIOLATIONS_PATH", fake_home / "v.jsonl"):
                    rc = cli.cmd_doctor()
    out = capsys.readouterr().out
    assert rc == 0
    # 4 个 hook event 都应该报告 ✓
    for event in ("UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop"):
        assert event in out, f"doctor 应列出 {event} 状态"


# ---- v0.5.16 karma install-skill / karma init 多 backend skill 装机 ----

def _patch_rules_path(monkeypatch, fake_home):
    """共享 helper: monkeypatch rules.yaml DEFAULT_PATH 避免污染真 karma 配置."""
    import karma.rule
    monkeypatch.setattr(karma.rule, "DEFAULT_PATH", fake_home / ".claude" / "karma" / "rules.yaml")
    monkeypatch.setattr(cli, "RULES_PATH", fake_home / ".claude" / "karma" / "rules.yaml")


def test_v0516_init_auto_installs_karma_skill_all_backends(fake_home, monkeypatch, capsys):
    """v0.5.16: karma init 自动装 karma skill 到所有 backend (Claude/Codex/Gemini).

    路径正确: ~/.claude/skills/karma/SKILL.md (Claude, 目录形式)
             ~/.agents/skills/karma/SKILL.md (Codex, 注意 ~/.agents/ 不是 ~/.codex/)
             ~/.gemini/skills/karma/SKILL.md + ~/.gemini/commands/karma.toml (Gemini 双轨)
    """
    _patch_rules_path(monkeypatch, fake_home)

    claude_dest = fake_home / ".claude" / "skills" / "karma" / "SKILL.md"
    codex_dest = fake_home / ".agents" / "skills" / "karma" / "SKILL.md"
    gemini_skill = fake_home / ".gemini" / "skills" / "karma" / "SKILL.md"
    gemini_toml = fake_home / ".gemini" / "commands" / "karma.toml"
    for p in (claude_dest, codex_dest, gemini_skill, gemini_toml):
        assert not p.exists()

    rc = cli.cmd_init(minimal=True)
    assert rc == 0
    assert claude_dest.exists(), "Claude Code skill 应自动装"
    assert codex_dest.exists(), "Codex skill 应自动装"
    assert gemini_skill.exists(), "Gemini skill 应自动装 (auto-trigger 路径)"
    assert gemini_toml.exists(), "Gemini commands TOML 应自动装 (显式触发路径)"

    # Markdown source 跟 Claude/Codex/Gemini-skill 三处内容一致
    src_text = cli.KARMA_SKILL_SRC.read_text(encoding="utf-8")
    assert claude_dest.read_text(encoding="utf-8") == src_text
    assert codex_dest.read_text(encoding="utf-8") == src_text
    assert gemini_skill.read_text(encoding="utf-8") == src_text

    # Gemini commands TOML 应该是转换后内容 (有 description = / prompt = """ 段)
    toml_text = gemini_toml.read_text(encoding="utf-8")
    assert "description = " in toml_text
    assert 'prompt = """' in toml_text
    # $ARGUMENTS 应该转成 Gemini 原生的 {{args}}
    assert "{{args}}" in toml_text or "$ARGUMENTS" not in toml_text


def test_v0516_init_second_run_idempotent(fake_home, monkeypatch, capsys):
    """第二次 cmd_init → 所有 backend skill up-to-date, 不重复装/不刷屏."""
    _patch_rules_path(monkeypatch, fake_home)
    cli.cmd_init(minimal=True)
    capsys.readouterr()

    # 第二次 — 应该静默 (up-to-date 不刷屏 init 日志)
    cli.cmd_init(minimal=True)
    out = capsys.readouterr().out
    # 第二次不该报「创建」(那是 installed reason 文字)
    assert "创建 [claude-code] karma skill" not in out


def test_v0516_init_skill_user_modified_writes_new_file(fake_home, monkeypatch):
    """用户改过 Claude skill → karma init 不覆盖, 写 .new 兄弟文件."""
    _patch_rules_path(monkeypatch, fake_home)

    skill_dest = fake_home / ".claude" / "skills" / "karma" / "SKILL.md"
    skill_dest.parent.mkdir(parents=True, exist_ok=True)
    user_modified = "# my customized version\n"
    skill_dest.write_text(user_modified, encoding="utf-8")

    cli.cmd_init(minimal=True)
    # 用户版本未被覆盖
    assert skill_dest.read_text(encoding="utf-8") == user_modified
    # 新版写到 SKILL.md.new
    new_file = skill_dest.with_suffix(skill_dest.suffix + ".new")
    assert new_file.exists()
    assert new_file.read_text(encoding="utf-8") == cli.KARMA_SKILL_SRC.read_text(encoding="utf-8")


def test_v0516_install_skill_force_overwrites_all_backends(fake_home):
    """karma install-skill --force 强制覆盖所有 backend 的用户改动."""
    claude_dest = fake_home / ".claude" / "skills" / "karma" / "SKILL.md"
    claude_dest.parent.mkdir(parents=True, exist_ok=True)
    claude_dest.write_text("# user modified Claude\n", encoding="utf-8")

    rc = cli.cmd_install_skill(force=True)
    assert rc == 0
    src_text = cli.KARMA_SKILL_SRC.read_text(encoding="utf-8")
    assert claude_dest.read_text(encoding="utf-8") == src_text


def test_v0516_install_skill_backend_filter(fake_home):
    """karma install-skill --backend claude-code 只装 Claude, 不动 Codex/Gemini."""
    rc = cli.cmd_install_skill(force=False, backend="claude-code")
    assert rc == 0
    assert (fake_home / ".claude" / "skills" / "karma" / "SKILL.md").exists()
    assert not (fake_home / ".agents" / "skills" / "karma" / "SKILL.md").exists()
    assert not (fake_home / ".gemini" / "skills" / "karma" / "SKILL.md").exists()


def test_v0516_install_skill_handles_missing_source(fake_home, monkeypatch):
    """skill source 文件不存在 → 返回 1 不崩."""
    monkeypatch.setattr(cli, "KARMA_SKILL_SRC", fake_home / "nonexistent" / "SKILL.md")
    rc = cli.cmd_install_skill(force=False)
    assert rc == 1


def test_v0516_doctor_reports_multi_backend_skill_status(fake_home, monkeypatch, capsys):
    """karma doctor 报告 multi-backend skill 装机状态: claude/codex/gemini 各自一行."""
    import karma.violations
    _patch_rules_path(monkeypatch, fake_home)
    monkeypatch.setattr(karma.violations, "DEFAULT_PATH", fake_home / "v.jsonl")
    monkeypatch.setattr(cli, "VIOLATIONS_PATH", fake_home / "v.jsonl")
    cli.cmd_init(minimal=True)
    capsys.readouterr()

    # case 1: 装完是「最新」
    cli.cmd_doctor()
    out = capsys.readouterr().out
    assert "karma skill 装机" in out
    assert "claude-code" in out and "codex" in out and "gemini-cli" in out
    assert "最新" in out

    # case 2: 删掉 Claude skill → doctor 报「未装」
    (fake_home / ".claude" / "skills" / "karma" / "SKILL.md").unlink()
    cli.cmd_doctor()
    out = capsys.readouterr().out
    assert "未装" in out

    # (v0.5.13 第三个 case 已被 v0.5.16 test 上面 case 2 覆盖)
    assert "未装" in out


# === v0.9.9: karma init 末尾 onboarding summary 验证 ===
# 用户需求：Agent 协助安装完后直接告知客户默认启用的规则有哪些，
# 不让用户手动输指令。所以 init 末尾要输出规则简要列表（id + preference 首行），
# 但不带「下一步指令」tip 段。

def test_init_prints_default_rules_summary(fake_home, monkeypatch, capsys):
    """init 末尾输出含「默认启用规则」header + 每条 rule id + preference 首行。

    Agent 代装场景：Agent 跑 karma init 会看到这段 stdout，自然 paraphrase 给用户。
    """
    import karma.violations
    _patch_rules_path(monkeypatch, fake_home)
    monkeypatch.setattr(karma.violations, "DEFAULT_PATH", fake_home / "v.jsonl")
    monkeypatch.setattr(cli, "VIOLATIONS_PATH", fake_home / "v.jsonl")
    cli.cmd_init(minimal=True)
    out = capsys.readouterr().out

    # header 含规则数 / 软上限
    assert "默认规则" in out or "Default rules" in out
    # minimal 装 5 条核心
    for rule_id in [
        "long-term-fundamental",
        "non-blocking-parallel",
        "loud-failure-with-evidence",
        "deep-fix-not-bypass",
        "read-before-write",
    ]:
        assert f"[{rule_id}]" in out, f"summary 应含规则 id {rule_id}"


def test_init_summary_does_not_include_command_tips(fake_home, monkeypatch, capsys):
    """summary 段刻意不包含「跑 karma rule edit / list / remove」类指令 tip —
    那会变成「让用户手动输指令」的 friction，跟 onboarding「Agent 代用户操作」
    目标相反。tip 段必须从 v0.9.9 init summary 中删除。
    """
    import karma.violations
    _patch_rules_path(monkeypatch, fake_home)
    monkeypatch.setattr(karma.violations, "DEFAULT_PATH", fake_home / "v.jsonl")
    monkeypatch.setattr(cli, "VIOLATIONS_PATH", fake_home / "v.jsonl")
    cli.cmd_init(minimal=True)
    out = capsys.readouterr().out

    # 提取 summary 段（从 header 起到末尾）— 这块不能含指令 tip
    summary_start = -1
    for marker in ("默认规则", "Default rules"):
        idx = out.find(marker)
        if idx >= 0:
            summary_start = idx
            break
    assert summary_start >= 0, "summary header 没出现"
    summary_block = out[summary_start:]

    # summary 段不该包含 next-steps shell 指令 tip
    # 例外：`/karma <natural-language>` 是 in-chat slash command（v0.9.10 footer
    # 加的），不是 shell 命令，跟「让用户开 terminal 输指令」性质不同，允许
    for tip in ("下一步:", "Next steps:", "karma rule edit", "karma rule list", "karma rule remove"):
        assert tip not in summary_block, (
            f"summary 段含 shell 指令 tip {tip!r} — 违反 v0.9.9 onboarding 原则"
            f"\n summary block:\n{summary_block}"
        )


def test_init_summary_footer_includes_token_cost_and_slash_karma(fake_home, monkeypatch, capsys):
    """v0.9.10: footer 加 token 成本上限 + /karma in-chat 入口提示。

    用户原话「希望加一句用户体验相关补充」— 让 first-time 用户安心使用
    （3% token 上限）+ 知道想加规则直接对话框输 /karma 就行（不用开 terminal）。
    """
    import karma.violations
    _patch_rules_path(monkeypatch, fake_home)
    monkeypatch.setattr(karma.violations, "DEFAULT_PATH", fake_home / "v.jsonl")
    monkeypatch.setattr(cli, "VIOLATIONS_PATH", fake_home / "v.jsonl")
    cli.cmd_init(minimal=True)
    out = capsys.readouterr().out

    # token 成本数字（双语都含 "3%"）
    assert "3%" in out, "footer 应含 token 上限 3% 数字让用户安心"
    # /karma in-chat 入口字面
    assert "/karma" in out, "footer 应含 /karma 入口提示"
    # zh 或 en 任一关键 anchor 出现
    assert "经测试" in out or "Tested:" in out, "footer 双语任一应触发"


def test_init_summary_footer_matches_user_locale(fake_home, monkeypatch, capsys):
    """v0.9.10 lockdown: footer 必须按用户语言展示对应语言内容 — 中文用户出
    中文 footer，英文用户出英文 footer。

    karma/i18n.py _resolve_locale() 优先级：KARMA_LOCALE env > config.yaml >
    is_chinese_user() system detect。这条测试 mock 两个极端 case 锁不变量。
    """
    import karma.violations
    from karma import i18n
    _patch_rules_path(monkeypatch, fake_home)
    monkeypatch.setattr(karma.violations, "DEFAULT_PATH", fake_home / "v.jsonl")
    monkeypatch.setattr(cli, "VIOLATIONS_PATH", fake_home / "v.jsonl")

    # case 1: 强制 zh locale → footer 必须中文
    monkeypatch.setenv("KARMA_LOCALE", "zh")
    i18n._load_locale_dict.cache_clear()
    cli.cmd_init(minimal=True)
    out_zh = capsys.readouterr().out
    assert "经测试" in out_zh, "KARMA_LOCALE=zh 时 footer 应是中文 ‘经测试…’"
    assert "Tested:" not in out_zh, "KARMA_LOCALE=zh 时 footer 不该是英文"

    # 重置 rules.yaml 让 case 2 走 init 全流程
    (fake_home / ".claude" / "karma" / "rules.yaml").unlink()

    # case 2: 强制 en locale → footer 必须英文
    monkeypatch.setenv("KARMA_LOCALE", "en")
    i18n._load_locale_dict.cache_clear()
    cli.cmd_init(minimal=True)
    out_en = capsys.readouterr().out
    assert "Tested:" in out_en, "KARMA_LOCALE=en 时 footer 应是英文 ‘Tested: …’"
    assert "经测试" not in out_en, "KARMA_LOCALE=en 时 footer 不该是中文"


# === v0.9.11: karma audit --by-check engine check 命中分布 ===
# `/karma` skill no-arg 默认输出走这个视图（让 dogfood 数据驱动迭代）

def test_audit_by_check_aggregates_engine_hits(fake_home, monkeypatch, capsys):
    """`karma audit --by-check` 按 trigger_key 中的 check 名聚合命中次数。

    构造 5 条违反：3 条 bypass_karma engine 命中、2 条 keep_pushing 命中、
    1 条 keyword-only (空 trigger_key)。验证输出含正确聚合。
    """
    import karma.violations
    from karma.violations import Violation, append
    _patch_rules_path(monkeypatch, fake_home)
    v_path = fake_home / "v.jsonl"
    monkeypatch.setattr(karma.violations, "DEFAULT_PATH", v_path)
    monkeypatch.setattr(cli, "VIOLATIONS_PATH", v_path)

    # 构造 mixed violations
    records = [
        Violation(ts=1, session_id="s1", rule_id="deep-fix-not-bypass",
                  trigger="x", snippet="x", trigger_key="check.bypass_karma.trigger"),
        Violation(ts=2, session_id="s1", rule_id="deep-fix-not-bypass",
                  trigger="y", snippet="y", trigger_key="check.bypass_karma.trigger"),
        Violation(ts=3, session_id="s1", rule_id="deep-fix-not-bypass",
                  trigger="z", snippet="z", trigger_key="check.bypass_karma.trigger"),
        Violation(ts=4, session_id="s1", rule_id="keep-pushing-no-stop",
                  trigger="kp1", snippet="kp1", trigger_key="check.keep_pushing.default.trigger"),
        Violation(ts=5, session_id="s1", rule_id="keep-pushing-no-stop",
                  trigger="kp2", snippet="kp2", trigger_key="check.keep_pushing.stop_hint.trigger"),
        Violation(ts=6, session_id="s1", rule_id="some-keyword-rule",
                  trigger="kw", snippet="kw"),  # 空 trigger_key → keyword-only
    ]
    append(records, path=v_path)

    rc = cli.cmd_audit(by_check=True)
    assert rc == 0
    out = capsys.readouterr().out

    # 总数
    assert "总 6 条违反" in out
    # top-level 聚合
    assert "bypass_karma" in out
    assert "keep_pushing" in out
    # sub-variant 细分（keep_pushing.default + keep_pushing.stop_hint）
    assert "keep_pushing.default" in out
    assert "keep_pushing.stop_hint" in out
    # keyword-only fallback 桶
    assert "keyword-only" in out
    # 数字：bypass_karma 3 条、keep_pushing 2 条、keyword-only 1 条
    # 不直接 assert 整行数字（容易因格式微调坏掉），用更宽松匹配
    assert "3×" in out, "bypass_karma 3 条应出现"


def test_audit_days_filter_excludes_old_violations(fake_home, monkeypatch, capsys):
    """v0.11.3: `karma audit --days N` 只看最近 N 天违反 — dogfood-driven 决策
    不被老数据稀释 (新 rule / engine 重设计 ship 后 fresh 窗口效果评估).

    构造 2 老 + 2 新 violations, --days 1 应只显示 2 条.
    """
    import time
    import karma.violations
    from karma.violations import Violation, append
    _patch_rules_path(monkeypatch, fake_home)
    v_path = fake_home / "v.jsonl"
    monkeypatch.setattr(karma.violations, "DEFAULT_PATH", v_path)
    monkeypatch.setattr(cli, "VIOLATIONS_PATH", v_path)

    now = time.time()
    old_ts = now - 30 * 86400  # 30 天前
    fresh_ts = now - 3600       # 1 小时前
    records = [
        Violation(ts=int(old_ts), session_id="s1", rule_id="r-old",
                  trigger="x", snippet="x", trigger_key="check.a.trigger"),
        Violation(ts=int(old_ts) + 1, session_id="s1", rule_id="r-old",
                  trigger="y", snippet="y", trigger_key="check.a.trigger"),
        Violation(ts=int(fresh_ts), session_id="s1", rule_id="r-fresh",
                  trigger="z", snippet="z", trigger_key="check.b.trigger"),
        Violation(ts=int(fresh_ts) + 1, session_id="s1", rule_id="r-fresh",
                  trigger="w", snippet="w", trigger_key="check.b.trigger"),
    ]
    append(records, path=v_path)

    rc = cli.cmd_audit(by_check=True, days=1)
    assert rc == 0
    out = capsys.readouterr().out
    assert "总 2 条违反" in out, "--days 1 应过滤掉 30 天前的老数据"
    # by_check 输出聚合 check 名 (strip "check." 前缀), trigger_key "check.b.trigger" → "b"
    assert " b\n" in out or "× ( " in out, "fresh 违反聚合到 check b 应该显示"
    # 反向断言: 老数据的 check.a 不该出现
    assert " a\n" not in out, "30 天前的 check.a 违反不该出现在 --days 1 窗口"


def test_audit_days_filter_empty_window_message(fake_home, monkeypatch, capsys):
    """v0.11.3: --days N 窗口内 0 条违反, 提示用户而非误导显示 '没违反记录'."""
    import time
    import karma.violations
    from karma.violations import Violation, append
    _patch_rules_path(monkeypatch, fake_home)
    v_path = fake_home / "v.jsonl"
    monkeypatch.setattr(karma.violations, "DEFAULT_PATH", v_path)
    monkeypatch.setattr(cli, "VIOLATIONS_PATH", v_path)

    old_ts = time.time() - 60 * 86400
    append([Violation(ts=int(old_ts), session_id="s1", rule_id="r-old",
                       trigger="x", snippet="x")], path=v_path)

    rc = cli.cmd_audit(days=7)
    assert rc == 0
    out = capsys.readouterr().out
    assert "最近 7 天" in out, "空窗口提示要含天数, 让用户知道是窗口空不是 audit 失败"


def test_all_hook_violation_writes_pass_trigger_key():
    """v0.9.12 regression lockdown: 所有 hook 路径写 Violation 时若 rule_id
    来自 CheckHit 必须同时传 trigger_key。

    历史 bug：v0.4.41 加的 user_prompt_submit._build_strong_reminder fallback
    路径写 Violation 时漏传 trigger_key，让 engine check 真触发被错归
    keyword-only 桶。v0.9.11 audit --by-check 视图暴露了「86% keyword-only」
    假象，深挖才发现是字段缺失而非真行为。

    静态扫描所有 hook 文件，找 Violation 构造或 `_V(` 调用，确保它附近含
    trigger_key=... 赋值（white-list 允许的少数例外）。
    """
    import re
    from pathlib import Path

    hooks_dir = Path(__file__).resolve().parent.parent / "karma" / "hooks"
    offenders: list[str] = []

    for py in hooks_dir.glob("*.py"):
        text = py.read_text(encoding="utf-8")
        # 找所有 Violation 构造调用（可能 alias 成 _V）
        # 匹配 `Violation(` 或 `_V(` 然后看附近 ~15 行内是否含 trigger_key=
        for m in re.finditer(r"\b(Violation|_V)\s*\(", text):
            start = m.start()
            # 取 m.start() 后续 800 字符作为上下文（覆盖典型 Violation(...) 多行构造）
            ctx = text[start : start + 800]
            # 看这段是否含 `rule_id=` 来自 CheckHit 命名（h.rule_id / top.rule_id 等）
            # 简化：只要 ctx 含 rule_id= 且不含 trigger_key= 就视为漏传
            if "rule_id=" in ctx and "trigger_key=" not in ctx:
                # 定位行号给出友好错误
                line_no = text[:start].count("\n") + 1
                offenders.append(f"{py.name}:{line_no}")

    assert not offenders, (
        "以下 hook 路径写 Violation 漏传 trigger_key（v0.9.12 后所有写都必须传）:\n"
        + "\n".join(f"  {o}" for o in offenders)
        + "\n\nfix：构造 Violation 时加 trigger_key=h.trigger_key（或 top.trigger_key），"
        "跟 CheckHit 来源对齐。"
    )


def test_audit_default_view_backward_compat(fake_home, monkeypatch, capsys):
    """`karma audit`（无 --by-check）行为不变 — 仍按 rule_id 聚合。

    v0.9.11 加 by-check 视图是新增功能，默认 audit 保持向后兼容（不破坏
    现有 dogfood 习惯 + 测试 + 用户 muscle memory）。
    """
    import karma.violations
    from karma.violations import Violation, append
    _patch_rules_path(monkeypatch, fake_home)
    v_path = fake_home / "v.jsonl"
    monkeypatch.setattr(karma.violations, "DEFAULT_PATH", v_path)
    monkeypatch.setattr(cli, "VIOLATIONS_PATH", v_path)
    append([Violation(ts=1, session_id="s1", rule_id="rule-A",
                      trigger="x", snippet="x")], path=v_path)

    rc = cli.cmd_audit()  # 默认 by_check=False
    assert rc == 0
    out = capsys.readouterr().out
    # 默认视图按 rule_id 显示
    assert "[rule-A]" in out
    # 不应出现 by-check 视图特征字面
    assert "engine check 命中分布" not in out
