"""#7 keep-pushing-no-stop — 不主动停下问用户。

用户精准定位（2026-05-14）：
- **没有疑问句的停止**才是要监控的 — 陈述完结无下一步 = 真停下
- 只是陈述而且有下一步计划 → 应鼓励 Agent 继续
- 问号 → 合理询问决策，**豁免**（不该拦询问 ≠ 不该拦停止）

检测设计（post_response / Stop hook 扫 Agent response）：
1. 末尾 80 字含「推进信号」（我现在/立刻/马上 + 动词 等）→ 豁免（有下一步计划）
2. 末尾 80 字含问号（? 或 ？）→ 豁免（合理询问用户决策）
3. 末尾 80 字含「停顿语气词」（下次/先到这/告一段落）→ 命中（明确表达暂停）
4. **既无推进 + 无问号 + 无停顿词 = 默认命中**（纯陈述完结无下一步 = 真停下）

豁免顺序：推进 > 问号 > 停顿词检测 > 默认命中
"""

from __future__ import annotations

import re

from karma.checks._types import CheckHit
from karma.i18n import tr

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

# 停顿语气词 — Agent 明确表达「暂停 / 等下次 / 告一段落」类
# 这些词出现在末尾窗口且无推进信号 → 沉默式停下（用户的「没问号也停了」反馈）
# v0.4.19：「下次」字面收紧 — 「下次再来」「下次见」「下次有空再」类是真停，
# 但「下次接手做 X」「下个 session 推进 X」是真规划下一步，应豁免（_PUSH_SIGNAL_RE
# 识别）。这里只匹配「下次」后跟模糊副词（再 / 见 / 有 + 收尾）不跟具体动作。
_STOP_HINT_RE = re.compile(
    r"(?:"
    r"等下次|下次再来|下次再说|下次见|下次有空"
    r"|先到这|先到此|告一段落|暂告一段落|暂停一下|停一下|这阶段(?:完|结束)"
    r"|当前(?:状态|进度)是|当前节点|本轮 OK"
    r"|累积到一定量再"
    r"|看新出现什么"
    # v0.4.22：柔性停顿 — v0.4.19/20 漏拦的真停顿语气
    r"|今天到此|到此为止|就这样了|就这样吧|就到这|今天就这"
    r"|搞不定了|改不动了|算了吧|放着吧"
    r")",
    re.IGNORECASE,
)

# v0.4.19：显式让用户介入豁免 — 按 sticky #7「显式让用户介入」原则，
# response 末尾含「请决定 / 请授权 / 等你 X」类明确 ask 句式是合法 stop
# 路径（不是 sticky #8 禁止的「停下问反馈」），应豁免。
_EXPLICIT_USER_HANDOFF_RE = re.compile(
    r"(?:请(?:决定|授权|确认|定夺|拍板)|等你(?:决定|授权|确认|看|说|回复|反馈)|"
    r"等用户(?:决定|授权|确认|介入)|你说(?:要不要|怎么|呢))",
    re.IGNORECASE,
)

