"""Shared tool gate — preToolUse / beforeShellExecution / beforeMCPExecution."""

from __future__ import annotations

import json
import sys
import time

from pinrule import session_state
from pinrule.backends.protocol_adapter import (
    emit_allow,
    emit_deny,
    normalize_tool_input,
    normalize_tool_name,
)
from pinrule.checks import run_checks
from pinrule.checks.common import (
    extract_natural_language,
    extract_tool_text,
    strip_shell_quoted_literals,
)
from pinrule.checks.description_context import is_description_context
from pinrule.i18n import tr
from pinrule.rule import RuleConfigError, load
from pinrule.violations import Violation, append, detect


def run_tool_gate(payload: dict) -> int:
    """Run pinrule pre-tool checks; print allow/deny JSON to stdout.

    v0.16.6 fail-open wrap: 任何异常 (OSError disk full / TypeError 字段意外 shape /
    PermissionError ~/.pinrule 不可写 等) → fail-open allow + return 0, 不让 hook
    错误卡用户 tool 调用 (sticky #1 historical lesson: v0.9.14 update_state 漏 try
    导致 fail-closed; 这次 wrap 整段防类似 future regression).
    """
    try:
        return _run_tool_gate_inner(payload)
    except Exception as e:
        # fail-open: 打印 allow shape, 让客户端继续, 不卡用户
        from pinrule.backends.protocol_adapter import emit_allow
        try:
            print(emit_allow(payload))
        except Exception:
            print("{}")  # 万一连 emit_allow 也炸, 裸 {} 兜底
        print(f"pinrule run_tool_gate fail-open: {type(e).__name__}: {e}", file=sys.stderr)
        return 0


def _run_tool_gate_inner(payload: dict) -> int:
    """真 gate logic — 被 run_tool_gate 外层 try wrap."""
    raw_tool_name = payload.get("tool_name", "")
    tool_name = normalize_tool_name(raw_tool_name, payload)
    raw_tool_input = payload.get("tool_input", {})
    tool_input = normalize_tool_input(raw_tool_name, raw_tool_input, payload)
    if not isinstance(tool_input, dict):
        tool_input = {}

    from pinrule.hooks._payload import extract_session_id, extract_subagent_id
    session_id = extract_session_id(payload)
    agent_id = extract_subagent_id(payload) or None

    if tool_name == "Agent":
        sub_model = tool_input.get("model")
        if sub_model:
            try:
                def _enqueue_sub_model(state):
                    state.pending_subagent_models.append(sub_model)
                session_state.update_state(session_id, _enqueue_sub_model)
            except Exception as e:
                print(f"pinrule tool gate: 入队子 Agent model 失败 ({e})", file=sys.stderr)

    try:
        sticky_list = load()
    except RuleConfigError as e:
        print(f"pinrule: {e}", file=sys.stderr)
        print(emit_allow(payload))
        return 0

    if not sticky_list:
        print(emit_allow(payload))
        return 0

    try:
        state, _ = session_state.update_state(
            session_id,
            lambda s: s.catchup_pending_bg(),
            agent_id=agent_id,
        )
    except Exception as e:
        print(f"pinrule tool gate: update_state fallback ({e})", file=sys.stderr)
        state = session_state.load(session_id, agent_id=agent_id)

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
        print(emit_allow(payload))
        return 0

    if check_hits:
        top = check_hits[0]
        append([Violation(
            ts=int(time.time()),
            session_id=session_id,
            rule_id=top.rule_id,
            trigger=top.trigger,
            snippet=top.snippet,
            turn=state.turn_count,
            agent_id=agent_id,
            trigger_key=top.trigger_key,
        )])
        sticky_pref = next((s.preference for s in sticky_list if s.id == top.rule_id), "")
        reason = tr(
            "hook.pre_tool_use.deny_engine_reason",
            rule_id=top.rule_id,
            trigger=top.trigger,
            preference=sticky_pref.strip(),
            fix=top.suggested_fix,
        )
        print(emit_deny(reason, payload))
        print(f"🛑 pinrule: {top.rule_id} (tool={tool_name}) — {top.trigger}", file=sys.stderr)
    else:
        top_kw = keyword_violations[0]
        append([top_kw])
        sticky_pref = next((s.preference for s in sticky_list if s.id == top_kw.rule_id), "")
        reason = tr(
            "hook.pre_tool_use.deny_keyword_reason",
            rule_id=top_kw.rule_id,
            trigger=top_kw.trigger,
            preference=sticky_pref.strip(),
        )
        print(emit_deny(reason, payload))
        print(
            f"🛑 pinrule: {top_kw.rule_id} (tool={tool_name}, 关键词 {top_kw.trigger!r})",
            file=sys.stderr,
        )
    return 0


def main_stdin() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"pinrule tool gate: JSON 解析失败 ({e})", file=sys.stderr)
        print(emit_allow({}))
        return 0
    return run_tool_gate(payload)
