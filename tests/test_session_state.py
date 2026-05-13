"""session_state IO + 状态跟踪测试。"""

from __future__ import annotations

from karma.session_state import SessionState, load, save


def test_round_trip(tmp_path):
    s = SessionState(session_id="abc")
    s.record_read("/tmp/a.py")
    s.record_read("/tmp/b.py")
    s.record_edit("/tmp/a.py")
    s.record_bash("pytest tests/", "==== 10 passed in 0.1s ====")
    s.record_bash("ls", "a.txt b.txt")
    save(s, base_dir=tmp_path)

    loaded = load("abc", base_dir=tmp_path)
    assert loaded.read_files == {"/tmp/a.py", "/tmp/b.py"}
    assert loaded.edit_files == ["/tmp/a.py"]
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
    assert loaded.read_files == {"/tmp/a"}
