"""keep_pushing_no_stop check 测试 — 末尾问句无推进信号 = 疑似停下等用户。"""

from __future__ import annotations

from karma.checks import REGISTRY


def _check(response: str):
    return REGISTRY["keep_pushing_no_stop"](response=response)


def test_question_at_tail_exempted():
    """末尾问句 → 豁免（用户反馈：合理询问决策应鼓励，不该拦）。"""
    hit = _check("做完了。要不要继续做下一步？")
    assert hit is None


def test_push_signal_exempted():
    """末尾含推进信号 → 豁免（有下一步计划）。"""
    hit = _check("做完了。我现在开始做下一步。")
    assert hit is None


def test_chinese_question_mark_also_exempted():
    """中文 ？ 也算询问豁免。"""
    hit = _check("两个方向都可以，您想要哪个？")
    assert hit is None


def test_question_in_middle_chenshu_at_tail_blocked():
    """问号在中段（超 80 字窗口外）但末尾纯陈述无推进 → 命中。"""
    # 让问号在末尾窗口外（前部填长内容）
    long_intro = "之前讨论过一个问题：是否做 X？答案是要的。" + "中段内容 " * 30
    response = long_intro + "测试通过。"  # 末尾「测试通过」无推进无问号
    hit = _check(response)
    assert hit is not None


def test_empty_response_passes():
    assert _check("") is None
    assert _check("   ") is None


def test_long_response_short_tail_window():
    """末尾窗口只看最后 80 字。"""
    middle_q = "前面讨论问题：要 X 吗？" + " 后面 " * 50 + "我马上开始做实施。"
    hit = _check(middle_q)
    assert hit is None  # 末尾「我马上开始做实施。」是推进信号


# ---- 停顿语气词（明确暂停） ----

def test_silent_stop_with_next_time_phrase_blocked():
    """末尾「下次跑 X 看」— 沉默式停下，命中。"""
    hit = _check("M3 完成了，commit 推完了。下次跑 audit 看新出现什么。")
    assert hit is not None


def test_silent_stop_xianzheli_blocked():
    """末尾「先到这」— 命中。"""
    hit = _check("一波改完了，测试 187 全过。先到这。")
    assert hit is not None


def test_silent_stop_gaoyiduanluo_blocked():
    """末尾「告一段落」— 命中。"""
    hit = _check("这阶段任务完成。告一段落，等真实数据再迭代。")
    assert hit is not None


def test_silent_stop_with_push_signal_exempted():
    """末尾有「下次」字眼但同时有推进信号 → 不命中。"""
    hit = _check("commit 推了。我现在开始改下一个文件，下次跑测试前确认 X。")
    assert hit is None


# ---- 用户反馈核心：无问句无推进的纯陈述 = 真停下 ----

def test_pure_statement_no_push_no_question_blocked():
    """纯陈述完结无推进无问号 → 命中（用户反馈核心场景）。"""
    hit = _check("commit ffcbd07 已推 origin/main。测试 187/187 通过。")
    assert hit is not None
    assert "纯陈述" in hit.trigger or "无推进" in hit.trigger


def test_pure_statement_with_next_step_exempted():
    """陈述 + 下一步计划 → 豁免。"""
    hit = _check("commit 已推。我接下来去做 Y。")
    assert hit is None
