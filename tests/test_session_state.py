"""session_state IO + 状态跟踪测试。"""

from __future__ import annotations

from pathlib import Path

from pinrule.session_state import SessionState, get_current_session_id, load, save

from tests.conftest import np


def test_round_trip(tmp_path):
    s = SessionState(session_id="abc")
    s.record_read("/tmp/a.py")
    s.record_read("/tmp/b.py")
    s.record_edit("/tmp/a.py")
    s.record_bash("pytest tests/", "==== 10 passed in 0.1s ====")
    s.record_bash("ls", "a.txt b.txt")
    save(s, base_dir=tmp_path)

    loaded = load("abc", base_dir=tmp_path)
    assert loaded.read_files == {np("/tmp/a.py"), np("/tmp/b.py")}
    assert loaded.edit_files == [np("/tmp/a.py")]
    assert len(loaded.recent_bash) == 2
    assert loaded.recent_bash[0].is_test_cmd
    assert loaded.recent_bash[0].output_passed
    assert not loaded.recent_bash[1].is_test_cmd


def test_has_read(tmp_path):
    s = SessionState(session_id="s")
    s.record_read("/tmp/x.py")
    assert s.has_read("/tmp/x.py")
    assert not s.has_read("/tmp/y.py")


def test_has_recent_test_pass(tmp_path):
    s = SessionState(session_id="s")
    s.record_bash("ls", "a")
    s.record_bash("pytest", "10 passed")
    assert s.has_recent_test_pass()


def test_has_recent_test_pass_failed_not_counted(tmp_path):
    s = SessionState(session_id="s")
    s.record_bash("pytest", "1 failed, 2 passed")
    assert not s.has_recent_test_pass()


def test_has_recent_test_pass_no_test(tmp_path):
    s = SessionState(session_id="s")
    s.record_bash("ls -la", "files...")
    assert not s.has_recent_test_pass()


def test_has_recent_test_pass_survives_many_non_test_bashes(tmp_path):
    """测试通过后跑 N 次普通 Bash 仍算通过 — 不受计数窗口限制。"""
    s = SessionState(session_id="s")
    s.record_bash("pytest", "10 passed in 0.1s")
    for i in range(20):
        s.record_bash(f"ls dir{i}", "files")
    assert s.has_recent_test_pass()


def test_has_recent_test_pass_invalidated_after_edit(tmp_path):
    """测试通过后改了代码 → 通过证据失效（代码变了没重测）。"""
    s = SessionState(session_id="s")
    s.record_bash("pytest", "10 passed")
    assert s.has_recent_test_pass()
    s.record_edit("/tmp/x.py")
    assert not s.has_recent_test_pass(), "Edit 后应该失效"


def test_has_recent_test_pass_after_edit_then_retest(tmp_path):
    """改代码后重新测试通过 → 又算通过。"""
    s = SessionState(session_id="s")
    s.record_bash("pytest", "10 passed")
    s.record_edit("/tmp/x.py")
    assert not s.has_recent_test_pass()
    s.record_bash("pytest", "10 passed")
    assert s.has_recent_test_pass()


def test_zero_errors_in_output_not_failed(tmp_path):
    """pytest 输出 '0 errors' 不应误认为 failed。"""
    s = SessionState(session_id="s")
    s.record_bash("pytest", "75 passed in 0.05s, 0 errors, 0 warnings")
    assert s.has_recent_test_pass(), "0 errors 不算 fail"


def test_traceback_is_failed(tmp_path):
    """Python traceback 应被认成 failed。"""
    s = SessionState(session_id="s")
    s.record_bash("pytest", "Traceback (most recent call last):\n  File ...")
    assert not s.has_recent_test_pass()


def test_pytest_failed_line_is_failed(tmp_path):
    """pytest 单测失败行 'FAILED tests/...' 应被认成 failed。"""
    s = SessionState(session_id="s")
    s.record_bash("pytest", "FAILED tests/test_x.py::test_y - AssertionError")
    assert not s.has_recent_test_pass()


