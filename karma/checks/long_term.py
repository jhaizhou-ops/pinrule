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

# 检测规则：(regex, 中文描述, suggested fix 提示后缀)
_PATTERNS = [
    (
        re.compile(r"""if\s+\w+\s*==\s*['"][\w\-]{12,}['"]"""),
        "长 ID 字面写在 if 分支（特例分支硬编码）",
        "把这种长 ID 字面提到配置 / 通用判定逻辑，不要硬写 if-elif 分支。",
    ),
    (
        re.compile(r"""git\s+commit.*?["'](?:[^"']*?)(quick\s*fix|hack\b|temp\b|workaround|临时|凑数)""", re.IGNORECASE),
        "git commit message 含 quick fix / hack / temp / 临时",
        "改 commit message 清楚说明改了什么 + 为什么。这不是临时改动。",
    ),
    (
        re.compile(r"--no-verify\b|--skip[\w-]*|--force(?:\s+|$)", re.IGNORECASE),
        "强制跳过验证 flag（--no-verify / --skip / --force）",
        "不要跳过 pre-commit / 测试 / 验证。先把验证修对再 commit。",
    ),
    (
        re.compile(r"#\s*(TODO|FIXME|HACK|XXX|临时|tmp)\b", re.IGNORECASE),
        "代码含 TODO / FIXME / HACK / 临时 注释",
        "把临时注释解决掉再提交，或者在 PR 里明确 follow-up 计划。",
    ),
    (
        re.compile(
            r"""=\s*\[\s*\n?\s*["'][^"'\n]{2,40}["']\s*,\s*\n?\s*["'][^"'\n]{2,40}["']""",
        ),
        "字面量列表（疑似 surface-form 黑名单 / 测试集白名单）",
        "用通用判定逻辑替代字面量列表，避免针对具体值打补丁。",
    ),
]

_STICKY_ID = "long-term-fundamental"


def check(*, tool_name: str = "", tool_input: dict | None = None, **_):
    """Edit/Write/Bash content 扫硬编码 / quick fix pattern。"""
    if tool_name not in ("Bash", "Write", "Edit", "NotebookEdit"):
        return None
    text = extract_tool_text(tool_name, tool_input or {})
    if not text:
        return None
    for pat, desc, fix in _PATTERNS:
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
