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

from pinrule.checks._types import CheckHit
from pinrule.checks.common import extract_tool_text
from pinrule.checks.description_context import is_description_context
from pinrule.i18n import tr

# 检测规则按 tool 范围分组：避免文档 / 代码字符串里出现描述性字面被误判

# 适用所有 tool（Bash / Write / Edit）— 违反不分上下文
_PATTERNS_ALL = [
    (
        # 长 ID 字面写在 if 分支 — 必须含数字才命中
        # 区分违反（UUID / hash / 长数字串如 'abc-12345-def'）跟合法 CLI dispatch
        # （字面如 'install-hooks' / 'no-testset-no-future-leakage' — kebab-case 命令
        # 名 / sticky id 不含数字，是合法分发不是 ID 硬写）
        re.compile(r"""if\s+\w+\s*==\s*(['"])(?=[\w\-]{12,}\1)[\w\-]*\d[\w\-]*\1"""),
        "check.long_term.long_id_branch.trigger",
        "check.long_term.long_id_branch.fix",
    ),
    (
        # 变量名带黑白名单语义 hint 才算「真黑/白名单字面量」
        # 避免普通 samples=['a','b'] / examples=[...] 等探针 / 测试样本误判
        re.compile(
            r"""\b\w*(?:blacklist|whitelist|stopwords?|badwords?|forbidden|banned|excluded?|ignored|filter_?words?|skip_?list|denylist|allowlist)\w*\s*=\s*\[\s*["']""",
            re.IGNORECASE,
        ),
        "check.long_term.blacklist_literal.trigger",
        "check.long_term.blacklist_literal.fix",
    ),
    (
        # 全大写常量名 + 5 元素以上字符串列表（捕捉 BAD_USERS / SPECIAL_IDS / KNOWN_BOTS 等
        # 不带 blacklist 字眼但是常见硬编码名单变量名风格）
        # 要求 5+ 元素避开 EXAMPLES=['a','b'] 这种短小测试样本
        re.compile(
            r"""\b[A-Z][A-Z0-9_]{2,}\s*=\s*\[\s*(?:["'][^"'\n]+["']\s*,\s*){4,}""",
        ),
        "check.long_term.uppercase_const_list.trigger",
        "check.long_term.uppercase_const_list.fix",
    ),
]

# 仅 Bash tool 检测 — 这些 flag 在文档/代码字符串里出现是描述，不是违反
_PATTERNS_BASH_ONLY = [
    (
        # 限定字眼出现在 commit message 标题行（开始 80 字内、第一行）—
        # git 规范标题行 < 72 字。后部长描述里讨论字眼是元层面 ≠ 违反。
        # `[^"'\n]{0,80}?` 要求字眼前最多 80 个非引号非换行字符。
        re.compile(r"""git\s+commit.*?["'](?:[^"'\n]{0,80}?)(quick\s*fix|hack\b|temp\b|workaround|临时|凑数)""", re.IGNORECASE),
        "check.long_term.commit_hack.trigger",
        "check.long_term.commit_hack.fix",
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
        "check.long_term.git_skip_verify.trigger",
        "check.long_term.git_skip_verify.fix",
    ),
]

# 仅 Write/Edit 代码内容 — TODO/HACK 标记在 Bash 命令里没意义
_PATTERNS_WRITE_EDIT_ONLY = [
    (
        re.compile(r"(?:#|//|--)\s*(?:TODO|FIXME|HACK|XXX)(?:\s*[:(]|\s+@)|(?:#|//|--)\s*临时\b", re.IGNORECASE),
        "check.long_term.todo_marker.trigger",
        "check.long_term.todo_marker.fix",
    ),
    (
        # 明确「打补丁/绕过/凑数」意图的注释（M3 之前关键词层兜底，现在工程层精准化捕获）
        re.compile(
            r"(?:#|//|--)\s*[^\n]{0,60}?(?:先打个?补丁|临时方案|快速绕过|workaround|hack\s*around|quick\s*fix|凑数|短期\s*目标|hack\s+for|patch\s+for\s+now)",
            re.IGNORECASE,
        ),
        "check.long_term.patch_intent.trigger",
        "check.long_term.patch_intent.fix",
    ),
]

