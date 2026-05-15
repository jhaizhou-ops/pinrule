"""#7 keep-pushing-no-stop — 不主动停下问用户。

用户精准定位（2026-05-14）：
- **没有疑问句的停止**才是要监控的 — 陈述完结无下一步 = 停下
- 只是陈述而且有下一步计划 → 应鼓励 Agent 继续
- 问号 → 合理询问决策，**豁免**（不该拦询问 ≠ 不该拦停止）

检测设计（post_response / Stop hook 扫 Agent response）：
1. 末尾 80 字含「推进信号」（我现在/立刻/马上 + 动词 等）→ 豁免（有下一步计划）
2. 末尾 80 字含问号（? 或 ？）→ 豁免（合理询问用户决策）
3. 末尾 80 字含「停顿语气词」（下次/先到这/告一段落）→ 命中（明确表达暂停）
4. **既无推进 + 无问号 + 无停顿词 = 默认命中**（纯陈述完结无下一步 = 停下）

豁免顺序：推进 > 问号 > 停顿词检测 > 默认命中
"""

from __future__ import annotations

import re

from karma.checks._types import CheckHit
from karma.i18n import tr
from karma.signals import compile_alternation

_STICKY_ID = "keep-pushing-no-stop"

# 末尾问号（中英文）— 限定 response 最后 80 字（多数「停下问」signal 在末尾）
_TAIL_QUESTION_RE = re.compile(r"[?？]")

# 成功汇报（数字证据 + 通过词）— 这是 sticky #4「loud-failure-with-evidence」
# 鼓励的行为，不该被 #7 keep-pushing 处罚为「停下」。
# 命中如「100/100 通过」「测试 232 passed」「全部跑过」等汇报句。
_SUCCESS_REPORT_RE = re.compile(
    r"\d+\s*[/／]\s*\d+\s*(?:通过|passed|pass|绿|过)"            # 232/232 通过
    r"|\d+\s*(?:passed|tests?\s+passed)"                          # 232 passed
    r"|\d+\s*(?:测试|个测试|项测试|tests?)\s*(?:全|all)?\s*"
    r"(?:通过|过|绿|passed|pass)"                                  # 316 测试全过
    r"|(?:测试|tests?)\s*\d+\s*(?:全|all)?\s*"
    r"(?:通过|过|绿|passed|pass)",                                 # 测试 316 全过
    re.IGNORECASE,
)

# v0.8.0: 字眼从 data/signals/stop_hints/{zh,en}.txt 加载（多语言 union）
# 历史: v0.4.19 设计「下次」字面收紧 — 「下次再来 / 下次见」是停，
# 「下次接手做 X」是规划（_PUSH_SIGNAL_RE 识别）。
# v0.4.22 加柔性停顿（今天到此 / 改不动了）。
# v0.8.0 外部化 + 加英文 → 英文用户对偶覆盖。
_STOP_HINT_RE = compile_alternation("stop_hints")

# v0.8.0: 字眼从 data/signals/explicit_handoff/{zh,en}.txt 加载
# 历史: v0.4.19 设计 — sticky #7「显式让用户介入」是合法 stop 路径
# 应豁免，跟「沉默式停下问下一步」区分。
_EXPLICIT_USER_HANDOFF_RE = compile_alternation("explicit_handoff")

# v0.8.1: 字眼从 data/signals/push_signals/{zh,en}.yaml 加载
# 历史: v0.4.19 设计三类「未来推进规划」识别。v0.4.22 加「下次 X 吧」尾字过滤。
# v0.5.6 加「下一推进点 / 下一步是」类。
# v0.8.1 把 cartesian 字眼搬到 yaml — `{subject} {verb}` 用 templates 展开，
# 不需 cartesian 的整句平面字眼用 phrases。yaml schema 支持英文用户一并加。
_PUSH_SIGNAL_RE = compile_alternation("push_signals")

# v0.4.22 dogfood 实证：「下次接手吧 / 下次推进行不」是推卸不是推进。
# 历史 regex 用 lookahead `(?!\s*[吧行])` 排除，v0.8.1 把这逻辑下沉到 check()
# 后处理（让 yaml 字眼保持简洁，不承载 lookahead 复杂度）。
_PUSHBACK_TAIL_RE = re.compile(r"^\s*(?:吧|行不|算了)")

# 末尾扫描窗口（字符数）— 80 字平衡覆盖跟假阳
_TAIL_WINDOW = 80


# v0.8.0: 字眼从 data/signals/user_stop_hints/{zh,en}.txt 加载
# 历史: v0.4.41 设计「用户明确叫停」整 turn 豁免（sticky #8 例外）。
# v0.7.4 加「满意 / 确认」类（不错 / 挺稳定 / OK 了）。
# v0.8.0 外部化 + 加英文 → 英文用户「looks good / LGTM」对偶覆盖。
_USER_STOP_HINT_RE = compile_alternation("user_stop_hints")

# v0.8.0: 字眼从 data/signals/agent_saturation/{zh,en}.txt 加载
# 历史: v0.5.19 设计 — sticky #8 例外 ②「任务饱和明说卡在哪」豁免。
# 跟 stop_hints 互斥: 强饱和声明（任务饱和 / 卡在 X / 明天接力）该豁免，
# 柔性偷懒（今天到此 / 改不动了）该拦。
# v0.8.0 外部化 + 加英文 → 英文 Agent「I'm saturated / stuck at」对偶覆盖。
_AGENT_SATURATION_RE = compile_alternation("agent_saturation")