def test_word_error_alone_not_failed(tmp_path):
    """单独 'error' 字眼（如帮助文本 'show errors' / 路径含 error）不算 failed。"""
    s = SessionState(session_id="s")
    s.record_bash("pytest --show-errors", "10 passed in 0.1s")
    assert s.has_recent_test_pass()


# -------- background 任务输出 catch-up --------

def test_record_bg_task_then_catchup(tmp_path):
    """background 任务启动 → pending；任务完成 → catchup 读用户重定向 log。

    Claude Code 实际 tool_response 是 dict {stdout, stderr, backgroundTaskId, ...}。
    catchup 从 command 解析 `> /path` 重定向取输出。
    """
    s = SessionState(session_id="s")
    log_path = tmp_path / "bg.log"
    s.record_bash(
        f"pytest tests/ > {log_path} 2>&1",
        {"stdout": "", "stderr": "", "backgroundTaskId": "abc"},
        run_in_background=True,
    )
    # background 启动 stdout 是空，还没 PASS 信号
    assert not s.has_recent_test_pass()
    # 任务完成，写入 log
    log_path.write_text("===== 99 passed in 0.05s =====")
    # catchup
    n = s.catchup_pending_bg()
    assert n == 1
    assert s.has_recent_test_pass()


def test_catchup_skips_missing_log(tmp_path):
    """log 文件还不存在 / 空 → 保留在 pending，不算通过。"""
    s = SessionState(session_id="s")
    log_path = tmp_path / "never_written.log"
    s.record_bash(
        f"pytest tests/ > {log_path} 2>&1",
        {"stdout": "", "backgroundTaskId": "abc"},
        run_in_background=True,
    )
    n = s.catchup_pending_bg()
    assert n == 0
    assert not s.has_recent_test_pass()


def test_bg_failed_task_catchup_marks_failed(tmp_path):
    """background 任务失败 → catchup 读到 FAILED → 不算通过。"""
    s = SessionState(session_id="s")
    log_path = tmp_path / "bg.log"
    s.record_bash(
        f"pytest tests/ > {log_path} 2>&1",
        {"stdout": "", "backgroundTaskId": "abc"},
        run_in_background=True,
    )
    log_path.write_text("FAILED tests/test_x.py::test_y\n1 failed, 5 passed")
    s.catchup_pending_bg()
    assert not s.has_recent_test_pass()


def test_catchup_idempotent_no_race(tmp_path):
    """task #8.1 fix：catchup 用 log mtime 当 ts，多次跑 ltp 不漂移。

    Race condition：手动 update ltp 到 future 后，catchup 不应把 ltp 拉回。
    """
    import os
    s = SessionState(session_id="s")
    log_path = tmp_path / "bg.log"
    log_path.write_text("===== 99 passed in 0.05s =====")
    s.pending_bg_tasks = [{
        "cmd": "pytest tests/",
        "output_file": str(log_path),
        "started_ts": 0,
    }]
    # 第一次 catchup
    s.catchup_pending_bg()
    log_mtime = os.path.getmtime(log_path)
    assert abs(s.last_test_pass_ts - log_mtime) < 0.01, "第一次 catchup ltp 应 = log mtime"
    # 手动 update ltp 到 future（模拟用户 / hook 之后 update）
    import time
    future_ts = time.time() + 3600
    s.last_test_pass_ts = future_ts
    # 重新加 pending（模拟 race — 同一 log 被 catchup 重复处理）
    s.pending_bg_tasks = [{
        "cmd": "pytest tests/",
        "output_file": str(log_path),
        "started_ts": 0,
    }]
    s.catchup_pending_bg()
    # 第二次 catchup 不该把 ltp 拉回 mtime — force_ts > 当前 ltp 才推
    assert s.last_test_pass_ts == future_ts, \
        f"catchup 不该把 ltp 从 future 拉回 mtime: {s.last_test_pass_ts} vs {future_ts}"


