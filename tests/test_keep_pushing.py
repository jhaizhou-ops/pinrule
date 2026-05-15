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
    hit = _check("这阶段任务完成。告一段落，等数据再迭代。")
    assert hit is not None


def test_silent_stop_with_push_signal_exempted():
    """末尾有「下次」字眼但同时有推进信号 → 不命中。"""
    hit = _check("commit 推了。我现在开始改下一个文件，下次跑测试前确认 X。")
    assert hit is None


# ---- 用户反馈核心：无问句无推进的纯陈述 = 停下 ----

def test_pure_statement_no_push_no_question_blocked():
    """纯陈述完结无推进无问号 → 命中（用户反馈核心场景）。

    注：成功汇报（数字 + 通过词）有专门豁免（跟 sticky #4 鼓励的「完成要有
    证据」一致），所以这里用「目前情况如此」类纯文字陈述，没数字证据。
    """
    # v0.4.22：「就这样了」加入 _STOP_HINT_RE 后会被更精准识别为停顿语气而非
    # 「纯陈述无推进」。两种 trigger 都算成功识别停下。
    hit = _check("commit ffcbd07 已推 origin/main。目前情况看起来差不多。")
    assert hit is not None
    assert "纯陈述" in hit.trigger or "无推进" in hit.trigger


def test_success_report_with_numbers_exempted():
    """成功汇报（数字 + 通过词）→ 豁免。这是 sticky #4 鼓励的行为不该被罚。
    评审 B Agent 发现：'测试 100/100 通过' 类汇报被错拦是痛点。
    """
    hit = _check("commit 已推。测试 232/232 通过。")
    assert hit is None


def test_success_report_passed_count_exempted():
    """'N passed' 风格成功汇报也豁免。"""
    hit = _check("All good. 232 passed.")
    assert hit is None


def test_pure_statement_with_next_step_exempted():
    """陈述 + 下一步计划 → 豁免。"""
    hit = _check("commit 已推。我接下来去做 Y。")
    assert hit is None


# ---- edge cases ----

def test_single_char_response_blocked():
    """极短回复无任何信号 → 命中（用户反馈：陈述完结无下一步 = 停下）。"""
    hit = _check("✓")
    assert hit is not None


def test_response_with_markdown_codeblock_blocked():
    """末尾 markdown 代码块结束，无推进 → 命中。"""
    hit = _check("做完了。\n```python\nprint('hi')\n```")
    assert hit is not None


def test_response_with_tail_period_only_blocked():
    """末尾就是「。」陈述结束 → 命中。"""
    hit = _check("commit 已推到远程。")
    assert hit is not None


def test_response_with_xianzheli_in_quote_still_blocked():
    """引号里的「先到这」也命中（不能引号绕开 — 整体语气还是停下）。"""
    hit = _check("用户说要「先到这」休息。")
    assert hit is not None


def test_response_with_action_then_summary_passes():
    """先汇报再下一步推进 → 豁免（标准格式）。"""
    hit = _check("测试 203 通过。我现在去做 X 推进。")
    assert hit is None


def test_success_report_chinese_quanguo_exempted():
    """「N 测试全过」语序也算成功汇报豁免。

    dogfooding 实测假阳：「316 测试全过，Release 链接：...」末尾被错拦。
    `\\d+ 测试 全过` 跟 `\\d+ 测试 通过` 等价是真成功汇报应豁免。
    """
    assert _check("316 测试全过，Release 链接：https://example.com") is None
    assert _check("一波改完了，测试 316 全过。下个推进点想好了。") is None


def test_future_plan_xia_ci_jie_shou_exempted():
    """v0.4.19 第 3 类假阳治理：「下次接手做 X」「下个 session 推进 X」类
    未来推进规划 → 有下一步计划应豁免（不是「就此停下」）。

    dogfooding 实测：本回合末尾我多次写「下次接手做 non-blocking 治理」
    被错算停下，但是规划下一步推进延续。
    """
    cases = [
        "本回合饱和收口。下次接手做 non-blocking 假阳治理。",
        "做完了。下个 session 接手 keep-pushing 第 3 类。",
        "fix 完了。候选清单：1. X 2. Y 3. Z。",
        "v0.4.18 发布。接手做 audit timeline。",
    ]
    for c in cases:
        assert _check(c) is None, f"未来推进规划不该被算停下: {c!r}"


