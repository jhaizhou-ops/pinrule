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
from karma.rule import RuleConfigError, load
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

    # v0.4.37 子 Agent model 捕获到 — manual run 实验验证：
    # PreToolUse 派子 Agent 时 tool_name == "Agent"（不是 "Task"，dogfooding 真名）
    # tool_input 含 model 字段（如 "sonnet" / "opus" / "haiku"）。
    # 主 Agent 派子 Agent 流程：主 PreToolUse(Agent, model=X) → SubagentStart(agent_id) →
    # 子 Agent 内 PostToolUse → SubagentStop。karma 在主 PreToolUse 时把 model
    # 入队 pending，SubagentStart 时 pop 出队写子 Agent state.model 让按模型阈值。
    if tool_name == "Agent":
        sub_model = tool_input.get("model")
        if sub_model:
            try:
                # v0.9.8: update_state 让入队对同 session 并发安全
                # （主 Agent 同时派多个子 Agent 时多个 PreToolUse 同时跑会丢入队）
                def _enqueue_sub_model(state):
                    state.pending_subagent_models.append(sub_model)
                session_state.update_state(session_id, _enqueue_sub_model)
            except Exception as e:
                print(f"karma PreToolUse: 入队子 Agent model 失败 ({e})", file=sys.stderr)

    try:
        sticky_list = load()
    except RuleConfigError as e:
        print(f"karma: {e}", file=sys.stderr)
        _allow()
        return 0

    if not sticky_list:
        _allow()
        return 0

    # v0.9.13 fix race/no-save: catchup 之前用 load + modify 不 save 让 catchup
    # 改动（移除已处理的 pending_bg_tasks / record_bash 推 last_test_pass_ts /
    # recent_bash）全丢失，下次 hook load 又看到原 pending 列表重复处理。改用
    # v0.9.8 加的 update_state 高阶 API 让 load → catchup → save 跨进程原子 +
    # 持久化（跟 post_tool_use.py 的 update_state 一致）。后续决策仍用拿到的
    # state 内存对象。
    #
    # v0.9.14 fail-open 兜底：v0.9.13 这条改动我漏了 try/except — update_state
    # 内部 fcntl.flock acquire / fn 抛 / save OSError 任一异常 bubble 出去会让
    # PreToolUse return 非 0 → Claude Code 看到 hook 失败卡用户（fail-closed
    # 违反 karma 设计原则）。多 Agent audit 视角 3 抓到这条 v0.9.13 引入的
    # 回归。fallback：异常时降级用裸 load() 拿 state 不持久化（catchup 真改动
    # 这一 turn 丢失但下次 PostToolUse 会重新 catchup —— 跟 v0.9.13 前同等行为）。
    try:
        state, _ = session_state.update_state(
            session_id,
            lambda s: s.catchup_pending_bg(),
            agent_id=agent_id,
        )
    except Exception as e:
        print(f"karma PreToolUse: update_state 失败 fallback 裸 load ({e})", file=sys.stderr)
        state = session_state.load(session_id, agent_id=agent_id)

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
            rule_id=s.id,
        )
        check_hits.extend(hits)

    # 关键词层（兜底）—
    # Bash: 扫命令骨架（剥引号字面、剥 python/cat 等 heredoc 数据）
    # Write/Edit 非描述上下文: 扫代码注释 + docstring，不扫代码主体
    #   （主体字面词几乎全是数据/描述假阳；注释里写意图字面才是违反）
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

    # 优先工程层：含 suggested_fix 比关键词层信息密度高
    if check_hits:
        _emit_engine_denial(check_hits[0], sticky_list, tool_name, session_id, state, agent_id)
    else:
        _emit_keyword_denial(keyword_violations[0], sticky_list, tool_name)
    return 0


def _emit_engine_denial(
    top, sticky_list, tool_name: str, session_id: str, state, agent_id,
) -> None:
    """工程层 (CheckHit) 命中 → 写 violation + _deny + stderr 🛑。

    🛑 = pre_tool_use 拦截阻止 Agent 做事；stop hook 用 ⚠️ 表事后告警
    （语义差异化刻意保留：🛑 阻止动作 / ⚠️ 已发生需关注）
    """
    append([Violation(
        ts=int(time.time()),
        session_id=session_id,
        rule_id=top.rule_id,
        trigger=top.trigger,
        snippet=top.snippet,
        turn=state.turn_count,
        agent_id=agent_id,
        trigger_key=top.trigger_key,  # v0.5.7: locale-agnostic 分组 key
    )])
    sticky_pref = next((s.preference for s in sticky_list if s.id == top.rule_id), "")
    reason = (
        f"karma 拦截：违反 {top.rule_id!r}。\n"
        f"检测到：{top.trigger}\n"
        f"方向：{sticky_pref.strip()}\n"
        f"建议：{top.suggested_fix}"
    )
    _deny(reason)
    print(
        f"🛑 karma: {top.rule_id} (tool={tool_name}) — {top.trigger}",
        file=sys.stderr,
    )


def _emit_keyword_denial(
    top_kw: Violation, sticky_list, tool_name: str,
) -> None:
    """关键词层 (Violation) 命中 → append (已含完整字段) + _deny + stderr 🛑。"""
    append([top_kw])
    sticky_pref = next((s.preference for s in sticky_list if s.id == top_kw.rule_id), "")
    reason = (
        f"karma 拦截：违反 {top_kw.rule_id!r}（触发词 {top_kw.trigger!r}）。\n"
        f"方向：{sticky_pref.strip()}\n"
        f"请改写，不要用 {top_kw.trigger!r} 这种方式。"
    )
    _deny(reason)
    print(
        f"🛑 karma: {top_kw.rule_id} (tool={tool_name}, 关键词 {top_kw.trigger!r})",
        file=sys.stderr,
    )


if __name__ == "__main__":
    sys.exit(main())
