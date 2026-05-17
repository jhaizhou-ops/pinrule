"""SubagentStop hook — 子 Agent 完成时给主 Agent 一个轻提醒（pinrule v3 第六步）。

Claude Code 协议:
- stdin payload: {agent_id, agent_type, session_id, transcript_path, ...}
- stdout: {"hookSpecificOutput": {"hookEventName": "SubagentStop",
           "additionalContext": "..."}}

设计（v0.4.30 — 早期 stub 用 substring match 扫 transcript 关键词，假阳爆发：
子 Agent 在 transcript 里讨论「先打个补丁」字面就算违反，跟 pinrule 主流程对
Bash/Edit 的工程检测精度根本不同档。改成不做内容扫描，只做透明度提醒）：

- 子 Agent 完成后给主 Agent 注入一行轻提醒「子 Agent X 已完成」
- 不扫 transcript 关键词（substring match 假阳爆发）
- 违反检测交给主 Agent 自己的 PreToolUse / PostToolUse / Stop hook
  （子 Agent 不执行 tool，只返回结果给主 Agent，主 Agent 处理结果时
  pinrule 主流程 hook 自然会拦）
- 加 sticky 关键方向回声让主 Agent 在子 Agent 结果回来时自检

Fail open：异常 / 配置坏 → passthrough。
"""

from __future__ import annotations

import json
import sys

def _passthrough() -> None:
    print(json.dumps({}))


def main() -> int:
    """SubagentStop — 仅做子 Agent state 销毁 side effect，无 stdout 输出。

    2026-05-15 原因 fix：SubagentStop 协议**不支持 hookSpecificOutput**
    （Claude Code 官方文档：仅 decision/reason 模式，无 additionalContext）。
    v0.4.30 起的 hookSpecificOutput.additionalContext 输出一直被 Claude Code
    静默拒绝，主 Agent 根本没看到「子 Agent X 已结束」透明度提醒。

    子 Agent state 销毁 side effect 保留（v0.4.34 设计核心）。透明度提醒
    Claude Code UI 自身会显示子 Agent 完成事件，pinrule 不需重复 echo。
    """
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"pinrule SubagentStop: 输入 JSON 解析失败 ({e})", file=sys.stderr)
        _passthrough()
        return 0

    from pinrule.hooks._payload import extract_session_id, extract_subagent_id
    agent_id = extract_subagent_id(payload) or "unknown"
    session_id = extract_session_id(payload)

    # v0.4.34 子 Agent 独立 state 销毁 — 子 Agent 完成 → 临时 state 自动销毁
    # （用户「彼此互不干扰 + 临时独立 + 自动销毁」原则）
    if agent_id and agent_id != "unknown":
        try:
            from pinrule import session_state
            session_state.purge_subagent_state(session_id, agent_id)
        except OSError as e:
            print(f"pinrule SubagentStop: 销毁子 Agent state 失败 ({e})", file=sys.stderr)

    _passthrough()
    return 0


if __name__ == "__main__":
    sys.exit(main())
