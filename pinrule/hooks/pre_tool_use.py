"""PreToolUse hook — Agent 调 tool 前拦截违反。

Claude Code 实际协议:
- stdin payload: {tool_name, tool_input, tool_use_id, session_id, transcript_path, ...}
- stdout 输出:
    allow: {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}}
    deny : {"hookSpecificOutput": {..., "permissionDecision": "deny", "permissionDecisionReason": "..."}}

检测两层：
1. 工程层 violation_checks (pinrule.checks 函数库)
2. 关键词层 violation_keywords (兜底)

性能预算：< 100ms
Fail open：配置坏 / 异常 → allow (不卡 Agent)
"""

from __future__ import annotations

import sys


def main() -> int:
    # v0.14.0: pre_tool_use 主逻辑搬到 _tool_gate, 这里只是入口
    # cursor agent 重写后 _allow/_deny helper 不需要了 (走 _tool_gate 内部 emit)
    from pinrule.hooks._tool_gate import main_stdin
    return main_stdin()


if __name__ == "__main__":
    sys.exit(main())
