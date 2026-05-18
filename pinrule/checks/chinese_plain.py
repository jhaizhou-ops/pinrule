"""#3 chinese-plain-no-jargon — 直白中文，不堆 jargon。

检测的行为模式（post_response 扫 Agent 自然语言响应）：
1. 自然语言部分（剔除 code block）中文占比 < 40%
2. 技术术语命中后 30 字内无中文跟随 → 真 jargon

关键决策：
- code block (``` 包裹) 内英文豁免（合法引用代码）
- inline `code` 也豁免
- 术语后 30 字内有 ≥ 2 个中文字符跟随 → 视为「英文术语 + 中文解释」豁免
"""

from __future__ import annotations

import re

from pinrule.checks._types import CheckHit
from pinrule.checks.common import (
    chinese_char_count,
    strip_code_blocks,
    total_visible_char_count,
)
from pinrule.i18n import tr

_STICKY_ID = "chinese-plain-no-jargon"

# URL 全英文但是结构性内容（不是 jargon 话术）— 算 ratio 时先剥
# 覆盖 https/http/带 markdown 链接 [text](url) 形式
_URL_RE = re.compile(
    r"\[(?:[^\]]*)\]\((?:https?://[^)]+)\)"  # markdown link [text](url)
    r"|https?://\S+"                           # 裸 URL
    r"|`?(?:[\w.-]+@[\w.-]+\.[a-z]{2,})`?"      # email
)

# markdown 表格 — 整行 `| ... | ... |` 是结构性数据不是 jargon 话术
# 含分隔行 `|---|---|` 跟正常 cell 行
_TABLE_ROW_RE = re.compile(r"^\s*\|.*\|\s*$", re.MULTILINE)

# 版本号字面（v0.4.6 / 0.4.3 / v1.2.3-rc1 等） — 不是自然语言 jargon 是数据
_VERSION_RE = re.compile(r"\bv?\d+\.\d+(?:\.\d+)?(?:[-+][\w.]+)?\b")

# markdown emphasis / list / heading 标记 — 不算自然语言字符
# `**bold**` / `*italic*` / `~~strike~~` / 行首 `- ` `* ` `# ` 等
_MARKDOWN_MARK_RE = re.compile(
    r"\*\*|\*|~~|^\s*[-*#>+]\s+|`",
    re.MULTILINE,
)

# v0.16.13: inline backtick 内**内容**也剥 — round-1 audit 视角 1 #6 真 FP:
# `precision` 这种 inline code 应该豁免 (docstring 说明文档 first-use example),
# 但老 _MARKDOWN_MARK_RE 只剥反引号字符不剥内容, 让 jargon scan 真 hit 'precision'.
_INLINE_BACKTICK_CONTENT_RE = re.compile(r"`[^`\n]+`")

# emoji / 装饰符号 — 不算可见自然语言字符
_EMOJI_RE = re.compile(
    r"[☀-➿\U0001F300-\U0001FAFF✅❌⚠✨⭐]"
)

# kebab-case / snake_case 项目标识符（含连字符或下划线连接的英文 token）—
# 如 `chinese-plain-no-jargon` / `force_block` / `karma-v1` / `sticky_id` —
# 这是 code identifier 不是自然语言 jargon 话术，算 ratio 时剥。
# 边界 `\b` 避免匹配 URL 内片段（已先被 _URL_RE 剥）。
_KEBAB_SNAKE_IDENT_RE = re.compile(
    r"\b[a-zA-Z][a-zA-Z0-9]*(?:[-_][a-zA-Z0-9]+)+\b"
)

# v0.4.40 dotted 标识符 — 含点号的 module.attr / file.ext / state.model 等
# 工程标识符（不是自然语言 jargon），算 ratio 时剥。
# 例：`pre_tool_use.py` / `state.model` / `tool_input.model` / `pinrule.hooks` /
# `extract_model_from_transcript()` （函数调用形式）
_DOTTED_IDENT_RE = re.compile(
    r"\b[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)+(?:\(\))?\b"
)

# v0.4.40 路径字面 — `/path/to/file` `~/.claude/...` 等绝对路径不算自然语言
# v0.10.5 (Agent 1 F1.5 fix): 显式 ASCII 字符集. 原来 `\w` 默认 Unicode-aware
# 会吃中文路径段 (例 `/桌面/某目录/文件.py` 整段被剥), 让 chinese-plain ratio
# 计算少算汉字 → 假阳更易触发. 改成 [a-zA-Z0-9./\-_] 显式只匹配 ASCII 路径字符.
_PATH_LITERAL_RE = re.compile(
    r"(?:~|/)[a-zA-Z0-9./\-_]{4,}"
)