def test_bg_no_redirect_no_pending(tmp_path):
    """background 任务命令没有 > 重定向 → pending 不能定位 output file，跳过 record。

    （catchup 没有可读的输出，evidence check 无法接到通过证据 — 用户应该总是
    重定向 background 任务的 stdout）。
    """
    s = SessionState(session_id="s")
    s.record_bash(
        "pytest tests/",
        {"stdout": "", "backgroundTaskId": "abc"},
        run_in_background=True,
    )
    assert s.pending_bg_tasks == []


def test_bg_dict_with_stdout_passed_synchronous(tmp_path):
    """run_in_background=False 时 tool_response dict 的 stdout 字段被正确读取。"""
    s = SessionState(session_id="s")
    s.record_bash(
        "pytest tests/",
        {"stdout": "===== 99 passed in 0.05s =====", "stderr": ""},
        run_in_background=False,
    )
    assert s.has_recent_test_pass()


def test_parse_redirect_target():
    """从 shell 命令字符串解析 > 重定向路径。"""
    from pinrule.session_state import _parse_redirect_target
    assert _parse_redirect_target("pytest > /tmp/x.log") == "/tmp/x.log"
    assert _parse_redirect_target("pytest > /tmp/x.log 2>&1") == "/tmp/x.log"
    assert _parse_redirect_target("pytest 2>&1 > /tmp/x.log") == "/tmp/x.log"
    assert _parse_redirect_target("pytest >> /tmp/x.log") == "/tmp/x.log"
    assert _parse_redirect_target("pytest tests/") is None
    # 不要被 fd 重定向（2>&1）误捕
    assert _parse_redirect_target("pytest 2>&1") is None


# ---- 缺口 #3 session-state 文件清理 ----

def test_purge_old_session_states(tmp_path):
    """删 mtime 老于 max_age_days 的 session-state json。"""
    import os
    import time
    from pinrule.session_state import purge_old_states
    old1 = tmp_path / "old1.json"
    old2 = tmp_path / "old2.json"
    fresh = tmp_path / "fresh.json"
    for p in (old1, old2, fresh):
        p.write_text("{}")
    # 把 old1/old2 的 mtime 改成 31 天前
    old_ts = time.time() - 31 * 86400
    os.utime(old1, (old_ts, old_ts))
    os.utime(old2, (old_ts, old_ts))
    n = purge_old_states(max_age_days=30, base_dir=tmp_path)
    assert n == 2
    assert not old1.exists()
    assert not old2.exists()
    assert fresh.exists()


def test_purge_no_old_files(tmp_path):
    """没老文件 → 返回 0，不动新文件。"""
    from pinrule.session_state import purge_old_states
    fresh = tmp_path / "fresh.json"
    fresh.write_text("{}")
    n = purge_old_states(max_age_days=30, base_dir=tmp_path)
    assert n == 0
    assert fresh.exists()


def test_purge_missing_dir(tmp_path):
    """目录不存在 → 返回 0 不抛错。"""
    from pinrule.session_state import purge_old_states
    n = purge_old_states(max_age_days=30, base_dir=tmp_path / "nonexistent")
    assert n == 0


# ---- 缺口 #5 session_state.save() 并发安全 tmp 名 ----

def test_save_uses_unique_tmp_name(tmp_path, monkeypatch):
    """tmp 文件名应含 pid + nanosecond 避免并发冲突。"""
    from pinrule.session_state import save, SessionState
    s = SessionState(session_id="x")
    captured_tmp_names = []
    real_write = type(tmp_path).write_text

    def spy_write(self, *args, **kwargs):
        if self.suffix == ".tmp":
            captured_tmp_names.append(self.name)
        return real_write(self, *args, **kwargs)
    monkeypatch.setattr(type(tmp_path), "write_text", spy_write)
    save(s, base_dir=tmp_path)
    assert len(captured_tmp_names) == 1
    tmp_name = captured_tmp_names[0]
    # 不该是固定的 'x.json.tmp' — 应含 pid 数字段
    import os
    assert str(os.getpid()) in tmp_name, f"tmp 名 {tmp_name} 应含 pid"


