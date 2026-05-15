"""karma.signals i18n 信号加载器测试 (v0.8.0)。

确保:
1. .txt 文件按目录正确加载 (signal_name → phrases tuple)
2. 中英文 union 编译成单个 regex 正确匹配
3. 长字眼优先（避免「OK」抢在「OK 了」前面命中）
4. 注释行 + 空行跳过
5. 不同语言字符集不互相误命中
6. signal_name 不存在时返回 never-match pattern
"""

from __future__ import annotations

import re

from karma.signals import compile_alternation, load_phrases, reset_cache


def setup_function():
    """每个测试前清缓存，让 signals.py 重新读 data/signals/。"""
    reset_cache()


def test_load_phrases_user_stop_hints_has_both_languages():
    """user_stop_hints 加载应同时含中英文字眼。"""
    phrases = load_phrases("user_stop_hints")
    # 中文样本
    assert "不错不错" in phrases
    assert "休息吧" in phrases
    # 英文样本
    assert "looks good" in phrases
    assert "LGTM" in phrases


def test_compile_alternation_matches_chinese_phrases():
    """中文字眼应能匹配。"""
    pat = compile_alternation("user_stop_hints")
    assert pat.search("感觉已经挺稳定了，不错不错") is not None
    assert pat.search("休息吧明天再说") is not None
    assert pat.search("纯随机文本无叫停字眼") is None


def test_compile_alternation_matches_english_phrases():
    """英文字眼应能匹配 + IGNORECASE 不分大小写。"""
    pat = compile_alternation("user_stop_hints")
    assert pat.search("looks good, ship it") is not None
    assert pat.search("LGTM") is not None
    assert pat.search("lgtm") is not None  # 大小写不敏感
    assert pat.search("This is some random text") is None


def test_compile_alternation_long_phrase_priority():
    """长字眼优先 — 「OK 了」应整体匹配，不是「OK」抢先。"""
    pat = compile_alternation("user_stop_hints")
    m = pat.search("OK 了")
    assert m is not None
    assert m.group() == "OK 了"  # 不是只匹配 "OK"


def test_load_phrases_skips_comments_and_blank():
    """文件头 `#` 注释行 + 空行应跳过。"""
    phrases = load_phrases("user_stop_hints")
    # 确认没把注释行当 phrase 加进来
    for p in phrases:
        assert not p.startswith("#"), f"注释行不该当字眼: {p!r}"
        assert p.strip() == p, f"字眼应已 strip: {p!r}"


def test_compile_alternation_unknown_signal_never_matches():
    """signal 目录不存在 → 返回 never-match pattern (不抛错)。"""
    pat = compile_alternation("__nonexistent_signal__")
    assert pat.search("anything") is None
    assert pat.search("") is None


def test_compile_alternation_zh_phrase_not_match_en_text():
    """中英文字符集不重叠 — 中文字眼不会误命中英文文本。"""
    pat = compile_alternation("agent_saturation")
    # 中文「卡在这一步」应只匹配中文
    assert pat.search("stuck at the regex pattern") is not None  # 命中英文字眼「stuck at」
    # 但纯英文文本不该被中文字眼误中
    en_text = "Working on the task, no saturation here."
    # en_text 不含任何 saturation 字眼（既无中文也无英文）
    assert pat.search(en_text) is None


def test_load_phrases_dedupe_across_languages():
    """同字眼在多语言文件里只保留一份（去重）。"""
    # weak_claims 各自语言独立字眼，去重不会影响数量
    phrases = load_phrases("weak_claims")
    assert len(phrases) == len(set(phrases)), "phrases 应去重"


def test_compile_alternation_re_escape_works():
    """特殊 regex 字符 (如 `?` `.` `(`) 在字眼里被 escape，不当 metachar。"""
    # explicit_handoff 含「you say」类，没特殊字符；但验证机制：
    # 假设字眼里有 `?` 该当字面 `?` 不当 0/1 次量词
    pat = compile_alternation("explicit_handoff")
    # 「你说怎么」字面有特殊字符无关，正常匹配
    m = pat.search("最后你说怎么办呢")
    assert m is not None


def test_all_five_signals_loadable():
    """v0.8.0 所有 5 个信号目录都能加载（不空）。"""
    for name in (
        "user_stop_hints",
        "agent_saturation",
        "stop_hints",
        "explicit_handoff",
        "weak_claims",
    ):
        phrases = load_phrases(name)
        assert len(phrases) > 0, f"signal {name!r} 应非空"
        pat = compile_alternation(name)
        # pattern 非 never-match
        assert pat.pattern != r"(?!)"


def test_lru_cache_reused():
    """同 signal 多次调用应 lru_cache 复用 (同一 Pattern 对象)。"""
    p1 = compile_alternation("user_stop_hints")
    p2 = compile_alternation("user_stop_hints")
    assert p1 is p2


def test_reset_cache_invalidates():
    """reset_cache() 后 lru_cache 被清 (用于测试隔离)。"""
    # 触发一次加载填充 cache
    compile_alternation("user_stop_hints")
    assert compile_alternation.cache_info().currsize > 0
    reset_cache()
    # cache 清空
    assert compile_alternation.cache_info().currsize == 0


def test_regex_compile_flags_ignorecase():
    """compile 默认 IGNORECASE flag — 英文大小写不区分。"""
    pat = compile_alternation("user_stop_hints")
    assert pat.flags & re.IGNORECASE