# v0.4.40 commit message 引号块剥 — Agent 写「我写的 commit message 是
# `git commit -m \"feat(...)...\"`」时引号内 commit message 通常 conventional
# commit 全英文（feat / fix / chore / docs），算 Agent 自然语言中英比是不公正的
_COMMIT_MSG_RE = re.compile(
    r"(?:git\s+commit\s+-m|gh\s+release\s+create[^\n]*?--(?:title|notes))\s+[\"']([^\"']+)[\"']"
)

# 常见 jargon 术语 — 软件开发场景的英文技术词（用户偏好直白中文时拦）
# 边界要求避免 e.g. `recall` 误匹配 `recalls` / `dispatch` 误匹配 `dispatcher`
# 包括：ML 词 + 通用编程词（并发 / 设计模式 / 异步 / 分布式）
_JARGON_RE = re.compile(
    r"\b("
    # ML / 数据
    r"F1|F1\s*score|precision|recall|oracle|supervisor|heuristic|paradigm|"
    r"retrieval|inference|threshold|baseline|ground\s*truth|embedding|"
    r"transformer|tokenizer|softmax|gradient|epoch|hyperparameter|"
    # 通用编程：并发 / 同步
    r"mutex|semaphore|coroutine|"
    # 设计模式 / 架构
    r"orchestrator|orchestration|dispatcher|observer|subscriber|publisher|"
    r"scheduler|executor|coordinator"
    r")\b",
    re.IGNORECASE,
)

# 中文占比下限（自然语言部分）
_MIN_CHINESE_RATIO = 0.40
# 触发 ratio check 的最小英文词数（避免短句误判）
_MIN_ENGLISH_WORDS_FOR_RATIO = 8
# 术语后多少字符内需要中文跟随才算「解释了」
_JARGON_CONTEXT_RADIUS = 30
_MIN_CHINESE_AFTER_JARGON = 2
# 术语后括号闭合的最大距离 — 太远的括号不当解释看（避免远距离误命中）
_JARGON_PAREN_MAX_DIST = 30