def test_write_implies_read_for_same_file(tmp_path):
    """Write 一个文件后，has_read 应为 True — Agent 写过的内容自己当然知道。

    post_tool_use hook 对 Write/NotebookEdit 既 record_edit 也 record_read，
    避免后续 Edit 同文件被 read_first 多余拦。
    """
    # 这个测试验证 has_read 逻辑 — 实际 record_read 由 post_tool_use 触发
    s = SessionState(session_id="s")
    s.record_edit("/x/new.py")
    s.record_read("/x/new.py")  # 模拟 post_tool_use 对 Write 做的事
    assert s.has_read("/x/new.py")


def test_load_missing_returns_empty(tmp_path):
    loaded = load("never-exists", base_dir=tmp_path)
    assert loaded.read_files == set()
    assert loaded.recent_bash == []


def test_session_id_with_unsafe_chars(tmp_path):
    """session_id 含特殊字符 → 清洗成文件名安全。"""
    s = SessionState(session_id="/var/some/path with spaces")
    s.record_read("/tmp/a")
    save(s, base_dir=tmp_path)
    # 加载用同样 id 应该能拿到
    loaded = load("/var/some/path with spaces", base_dir=tmp_path)
    assert loaded.read_files == {np("/tmp/a")}


def test_get_current_session_id_empty_dir(tmp_path):
    """目录不存在 / 空 → 返回 None。"""
    assert get_current_session_id(base_dir=tmp_path / "nonexistent") is None
    (tmp_path / "empty").mkdir()
    assert get_current_session_id(base_dir=tmp_path / "empty") is None


def test_get_current_session_id_picks_latest_mtime(tmp_path):
    """多个 session 文件 → 选最新 mtime 的 session_id。"""
    import os
    save(SessionState(session_id="old-session"), base_dir=tmp_path)
    save(SessionState(session_id="new-session"), base_dir=tmp_path)
    # 显式给 old 文件设置更早 mtime（避免文件系统精度问题）
    old_path = tmp_path / "old-session.json"
    new_path = tmp_path / "new-session.json"
    os.utime(old_path, (1000, 1000))
    os.utime(new_path, (2000, 2000))
    assert get_current_session_id(base_dir=tmp_path) == "new-session"


def test_get_current_session_id_excludes_subagent(tmp_path):
    """子 Agent state 文件名含 `__<agent_id>` 后缀 → 不算「当前活跃 session」。

    避免子 Agent state 比主 Agent 后写入时混淆。stats / audit / doctor 看的是
    主 Agent session 视角。
    """
    import os
    save(SessionState(session_id="main-session"), base_dir=tmp_path)
    save(
        SessionState(session_id="main-session", agent_id="sub-1"),
        base_dir=tmp_path,
    )
    # 让子 Agent state 更晚写入
    os.utime(tmp_path / "main-session.json", (1000, 1000))
    os.utime(tmp_path / "main-session__sub-1.json", (2000, 2000))
    # 仍然返回主 Agent session
    assert get_current_session_id(base_dir=tmp_path) == "main-session"


# -------- v0.6.1: 非代码 edit 路径豁免 (issue #1 原因 fix) --------

def test_v061_edit_readme_after_test_pass_keeps_fresh():
    """v0.6.1 原因 fix (issue #1 复现):
    docker pytest 通过 → 改 README.md → has_recent_test_pass 仍 True.
    """
    from pinrule.session_state import SessionState
    state = SessionState(session_id="test")
    state.record_bash("docker exec c1 python -m pytest tests/", "1190 passed in 42s")
    assert state.has_recent_test_pass(), "pytest 通过应 True"
    state.record_edit("/repo/README.md")
    assert state.has_recent_test_pass(), "改 README 不该让 has_recent_test_pass 翻 False"


def test_v061_edit_changelog_keeps_fresh():
    from pinrule.session_state import SessionState
    state = SessionState(session_id="test")
    state.record_bash("pytest", "5 passed in 1s")
    state.record_edit("/repo/CHANGELOG.md")
    assert state.has_recent_test_pass()


