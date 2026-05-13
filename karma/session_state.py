"""跨 hook 共享的 session 状态 — Read 历史 / Bash 测试结果 / Edit 累积。

post_tool_use 写入，pre_tool_use / post_response 读取。
存到 ~/.claude/karma/session-state/{session_id}.json。
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_DIR = Path.home() / ".claude" / "karma" / "session-state"
MAX_RECENT_BASH = 15  # 保留最近 N 条 Bash 摘要

# 测试通过 / 失败信号 regex
_PASS_RE = re.compile(r"\bpassed\b|\bPASS\b|✓|all green|all tests pass", re.IGNORECASE)
_FAIL_RE = re.compile(r"\bfailed\b|\bFAIL\b|✗|error|traceback", re.IGNORECASE)
_TEST_CMD_RE = re.compile(
    r"\b(pytest|jest|cargo test|go test|npm test|tox|mocha|vitest|rspec|phpunit)\b",
    re.IGNORECASE,
)


@dataclass
class BashSnapshot:
    """单次 Bash 调用的摘要 — 只记关键信号，不存全文。"""

    ts: float
    command_summary: str  # command 前 100 字
    is_test_cmd: bool      # 命令是否含 pytest/jest 等测试 runner
    output_passed: bool    # 输出含 PASS 信号
    output_failed: bool    # 输出含 FAIL 信号


@dataclass
class SessionState:
    session_id: str
    read_files: set[str] = field(default_factory=set)         # 本 session Read 过的 file_path
    edit_files: list[str] = field(default_factory=list)        # Edit/Write 顺序记录（重复也保留）
    recent_bash: list[BashSnapshot] = field(default_factory=list)

    def has_read(self, file_path: str) -> bool:
        return file_path in self.read_files

    def has_recent_test_pass(self, last_n: int = 5) -> bool:
        """最近 N 条 Bash 中是否有测试 + 通过。"""
        for snap in self.recent_bash[-last_n:]:
            if snap.is_test_cmd and snap.output_passed and not snap.output_failed:
                return True
        return False

    def record_read(self, file_path: str) -> None:
        if file_path:
            self.read_files.add(file_path)

    def record_edit(self, file_path: str) -> None:
        if file_path:
            self.edit_files.append(file_path)

    def record_bash(self, command: str, output: str) -> None:
        if not command:
            return
        is_test = bool(_TEST_CMD_RE.search(command))
        passed = bool(_PASS_RE.search(str(output)))
        failed = bool(_FAIL_RE.search(str(output).lower()))
        self.recent_bash.append(BashSnapshot(
            ts=time.time(),
            command_summary=command[:100],
            is_test_cmd=is_test,
            output_passed=passed,
            output_failed=failed,
        ))
        # 保留最近 N 条
        self.recent_bash = self.recent_bash[-MAX_RECENT_BASH:]


def _state_path(session_id: str, base_dir: Path | None = None) -> Path:
    base = base_dir or DEFAULT_DIR
    # session_id 可能含 /，简单清洗成单文件名
    safe_id = re.sub(r"[^\w.-]", "_", session_id) or "default"
    return base / f"{safe_id}.json"


def load(session_id: str, base_dir: Path | None = None) -> SessionState:
    """加载 session 状态。文件不存在 → 返回空 state。"""
    p = _state_path(session_id, base_dir)
    if not p.exists():
        return SessionState(session_id=session_id)
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return SessionState(session_id=session_id)
    state = SessionState(
        session_id=session_id,
        read_files=set(d.get("read_files", [])),
        edit_files=list(d.get("edit_files", [])),
        recent_bash=[
            BashSnapshot(
                ts=float(b.get("ts", 0)),
                command_summary=b.get("command_summary", ""),
                is_test_cmd=bool(b.get("is_test_cmd", False)),
                output_passed=bool(b.get("output_passed", False)),
                output_failed=bool(b.get("output_failed", False)),
            )
            for b in d.get("recent_bash", [])
        ],
    )
    return state


def save(state: SessionState, base_dir: Path | None = None) -> None:
    """保存 session 状态（atomic rewrite）。"""
    p = _state_path(state.session_id, base_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "session_id": state.session_id,
        "read_files": sorted(state.read_files),
        "edit_files": state.edit_files,
        "recent_bash": [
            {
                "ts": b.ts,
                "command_summary": b.command_summary,
                "is_test_cmd": b.is_test_cmd,
                "output_passed": b.output_passed,
                "output_failed": b.output_failed,
            }
            for b in state.recent_bash
        ],
    }
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    import os
    os.replace(tmp, p)