def test_explicit_user_handoff_exempted():
    """v0.4.19：「请决定 / 请授权 / 等你 X」是 sticky #7「显式让用户介入」
    合法 stop 路径，应豁免（区别于 sticky #8 禁止的「停下问反馈等用户随便决定」）。

    dogfooding：本回合请求清历史授权 → 按 sticky #7 是合法做法，但被 keep-
    pushing 算停下。
    """
    cases = [
        "我会跑 karma violations clear。授权后才执行。请决定。",
        "改完了。等你确认。",
        "做了 A 跟 B。请授权。",
    ]
    for c in cases:
        assert _check(c) is None, f"显式让用户介入合法 stop 应豁免: {c!r}"


def test_v422_soft_stop_hints_blocked():
    """v0.4.22：v0.4.19/20 漏拦的柔性停顿语气 — 「OK 就这样了」/「今天到此为止」
    /「就到这」/「搞不定了」类应拦。
    """
    cases = [
        "做了 A B C。OK 就这样了。",
        "改不动了。今天到此为止。",
        "改完。就这样吧。",
        "试了几次。搞不定了。算了吧。",
    ]
    for c in cases:
        hit = _check(c)
        assert hit is not None, f"柔性停顿语气应拦: {c!r}"


def test_v420_push_signal_in_middle_tail_pure_statement_exempted():
    """v0.4.20：推进信号在 response 中段，末尾是列表 / 收尾陈述 → 整段已有
    推进意图应豁免。

    dogfooding 触发：「下次接手做 HANDOFF 候选...（chinese-plain / long-term
    / audit）」 — 「下次接手做」在中段，列表「(X / Y / Z)」在末尾，tail 80
    字看不到推进信号被错算无推进。
    """
    # 推进信号在中段，末尾纯陈述无推进
    case = "本回合做了 6 件。下次接手做 A 治理 + B 推进 + C 修复。" + \
        "中段细节填充内容很长。" * 8 + "\n\n最终交付清单已完整。"
    assert _check(case) is None, "整段已有推进规划但末尾是收尾陈述应豁免"


def test_v420_push_in_middle_tail_stop_hint_still_caught():
    """v0.4.20 对偶守护：整 response 有推进 + 末尾窗口含明确停顿语气 → 仍命中
    （停顿优先于「整段有推进」豁免，否则推进 + 停顿同时存在该按停顿算）。
    """
    case = "做了 A 跟 B。下次接手做 C 推进规划很完整。" + \
        "中段细节内容填充很长。" * 8 + "\n\n但今天不做了。先到这。"
    hit = _check(case)
    assert hit is not None, "整段有推进 + 末尾停顿语气仍应拦"
    assert "先到这" in hit.trigger or "停顿" in hit.trigger


def test_v419_real_stop_still_caught():
    """对偶守护：v0.4.19 豁免不影响停顿语气拦截。"""
    cases = [
        ("commit 已推。下次再说吧。", "下次再说"),
        ("改完了。先到这。", "先到这"),
        ("OK 了。告一段落。", "告一段落"),
        ("好的。下次见。", "下次见"),
    ]
    for cmd, expected_word in cases:
        hit = _check(cmd)
        assert hit is not None, f"停顿语气仍应拦: {cmd!r}"
        assert expected_word in hit.trigger, f"trigger 应识别 {expected_word!r}: {hit.trigger}"


def test_push_signal_woqu_kan_exempted():
    """「我去看 / 我去查 / 我要去做 X」简单近 future 动作 → 豁免推进。

    dogfooding 实测：「我去看 karma check 能不能加一条...」被错拦
    （`_PUSH_SIGNAL_RE` 漏「我去 + 看/查」类动词组合）。
    """
    assert _check("commit 推完。我去看 karma stats 累积违反。") is None
    assert _check("做好了。我去查下个推进点。") is None
    assert _check("OK。接下来去看 force_block 累计。") is None


def test_v0441_user_stop_hint_exempts_keep_pushing():
    """v0.4.41 原因 fix：user 上 turn 含明确叫停字眼 → 整 turn 豁免反思 hook
    （HANDOFF v3 第三步候选实际落地，今晚多次 dogfooding 触发）。
    """
    fn = REGISTRY["keep_pushing_no_stop"]
    bare_stop = "好了，这一波我处理好了。"  # 纯陈述无数字证据无问号无停顿词 → 默认命中
    # 基线：无 user_prompt 时纯陈述完结仍命中
    assert fn(response=bare_stop) is not None, "无 user_prompt 时纯陈述完结仍命中"

    # 用户上 turn 含叫停字眼 → 豁免
    stop_hints = [
        "不用啦感谢，休息吧",
        "好了好了你走火入魔了",
        "明天再说吧",
        "先到这吧",
        "算了不用了",
        "晚安",
        "够了",
    ]
    for hint in stop_hints:
        result = fn(response=bare_stop, user_prompt=hint)
        assert result is None, f"用户叫停 {hint!r} 应豁免反思 hook: {result}"