def test_v061_edit_docs_dir_keeps_fresh():
    from pinrule.session_state import SessionState
    state = SessionState(session_id="test")
    state.record_bash("pytest", "5 passed in 1s")
    state.record_edit("/repo/docs/ARCHITECTURE.md")
    assert state.has_recent_test_pass()


def test_v061_edit_gitignore_keeps_fresh():
    from pinrule.session_state import SessionState
    state = SessionState(session_id="test")
    state.record_bash("pytest", "5 passed in 1s")
    state.record_edit("/repo/.gitignore")
    assert state.has_recent_test_pass()


def test_v061_edit_src_code_still_invalidates():
    """v0.6.1 对偶: 业务代码 edit 仍按设计让 has_recent_test_pass 翻 False.

    不该松开「改完没重测就 commit」的核心拦截语义.
    """
    from pinrule.session_state import SessionState
    state = SessionState(session_id="test")
    state.record_bash("pytest", "5 passed in 1s")
    assert state.has_recent_test_pass()
    state.record_edit("/repo/src/handler.py")
    assert not state.has_recent_test_pass(), "改 src/*.py 仍应让 has_recent_test_pass 翻 False"


def test_v061_edit_tests_dir_still_invalidates():
    """v0.6.1 对偶: 改测试文件本身也算「测试还没重跑」状态."""
    from pinrule.session_state import SessionState
    state = SessionState(session_id="test")
    state.record_bash("pytest", "5 passed in 1s")
    state.record_edit("/repo/tests/test_x.py")
    assert not state.has_recent_test_pass()


# === v0.9.8: update_state / read_state / _state_lock ===
# 跨进程 atomic load → modify → save，修「多 hook 同时跑覆盖彼此更新」race。
# 之前直接 load + modify + save 在多个 Claude Code 进程同 session 并发场景下
# 会丢更新（read_files / edit_files / pending_bg_tasks 任何字段都可能）。

def test_update_state_applies_fn_and_persists(tmp_path):
    """update_state 应用 fn 改 state 并落盘 — 下次 load 看到改动。"""
    from pinrule.session_state import update_state, load

    def _add_read(state):
        state.record_read("/foo.py")

    state, _ = update_state("sess1", _add_read, base_dir=tmp_path)
    assert np("/foo.py") in state.read_files

    # 落盘验证
    reloaded = load("sess1", base_dir=tmp_path)
    assert np("/foo.py") in reloaded.read_files


def test_update_state_returns_fn_value(tmp_path):
    """update_state 返回 (state, fn_return) — fn 可 derive 计算结果。"""
    from pinrule.session_state import update_state

    def _compute(state):
        state.tool_byte_seq += 1000
        return f"computed_{state.tool_byte_seq}"

    state, derived = update_state("sess1", _compute, base_dir=tmp_path)
    assert state.tool_byte_seq == 1000
    assert derived == "computed_1000"


def test_update_state_fn_exception_rolls_back(tmp_path):
    """fn 抛异常 → state 不 save，磁盘保持旧状态（rollback）。"""
    from pinrule.session_state import SessionState, save, update_state, load

    initial = SessionState(session_id="sess1")
    initial.record_read("/initial.py")
    save(initial, base_dir=tmp_path)

    def _bad_fn(state):
        state.record_read("/should_not_persist.py")
        raise RuntimeError("fn fails midway")

    import pytest
    with pytest.raises(RuntimeError):
        update_state("sess1", _bad_fn, base_dir=tmp_path)

    # 磁盘 state 没变（rollback）
    reloaded = load("sess1", base_dir=tmp_path)
    assert np("/initial.py") in reloaded.read_files
    assert np("/should_not_persist.py") not in reloaded.read_files


