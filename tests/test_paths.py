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
