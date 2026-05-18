"""Cursor hook transcript_path 健康检查 — 从 Cursor Hooks 输出日志推断.

Cursor 官方文档 (cursor.com/docs/hooks): transcript_path 为 null 表示 transcripts disabled.
实测 (dogfood): 桌面 Agent/Composer 在 session 跑起来后 **绝大多数** hook 会带 .jsonl 路径;
sessionStart 几乎总是 null (会话尚未落盘). 未发现可写的 User settings.json 键.

本模块只 **读** ~/Library/Application Support/Cursor/logs/.../cursor.hooks*.log, 不改 Cursor 配置.
"""

from __future__ import annotations

import re
from pathlib import Path


def _latest_hooks_log() -> Path | None:
    logs_root = Path.home() / "Library" / "Application Support" / "Cursor" / "logs"
    if not logs_root.is_dir():
        return None
    candidates = sorted(logs_root.glob("**/cursor.hooks*.log"), key=lambda p: p.stat().st_mtime)
    return candidates[-1] if candidates else None


def _parse_hook_log(path: Path) -> dict[str, dict[str, int]]:
    """Return {event_name: {"set": n, "null": n}} from INPUT blocks."""
    text = path.read_text(encoding="utf-8", errors="replace")
    stats: dict[str, dict[str, int]] = {}
    for chunk in text.split("INPUT")[1:]:
        ev_m = re.search(r'"hook_event_name"\s*:\s*"([^"]+)"', chunk)
        tp_m = re.search(r'"transcript_path"\s*:\s*(null|"/[^"]+")', chunk)
        if not ev_m or not tp_m:
            continue
        ev = ev_m.group(1)
        bucket = stats.setdefault(ev, {"set": 0, "null": 0})
        if tp_m.group(1) == "null":
            bucket["null"] += 1
        else:
            bucket["set"] += 1
    return stats


def cursor_transcript_doctor_lines() -> list[str]:
    """Lines for `pinrule doctor` (empty if Cursor not on darwin or no logs)."""
    log = _latest_hooks_log()
    if log is None:
        return [
            "",
            "  Cursor Agent transcripts (hook transcript_path):",
            "    ⚠️  未找到 Cursor Hooks 日志 (~/.cursor 未跑过 Agent hook?)",
            "    在 Cursor 里用 Agent 发一条消息后重跑 doctor.",
        ]

    stats = _parse_hook_log(log)
    if not stats:
        return [
            "",
            "  Cursor Agent transcripts (hook transcript_path):",
            f"    ⚠️  日志无 INPUT 块: {log}",
        ]

    lines = [
        "",
        "  Cursor Agent transcripts (hook transcript_path):",
        f"    日志: {log}",
    ]

    # Response-level hooks: need transcript or afterAgentResponse.text
    for ev in ("stop", "afterAgentResponse", "beforeSubmitPrompt"):
        b = stats.get(ev)
        if not b:
            continue
        total = b["set"] + b["null"]
        if total == 0:
            continue
        if b["null"] == 0:
            lines.append(f"    [{ev}] {b['set']}/{total} 带 transcript_path ✓ (回复级检查可用)")
        else:
            lines.append(
                f"    [{ev}] {b['null']}/{total} 为 null ⚠️ "
                f"(回复级检查可能弱; 见 README Cursor transcripts 节)"
            )

    ss = stats.get("sessionStart")
    if ss and ss["null"] and not ss["set"]:
        lines.append(
            f"    [sessionStart] {ss['null']} 次全为 null — 正常 (起手时 transcript 尚未创建)"
        )

    pre = stats.get("preToolUse")
    if pre:
        total = pre["set"] + pre["null"]
        if total and pre["null"] == total:
            lines.append(
                "    [preToolUse] 全部 null — 异常; 检查 Cursor 隐私模式是否禁止本地 Agent 记录"
            )
        elif pre["null"] and pre["set"]:
            pct = int(100 * pre["null"] / total)
            if pct > 25:
                lines.append(
                    f"    [preToolUse] {pre['null']}/{total} 为 null ({pct}%) "
                    "— 多为会话刚起; stop/afterAgentResponse 仍应 mostly 有路径"
                )

    lines.extend([
        "    说明: 桌面 Agent 一般 **无需** 单独开 transcript 开关; install-hooks + Agent 会话即会写",
        "    ~/.cursor/projects/<id>/agent-transcripts/*.jsonl 。无法用 CLI 可靠写入 Cursor 内部开关。",
    ])
    return lines
