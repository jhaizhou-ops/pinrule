"""Lockdown for v0.16.13 check FP fixes — ground-truth test fixtures.

Per sticky #5 (no-testset-no-future-leakage): each fix gets a positive case
(should-hit) + negative case (should-not-hit). Regex tweaks must keep both
columns passing — protects against future "fix one direction, break the other"
regression.

Audit round-1 viewpoint 1 originally reported 4 FPs that v0.16.13 fixed:
- long_term.py #3: negation context (不要/Don't 前置)
- long_term.py #4: markdown code block (反例引用)
- chinese_plain.py #6: inline backtick (`precision`)
- chinese_plain.py #8: full-width punctuation in CJK char count
"""
from __future__ import annotations

from pinrule.checks.chinese_plain import check as cp_check
from pinrule.checks.common import chinese_char_count
from pinrule.checks.long_term import check as lt_check


# ---- long_term.py: negation context (FIX #2, round-1 #3) ----

def test_long_term_negation_chinese_prefix_exempts() -> None:
    """中文否定词前置 30 字内 → 反 advice, 真豁免."""
    txt = "不要我先打补丁让 CI 过, 该挖根因."
    assert lt_check(response=txt) is None


def test_long_term_negation_english_prefix_exempts() -> None:
    """英文否定词前置 → 反 advice, 真豁免."""
    txt = "Don't let me hardcode this value. We need a proper fix."
    assert lt_check(response=txt) is None


def test_long_term_real_patch_intent_still_hits() -> None:
    """真短期意图 (无否定词) → 仍 hit."""
    txt = "我先打补丁让 CI 过, 之后再说."
    assert lt_check(response=txt) is not None


# ---- long_term.py: markdown code block (FIX #3, round-1 #4) ----

def test_long_term_markdown_fenced_code_block_exempts() -> None:
    """``` fenced block 内 patch-intent 字面 → 反例引用, 真豁免."""
    txt = "反例:\n```\n我先打补丁\n```\n这是反 advice."
    assert lt_check(response=txt) is None


def test_long_term_inline_backtick_quote_exempts() -> None:
    """inline `backtick` 内 patch-intent → 反例引用, 真豁免."""
    txt = "引用反例: `我先硬编码` 这是错误示范."
    assert lt_check(response=txt) is None


def test_long_term_plain_text_intent_still_hits() -> None:
    """无 markdown 包装 + 真意图 → 仍 hit."""
    txt = "Let me hardcode this case for now, will fix later."
    assert lt_check(response=txt) is not None


# ---- chinese_plain.py: inline backtick (FIX #4, round-1 #6) ----

def test_chinese_plain_inline_backtick_jargon_exempts() -> None:
    """中文用户引用 inline `precision` `recall` → 已标记 code, 不算 jargon."""
    txt = (
        "本次实验跑下来, 模型在 `precision` 这项指标表现不错, "
        "`recall` 也很高, `F1` 综合得分到 0.85, 不同 setup 都稳定."
    )
    assert cp_check(response=txt) is None


def test_chinese_plain_raw_jargon_still_hits() -> None:
    """中文用户裸 jargon 无 backtick → 仍 hit."""
    txt = (
        "本次实验跑下来, 模型在 precision 这项指标表现不错, "
        "recall 也很高, F1 综合得分到 0.85, 不同 setup 都稳定."
    )
    assert cp_check(response=txt) is not None


# ---- chinese_plain.py: full-width punctuation (FIX #5, round-1 #8) ----

def test_chinese_char_count_includes_full_width_punctuation() -> None:
    """全角标点 (，。、) 真算中文字符 — 之前 U+FF00 范围漏算让中文带标点 ratio 假低."""
    assert chinese_char_count("中文带标点。") >= 6  # 5 汉字 + 1 句号
    assert chinese_char_count("中文，逗号、顿号。") >= 9  # 7 汉字 + 3 标点


def test_chinese_char_count_excludes_ascii() -> None:
    """ASCII 不算中文."""
    assert chinese_char_count("English only.") == 0
    assert chinese_char_count("Hello world") == 0


def test_chinese_char_count_includes_cjk_symbols() -> None:
    """CJK 书名号 / 引号 (U+3000-U+303F) 也算."""
    assert chinese_char_count("《引用》") >= 4  # 2 书名号 + 2 汉字
