"""#8 read-before-write — 修文件前先读。

检测的行为模式（pre_tool_use Edit/Write + session_state）：
- Agent 调 Edit/Write，但本 session 没 Read 过该 file_path
- Write 全新（不存在的）文件可以豁免

最强检测 — 完全确定性，假阳极低。
"""

from __future__ import annotations

from pathlib import Path

from karma.checks._types import CheckHit
from karma.i18n import tr

_STICKY_ID = "read-before-write"


def check(*, tool_name: str = "", tool_input: dict | None = None, session_state=None, **_):
    if tool_name not in ("Edit", "Write"):
        return None
    if session_state is None:
        return None  # 没 session 历史就不能判断
    ti = tool_input or {}

    # v0.10.0 多文件 patch canonical 字段（backend-neutral）— Codex apply_patch
    # / 未来某 backend 可能也用 envelope-style 多文件协议都走这个字段。任一 Update
    # path 未 Read 过 → 拦. Add path (新建文件) 跟 Write 全新逻辑一致豁免.
    multi_file_targets = ti.get("multi_file_targets")
    if multi_file_targets:
        for f in multi_file_targets:
            op = f.get("op")
            path = f.get("path", "")
            if not path:
                continue
            if op == "Add":
                # 新建文件不需要先 Read（跟 Write 新文件豁免对齐）
                continue
            if op == "Delete":
                # 删除不算 edit-without-read（karma 暂不拦 Delete）
                continue
            # op == "Update": 修改已有文件必须先 Read
            if not session_state.has_read(path):
                # 用 tool_name (caller 传入) 不写死 apply_patch 字面 — 让通用层
                # backend-neutral（未来某 backend 也用多文件 envelope 复用同条 check）
                return CheckHit(
                    rule_id=_STICKY_ID,
                    trigger=tr("check.read_first.trigger", tool=tool_name, file_path=path),
                    trigger_key="check.read_first.trigger",
                    snippet=f"{tool_name}({path!r})",
                    suggested_fix=tr("check.read_first.fix", file_path=path),
                )
        return None

    file_path = ti.get("file_path", "")
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
        rule_id=_STICKY_ID,
        trigger=tr("check.read_first.trigger", tool=tool_name, file_path=file_path),
        trigger_key="check.read_first.trigger",
        snippet=f"{tool_name}({file_path!r})",
        suggested_fix=tr("check.read_first.fix", file_path=file_path),
    )
