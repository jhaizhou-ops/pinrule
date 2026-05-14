"""描述上下文豁免测试 — 区分「执行意图」vs「描述模式」。"""

from __future__ import annotations

from karma.checks.description_context import is_description_context


def test_markdown_doc_is_description():
    assert is_description_context("Write", {"file_path": "/x/README.md"})[0]
    assert is_description_context("Edit", {"file_path": "/x/HANDOFF.md"})[0]
    assert is_description_context("Write", {"file_path": "foo.rst"})[0]
    assert is_description_context("Write", {"file_path": "y.markdown"})[0]
    assert is_description_context("Write", {"file_path": "z.txt"})[0]
    assert is_description_context("Write", {"file_path": "x.adoc"})[0]


def test_tests_directory_is_description():
    """tests/ 下任何文件都是描述/测试上下文。"""
    assert is_description_context("Write", {"file_path": "/x/tests/test_foo.py"})[0]
    assert is_description_context("Edit", {"file_path": "tests/conftest.py"})[0]
    assert is_description_context("Write", {"file_path": "/repo/foo/tests/bar.py"})[0]


def test_test_file_name_pattern():
    """文件名匹配 test_*.py / *_test.py / *_test.go 算测试代码。"""
    assert is_description_context("Write", {"file_path": "src/test_foo.py"})[0]
    assert is_description_context("Write", {"file_path": "foo_test.go"})[0]
    assert is_description_context("Write", {"file_path": "x_test.rs"})[0]


def test_tmp_scratch_files_are_description():
    """/tmp/ 下临时文件 / 文件名含 probe/scratch/sample 算探针。"""
    assert is_description_context("Write", {"file_path": "/tmp/x.py"})[0]
    assert is_description_context("Write", {"file_path": "/x/karma_probe.py"})[0]
    assert is_description_context("Write", {"file_path": "/x/scratch.py"})[0]
    assert is_description_context("Write", {"file_path": "/x/sample_data.py"})[0]


def test_normal_source_code_not_description():
    """正常源码不豁免。"""
    assert not is_description_context("Write", {"file_path": "src/karma.py"})[0]
    assert not is_description_context("Edit", {"file_path": "/repo/foo.py"})[0]
    assert not is_description_context("Write", {"file_path": "lib/handler.ts"})[0]


def test_bash_never_description():
    """Bash 永远是执行意图 — 不豁免。"""
    assert not is_description_context("Bash", {"command": "git commit"})[0]
    assert not is_description_context("Bash", {"command": "rm -rf /tmp/x"})[0]


def test_read_tool_not_in_scope():
    """Read tool 不在 check 范围 — 返回 False（让上层决定不调用）。"""
    assert not is_description_context("Read", {"file_path": "/x/README.md"})[0]


def test_empty_or_missing_input():
    assert not is_description_context("Write", {})[0]
    assert not is_description_context("Write", {"file_path": ""})[0]
    assert not is_description_context("", {})[0]


def test_reason_string_helpful():
    """第二个返回值是原因 string，便于调试。"""
    is_desc, reason = is_description_context("Write", {"file_path": "/x/README.md"})
    assert is_desc
    assert "markdown" in reason.lower() or "文档" in reason
