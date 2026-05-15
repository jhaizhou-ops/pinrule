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

from karma.checks._types import CheckHit
from karma.checks.common import (
    chinese_char_count,
    strip_code_blocks,
    total_visible_char_count,
)

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
# 例：`pre_tool_use.py` / `state.model` / `tool_input.model` / `karma.hooks` /
# `extract_model_from_transcript()` （函数调用形式）
_DOTTED_IDENT_RE = re.compile(
    r"\b[a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)+(?:\(\))?\b"
)

# v0.4.40 路径字面 — `/path/to/file` `~/.claude/...` 等绝对路径不算自然语言
_PATH_LITERAL_RE = re.compile(
    r"(?:~|/)[\w./\-_]{4,}"
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


def check(*, response: str = "", **_):
    if not response or not response.strip():
        return None

    natural = strip_code_blocks(response)
    if not natural.strip():
        return None  # 全是代码 - 不算 jargon 对话

    # 先剥**结构性内容**（不是自然语言 jargon 话术）算 ratio：
    # - URL / email / markdown 表格行（v0.4.3 加）
    # - 版本号字面（v0.4.6 / 0.4.3 等）+ markdown emphasis / list / heading 标记
    #   + emoji 装饰（v0.4.9 dogfooding 实测 5 次累积假阳：技术报告 response 含
    #   大量版本号 + markdown ** * - + emoji ✅⚠️ 标记把中文占比拉到 34-39%）
    natural_for_ratio = _URL_RE.sub("", natural)
    natural_for_ratio = _TABLE_ROW_RE.sub("", natural_for_ratio)
    natural_for_ratio = _VERSION_RE.sub("", natural_for_ratio)
    natural_for_ratio = _MARKDOWN_MARK_RE.sub("", natural_for_ratio)
    natural_for_ratio = _EMOJI_RE.sub("", natural_for_ratio)
    natural_for_ratio = _KEBAB_SNAKE_IDENT_RE.sub("", natural_for_ratio)
    # v0.4.40 真精化：算 ratio 时剥工程标识符 / 路径 / commit message 引号块
    # 这些是工程上下文不是 Agent 自然语言，算英文比不公正（不放松 40% 阈值
    # 而是让分母真反映 Agent 自然表达）
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
                sticky_id=_STICKY_ID,
                trigger=f"自然语言中文占比 {ratio*100:.0f}% < {_MIN_CHINESE_RATIO*100:.0f}%",
                snippet=natural_for_ratio[:150],
                suggested_fix="本段读起来用户可能要停下查几次「这词什么意思」。看看哪些英文是"
                              "「项目名 / 论文术语」（这种保留 + 首现加中文解释），哪些是"
                              "「随手用了英文」（换成精度 / 召回率 / 分发器 等汉字）。"
                              "目标不是中文凑比例，是让用户读完不用查词。",
            )

    # === Check 2: 术语命中且后续无「括号内中文解释」 ===
    # v0.4.15：jargon 扫描用 natural_for_ratio（已剥表格 / URL / 版本号 / kebab-snake）
    # 让单个 jargon 项目术语引用豁免。
    # v0.4.22：v0.4.15 过宽 — 表格 cell 里堆 ≥ 3 个 jargon 是真话术不是引用。
    # 真触发：`| A | 用 retrieval 加 reranker 做精排比 baseline 强 |` 全英文 jargon
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
                if 0 < bc_in_full - (m.end() + bo) < 30:
                    paren_content = jargon_scan_text[m.end() + bo + 1: bc_in_full]
                    if chinese_char_count(paren_content) >= 2:
                        has_paren_explanation = True
                        break
        if has_paren_explanation:
            continue
        # 没括号解释 → 算违反
        return CheckHit(
            sticky_id=_STICKY_ID,
            trigger=f"术语 {m.group()!r} 后无括号内中文解释",
            snippet=jargon_scan_text[max(0, m.start() - 20): m.end() + _JARGON_CONTEXT_RADIUS],
            suggested_fix=f"「{m.group()}」用户可能要停下想「这是什么」。如果是项目名 / 论文术语 / "
                          f"标准接口名（必须保留），首次出现配中文短解释（如 "
                          f"`precision (精度)`）让他能跟上；如果只是随手英文，直接换"
                          f"「精度 / 召回率」等汉字会让他读起来更顺。",
        )

    # === Check 3: 同前缀重复防御性自证（v0.4.40 治理「真字狂魔」副作用）===
    # 真触发：sticky #4「证据」+ sticky #1「最根本」叠加效应让 LLM 防御性堆
    # 「真X / 真X / 真X」前缀证明「不糊弄」（如「真根因 / 真生效 / 真完成
    # / 真效果 / 真证据」）— Agent 表达扭曲，HANDOFF 第 7 类矛盾根因。
    # 不改 sticky 文案（用户最高优先级方向），加 reactive 自审 check 提醒
    # Agent 减弱前缀堆叠习惯（治症状不治根因，但能减弱视觉别扭程度）。
    repeated_hit = _check_repeated_prefix(natural)
    if repeated_hit:
        return repeated_hit

    return None


# v0.4.40 同前缀重复检测真实施
_PREFIX_REPEAT_THRESHOLD = 5  # 同前缀字 ≥ N 次/response 触发自审


def _check_repeated_prefix(text: str):
    """扫 response 找单字前缀重复（如「真X 真X 真X」≥ 5 次）。

    实施：扫所有「单字 + 中文/英文 token」组合，按前缀字统计 count。
    某前缀 count ≥ _PREFIX_REPEAT_THRESHOLD → 触发自审。
    """
    # 找模式：单中文字 + 跟着 1-4 个中英文字符（如「真根因 / 真生效 / 真完成」）
    matches = re.findall(r"([一-鿿])(?=[一-鿿a-zA-Z])", text)
    if not matches:
        return None
    from collections import Counter
    prefix_counts = Counter(matches)
    for prefix, count in prefix_counts.most_common(3):
        if count >= _PREFIX_REPEAT_THRESHOLD:
            # 排除真合理高频前缀（不算防御性堆叠）
            if prefix in ("一", "不", "是", "有", "没", "我", "你", "他", "这", "那", "在"):
                continue
            return CheckHit(
                sticky_id=_STICKY_ID,
                trigger=f"前缀字 {prefix!r} 重复 {count} 次（疑似防御性堆叠）",
                snippet=f"「{prefix}」字在本 response 出现 {count} 次开头位置",
                suggested_fix=(
                    f"「{prefix}X」前缀重复堆叠让表达显得在自证而非自然 — 用户读起来"
                    f"觉得你紧张。sticky #4「证据」要的是数据 / 测试通过 / 截图 / "
                    f"复现脚本，不是前缀强调词。下次试试去掉前缀让句子更直接。"
                ),
            )
    return None
