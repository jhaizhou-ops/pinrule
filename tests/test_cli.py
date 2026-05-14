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
    assert len(cc_wrappers) == 4
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


def test_install_hooks_unknown_backend_errors(fake_home, capsys):
    """未知 backend 名报错不 silent fail。"""
    rc = cli.cmd_install_hooks(backend_name="not-real-backend")
    assert rc == 1
    captured = capsys.readouterr()
    assert "未知 backend" in captured.err or "not-real-backend" in captured.err


def test_init_explicit_no_minimal_installs_7_sticky(fake_home, capsys):
    """karma init --no-minimal 强制装 7 条 dev.example（覆盖自动检测）。"""
    import karma.sticky
    monkeypatch_path = fake_home / ".claude" / "karma" / "sticky.yaml"
    import unittest.mock
    with unittest.mock.patch.object(cli, "STICKY_PATH", monkeypatch_path):
        with unittest.mock.patch.object(karma.sticky, "DEFAULT_PATH", monkeypatch_path):
            rc = cli.cmd_init(minimal=False)
    assert rc == 0
    assert monkeypatch_path.exists()
    sticky_list = karma.sticky.load(monkeypatch_path)
    assert len(sticky_list) == 7


def test_init_explicit_minimal_installs_5_sticky(fake_home, capsys):
    """karma init --minimal 强制装 5 条精简（覆盖自动检测）。"""
    import karma.sticky
    monkeypatch_path = fake_home / ".claude" / "karma" / "sticky.yaml"
    import unittest.mock
    with unittest.mock.patch.object(cli, "STICKY_PATH", monkeypatch_path):
        with unittest.mock.patch.object(karma.sticky, "DEFAULT_PATH", monkeypatch_path):
            rc = cli.cmd_init(minimal=True)
    assert rc == 0
    sticky_list = karma.sticky.load(monkeypatch_path)
    assert len(sticky_list) == 5
    ids = {s.id for s in sticky_list}
    assert "chinese-plain-no-jargon" not in ids
    assert "no-testset-no-future-leakage" not in ids


def test_init_auto_chinese_user_installs_7_sticky(fake_home, capsys):
    """minimal=None + 系统语言中文 → 自动装 7 条含 chinese_plain。"""
    import karma.sticky
    import karma.locale_detect
    monkeypatch_path = fake_home / ".claude" / "karma" / "sticky.yaml"
    import unittest.mock
    with unittest.mock.patch.object(cli, "STICKY_PATH", monkeypatch_path):
        with unittest.mock.patch.object(karma.sticky, "DEFAULT_PATH", monkeypatch_path):
            with unittest.mock.patch.object(karma.locale_detect, "detect_user_language",
                                            return_value="zh"):
                rc = cli.cmd_init(minimal=None)
    assert rc == 0
    sticky_list = karma.sticky.load(monkeypatch_path)
    assert len(sticky_list) == 7
    out = capsys.readouterr().out
    assert "zh" in out and "完整" in out  # 反馈给用户自动选了啥


def test_init_auto_non_chinese_user_installs_5_sticky(fake_home, capsys):
    """minimal=None + 系统语言非中文 → 自动装 5 条精简（砍 chinese_plain）。"""
    import karma.sticky
    import karma.locale_detect
    monkeypatch_path = fake_home / ".claude" / "karma" / "sticky.yaml"
    import unittest.mock
    with unittest.mock.patch.object(cli, "STICKY_PATH", monkeypatch_path):
        with unittest.mock.patch.object(karma.sticky, "DEFAULT_PATH", monkeypatch_path):
            with unittest.mock.patch.object(karma.locale_detect, "detect_user_language",
                                            return_value="en"):
                rc = cli.cmd_init(minimal=None)
    assert rc == 0
    sticky_list = karma.sticky.load(monkeypatch_path)
    assert len(sticky_list) == 5
    out = capsys.readouterr().out
    assert "en" in out and "精简" in out


def test_init_auto_unknown_locale_fallback_to_minimal(fake_home, capsys):
    """minimal=None + 检测不到（容器 / CI / 异常）→ fallback 5 条精简（最安全）。"""
    import karma.sticky
    import karma.locale_detect
    monkeypatch_path = fake_home / ".claude" / "karma" / "sticky.yaml"
    import unittest.mock
    with unittest.mock.patch.object(cli, "STICKY_PATH", monkeypatch_path):
        with unittest.mock.patch.object(karma.sticky, "DEFAULT_PATH", monkeypatch_path):
            with unittest.mock.patch.object(karma.locale_detect, "detect_user_language",
                                            return_value=None):
                rc = cli.cmd_init(minimal=None)
    assert rc == 0
    sticky_list = karma.sticky.load(monkeypatch_path)
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
                    cli.cmd_doctor()
    out = capsys.readouterr().out
    assert "✗" in out or "缺失" in out or "未安装" in out, f"doctor 应明确报告 hook 缺失: {out}"


def test_doctor_reports_fully_installed(fake_home, capsys, monkeypatch):
    """install Claude Code 后 doctor 应报告 Claude Code 全部 ✓（mock Codex 没装）。"""
    sticky_path = fake_home / ".claude" / "karma" / "sticky.yaml"
    sticky_path.parent.mkdir(parents=True, exist_ok=True)
    sticky_path.write_text("- id: test\n  preference: x\n")
    import karma.sticky
    import karma.violations
    from karma.backends import CodexBackend, GeminiCLIBackend
    import unittest.mock
    # mock 其他 backend 没装（fake_home 是 tmp，本测试只关心 Claude Code 路径）
    monkeypatch.setattr(CodexBackend, "client_installed", lambda self: False)
    monkeypatch.setattr(GeminiCLIBackend, "client_installed", lambda self: False)
    cli.cmd_install_hooks(backend_name="claude-code")
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