# 明确「推进信号」字眼 — 表达 Agent 主动继续推进
# v0.4.19：扩三类「未来推进规划」识别（已有下一步计划但不是「现在立即做」）：
# - 下次/下个 session/下回 + 具体动作（接手/做/治理/推进）= 真规划
# - 候选/待办/清单 + 优先级排序 = 真推进规划
# - 接手/接力 + 任务 = 真延续推进
_PUSH_SIGNAL_RE = re.compile(
    r"(?:"
    r"我(?:现在|立刻|马上|立即|继续|先|来|接着|接下来|顺手|去|要去)\s*"
    r"(?:做|改|加|修|跑|去|开始|实施|实现|动手|推|搞|写|发|提交|测试|验证|跑测|读|看|查|测|检查|确认|核对)"
    r"|立刻\s*(?:做|开始|实施|推|继续|动手)"
    r"|马上\s*(?:做|开始|实施|推|继续|动手)"
    r"|继续推进"
    r"|开始做"
    r"|直接(?:做|改|开始|实施|推|动手|去做)"
    r"|不停"
    r"|一并(?:做|改|实施)"
    r"|接下来\s*(?:去|做|改|加|修|跑|开始|实施|动手|推|测试|验证|看|查|检查|确认)"
    # 未来推进规划（已有下一步计划但不立即做）
    # v0.4.22：「下次 X 吧 / 行不」类推卸语气不算推进 — 要求紧跟动词后不是「吧/行不/算了」
    r"|下次(?:接手|做|治理|推进|fix|修|改)(?!\s*[吧行])"
    r"|下个\s*session\s*(?:接手|做|治理|推进|fix|修|改)(?!\s*[吧行])"
    r"|候选(?:清单|列表|第)?\s*\d*"
    r"|接手(?:做|改|fix|修|治理|推进)"
    # v0.5.6：「下一(推进点 / 步 / 波 / 个推进点)」类未来规划短语 — Agent 用这类
    # 短语收尾「下一推进点：X」明确给用户下一步信号. dogfooding 真触发：今晚 7 次
    # 错拦本是合法推进规划. 同 v0.4.19 根因（_PUSH_SIGNAL_RE 漏覆盖未来规划表达）.
    r"|下一(?:推进点|步|个|个推进点|波|个 milestone|个里程碑)"
    r"|下一步\s*(?:是|做|打算|准备|考虑|推进|继续|去|要|想|可以|应该)"
    r"|接下来\s*(?:打算|准备|计划|考虑|可以|可选|的方向|的推进点)"
    r"|后续\s*(?:推进|步骤|计划|打算|准备|是)"
    r")",
    re.IGNORECASE,
)

# 末尾扫描窗口（字符数）— 80 字平衡覆盖跟假阳
_TAIL_WINDOW = 80


# v0.4.41 用户叫停字眼检测 — sticky #8 例外条件「用户明确叫停」清单字面
# 命中任何字面 → 整 turn 豁免 keep-pushing reflection（用户已明确叫停 Agent
# 真合理停下，反复反思 hook 是 karma 自身真盲区不该拦）
_USER_STOP_HINT_RE = __import__("re").compile(
    r"(?:不用啦|不用了|休息吧|明天再说|先到这|算了|停一下|停下|"
    r"别推了|别继续|别推进|不再推|够了|到此为止|收尾吧|睡吧|晚安|"
    r"好了好了|走火入魔|够了别)",
    __import__("re").IGNORECASE,
)


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

    # v0.4.41 真根因 fix：用户上 turn 明确叫停字眼 → 整 turn 豁免 keep-pushing
    # 反思（HANDOFF v3 第三步候选真落地）。今晚多次 dogfooding 真触发 — 用户
    # 「不用啦 / 休息吧」明确叫停但 keep_pushing.check 看不到 user prompt 上文。
    if user_prompt and _USER_STOP_HINT_RE.search(user_prompt):
        return None

    text = response.strip()
    tail = text[-_TAIL_WINDOW:]

    # 豁免 1：明确推进信号 — tail 直接命中
    if _PUSH_SIGNAL_RE.search(tail):
        return None

    # v0.4.20：整 response 含推进规划 + 末尾窗口无明确停顿语气 → 豁免。
    # 真根因：推进信号常在「下次接手做 A / B / C」之后接「(X / Y / Z)」列表结尾，
    # 整段已有推进意图但 tail 80 字看不到。dogfooding 真触发：v0.4.19 装上后
    # 「下次接手做 HANDOFF 候选...（chinese-plain / long-term / audit ...）」
    # 末尾是列表收尾仍被错算无推进。
    # 守护：要求末尾窗口同时无 _STOP_HINT_RE 命中（不然真有推进 + 真停顿同
    # 时存在该按停顿算）。
    if _PUSH_SIGNAL_RE.search(text) and not _STOP_HINT_RE.search(tail):
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
    # 仍是真停下，数字证据不能盖过明确停顿语气）
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
