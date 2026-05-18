"""描述上下文豁免测试 — 区分「执行意图」vs「描述模式」。"""

from __future__ import annotations

from pinrule.checks.description_context import is_description_context


def test_markdown_doc_is_description():
    assert is_description_context("Write", {"file_path": "/x/README.md"})[0]
    assert is_description_context("Edit", {"file_path": "/x/HANDOFF.md"})[0]
    assert is_description_context("Write", {"file_path": "foo.rst"})[0]
    assert is_description_context("Write", {"file_path": "y.markdown"})[0]
    assert is_description_context("Write", {"file_path": "z.txt"})[0]
    assert is_description_context("Write", {"file_path": "x.adoc"})[0]


def test_pinrule_impl_files_are_description():
    """pinrule/checks/ 和 pinrule/hooks/ 下 .py 文件是检测器实现 — 必然要含触发
    字面（pattern 定义 / docstring 描述）→ 豁免。任何 pinrule 用户都有这些文件，
    不算针对作者作弊。"""
    assert is_description_context("Write", {"file_path": "/x/pinrule/checks/long_term.py"})[0]
    assert is_description_context("Edit", {"file_path": "/repo/pinrule/checks/bypass_pinrule.py"})[0]
    assert is_description_context("Write", {"file_path": "/a/pinrule/hooks/stop.py"})[0]
    # 但 pinrule/cli.py / pinrule/sticky.py 等非 checks/hooks 不豁免
    assert not is_description_context("Write", {"file_path": "/x/pinrule/cli.py"})[0]
    assert not is_description_context("Write", {"file_path": "/x/pinrule/sticky.py"})[0]


def test_data_config_files_are_description():
    """yaml/json/toml 等数据文件 — 内容是描述性数据不是执行字面。"""
    assert is_description_context("Write", {"file_path": "/x/sticky.json"})[0]
    assert is_description_context("Write", {"file_path": "/x/config.yml"})[0]
    assert is_description_context("Write", {"file_path": "/x/data.json"})[0]
    assert is_description_context("Write", {"file_path": "/x/pyproject.toml"})[0]
    assert is_description_context("Write", {"file_path": "/x/setup.ini"})[0]
    assert is_description_context("Edit", {"file_path": "/x/data.csv"})[0]


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
    assert is_description_context("Write", {"file_path": "/x/pinrule_probe.py"})[0]
    assert is_description_context("Write", {"file_path": "/x/scratch.py"})[0]
    assert is_description_context("Write", {"file_path": "/x/sample_data.py"})[0]


def test_normal_source_code_not_description():
    """正常源码不豁免。"""
    assert not is_description_context("Write", {"file_path": "src/pinrule.py"})[0]
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
