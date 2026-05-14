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

_STICKY_ID = "keep-pushing-no-stop"

# 末尾问号（中英文）— 限定 response 最后 80 字（多数「停下问」signal 在末尾）
_TAIL_QUESTION_RE = re.compile(r"[?？]")

# 成功汇报（数字证据 + 通过词）— 这是 sticky #4「loud-failure-with-evidence」
# 鼓励的行为，不该被 #7 keep-pushing 处罚为「停下」。
# 命中如「100/100 通过」「测试 232 passed」「全部跑过」等汇报句。
_SUCCESS_REPORT_RE = re.compile(
    r"\d+\s*[/／]\s*\d+\s*(?:通过|passed|pass|绿|过)"
    r"|\d+\s*(?:passed|tests?\s+passed)"
    r"|测试\s*\d+",
    re.IGNORECASE,
)

# 停顿语气词 — Agent 明确表达「暂停 / 等下次 / 告一段落」类
# 这些词出现在末尾窗口且无推进信号 → 沉默式停下（用户的「没问号也停了」反馈）
_STOP_HINT_RE = re.compile(
    r"(?:"
    r"等下次|下次跑|下次看|下次再|下次见|下次有"
    r"|先到这|先到此|告一段落|暂告一段落|暂停一下|停一下|这阶段(?:完|结束)"
    r"|当前(?:状态|进度)是|当前节点|本轮 OK"
    r"|累积到一定量再"
    r"|看新出现什么"
    r")",
    re.IGNORECASE,
)

# 明确「推进信号」字眼 — 表达 Agent 主动继续推进
_PUSH_SIGNAL_RE = re.compile(
    r"(?:"
    r"我(?:现在|立刻|马上|立即|继续|先|来|接着|接下来|顺手)\s*(?:做|改|加|修|跑|去|开始|实施|实现|动手|推|搞|写|发|提交|测试|验证|跑测|读)"
    r"|立刻\s*(?:做|开始|实施|推|继续|动手)"
    r"|马上\s*(?:做|开始|实施|推|继续|动手)"
    r"|继续推进"
    r"|开始做"
    r"|直接(?:做|改|开始|实施|推|动手|去做)"
    r"|不停"
    r"|一并(?:做|改|实施)"
    r"|接下来\s*(?:去|做|改|加|修|跑|开始|实施|动手|推|测试|验证)"
    r")",
    re.IGNORECASE,
)

# 末尾扫描窗口（字符数）— 80 字平衡覆盖跟假阳
_TAIL_WINDOW = 80


def check(*, response: str = "", **_):
    """检测 Agent response 是不是「无下一步陈述完结」型停下。

    豁免优先级：
    1. 推进信号（我现在/立刻 + 动词）→ 豁免（有下一步计划）
    2. 问号（? 或 ？）→ 豁免（合理询问用户决策，鼓励）
    3. 停顿语气词（下次/先到这/告一段落）→ 命中（明确暂停）
    4. 其他（纯陈述完结无下一步）→ 命中（用户反馈核心：无问句的停止才是要监控的）
    """
    if not response or not response.strip():
        return None
    text = response.strip()
    tail = text[-_TAIL_WINDOW:]

    from karma.checks import CheckHit

    # 豁免 1：明确推进信号
    if _PUSH_SIGNAL_RE.search(tail):
        return None

    # 豁免 2：问号（合理询问决策，鼓励）
    if _TAIL_QUESTION_RE.search(tail):
        return None

    # 命中 1：明确停顿语气词 — 比成功汇报豁免优先级高（「测试通过。先到这。」
    # 仍是真停下，数字证据不能盖过明确停顿语气）
    m_stop = _STOP_HINT_RE.search(tail)
    if m_stop:
        return CheckHit(
            sticky_id=_STICKY_ID,
            trigger=f"response 末尾含停顿语气 {m_stop.group()!r} — 明确表达暂停",
            snippet=tail[:200],
            suggested_fix="去掉「下次/先到这/告一段落」等停顿词，直接说明现在去做啥。"
                          "汇报跟推进并行：写完汇报立刻开始下个 tool 调用。",
        )

    # 豁免 3（晚于停顿词检测）：成功汇报（数字证据 + 通过词）— 跟 sticky #4
    # 「完成要有证据」一致，这种汇报应该被鼓励而不是处罚。
    # 例如「测试 232/232 通过」「100 passed」
    if _SUCCESS_REPORT_RE.search(tail):
        return None

    # 命中 2（默认）：纯陈述完结无下一步 — 用户反馈核心场景
    # 「没有疑问句的停止才是该监控的」
    return CheckHit(
        sticky_id=_STICKY_ID,
        trigger="response 纯陈述完结，无推进信号 / 无询问决策 — 真停下，没下一步计划",
        snippet=tail[:200],
        suggested_fix="response 末尾加「我接下来去做 X」类下一步计划，"
                      "或直接开始下个 tool 调用。陈述完结无下一步 = 停下了。",
    )
