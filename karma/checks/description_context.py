"""描述上下文判定 — 区分「执行意图」vs「描述触发模式」。

工程 check（long_term / testset 等）扫 tool_input 找触发模式，
但无法区分用户是「真要这么干」还是「在文档/测试代码/探针文件里描述这种模式」。
这层抽象把所有自指场景的豁免逻辑收归一处。

豁免维度（按 file_path 判定，因为 hit 在 file_path 对应的语境里）：
1. 文档后缀 — .md / .rst / .txt / .markdown / .adoc
2. 测试目录 — 路径含 /tests/ 或 /test/
3. 测试文件名 — test_*.py / *_test.py / *_test.go / *_test.rs
4. 临时探针 — /tmp/ 路径或文件名含 probe / scratch / sample

不豁免：
- Bash command — 永远是执行意图
- 正常源码（src/x.py, lib/y.ts 等）

返回 (是否描述, 原因 string)。原因便于调试 / 日志输出。
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

_DOC_SUFFIXES = (".md", ".rst", ".txt", ".markdown", ".adoc")
_TEST_FILE_RE = re.compile(r"(?:^|[/_])test_[\w\-]+\.\w+$|[\w\-]+_test\.\w+$")
_SCRATCH_NAME_RE = re.compile(r"(?:probe|scratch|sample|playground|fixture)", re.IGNORECASE)

# 这些 tool 会被各类 check 扫；只对它们做上下文判定
_IN_SCOPE_TOOLS = frozenset({"Write", "Edit", "NotebookEdit"})


def is_description_context(
    tool_name: str,
    tool_input: dict | None,
) -> tuple[bool, str]:
    """判断 tool 调用是否为「描述上下文」（应豁免 pattern check）。

    Bash / Read 等永远返回 (False, "")，因为：
    - Bash 是执行意图
    - Read 不在 check 范围内
    """
    if tool_name not in _IN_SCOPE_TOOLS:
        return False, ""
    if not tool_input:
        return False, ""

    file_path = (tool_input.get("file_path") or tool_input.get("notebook_path") or "").strip()
    if not file_path:
        return False, ""

    fp_lower = file_path.lower()

    # 1. 文档后缀
    if fp_lower.endswith(_DOC_SUFFIXES):
        return True, f"文档文件 ({fp_lower.rsplit('.', 1)[-1]})"

    # 2. 测试目录
    parts = PurePosixPath(file_path).parts
    if any(p in ("tests", "test", "__tests__", "spec") for p in parts):
        return True, "测试目录"

    # 3. 测试文件名
    name = PurePosixPath(file_path).name
    if _TEST_FILE_RE.search(name):
        return True, "测试文件名模式"

    # 4. 临时探针 — /tmp/ 路径
    if file_path.startswith("/tmp/") or file_path.startswith("/var/tmp/"):
        return True, "临时探针路径 (/tmp)"

    # 5. 文件名含 probe / scratch / sample
    if _SCRATCH_NAME_RE.search(name):
        return True, "探针/样本文件名"

    return False, ""
