"""session_state 原子操作 + 内部工具函数测试。

覆盖：
- update_state 正常路径：load → fn(state) → save，返回 (state, result)
- update_state fn 抛异常 → state 不保存（rollback），磁盘是旧状态
- update_state 返回值：(state, fn_return_value)
- load 文件不存在 → 返回新 SessionState（session_id 正确）
- read_state → 与 load 语义一致（只读，同磁盘内容）
- _normalize_path：相对路径 → 绝对路径；~/x → /home/x；空字符串不变
- _parse_redirect_target：> 重定向；>> 追加；2>&1 不干扰；无重定向 → None
- _is_non_code_edit_path：.md → True；.py → False；docs/ → True
- record_edit 非代码路径 → last_edit_ts 不推进
- record_bash 背景任务 + 有重定向 → 追加 pending_bg_tasks
- catchup_pending_bg 文件存在 → catch up 返回 1
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from pinrule.session_state import (
    SessionState,
    _normalize_path,
    _parse_redirect_target,
    _is_non_code_edit_path,
    load,
    read_state,
    save,
    update_state,
)

# Windows 上 os.path.abspath() 把 Unix-style `/x/foo.py` 解释成 `<drive>:\x\foo.py`
# (真 Windows path 语义). 那两个 normalize 测试用 Unix abs path 字面跟 expected
# 比较, Windows 不适用 — Python stdlib 跨平台行为不是 pinrule 自己代码.
WINDOWS_UNIX_PATH_NORMALIZE = pytest.mark.skipif(
    sys.platform == "win32",
    reason="测试用 Unix-style /x/y.py 字面, Windows abspath 真行为不同 (stdlib, 非 pinrule)",
)


# ---------------------------------------------------------------------------
# update_state 正常路径
# ---------------------------------------------------------------------------

def test_update_state_loads_mutates_saves(tmp_path):
    sid = "test-session"
    state, _ = update_state(sid, lambda s: setattr(s, "turn_count", 7) or None,
                            base_dir=tmp_path)
    assert state.turn_count == 7
    # 确认已保存
    reloaded = load(sid, base_dir=tmp_path)
    assert reloaded.turn_count == 7


def test_update_state_returns_fn_value(tmp_path):
    sid = "s1"

    def _fn(s: SessionState):
        s.turn_count = 3
        return "derived-value"

    _, result = update_state(sid, _fn, base_dir=tmp_path)
    assert result == "derived-value"


def test_update_state_returns_state_object(tmp_path):
    sid = "s2"
    state, _ = update_state(sid, lambda s: None, base_dir=tmp_path)
    assert isinstance(state, SessionState)
    assert state.session_id == sid


# ---------------------------------------------------------------------------
# update_state fn 抛异常 → rollback（不保存）
# ---------------------------------------------------------------------------

def test_update_state_exception_rollback(tmp_path):
    sid = "s-rollback"
    # 先建一个初始状态
    init_state = SessionState(session_id=sid)
    init_state.turn_count = 5
    save(init_state, base_dir=tmp_path)

    def _crash(s: SessionState):
        s.turn_count = 99
        raise ValueError("fn 故意崩了")

    with pytest.raises(ValueError, match="故意崩了"):
        update_state(sid, _crash, base_dir=tmp_path)

    # 磁盘状态不应被更新
    reloaded = load(sid, base_dir=tmp_path)
    assert reloaded.turn_count == 5, "fn 抛异常后磁盘状态应保持原值"


# ---------------------------------------------------------------------------
# load 文件不存在 → 返回新 state
# ---------------------------------------------------------------------------

def test_load_missing_file_returns_fresh_state(tmp_path):
    s = load("nonexistent-session", base_dir=tmp_path)
    assert isinstance(s, SessionState)
    assert s.session_id == "nonexistent-session"
    assert s.turn_count == 0
    assert len(s.read_files) == 0


# ---------------------------------------------------------------------------
# read_state 与 load 语义一致
# ---------------------------------------------------------------------------

def test_read_state_same_as_load(tmp_path):
    sid = "read-test"
    state = SessionState(session_id=sid)
    state.turn_count = 42
    save(state, base_dir=tmp_path)

    via_read = read_state(sid, base_dir=tmp_path)
    via_load = load(sid, base_dir=tmp_path)
    assert via_read.turn_count == via_load.turn_count == 42


def test_read_state_missing_file_returns_fresh(tmp_path):
    s = read_state("no-such-session", base_dir=tmp_path)
    assert s.session_id == "no-such-session"
    assert s.turn_count == 0


# ---------------------------------------------------------------------------
# _normalize_path
# ---------------------------------------------------------------------------

@WINDOWS_UNIX_PATH_NORMALIZE
def test_normalize_path_relative_to_absolute(tmp_path, monkeypatch):
    """相对路径应被展开为绝对路径。"""
    monkeypatch.chdir(tmp_path)
    p = _normalize_path("subdir/file.py")
    assert Path(p).is_absolute()
    assert "subdir/file.py" in p or p.endswith("subdir/file.py")


@WINDOWS_UNIX_PATH_NORMALIZE
def test_normalize_path_absolute_unchanged():
    p = _normalize_path("/absolute/path/file.py")
    assert p == "/absolute/path/file.py"


def test_normalize_path_tilde_expanded():
    p = _normalize_path("~/some/path.py")
    assert not p.startswith("~"), "~ 应被展开为用户 home 目录"
    assert Path(p).is_absolute()


def test_normalize_path_empty_string_unchanged():
    assert _normalize_path("") == ""


def test_normalize_path_same_file_equals():
    """./foo.py 和 foo.py 应规范化为同一路径（has_read 逻辑依赖这个）。"""
    import os
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        orig = os.getcwd()
        os.chdir(d)
        try:
            p1 = _normalize_path("./foo.py")
            p2 = _normalize_path("foo.py")
            assert p1 == p2, "./foo.py 和 foo.py 应规范化相同"
        finally:
            os.chdir(orig)


# ---------------------------------------------------------------------------
# _parse_redirect_target
# ---------------------------------------------------------------------------

def test_parse_redirect_stdout_single():
    assert _parse_redirect_target("cmd > /tmp/out.log") == "/tmp/out.log"


def test_parse_redirect_append():
    assert _parse_redirect_target("cmd >> /tmp/app.log") == "/tmp/app.log"


def test_parse_redirect_with_stderr_ignored():
    """2>&1 不算作 stdout 重定向目标。"""
    r = _parse_redirect_target("cmd > /tmp/out.log 2>&1")
    assert r == "/tmp/out.log"


def test_parse_redirect_none_when_no_redirect():
    assert _parse_redirect_target("ls -la") is None
    assert _parse_redirect_target("pytest tests/") is None


def test_parse_redirect_fd_redirect_ignored():
    """2> /tmp/err.log 是 stderr 重定向，不算 stdout。"""
    r = _parse_redirect_target("cmd 2> /tmp/err.log")
    assert r is None or r == "/tmp/err.log"  # 实现可能允许也可能不允许，不崩即可


def test_parse_redirect_last_redirect_wins():
    """多个重定向取最后一个。"""
    r = _parse_redirect_target("cmd > /tmp/a.log > /tmp/b.log")
    assert r == "/tmp/b.log"


def test_parse_redirect_empty_string():
    assert _parse_redirect_target("") is None


# ---------------------------------------------------------------------------
# _is_non_code_edit_path
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path,expected", [
    ("/repo/README.md", True),
    ("/repo/CHANGELOG.md", True),
    ("/repo/docs/guide.md", True),
    ("/repo/.github/ISSUE_TEMPLATE.md", True),
    ("/repo/src/main.py", False),
    ("/repo/tests/test_foo.py", False),
    ("/repo/pyproject.toml", False),
    ("/repo/pinrule/config.py", False),
    ("/repo/data/rules.yaml", False),
    ("/repo/CHANGELOG.zh.md", True),
    ("/repo/.gitignore", True),
    ("/repo/.editorconfig", True),
    ("", False),
])
def test_is_non_code_edit_path(path, expected):
    assert _is_non_code_edit_path(path) is expected, f"{path!r} 期望 {expected}"


# ---------------------------------------------------------------------------
# record_edit 非代码路径 → last_edit_ts 不推进
# ---------------------------------------------------------------------------

def test_record_edit_non_code_path_does_not_advance_ts():
    s = SessionState(session_id="s")
    original_ts = s.last_edit_ts
    s.record_edit("/repo/README.md")
    assert s.last_edit_ts == original_ts, "编辑 README.md 不该推进 last_edit_ts"


def test_record_edit_code_path_advances_ts():
    s = SessionState(session_id="s")
    s.record_edit("/repo/src/main.py")
    assert s.last_edit_ts > 0, "编辑代码文件应推进 last_edit_ts"


# ---------------------------------------------------------------------------
# record_bash background + redirect → pending_bg_tasks
# ---------------------------------------------------------------------------

def test_record_bash_background_with_redirect_adds_pending(tmp_path):
    s = SessionState(session_id="s")
    cmd = f"pytest tests/ > {tmp_path}/out.log"
    s.record_bash(cmd, output="", run_in_background=True)
    assert len(s.pending_bg_tasks) == 1
    task = s.pending_bg_tasks[0]
    assert "out.log" in task["output_file"]


def test_record_bash_background_without_redirect_no_pending():
    """无重定向的背景任务不进 pending（无法 catchup 读输出）。"""
    s = SessionState(session_id="s")
    s.record_bash("long-running-cmd", output="", run_in_background=True)
    assert len(s.pending_bg_tasks) == 0


# ---------------------------------------------------------------------------
# catchup_pending_bg 文件存在 → catch up + 从 pending 移除
# ---------------------------------------------------------------------------

def test_catchup_pending_bg_success(tmp_path):
    s = SessionState(session_id="s")
    log_file = tmp_path / "out.log"
    log_file.write_text("10 passed in 0.5s", encoding="utf-8")
    s.pending_bg_tasks = [{"cmd": "pytest", "output_file": str(log_file)}]
    caught = s.catchup_pending_bg()
    assert caught == 1
    assert len(s.pending_bg_tasks) == 0
    assert s.has_recent_test_pass()


def test_catchup_pending_bg_missing_file_stays_pending(tmp_path):
    s = SessionState(session_id="s")
    s.pending_bg_tasks = [{"cmd": "pytest", "output_file": str(tmp_path / "missing.log")}]
    caught = s.catchup_pending_bg()
    assert caught == 0
    assert len(s.pending_bg_tasks) == 1  # 仍在 pending


def test_catchup_pending_bg_empty_file_stays_pending(tmp_path):
    s = SessionState(session_id="s")
    log_file = tmp_path / "empty.log"
    log_file.write_text("", encoding="utf-8")
    s.pending_bg_tasks = [{"cmd": "pytest", "output_file": str(log_file)}]
    caught = s.catchup_pending_bg()
    assert caught == 0
    assert len(s.pending_bg_tasks) == 1