def check(*, response: str = "", rule_id: str = "", **_):
    if not response or not response.strip():
        return None

    natural = strip_code_blocks(response)
    if not natural.strip():
        return None  # 全是代码 - 不算 jargon 对话

    # v0.16.13: 起手剥 inline backtick 内容 — `precision` / `recall` 这种
    # markdown inline code 不该当自然话术算 jargon (round-1 audit 视角 1 #6
    # 真 FP). 影响 jargon scan + ratio 算都. strip_code_blocks 只剥 ``` block,
    # inline 单 backtick 这里补.
    natural = _INLINE_BACKTICK_CONTENT_RE.sub(" ", natural)

    # 先剥**结构性内容**（不是自然语言 jargon 话术）算 ratio：
    # - URL / email / markdown 表格行（v0.4.3 加）
    # - 版本号字面（v0.4.6 / 0.4.3 等）+ markdown emphasis / list / heading 标记
    #   + emoji 装饰（v0.4.9 dogfooding 实测 5 次累积假阳：技术报告 response 含
    #   大量版本号 + markdown ** * - + emoji ✅⚠️ 标记把中文占比拉到 34-39%）
    natural_for_ratio = _URL_RE.sub("", natural)
    natural_for_ratio = _TABLE_ROW_RE.sub("", natural_for_ratio)
    natural_for_ratio = _VERSION_RE.sub("", natural_for_ratio)
    # v0.16.13: 先剥 inline backtick 内容再剥单 backtick 字符 (顺序重要 — 后剥
    # 会让 _MARKDOWN_MARK_RE 删反引号但留内容 'precision' 被 jargon scan 误算)
    natural_for_ratio = _INLINE_BACKTICK_CONTENT_RE.sub("", natural_for_ratio)
    natural_for_ratio = _MARKDOWN_MARK_RE.sub("", natural_for_ratio)
    natural_for_ratio = _EMOJI_RE.sub("", natural_for_ratio)
    natural_for_ratio = _KEBAB_SNAKE_IDENT_RE.sub("", natural_for_ratio)
    # v0.4.40 真精化：算 ratio 时剥工程标识符 / 路径 / commit message 引号块
    # 这些是工程上下文不是 Agent 自然语言，算英文比不公正（不放松 40% 阈值
    # 而是让分母反映 Agent 自然表达）
    natural_for_ratio = _COMMIT_MSG_RE.sub("", natural_for_ratio)
    natural_for_ratio = _DOTTED_IDENT_RE.sub("", natural_for_ratio)
    natural_for_ratio = _PATH_LITERAL_RE.sub("", natural_for_ratio)

    # === Check 1: 自然语言中文占比 ===
    total = total_visible_char_count(natural_for_ratio)
    chinese = chinese_char_count(natural_for_ratio)
    english_words = len(re.findall(r"\b[a-zA-Z][a-zA-Z\-]{2,}\b", natural_for_ratio))
    if total > 50 and english_words >= _MIN_ENGLISH_WORDS_FOR_RATIO:
        ratio = chinese / max(total, 1)
        if ratio < _MIN_CHINESE_RATIO:
            return CheckHit(
                rule_id=rule_id or _STICKY_ID,
                trigger=tr("check.chinese_plain.ratio.trigger", ratio=f"{ratio*100:.0f}", min=f"{_MIN_CHINESE_RATIO*100:.0f}"),
                trigger_key="check.chinese_plain.ratio.trigger",
                snippet=natural_for_ratio[:150],
                suggested_fix=tr("check.chinese_plain.ratio.fix"),
            )

    # === Check 2: 术语命中且后续无「括号内中文解释」 ===
    # v0.4.15：jargon 扫描用 natural_for_ratio（已剥表格 / URL / 版本号 / kebab-snake）
    # 让单个 jargon 项目术语引用豁免。
    # v0.4.22：v0.4.15 过宽 — 表格 cell 里堆 ≥ 3 个 jargon 是真话术不是引用。
    # 触发：`| A | 用 retrieval 加 reranker 做精排比 baseline 强 |` 全英文 jargon
    # 堆叠应该拦。如果**原文** natural 含 ≥ 3 个 jargon 词，用 natural 扫（不剥表格）；
    # 单 / 双 jargon 词的「项目术语引用」场景用 natural_for_ratio 扫（剥表格）。
    jargon_count_in_natural = len(_JARGON_RE.findall(natural))
    jargon_scan_text = natural if jargon_count_in_natural >= 3 else natural_for_ratio
    for m in _JARGON_RE.finditer(jargon_scan_text):
        # 豁免：jargon 在括号 / 列表里（用户已用括号或列表举例 = 描述 jargon 不是用 jargon）
        # 检测：术语前 N 字内有 ( / （ 开括号 + 当前位置不在闭括号之后
        before = jargon_scan_text[max(0, m.start() - 40): m.start()]
        open_paren = max(before.rfind("("), before.rfind("（"))
        close_paren = max(before.rfind(")"), before.rfind("）"))
        if open_paren > close_paren and open_paren >= 0:
            # 当前 jargon 在某个括号里 — 检查括号是不是开放（未闭合）
            after_text = jargon_scan_text[m.end():]
            if ")" in after_text[:60] or "）" in after_text[:60]:
                # 括号在 60 字内闭合 → jargon 在「括号说明」里 → 豁免
                continue

        after_window = jargon_scan_text[m.end(): m.end() + 12]  # 紧邻 12 字内
        has_paren_explanation = False
        for bracket_open, bracket_close in [("(", ")"), ("（", "）")]:
            if bracket_open in after_window:
                # 找最近的括号闭合
                bo = after_window.find(bracket_open)
                bc_in_full = jargon_scan_text.find(bracket_close, m.end() + bo)
                if 0 < bc_in_full - (m.end() + bo) < _JARGON_PAREN_MAX_DIST:
                    paren_content = jargon_scan_text[m.end() + bo + 1: bc_in_full]
                    if chinese_char_count(paren_content) >= 2:
                        has_paren_explanation = True
                        break
        if has_paren_explanation:
            continue
        # 没括号解释 → 算违反
        return CheckHit(
            rule_id=rule_id or _STICKY_ID,
            trigger=tr("check.chinese_plain.jargon.trigger", term=m.group()),
            trigger_key="check.chinese_plain.jargon.trigger",
            snippet=jargon_scan_text[max(0, m.start() - 20): m.end() + _JARGON_CONTEXT_RADIUS],
            suggested_fix=tr("check.chinese_plain.jargon.fix", term=m.group()),
        )

    return None