def test_update_state_agent_id_isolation(tmp_path):
    """子 Agent agent_id 走独立 lock + 独立 state 文件 — 主子互不阻塞."""
    from pinrule.session_state import update_state, load

    def _set_main(state):
        state.tool_byte_seq = 100

    def _set_sub(state):
        state.tool_byte_seq = 200

    update_state("sess1", _set_main, base_dir=tmp_path)
    update_state("sess1", _set_sub, base_dir=tmp_path, agent_id="agent-A")

    main_loaded = load("sess1", base_dir=tmp_path)
    sub_loaded = load("sess1", base_dir=tmp_path, agent_id="agent-A")
    assert main_loaded.tool_byte_seq == 100
    assert sub_loaded.tool_byte_seq == 200


def test_read_state_returns_snapshot(tmp_path):
    """read_state 是只读快照（语义跟 load 一样，名字提示『别在这改 state』）."""
    from pinrule.session_state import SessionState, save, read_state

    s = SessionState(session_id="sess1")
    s.record_read("/x.py")
    save(s, base_dir=tmp_path)

    snap = read_state("sess1", base_dir=tmp_path)
    assert np("/x.py") in snap.read_files


def test_state_lock_acquire_and_release(tmp_path):
    """_state_lock contextmanager 能 acquire + release 不报错（单进程基础测）."""
    from pinrule.session_state import _state_lock

    with _state_lock("sess1", base_dir=tmp_path):
        # lock 内可以读写文件（lock 文件位于 <state_path>.json.lock）
        pass

    # 再次 acquire 应该成功（前一次已释放）
    with _state_lock("sess1", base_dir=tmp_path):
        pass


