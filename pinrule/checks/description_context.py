"""描述上下文判定 — 区分「执行意图」vs「描述触发模式」。

工程 check（long_term / testset 等）扫 tool_input 找触发模式，
但无法区分用户是「要这么干」还是「在文档/测试代码/探针文件里描述这种模式」。
这层抽象把所有自指场景的豁免逻辑收归一处。

豁免维度（按 file_path 判定，因为 hit 在 file_path 对应的语境里）：
1. 文档后缀 — .md / .rst / .txt / .markdown / .adoc
2. 数据/配置文件 — .yaml / .yml / .json / .toml / .ini / .csv / .tsv
3. 测试目录 — 路径含 /tests/ 或 /test/
4. 测试文件名 — test_*.py / *_test.py / *_test.go / *_test.rs
5. 临时探针 — /tmp/ 路径或文件名含 probe / scratch / sample

不豁免：
- Bash command — 永远是执行意图
- 正常源码（src/x.py, lib/y.ts 等）

返回 (是否描述, 原因 string)。原因便于调试 / 日志输出。
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

_DOC_SUFFIXES = (".md", ".rst", ".txt", ".markdown", ".adoc")
# 数据 / 配置文件 — 内容是描述性数据不是执行字面
# 例：rules.yaml 列违反字面、production config 含黑名单数据
_DATA_SUFFIXES = (".yaml", ".yml", ".json", ".toml", ".ini", ".csv", ".tsv")
_TEST_FILE_RE = re.compile(r"(?:^|[/_])test_[\w\-]+\.\w+$|[\w\-]+_test\.\w+$")
# pinrule 检测器实现路径 — 这些文件**必须**含触发字面（pattern 定义 / docstring 描述）
# 不算针对作者作弊，是任何 pinrule 用户的实现自身必然要描述要拦的字面
_PINRULE_IMPL_RE = re.compile(r"pinrule/checks/[\w\-]+\.py$|pinrule/hooks/[\w\-]+\.py$")
_SCRATCH_NAME_RE = re.compile(r"(?:probe|scratch|sample|playground|fixture)", re.IGNORECASE)

# 这些 tool 会被各类 check 扫；只对它们做上下文判定
_IN_SCOPE_TOOLS = frozenset({"Write", "Edit", "NotebookEdit"})

# v0.5.9: Bash redirect/heredoc 目标路径解析 — 提升自 testset.py v0.5.8 局部 helper.
# 跟 Write/Edit 走 file_path 一致的尺度: 写目标是描述上下文路径 → 写内容是描述性的.
# 触发场景: `cat >> tests/test_x.py <<'PY' ... PY` (字符串字面是测试代码不是执行),
# `echo "TODO: x" >> docs/CHANGELOG.md` (文档描述不是代码).
_BASH_REDIR_TARGET_RE = re.compile(r">>?\s*([^\s|;<>&]+)")


def _classify_path(file_path: str) -> tuple[bool, str]:
    """单纯 path → 描述上下文判定 helper.

    v0.5.9 提取自 is_description_context 的 Write/Edit 分支，让 Bash redirect 目标
    路径也能复用同一套尺度。返回 (是否描述, 原因 string).
    """
    if not file_path:
        return False, ""
    fp_lower = file_path.lower()

    # 1. 文档后缀
    if fp_lower.endswith(_DOC_SUFFIXES):
        return True, f"文档文件 ({fp_lower.rsplit('.', 1)[-1]})"

    # 2. 数据 / 配置文件
    if fp_lower.endswith(_DATA_SUFFIXES):
        return True, f"数据/配置文件 ({fp_lower.rsplit('.', 1)[-1]})"

    # 3. 测试目录
    parts = PurePosixPath(file_path).parts
    if any(p in ("tests", "test", "__tests__", "spec") for p in parts):
        return True, "测试目录"

    # 4. 测试文件名
    name = PurePosixPath(file_path).name
    if _TEST_FILE_RE.search(name):
        return True, "测试文件名模式"

    # 5. 临时探针 — /tmp/ 路径
    if file_path.startswith("/tmp/") or file_path.startswith("/var/tmp/"):
        return True, "临时探针路径 (/tmp)"

    # 6. 文件名含 probe / scratch / sample
    if _SCRATCH_NAME_RE.search(name):
        return True, "探针/样本文件名"

    # 7. pinrule 检测器实现路径
    if _PINRULE_IMPL_RE.search(file_path.replace("\\", "/")):
        return True, "pinrule 检测器实现 (self-reference 必然)"

    return False, ""


def is_description_context(
    tool_name: str,
    tool_input: dict | None,
) -> tuple[bool, str]:
    """判断 tool 调用是否为「描述上下文」（应豁免 pattern check）。

    Bash redirect / heredoc 目标路径符合描述上下文（tests/ / .md 等）→ 豁免
    （v0.5.9 起，跟 Write/Edit file_path 一致尺度）.
    Read 不在 check 范围内永远 (False, "").
    """
    if not tool_input:
        return False, ""

    # v0.5.9: Bash 命令含 redirect/heredoc 写目标路径符合 description context → 豁免
    if tool_name == "Bash":
        cmd = (tool_input.get("command") or "").strip()
        if not cmd:
            return False, ""
        for m in _BASH_REDIR_TARGET_RE.finditer(cmd):
            target = m.group(1)
            is_desc, reason = _classify_path(target)
            if is_desc:
                return True, f"Bash 写目标 → {reason}"
        return False, ""

    if tool_name not in _IN_SCOPE_TOOLS:
        return False, ""

    file_path = (tool_input.get("file_path") or tool_input.get("notebook_path") or "").strip()
    if not file_path:
        return False, ""

    return _classify_path(file_path)
