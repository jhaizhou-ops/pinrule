"""#1 long-term-fundamental — 用长期方案，不打补丁。

检测的行为模式（pre_tool_use Edit/Write/Bash）：
1. 长 hash ID 字面写在 if 分支（特例分支硬编码）
2. 高精度未解释 magic number（threshold=0.567）
3. commit message 含 quick fix / hack / temp / 临时
4. 强制跳过验证（--no-verify / --skip）
5. 代码含 TODO/HACK/XXX/临时 注释
"""

from __future__ import annotations

import re

from karma.checks.common import extract_tool_text

# 检测规则按 tool 范围分组：避免文档 / 代码字符串里出现描述性字面被误判

# 适用所有 tool（Bash / Write / Edit）— 真违反不分上下文
_PATTERNS_ALL = [
    (
        re.compile(r"""if\s+\w+\s*==\s*['"][\w\-]{12,}['"]"""),
        "长 ID 字面写在 if 分支（特例分支硬编码）",
        "把这种长 ID 字面提到配置 / 通用判定逻辑，不要硬写 if-elif 分支。",
    ),
    (
        re.compile(
            r"""=\s*\[\s*\n?\s*["'][^"'\n]{2,40}["']\s*,\s*\n?\s*["'][^"'\n]{2,40}["']""",
        ),
        "字面量列表（疑似 surface-form 黑名单 / 测试集白名单）",
        "用通用判定逻辑替代字面量列表，避免针对具体值打补丁。",
    ),
]

# 仅 Bash tool 检测 — 这些 flag 在文档/代码字符串里出现是描述，不是真违反
_PATTERNS_BASH_ONLY = [
    (
        re.compile(r"""git\s+commit.*?["'](?:[^"']*?)(quick\s*fix|hack\b|temp\b|workaround|临时|凑数)""", re.IGNORECASE),
        "git commit message 含 quick fix / hack / temp / 临时",
        "改 commit message 清楚说明改了什么 + 为什么。这不是临时改动。",
    ),
    (
        re.compile(r"--no-verify\b|--skip[\w-]*|--force(?:\s+|$)", re.IGNORECASE),
        "强制跳过验证 flag",
        "不要跳过 pre-commit / 测试 / 验证。先把验证修对再提交。",
    ),
]

# 仅 Write/Edit 代码内容 — TODO/HACK 标记在 Bash 命令里没意义
_PATTERNS_WRITE_EDIT_ONLY = [
    (
        re.compile(r"#\s*(TODO|FIXME|HACK|XXX|临时|tmp)\b", re.IGNORECASE),
        "代码含 TODO / FIXME / HACK / 临时 注释",
        "把临时注释解决掉再提交，或者在 PR 里明确 follow-up 计划。",
    ),
]

_STICKY_ID = "long-term-fundamental"


def check(*, tool_name: str = "", tool_input: dict | None = None, **_):
    """按 tool 类型选不同 pattern 集合扫。

    Bash 真要执行 → 严查 `--no-verify` 类执行行为
    Write/Edit 写代码内容 → 严查 TODO/HACK 注释
    通用 → 长 ID if 分支 / 字面量黑名单
    """
    if tool_name not in ("Bash", "Write", "Edit", "NotebookEdit"):
        return None
    text = extract_tool_text(tool_name, tool_input or {})
    if not text:
        return None

    # 按 tool 范围选 pattern
    patterns = list(_PATTERNS_ALL)
    if tool_name == "Bash":
        patterns.extend(_PATTERNS_BASH_ONLY)
    elif tool_name in ("Write", "Edit", "NotebookEdit"):
        patterns.extend(_PATTERNS_WRITE_EDIT_ONLY)

    for pat, desc, fix in patterns:
        m = pat.search(text)
        if m:
            from karma.checks import CheckHit
            snippet = text[max(0, m.start() - 30): m.end() + 30].strip()
            return CheckHit(
                sticky_id=_STICKY_ID,
                trigger=desc,
                snippet=snippet[:200],
                suggested_fix=fix,
            )
    return None
