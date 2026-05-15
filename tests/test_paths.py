"""karma_home() + KARMA_HOME env 隔离守护测试。

用 subprocess 跑新 Python 进程让 KARMA_HOME env 在 import karma 之前生效
（module-level 常量 import 时 freeze，inprocess monkeypatch 改 env 后 reimport 才生效）。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _spawn_karma_check(env_override: dict[str, str], code: str) -> str:
    """Spawn 子进程读 karma 路径，返回 stdout。"""
    env = os.environ.copy()
    env.update(env_override)
    # 让子进程能 import karma — 用 sys.executable + sys.path
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1]) + os.pathsep + env.get("PYTHONPATH", "")
    result = subprocess.run(
        [sys.executable, "-c", code],
        env=env, capture_output=True, text=True, timeout=10, check=True,
    )
    return result.stdout.strip()


def test_karma_home_default_when_env_not_set():
    """没 KARMA_HOME env → 默认 ~/.claude/karma/。"""
    out = _spawn_karma_check(
        {"KARMA_HOME": ""},  # 显式清空，子进程读不到
        "from karma.paths import karma_home; print(karma_home())",
    )
    assert out.endswith(".claude/karma"), f"默认应该是 ~/.claude/karma/，实际: {out!r}"


def test_karma_home_override_via_env():
    """`KARMA_HOME=/tmp/x` 生效，覆盖默认路径。"""
    out = _spawn_karma_check(
        {"KARMA_HOME": "/tmp/karma-test-isolated"},
        "from karma.paths import karma_home; print(karma_home())",
    )
    assert out == "/tmp/karma-test-isolated"


def test_karma_home_propagates_to_all_modules():
    """所有 5 个模块（sticky/violations/session_state/config/cli）都用 KARMA_HOME。"""
    out = _spawn_karma_check(
        {"KARMA_HOME": "/tmp/karma-multi-mod"},
        """
from karma.rule import DEFAULT_PATH as STICKY
from karma.violations import DEFAULT_PATH as VIOL
from karma.session_state import DEFAULT_DIR as SS
from karma.config import DEFAULT_PATH as CFG
from karma.cli import KARMA_DIR
print(STICKY)
print(VIOL)
print(SS)
print(CFG)
print(KARMA_DIR)
""",
    )
    lines = out.splitlines()
    # v0.5.0 起 sticky.yaml → rules.yaml（向后兼容 fallback 还在）
    assert lines[0] == "/tmp/karma-multi-mod/rules.yaml"
    assert lines[1] == "/tmp/karma-multi-mod/violations.jsonl"
    assert lines[2] == "/tmp/karma-multi-mod/session-state"
    assert lines[3] == "/tmp/karma-multi-mod/config.yaml"
    assert lines[4] == "/tmp/karma-multi-mod"


def test_karma_home_expanduser_tilde():
    """`KARMA_HOME=~/karma-x` 自动展开 home。"""
    out = _spawn_karma_check(
        {"KARMA_HOME": "~/karma-tilde-test"},
        "from karma.paths import karma_home; print(karma_home())",
    )
    expected = str(Path.home() / "karma-tilde-test")
    assert out == expected
