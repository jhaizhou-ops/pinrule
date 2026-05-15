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

from karma.checks._types import CheckHit
from karma.checks.common import extract_tool_text
from karma.checks.description_context import is_description_context

# 检测规则按 tool 范围分组：避免文档 / 代码字符串里出现描述性字面被误判

# 适用所有 tool（Bash / Write / Edit）— 真违反不分上下文
_PATTERNS_ALL = [
    (
        # 长 ID 字面写在 if 分支 — 必须含数字才命中
        # 区分真违反（UUID / hash / 长数字串如 'abc-12345-def'）跟合法 CLI dispatch
        # （字面如 'install-hooks' / 'no-testset-no-future-leakage' — kebab-case 命令
        # 名 / sticky id 不含数字，是合法分发不是 ID 硬写）
        re.compile(r"""if\s+\w+\s*==\s*(['"])(?=[\w\-]{12,}\1)[\w\-]*\d[\w\-]*\1"""),
        "长 ID 字面写在 if 分支（特例分支硬编码）",
        "长 ID 写在 if 分支后面别人加新 case 都要改这里 — 提到配置 / 通用判定逻辑让它能长期演化。",
    ),
    (
        # 变量名带黑白名单语义 hint 才算「真黑/白名单字面量」
        # 避免普通 samples=['a','b'] / examples=[...] 等探针 / 测试样本误判
        re.compile(
            r"""\b\w*(?:blacklist|whitelist|stopwords?|badwords?|forbidden|banned|excluded?|ignored|filter_?words?|skip_?list|denylist|allowlist)\w*\s*=\s*\[\s*["']""",
            re.IGNORECASE,
        ),
        "黑/白名单字面量列表 (变量名匹配黑白名单语义)",
        "黑白名单写死在代码里以后改名单要动代码 — 提到配置 / 用规则代替让它能演化。",
    ),
    (
        # 全大写常量名 + 5 元素以上字符串列表（捕捉 BAD_USERS / SPECIAL_IDS / KNOWN_BOTS 等
        # 不带 blacklist 字眼但是常见硬编码名单变量名风格）
        # 要求 5+ 元素避开 EXAMPLES=['a','b'] 这种短小测试样本
        re.compile(
            r"""\b[A-Z][A-Z0-9_]{2,}\s*=\s*\[\s*(?:["'][^"'\n]+["']\s*,\s*){4,}""",
        ),
        "全大写常量 + 5+ 元素字符串列表（疑似硬编码黑/白名单）",
        "全大写常量 5+ 元素字符串列表通常是硬编码名单 — 提到配置或用规则代替让它能长期演化。",
    ),
]

# 仅 Bash tool 检测 — 这些 flag 在文档/代码字符串里出现是描述，不是真违反
_PATTERNS_BASH_ONLY = [
    (
        # 限定字眼出现在 commit message 标题行（开始 80 字内、第一行）—
        # git 规范标题行 < 72 字。后部长描述里讨论字眼是元层面 ≠ 真违反。
        # `[^"'\n]{0,80}?` 要求字眼前最多 80 个非引号非换行字符。
        re.compile(r"""git\s+commit.*?["'](?:[^"'\n]{0,80}?)(quick\s*fix|hack\b|temp\b|workaround|临时|凑数)""", re.IGNORECASE),
        "git commit 标题行含 quick fix / hack / temp / 临时 字眼",
        "commit 标题是给用户看的「这次改了什么」信号。换成「fix X: 原因 Y」让他能直接看懂，不用展开读 diff。",
    ),
    (
        # 收紧到「git 危险动作 + 危险 flag 同句」— 之前泛 flag 匹配会误拦
        # pytest --skip-broken / pip install --skip-existing / cmake --force /
        # rsync --force / tar --skip-old-files 等合法 flag。
        # 真正想拦的是 git commit/push/merge/rebase 跳过验证。
        re.compile(
            r"git\s+(?:commit|push|merge|rebase|tag)\s+[^|;\n]*?"
            r"(?:--no-verify\b|--force(?!-with-lease)\b|--skip-hooks\b)",
            re.IGNORECASE,
        ),
        "git 危险动作跳过验证 flag",
        "跳过 pre-commit / hook 验证 = 短期通过但坏的代码进了 git 历史 — 用户回看时会发现。先修对再提交。",
    ),
]

# 仅 Write/Edit 代码内容 — TODO/HACK 标记在 Bash 命令里没意义
_PATTERNS_WRITE_EDIT_ONLY = [
    (
        re.compile(r"(?:#|//|--)\s*(?:TODO|FIXME|HACK|XXX)(?:\s*[:(]|\s+@)|(?:#|//|--)\s*临时\b", re.IGNORECASE),
        "代码含 TODO/FIXME/HACK/临时 标记注释",
        "TODO / FIXME / HACK 留在代码里 = 给以后的人留债。要么本次解决掉再提交，要么在 PR 里明确 follow-up 计划让用户知道。",
    ),
    (
        # 明确「打补丁/绕过/凑数」意图的注释（M3 之前关键词层兜底，现在工程层精准化捕获）
        re.compile(
            r"(?:#|//|--)\s*[^\n]{0,60}?(?:先打个?补丁|临时方案|快速绕过|workaround|hack\s*around|quick\s*fix|凑数|短期\s*目标|hack\s+for|patch\s+for\s+now)",
            re.IGNORECASE,
        ),
        "代码含「打补丁 / 绕过 / 凑数 / workaround」意图注释",
        "「先这样 / 临时方案 / 凑数」意图注释 = 给用户的「债还没还」信号 — 找根因方案再提交，他会更放心。",
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
    # 描述上下文（文档/测试代码/探针文件）整段豁免 — 那里出现 pattern 是描述不是执行
    is_desc, _label = is_description_context(tool_name, tool_input or {})
    if is_desc:
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
            snippet = text[max(0, m.start() - 30): m.end() + 30].strip()
            return CheckHit(
                sticky_id=_STICKY_ID,
                trigger=desc,
                snippet=snippet[:200],
                suggested_fix=fix,
            )
    return None
