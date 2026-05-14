"""SubagentStop hook — 子 Agent 完成时给主 Agent 一个轻提醒（karma v3 第六步）。

Claude Code 协议:
- stdin payload: {agent_id, agent_type, session_id, transcript_path, ...}
- stdout: {"hookSpecificOutput": {"hookEventName": "SubagentStop",
           "additionalContext": "..."}}

设计（v0.4.30 — 早期 stub 用 substring match 扫 transcript 关键词，假阳爆发：
子 Agent 在 transcript 里讨论「先打个补丁」字面就算违反，跟 karma 主流程对
Bash/Edit 的工程检测精度根本不同档。改成不做内容扫描，只做透明度提醒）：

- 子 Agent 完成后给主 Agent 注入一行轻提醒「子 Agent X 已完成」
- 不扫 transcript 关键词（substring match 假阳爆发）
- 真违反检测交给主 Agent 自己的 PreToolUse / PostToolUse / Stop hook
  （子 Agent 不真执行 tool，只返回结果给主 Agent，主 Agent 处理结果时
  karma 主流程 hook 自然会拦）
- 加 sticky 关键方向回声让主 Agent 在子 Agent 结果回来时自检

Fail open：异常 / 配置坏 → passthrough。
"""

from __future__ import annotations

import json
import sys

from karma.sticky import load as load_sticky


def _passthrough() -> None:
    print(json.dumps({}))


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"karma SubagentStop: 输入 JSON 解析失败 ({e})", file=sys.stderr)
        _passthrough()
        return 0

    agent_id = payload.get("agent_id", "") or "unknown"

    try:
        sticky_list = load_sticky()
    except Exception as e:
        print(f"karma SubagentStop: sticky 加载失败 ({e})", file=sys.stderr)
        _passthrough()
        return 0

    if not sticky_list:
        _passthrough()
        return 0

    # 透明度提醒 + sticky 关键方向回声 — 让主 Agent 接子 Agent 结果时自检
    sticky_ids = ", ".join(s.id for s in sticky_list)
    context = (
        f"[karma 子 Agent {agent_id} 已完成]\n"
        f"sticky 仍生效（{sticky_ids}）— 接结果时自检是否按这些方向处理。"
    )
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SubagentStop",
            "additionalContext": context,
        }
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
