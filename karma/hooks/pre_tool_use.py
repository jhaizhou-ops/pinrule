"""PreToolUse hook — Agent 调 tool 前拦截违反。

Claude Code 实际协议:
- stdin payload: {tool_name, tool_input, tool_use_id, session_id, transcript_path, ...}
- stdout 输出:
    allow: {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}}
    deny : {"hookSpecificOutput": {..., "permissionDecision": "deny", "permissionDecisionReason": "..."}}

检测两层：
1. 工程层 violation_checks (karma.checks 函数库)
2. 关键词层 violation_keywords (兜底)

性能预算：< 100ms
Fail open：配置坏 / 异常 → allow (不卡 Agent)
"""

from __future__ import annotations

import json
import sys
import time

from karma import session_state
from karma.checks import run_checks
from karma.checks.common import (
    extract_natural_language,
    extract_tool_text,
    strip_shell_quoted_literals,
)
from karma.checks.description_context import is_description_context
from karma.sticky import StickyConfigError, load
from karma.violations import Violation, append, detect


def _allow() -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
        }
    }))


def _deny(reason: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }, ensure_ascii=False))


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"karma PreToolUse: 输入 JSON 解析失败 ({e})", file=sys.stderr)
        _allow()
        return 0

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}
    session_id = payload.get("session_id", "") or "default"
    # v0.4.34 子 Agent 独立架构：agent_id 区分主/子 Agent
    # 主 Agent payload 没 agent_id 字段；子 Agent (Task tool 启动) payload 含 uuid
    agent_id = payload.get("agent_id") or None

    # v0.4.37 子 Agent model 真捕获 — manual run 实验真验证：
    # PreToolUse 派子 Agent 时 tool_name == "Agent"（不是 "Task"，dogfooding 真名）
    # tool_input 真含 model 字段（如 "sonnet" / "opus" / "haiku"）。
    # 主 Agent 派子 Agent 流程：主 PreToolUse(Agent, model=X) → SubagentStart(agent_id) →
    # 子 Agent 内 PostToolUse → SubagentStop。karma 在主 PreToolUse 时把 model
    # 入队 pending，SubagentStart 时 pop 出队写子 Agent state.model 让按真模型阈值。
    if tool_name == "Agent":
        sub_model = tool_input.get("model")
        if sub_model:
            try:
                main_state = session_state.load(session_id)
                main_state.pending_subagent_models.append(sub_model)
                session_state.save(main_state)
            except Exception as e:
                print(f"karma PreToolUse: 入队子 Agent model 失败 ({e})", file=sys.stderr)

    try:
        sticky_list = load()
    except StickyConfigError as e:
        print(f"karma: {e}", file=sys.stderr)
        _allow()
        return 0

    if not sticky_list:
        _allow()
        return 0

    state = session_state.load(session_id, agent_id=agent_id)
    # catchup pending background 任务（覆盖 PostToolUse 之外的 hook 触发场景）
    state.catchup_pending_bg()

    # 工程层 violation_checks
    check_hits = []
    for s in sticky_list:
        if not s.violation_checks:
            continue
        hits = run_checks(
            s.violation_checks,
            tool_name=tool_name,
            tool_input=tool_input,
            session_state=state,
            sticky_id=s.id,
        )
        check_hits.extend(hits)

    # 关键词层（兜底）—
    # Bash: 扫命令骨架（剥引号字面、剥 python/cat 等 heredoc 数据）
    # Write/Edit 非描述上下文: 扫代码注释 + docstring，不扫代码主体
    #   （主体字面词几乎全是数据/描述假阳；注释里写意图字面才是真违反）
    # Write/Edit 描述上下文 (.md / tests / /tmp / probe): 不扫
    keyword_violations: list[Violation] = []
    scan_text = ""
    if tool_name == "Bash":
        raw_cmd = extract_tool_text(tool_name, tool_input)
        scan_text = strip_shell_quoted_literals(raw_cmd)
    elif tool_name in ("Write", "Edit", "NotebookEdit"):
        is_desc, _ = is_description_context(tool_name, tool_input)
        if not is_desc:
            content = extract_tool_text(tool_name, tool_input)
            scan_text = extract_natural_language(content)
    if scan_text.strip():
        keyword_violations = detect(
            scan_text, sticky_list, session_id=session_id,
            turn=state.turn_count, agent_id=agent_id,
        )

    if not check_hits and not keyword_violations:
        _allow()
        return 0

    # 优先工程层
    if check_hits:
        top = check_hits[0]
        append([Violation(
            ts=int(time.time()),
            session_id=session_id,
            sticky_id=top.sticky_id,
            trigger=top.trigger,
            snippet=top.snippet,
            turn=state.turn_count,
            agent_id=agent_id,
        )])
        sticky_pref = next((s.preference for s in sticky_list if s.id == top.sticky_id), "")
        reason = (
            f"karma 拦截：违反 {top.sticky_id!r}。\n"
            f"检测到：{top.trigger}\n"
            f"方向：{sticky_pref.strip()}\n"
            f"建议：{top.suggested_fix}"
        )
        _deny(reason)
        # 🛑 = pre_tool_use 拦截阻止 Agent 做事；stop hook 用 ⚠️ 表事后告警
        # （语义差异化刻意保留：🛑 阻止动作 / ⚠️ 已发生需关注）
        print(
            f"🛑 karma: {top.sticky_id} (tool={tool_name}) — {top.trigger}",
            file=sys.stderr,
        )
        return 0

    # 仅关键词命中
    top_kw = keyword_violations[0]
    append([top_kw])
    sticky_pref = next((s.preference for s in sticky_list if s.id == top_kw.sticky_id), "")
    reason = (
        f"karma 拦截：违反 {top_kw.sticky_id!r}（触发词 {top_kw.trigger!r}）。\n"
        f"方向：{sticky_pref.strip()}\n"
        f"请改写，不要用 {top_kw.trigger!r} 这种方式。"
    )
    _deny(reason)
    print(
        f"🛑 karma: {top_kw.sticky_id} (tool={tool_name}, 关键词 {top_kw.trigger!r})",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