# v0.11.0: response-level 话术 pattern — 跟 tool_input 工程层 engine 并行.
# 真证据驱动: v0.10.x dogfooding 显示 long-term-fundamental engine 触发率 0%
# (12 条违反全 keyword fallback). 根因 = engine 维度选了工程层证据 (--no-verify
# / TODO / hardcoded hash 都很罕见), 而 Agent 真违反场景是**话术**「先打补丁 /
# 短期方案 / 硬编码先这样」. 这个新增 pattern 跟 violation_keywords 维度一致
# 但用结构化组合 pattern 比单字面更精: 必须含**意图前缀**(我/咱/先) + **短期动词**
# (打补丁/硬编码/凑数/临时...) 才命中, 避免 Agent 在讨论长期方案时引用「补丁」
# 字面被假阳 (e.g., "短期补丁不行" 不该命中 — 这是反思).
_RESPONSE_PATCH_INTENT_PATTERNS = [
    # 类 1: 第一人称 + 短期动作宣告 ("我先打个补丁 / 咱先硬编码 / 我临时这样改")
    # 必须**意图前缀** + **短期动作动词** 同短距离 (≤ 12 字),避免反思场景假阳
    (
        re.compile(
            r"(?:我|咱|让我|这次|目前|当前|临时)"  # 意图前缀
            r"[^。\n]{0,12}"                       # 短距离
            r"(?:先打个?补丁|打个?补丁\b|先硬编码|临时硬编码|先\s*hack|"
            r"凑数|短期\s*绕|临时\s*绕|短期方案|临时方案|绕过验证|"
            r"先\s*workaround|patch\s+一下|先\s*hardcode)",
            re.IGNORECASE,
        ),
        "check.long_term.response_patch_intent.trigger",
        "check.long_term.patch_intent.fix",
    ),
    # 类 2: 显式承认「不长期」+ 紧跟「但 / 先这样」 转折 (承认但仍执行短期路径)
    # e.g., "知道不是长期方案 但先这样"
    (
        re.compile(
            r"(?:知道|明白)[^。\n]{0,20}"
            r"(?:不是长期|不够根本|不优雅|是个补丁|不彻底)"
            r"[^。\n]{0,15}"
            r"(?:但|可是|不过|先这样|先用|先\s*ship)",
        ),
        "check.long_term.response_acknowledge_but_proceed.trigger",
        "check.long_term.patch_intent.fix",
    ),
    # 类 3 (v0.11.4 英文对偶): 第一人称意图前缀 (let me / I'll / let's just / for now)
    # + 短距离 (≤ 50 chars) + 短期动作动词 (hardcode / patch / hack / workaround / quick fix).
    # 跟类 1 中文 pattern 镜像对偶, 让英文用户的 demo / 真 dogfood 也能 catch
    # short-term intent 话术.
    # 用 \b 词边界避免「hardcoded」类合法名词被假阳 (例如「the hardcoded list」是
    # 描述讨论, 但「let me hardcode」是意图宣告).
    (
        re.compile(
            r"(?:let\s+me|i'?ll|let'?s\s+just|i\s+will|for\s+now|temporarily|"
            r"i\s+can\s+just|we'?ll\s+just|just)"  # intent prefix
            r"[^.\n]{0,50}?"                          # short distance
            r"\b(?:hardcode|patch\s+(?:it|this|that)|hack\s+around|"
            r"workaround|quick\s*fix|skip\s+(?:the\s+)?(?:test|check|verif)|"
            r"ship\s+it|kludge|band-?aid)\b",
            re.IGNORECASE,
        ),
        "check.long_term.response_patch_intent.trigger",
        "check.long_term.patch_intent.fix",
    ),
    # 类 4 (v0.11.4 英文对偶): 显式承认「not the right fix / not long-term」+
    # 紧跟「but / for now」转折 (承认但仍执行短期路径). 跟类 2 镜像.
    (
        re.compile(
            r"(?:i\s+know|aware|understand)[^.\n]{0,30}"
            r"(?:not\s+(?:the\s+)?(?:right|long-?term|clean|proper|ideal)|"
            r"is\s+a\s+(?:patch|hack|kludge|band-?aid))"
            r"[^.\n]{0,25}"
            r"(?:but|however|though|for\s+now|just\s+for\s+now|temporarily)",
            re.IGNORECASE,
        ),
        "check.long_term.response_acknowledge_but_proceed.trigger",
        "check.long_term.patch_intent.fix",
    ),
]

_STICKY_ID = "long-term-fundamental"


def check(*, tool_name: str = "", tool_input: dict | None = None, response: str = "", **_):
    """按 tool 类型选不同 pattern 集合扫 (tool_input 层),
    + v0.11.0 加 response-level 话术 pattern (response 层) 跟 keyword 维度互补.

    Bash 要执行 → 严查 `--no-verify` 类执行行为
    Write/Edit 写代码内容 → 严查 TODO/HACK 注释
    通用 → 长 ID if 分支 / 字面量黑名单
    Stop hook 给 response → 严查「我先打补丁 / 临时绕」类意图话术
    """
    # v0.11.0 response-level engine check — Stop hook 给 response 时跑.
    # 跟 tool_input 层并行 (response 是 Agent 自己说的, tool_input 是 Agent 执行的).
    # 必须先于 tool_name early return, 因为 Stop hook response check 没 tool_name.
    if response:
        for pat, trigger_key, fix_key in _RESPONSE_PATCH_INTENT_PATTERNS:
            m = pat.search(response)
            if m:
                snippet = response[max(0, m.start() - 30): m.end() + 30].strip()
                return CheckHit(
                    rule_id=_STICKY_ID,
                    trigger=tr(trigger_key),
                    trigger_key=trigger_key,
                    snippet=snippet[:200],
                    suggested_fix=tr(fix_key),
                )

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

    for pat, trigger_key, fix_key in patterns:
        m = pat.search(text)
        if m:
            snippet = text[max(0, m.start() - 30): m.end() + 30].strip()
            return CheckHit(
                rule_id=_STICKY_ID,
                trigger=tr(trigger_key),
                trigger_key=trigger_key,
                snippet=snippet[:200],
                suggested_fix=tr(fix_key),
            )
    return None
