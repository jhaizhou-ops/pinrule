"""#8 read-before-write — 修文件前先读。

检测的行为模式（pre_tool_use Edit/Write + session_state）：
- Agent 调 Edit/Write，但本 session 没 Read 过该 file_path
- Write 全新（不存在的）文件可以豁免

最强检测 — 完全确定性，假阳极低。
"""

from __future__ import annotations

from pathlib import Path

from karma.checks._types import CheckHit

_STICKY_ID = "read-before-write"


def check(*, tool_name: str = "", tool_input: dict | None = None, session_state=None, **_):
    if tool_name not in ("Edit", "Write"):
        return None
    if session_state is None:
        return None  # 没 session 历史就不能判断
    file_path = (tool_input or {}).get("file_path", "")
    if not file_path:
        return None

    # Write 全新文件（不存在）豁免
    if tool_name == "Write":
        try:
            if not Path(file_path).exists():
                return None
        except (OSError, ValueError):
            pass

    if session_state.has_read(file_path):
        return None

    return CheckHit(
        sticky_id=_STICKY_ID,
        trigger=f"未 Read 就 {tool_name} {file_path}",
        snippet=f"{tool_name}({file_path!r})",
        suggested_fix=f"先 Read {file_path} 看现有内容 / 上游调用者 / 相关约定 — 花 2 分钟"
                      "避免改坏 30 分钟才发现的连锁 bug。看清耦合再下手用户会更放心。",
    )
