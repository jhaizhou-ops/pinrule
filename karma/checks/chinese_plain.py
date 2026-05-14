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

from karma.checks.common import (
    chinese_char_count,
    strip_code_blocks,
    total_visible_char_count,
)

_STICKY_ID = "chinese-plain-no-jargon"

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

    from karma.checks import CheckHit

    # === Check 1: 自然语言中文占比 ===
    total = total_visible_char_count(natural)
    chinese = chinese_char_count(natural)
    english_words = len(re.findall(r"\b[a-zA-Z][a-zA-Z\-]{2,}\b", natural))
    if total > 50 and english_words >= _MIN_ENGLISH_WORDS_FOR_RATIO:
        ratio = chinese / max(total, 1)
        if ratio < _MIN_CHINESE_RATIO:
            return CheckHit(
                sticky_id=_STICKY_ID,
                trigger=f"自然语言中文占比 {ratio*100:.0f}% < {_MIN_CHINESE_RATIO*100:.0f}%",
                snippet=natural[:150],
                suggested_fix="用直白中文回应。英文术语需要时短解释一下，不堆 jargon。",
            )

    # === Check 2: 术语命中且后续无「括号内中文解释」 ===
    # 严格判定：术语紧跟 0-12 字内出现括号 ( 或 （ + 内部含 ≥2 中文字 = 算解释
    # 仅靠后续中文连接词不算（「oracle 不行」不豁免）
    for m in _JARGON_RE.finditer(natural):
        after_window = natural[m.end(): m.end() + 12]  # 紧邻 12 字内
        has_paren_explanation = False
        for bracket_open, bracket_close in [("(", ")"), ("（", "）")]:
            if bracket_open in after_window:
                # 找最近的括号闭合
                bo = after_window.find(bracket_open)
                bc_in_full = natural.find(bracket_close, m.end() + bo)
                if 0 < bc_in_full - (m.end() + bo) < 30:
                    paren_content = natural[m.end() + bo + 1: bc_in_full]
                    if chinese_char_count(paren_content) >= 2:
                        has_paren_explanation = True
                        break
        if has_paren_explanation:
            continue
        # 没括号解释 → 算违反
        return CheckHit(
            sticky_id=_STICKY_ID,
            trigger=f"术语 {m.group()!r} 后无括号内中文解释",
            snippet=natural[max(0, m.start() - 20): m.end() + _JARGON_CONTEXT_RADIUS],
            suggested_fix=f"用了 {m.group()} 后用括号给中文解释（如 `precision (精度)`），或者直接用「精度 / 召回率」等汉字。",
        )

    return None