def test_update_state_concurrent_no_lost_updates(tmp_path):
    """**core race fix 验证** — 多进程并发 update_state 不丢「写不同 key」更新。

    起 N=20 个子进程，每个往同 (session_id) 的 read_files 加自己唯一的 path。
    全部跑完后 load state，验证 read_files 含全部 N 个 path。

    这是「不丢更新」**最弱形式**：每个 worker 加不同 set member。即使有 race，
    set union 顺道可能保了一些。`test_update_state_concurrent_counter_increment`
    用 read-modify-write 同一字段验证 race fix 更彻底。
    """
    import subprocess
    import sys as _sys
    from pinrule.session_state import load

    n_workers = 20
    worker_script = """
import sys
sys.path.insert(0, sys.argv[1])
from pinrule.session_state import update_state
from pathlib import Path

worker_id = sys.argv[2]
base_dir = Path(sys.argv[3])

def _add_my_read(state):
    state.record_read(f"/worker_{worker_id}.py")

update_state("concurrent_sess", _add_my_read, base_dir=base_dir)
"""

    # 写 worker script 到 tmp
    worker_path = tmp_path / "worker.py"
    worker_path.write_text(worker_script)

    # 找 pinrule package 根（site-packages or repo root）
    import pinrule
    pinrule_pkg_dir = str(Path(pinrule.__file__).resolve().parent.parent)

    # 并发起 N 个 subprocess
    procs = [
        subprocess.Popen(
            [_sys.executable, str(worker_path), pinrule_pkg_dir, str(i), str(tmp_path)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        for i in range(n_workers)
    ]

    # 全部 wait
    for p in procs:
        p.wait(timeout=30)
        assert p.returncode == 0, f"worker failed: {p.stderr.read().decode()}"

    # 验证所有 N 个 update 都生效（无丢更新）
    final_state = load("concurrent_sess", base_dir=tmp_path)
    expected = {np(f"/worker_{i}.py") for i in range(n_workers)}
    assert final_state.read_files == expected, (
        f"丢更新 race: expected {n_workers} paths, got {len(final_state.read_files)}"
        f"\n missing: {expected - final_state.read_files}"
    )


def test_update_state_concurrent_counter_increment(tmp_path):
    """**race fix 试金石** — read-modify-write 同一字段不丢更新。

    起 N=30 个子进程，每个 `state.turn_count += 1`（典型 read-modify-write）。
    全部跑完 turn_count 必须是精确 30 — 不是 < 30（丢更新）也不是 > 30（脏写）。

    这种 RMW 同字段模式是 race 真试金石：没 lock 时几乎一定丢，因为：
    - 进程 A load (turn_count=0) → 改成 1 → save
    - 进程 B 在 A 改 / save 之间 load (turn_count=0) → 改成 1 → save
    - 两个 +1 操作只生效一次

    有 fcntl.flock 时：load → modify → save 整段串行化 → 30 次 += 1 = 30。
    """
    import subprocess
    import sys as _sys
    from pinrule.session_state import load

    n_workers = 30
    worker_script = """
import sys
sys.path.insert(0, sys.argv[1])
from pinrule.session_state import update_state
from pathlib import Path

base_dir = Path(sys.argv[2])

def _increment(state):
    state.turn_count += 1

update_state("counter_sess", _increment, base_dir=base_dir)
"""

    worker_path = tmp_path / "counter_worker.py"
    worker_path.write_text(worker_script)

    import pinrule
    pinrule_pkg_dir = str(Path(pinrule.__file__).resolve().parent.parent)

    procs = [
        subprocess.Popen(
            [_sys.executable, str(worker_path), pinrule_pkg_dir, str(tmp_path)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        for _ in range(n_workers)
    ]

    for p in procs:
        p.wait(timeout=30)
        assert p.returncode == 0, f"worker failed: {p.stderr.read().decode()}"

    final_state = load("counter_sess", base_dir=tmp_path)
    assert final_state.turn_count == n_workers, (
        f"counter race: expected turn_count={n_workers}, got {final_state.turn_count}\n"
        f"(读-改-写同字段 race 时，并发进程会读到相同旧值各自 += 1 → save 覆盖丢更新)"
    )


def test_update_state_different_sessions_truly_parallel(tmp_path):
    """**lock 颗粒度反向验证** — 不同 session 真并发不被全局串行化拖。

    起 N=10 进程各自 update 不同 session_id，每个 fn 阻塞 0.3s。
    串行（错误实施 — 全局 lock）：总耗时 ≥ N * 0.3 = 3.0s
    并发（正确实施 — per-session lock）：总耗时 ≈ 0.3s + 启动 overhead

    实施 bug 比如「lock 文件用固定路径不按 session_id 隔离」会让所有
    session 抢同一把 lock，pinrule 性能被全局串行化拖。这个测试反向防御。
    """
    import subprocess
    import sys as _sys
    import time
    from pinrule.session_state import load

    n_workers = 10
    worker_script = """
import sys
import time
sys.path.insert(0, sys.argv[1])
from pinrule.session_state import update_state
from pathlib import Path

session_id = sys.argv[2]
base_dir = Path(sys.argv[3])

def _slow_fn(state):
    time.sleep(0.3)  # 模拟 hook fn 内业务逻辑
    state.tool_byte_seq = 1

update_state(session_id, _slow_fn, base_dir=base_dir)
"""

    worker_path = tmp_path / "parallel_worker.py"
    worker_path.write_text(worker_script)

    import pinrule
    pinrule_pkg_dir = str(Path(pinrule.__file__).resolve().parent.parent)

    t0 = time.time()
    procs = [
        subprocess.Popen(
            [_sys.executable, str(worker_path), pinrule_pkg_dir, f"sess_{i}", str(tmp_path)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        for i in range(n_workers)
    ]
    for p in procs:
        p.wait(timeout=30)
        assert p.returncode == 0, f"worker failed: {p.stderr.read().decode()}"
    elapsed = time.time() - t0

    # 串行下界 N * 0.3 = 3.0s，并发上界宽松给到 1.5s（启动 overhead + IO）
    assert elapsed < 1.5, (
        f"不同 session 被串行化：N={n_workers} 个 fn 各 0.3s 跑了 {elapsed:.2f}s "
        f"(并发应 < 1.5s，串行约 {n_workers * 0.3}s) — _state_lock 颗粒度有 bug"
    )

    # 验证全部 update 落地
    for i in range(n_workers):
        s = load(f"sess_{i}", base_dir=tmp_path)
        assert s.tool_byte_seq == 1, f"session sess_{i} update 未落地"
