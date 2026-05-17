"""pinrule_home() + PINRULE_HOME env 隔离守护测试。

用 subprocess 跑新 Python 进程让 PINRULE_HOME env 在 import pinrule 之前生效
（module-level 常量 import 时 freeze，inprocess monkeypatch 改 env 后 reimport 才生效）。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _spawn_pinrule_check(env_override: dict[str, str], code: str) -> str:
    """Spawn 子进程读 pinrule 路径，返回 stdout。"""
    env = os.environ.copy()
    env.update(env_override)
    # 让子进程能 import pinrule — 用 sys.executable + sys.path
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1]) + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=env, capture_output=True, text=True, timeout=10, check=True,
    )
    return result.stdout.strip()


def test_pinrule_home_default_when_env_not_set():
    """没 PINRULE_HOME env → 默认 ~/.pinrule/（v0.14.0 共享目录）。"""
    out = _spawn_pinrule_check(
        {},
        "import os; os.environ.pop('PINRULE_HOME', None); "
        "from pinrule.paths import pinrule_home; print(pinrule_home())",
    )
    assert out.endswith(".pinrule"), f"默认应该是 ~/.pinrule/，实际: {out!r}"


def test_pinrule_home_override_via_env():
    """`PINRULE_HOME=/tmp/x` 生效，覆盖默认路径。"""
    out = _spawn_pinrule_check(
        {"PINRULE_HOME": "/tmp/pinrule-test-isolated"},
        "from pinrule.paths import pinrule_home; print(pinrule_home())",
    )
    assert out == "/tmp/pinrule-test-isolated"


def test_pinrule_home_propagates_to_all_modules():
    """所有 5 个模块（sticky/violations/session_state/config/cli）都用 PINRULE_HOME。"""
    out = _spawn_pinrule_check(
        {"PINRULE_HOME": "/tmp/pinrule-multi-mod"},
        """
from pinrule.rule import DEFAULT_PATH as STICKY
from pinrule.violations import DEFAULT_PATH as VIOL
from pinrule.session_state import DEFAULT_DIR as SS
from pinrule.config import DEFAULT_PATH as CFG
from pinrule.cli import PINRULE_DIR
print(STICKY)
print(VIOL)
print(SS)
print(CFG)
print(PINRULE_DIR)
""",
    )
    lines = out.splitlines()
    # v0.5.0 起 sticky.yaml → rules.yaml（向后兼容 fallback 还在）
    assert lines[0] == "/tmp/pinrule-multi-mod/rules.yaml"
    assert lines[1] == "/tmp/pinrule-multi-mod/violations.jsonl"
    assert lines[2] == "/tmp/pinrule-multi-mod/session-state"
    assert lines[3] == "/tmp/pinrule-multi-mod/config.yaml"
    assert lines[4] == "/tmp/pinrule-multi-mod"


def test_pinrule_home_expanduser_tilde():
    """`PINRULE_HOME=~/pinrule-x` 自动展开 home。"""
    out = _spawn_pinrule_check(
        {"PINRULE_HOME": "~/pinrule-tilde-test"},
        "from pinrule.paths import pinrule_home; print(pinrule_home())",
    )
    expected = str(Path.home() / "pinrule-tilde-test")
    assert out == expected


# ---- v0.16.11 真 sandbox: pinrule_install_root() 覆盖 hook wrapper / settings / skill ----
#
# 朋友外部 review 标的雷点: README/ARCHITECTURE 写 "全部装到 /tmp — 真实
# ~/.claude / ~/.cursor / ~/.codex 一个字节不改", 这是硬承诺. 之前测试只覆盖
# pinrule_home() (数据目录), pinrule_install_root() 全无测试. 一旦 backend
# 某个 path 漏走 install_root 直接接 Path.home(), README 就成虚假宣传.
# 这一组测把承诺锁死: 所有 backend 关键路径都必须 anchor 在 PINRULE_HOME 下.


def test_pinrule_install_root_default_when_env_not_set():
    """没 PINRULE_HOME → install_root = ~/ (生产默认行为)."""
    out = _spawn_pinrule_check(
        {},
        "import os; os.environ.pop('PINRULE_HOME', None); "
        "from pinrule.paths import pinrule_install_root; print(pinrule_install_root())",
    )
    assert out == str(Path.home())


def test_pinrule_install_root_override_via_env():
    """`PINRULE_HOME=/tmp/x` → install_root = /tmp/x."""
    out = _spawn_pinrule_check(
        {"PINRULE_HOME": "/tmp/pinrule-install-root-test"},
        "from pinrule.paths import pinrule_install_root; print(pinrule_install_root())",
    )
    assert out == "/tmp/pinrule-install-root-test"


def test_claude_backend_paths_honor_sandbox():
    """Claude backend hook wrapper / settings / backup 全 anchor 在 PINRULE_HOME 下."""
    out = _spawn_pinrule_check(
        {"PINRULE_HOME": "/tmp/pinrule-claude-sandbox"},
        """