def check(*, response: str = "", user_prompt: str = "", **_):
    """检测 Agent response 是不是「无下一步陈述完结」型停下。

    豁免优先级：
    0. **用户上 turn 含明确叫停字眼**（v0.4.41）→ 整 turn 豁免（sticky #8 例外）
    1. 推进信号（我现在/立刻 + 动词）→ 豁免（有下一步计划）
    2. 问号（? 或 ？）→ 豁免（合理询问用户决策，鼓励）
    3. 停顿语气词（下次/先到这/告一段落）→ 命中（明确暂停）
    4. 其他（纯陈述完结无下一步）→ 命中（用户反馈核心：无问句的停止才是要监控的）
    """
    if not response or not response.strip():
        return None

    # v0.4.41 原因 fix：用户上 turn 明确叫停字眼 → 整 turn 豁免 keep-pushing
    # 反思（HANDOFF v3 第三步候选实际落地）。今晚多次 dogfooding 触发 — 用户
    # 「不用啦 / 休息吧」明确叫停但 keep_pushing.check 看不到 user prompt 上文。
    if user_prompt and _USER_STOP_HINT_RE.search(user_prompt):
        return None

    text = response.strip()
    tail = text[-_TAIL_WINDOW:]

    # v0.5.19 原因 fix：Agent 自己声明饱和（sticky #8 例外条件 ②「任务饱和
    # 明说卡在哪」）→ 整 turn 豁免. 跟 v0.4.41 用户叫停豁免对偶, 不然 Agent
    # 老实说「今天饱和了」反而被反思 hook 拦, 激发不诚实假装继续推. dogfood
    # 触发: 上 turn 末尾「今天就这样收」+ 上 3 turn「任务饱和」明确声明被错拦.
    if _AGENT_SATURATION_RE.search(text):
        return None

    # 豁免 1：明确推进信号 — tail 直接命中
    # v0.4.22 + v0.8.1: 推进信号尾字过滤 — 「下次接手吧 / 推进行不 / 算了」
    # 类推卸语气不算真推进。yaml 字眼保持简洁，这层过滤在 check() 后处理。
    m_push = _PUSH_SIGNAL_RE.search(tail)
    if m_push:
        rest_after_push = tail[m_push.end():]
        if not _PUSHBACK_TAIL_RE.match(rest_after_push):
            return None

    # v0.4.20：整 response 含推进规划 + 末尾窗口无明确停顿语气 → 豁免。
    # 原因：推进信号常在「下次接手做 A / B / C」之后接「(X / Y / Z)」列表结尾，
    # 整段已有推进意图但 tail 80 字看不到。dogfooding 触发：v0.4.19 装上后
    # 「下次接手做 HANDOFF 候选...（chinese-plain / long-term / audit ...）」
    # 末尾是列表收尾仍被错算无推进。
    # 守护：要求末尾窗口同时无 _STOP_HINT_RE 命中（不然有推进 + 停顿同
    # 时存在该按停顿算）。
    m_push_full = _PUSH_SIGNAL_RE.search(text)
    if m_push_full and not _STOP_HINT_RE.search(tail):
        rest_after_push = text[m_push_full.end():]
        if not _PUSHBACK_TAIL_RE.match(rest_after_push):
            return None

    # 豁免 2：问号（合理询问决策，鼓励）
    if _TAIL_QUESTION_RE.search(tail):
        return None

    # 豁免 3（v0.4.19）：显式让用户介入（sticky #7 合法 stop 路径）— 「请决定 /
    # 请授权 / 等你 X」类。区别于「停下问反馈等用户随便决定」— 这是明确请求
    # 一个 deterministic decision（按 sticky #7「显式让用户介入」鼓励）。
    if _EXPLICIT_USER_HANDOFF_RE.search(tail):
        return None

    # 命中 1：明确停顿语气词 — 比成功汇报豁免优先级高（「测试通过。先到这。」
    # 仍是停下，数字证据不能盖过明确停顿语气）
    m_stop = _STOP_HINT_RE.search(tail)
    if m_stop:
        return CheckHit(
            rule_id=_STICKY_ID,
            trigger=tr("check.keep_pushing.stop_hint.trigger", word=m_stop.group()),
            trigger_key="check.keep_pushing.stop_hint.trigger",
            snippet=tail[:200],
            # v0.4.26 反思式语气改造：尊重 Agent 自主判断，不激发对抗
            suggested_fix=tr("check.keep_pushing.stop_hint.fix"),
        )

    # 豁免 3（晚于停顿词检测）：成功汇报（数字证据 + 通过词）— 跟 sticky #4
    # 「完成要有证据」一致，这种汇报应该被鼓励而不是处罚。
    # 例如「测试 232/232 通过」「100 passed」
    if _SUCCESS_REPORT_RE.search(tail):
        return None

    # 命中 2（默认）：纯陈述完结无下一步 — 用户反馈核心场景
    # 「没有疑问句的停止才是该监控的」
    return CheckHit(
        rule_id=_STICKY_ID,
        trigger=tr("check.keep_pushing.default.trigger"),
        trigger_key="check.keep_pushing.default.trigger",
        snippet=tail[:200],
        # v0.4.26 反思式语气：尊重 Agent 自主判断
        suggested_fix=tr("check.keep_pushing.default.fix"),
    )