def test_v0441_user_normal_prompt_no_exempt():
    """v0.4.41 对偶：user 上 turn 没叫停字眼 → 反思 hook 仍触发不该过宽。"""
    fn = REGISTRY["keep_pushing_no_stop"]
    bare_stop = "好了，这一波我处理好了。"  # 纯陈述无数字证据无问号无停顿词 → 默认命中
    normal_prompts = [
        "继续推下个候选",
        "你还能优化什么",
        "看看 audit 数据",
    ]
    for p in normal_prompts:
        result = fn(response=bare_stop, user_prompt=p)
        assert result is not None, f"正常 prompt {p!r} 不该豁免: 应仍命中"


def test_v056_next_push_point_phrasing_exempted():
    """v0.5.6: 「下一推进点 / 下一步是 / 接下来打算 / 下一波」类未来规划短语豁免.

    dogfooding 触发: 今晚 7 次错拦本是合法推进规划. _PUSH_SIGNAL_RE 漏覆盖
    这类未来规划表达 (跟 v0.4.19 根因相同). 同 sticky #7 合法推进意图.
    """
    fn = REGISTRY["keep_pushing_no_stop"]
    push_phrases = [
        "测试通过。下一推进点：dogfooding skill 工作流.",
        "测试通过。下一步是 testset.py 加 python -c 豁免.",
        "做完了。接下来打算 fix keep_pushing 漏覆盖根因.",
        "完成。下一波推进：trigger key i18n 收尾.",
        "做完了。后续推进 v0.5.6 release.",
        "测试通过。下一个推进点：检查 audit 数据.",
    ]
    for phrase in push_phrases:
        result = fn(response=phrase)
        assert result is None, f"未来推进规划短语 {phrase!r} 应豁免, 拦: {result}"


def test_v056_partial_stop_still_blocked():
    """v0.5.6 对偶: 停下不能因为加入「下一」字眼就豁免."""
    fn = REGISTRY["keep_pushing_no_stop"]
    # 「下一次再说吧」是推卸不是推进 — 不该豁免
    fake_push = "做完了。下一次再说吧。"
    result = fn(response=fake_push)
    assert result is not None, "推卸语气不该被错算推进规划豁免"


def test_v0519_agent_saturation_declaration_exempted():
    """v0.5.19: Agent 自己声明任务饱和 → 豁免反思 hook.

    sticky #8 例外条件 ②「任务饱和明说卡在哪」— 跟 v0.4.41 用户叫停豁免对偶.
    关键: 强饱和信号字眼 (饱和/卡点/明天接力) 才豁免, 不跟 v0.4.22 柔性停顿
    (今天到此为止/就这样吧) 重叠.
    """
    fn = REGISTRY["keep_pushing_no_stop"]
    saturation_phrases = [
        "今天 16 个 release 一波完了 任务饱和, 明天接力。",
        "卡在 v0.6.0 实际施这步 — 大变更不该一天 ship 完，明天再继续做 fix。",
        "本 session 饱和。等下次。",
        "审计跑完, 任务饱和, 卡在「需要用户拍方向」让你知道。",
        "我饱和了, 下次接力。",
    ]
    for phrase in saturation_phrases:
        result = fn(response=phrase)
        assert result is None, f"Agent 强饱和声明 {phrase!r} 应豁免, 拦: {result}"


def test_v0519_agent_soft_stop_without_saturation_still_blocked():
    """v0.5.19 对偶: 无强饱和信号的柔性停顿仍拦 (跟 v0.4.22 设计一致).

    确认 v0.5.19 没破 v0.4.22 — 「今天到此为止」「就这样吧」类偷懒收工仍拦.
    """
    fn = REGISTRY["keep_pushing_no_stop"]
    soft_stops = [
        "做了 A B C。OK 就这样了。",
        "改不动了。今天到此为止。",
        "改完。就这样吧。",
        "做完了，下次再说吧。",
    ]
    for phrase in soft_stops:
        result = fn(response=phrase)
        assert result is not None, f"无饱和信号的柔性停顿仍应拦: {phrase!r}"