from pinrule.backends.claude_code import ClaudeCodeBackend
b = ClaudeCodeBackend()
print(b.hooks_dir())
print(b.settings_path())
print(b.settings_backup_path())
""",
    )
    lines = out.splitlines()
    assert lines[0] == "/tmp/pinrule-claude-sandbox/.claude/hooks"
    assert lines[1] == "/tmp/pinrule-claude-sandbox/.claude/settings.json"
    assert lines[2] == "/tmp/pinrule-claude-sandbox/.claude/settings.json.before-pinrule"


def test_codex_backend_paths_honor_sandbox():
    """Codex backend hooks dir / settings 全 anchor 在 PINRULE_HOME 下."""
    out = _spawn_pinrule_check(
        {"PINRULE_HOME": "/tmp/pinrule-codex-sandbox"},
        """
from pinrule.backends.codex import CodexBackend
b = CodexBackend()
print(b.hooks_dir())
print(b.settings_path())
""",
    )
    lines = out.splitlines()
    assert lines[0] == "/tmp/pinrule-codex-sandbox/.codex/hooks"
    assert lines[1] == "/tmp/pinrule-codex-sandbox/.codex/hooks.json"


def test_cursor_backend_paths_honor_sandbox():
    """Cursor backend hooks dir / settings / rules dir 全 anchor 在 PINRULE_HOME 下."""
    out = _spawn_pinrule_check(
        {"PINRULE_HOME": "/tmp/pinrule-cursor-sandbox"},
        """
from pinrule.backends.cursor import CursorBackend
from pinrule.cursor_rules_sync import cursor_rules_dir
b = CursorBackend()
print(b.hooks_dir())
print(b.settings_path())
print(cursor_rules_dir())
""",
    )
    lines = out.splitlines()
    assert lines[0] == "/tmp/pinrule-cursor-sandbox/.cursor/hooks"
    assert lines[1] == "/tmp/pinrule-cursor-sandbox/.cursor/hooks.json"
    # cursor_rules_dir() 调 .resolve() 在 macOS 上把 /tmp 展成 /private/tmp
    assert lines[2] == str(Path("/tmp/pinrule-cursor-sandbox/.cursor/rules").resolve())


def test_real_home_untouched_when_sandbox_active():
    """硬承诺验证: 设了 PINRULE_HOME 之后, 没一个 backend 路径还指向真 ~/."""
    real_home = str(Path.home())
    out = _spawn_pinrule_check(
        {"PINRULE_HOME": "/tmp/pinrule-home-untouched-test"},
        """
from pinrule.backends.claude_code import ClaudeCodeBackend
from pinrule.backends.codex import CodexBackend
from pinrule.backends.cursor import CursorBackend
from pinrule.cursor_rules_sync import cursor_rules_dir
paths = []
for b in (ClaudeCodeBackend(), CodexBackend(), CursorBackend()):
    paths.append(str(b.hooks_dir()))
    paths.append(str(b.settings_path()))
    paths.append(str(b.settings_backup_path()))
paths.append(str(cursor_rules_dir()))
for p in paths:
    print(p)
""",
    )
    for line in out.splitlines():
        assert not line.startswith(real_home + "/"), (
            f"PINRULE_HOME sandbox 承诺破: {line} 仍 anchor 在真 home {real_home}"
        )
