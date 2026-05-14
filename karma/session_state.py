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

# Claude Code background 任务启动时 tool_response 的完整 marker — 整个句式要匹配
# 避免任意文本里出现「Output is being written to:」子串就被误判为 background marker
# （例：git diff 输出含本文件注释里的示例字面，子串匹配会假阳）
_BG_OUTPUT_FILE_RE = re.compile(
    # 捕获文件路径到下一个空白或句末标点（marker 句尾的 `.` / `,` 不是路径一部分）
    r"Command running in background with ID:\s+\S+\.\s+Output is being written to:\s*([^\s.,;]+(?:\.[^\s.,;]+)*)",
    re.IGNORECASE,
)

# 测试通过信号 — 出现 N passed / all green / 全绿勾
_PASS_RE = re.compile(
    r"\b\d+\s+passed\b|\ball\s+tests?\s+pass(?:ed)?\b|\ball\s+green\b|✓",
    re.IGNORECASE,
)

# 测试失败信号 — 精确匹配（不要单独的 'error' / 'traceback' 子串，假阳性高）
# - "1 failed" pytest 风格计数
# - "FAILED test_x" pytest 单测失败行（行首或空白后）
# - "FAILURES" 章节标题
# - "Traceback (most recent call last)" 真 Python traceback（不是字面词 traceback）
# - AssertionError 等明确的失败异常
_FAIL_RE = re.compile(
    r"\b\d+\s+failed\b"
    r"|(?:^|\n)FAILED\s"
    r"|\bFAILURES?\b"
    r"|Traceback\s*\(most\s+recent\s+call\s+last\)"
    r"|\b(?:AssertionError|RuntimeError)\b",
    re.IGNORECASE | re.MULTILINE,
)

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
    last_test_pass_ts: float = 0.0   # 最近一次测试通过的时间戳（0 = 从未通过）
    last_edit_ts: float = 0.0        # 最近一次代码 Edit/Write 的时间戳（0 = 本 session 未改代码）
    # background 任务 pending list — 启动时无真实输出，等下次 hook 触发 catchup 读 output file
    pending_bg_tasks: list[dict] = field(default_factory=list)

    def has_read(self, file_path: str) -> bool:
        return file_path in self.read_files

    def has_recent_test_pass(self) -> bool:
        """本 session 是否「自最近一次代码改动以来跑过测试且通过」。

        语义：last_test_pass_ts >= last_edit_ts（含相等防同时刻边界）。
        从未测试通过 → False。代码改了之后没重测 → False。
        """
        if self.last_test_pass_ts <= 0:
            return False
        return self.last_test_pass_ts >= self.last_edit_ts

    def record_read(self, file_path: str) -> None:
        if file_path:
            self.read_files.add(file_path)

    def _next_ts(self) -> float:
        """生成严格大于已有 last_*_ts 的时间戳。

        time.time() 在同微秒连续调用会返回相同值，无法区分先后；
        强制比已记录的最大 ts 大 1 微秒，保证 has_recent_test_pass 顺序判定正确。
        """
        ts = time.time()
        floor = max(self.last_test_pass_ts, self.last_edit_ts)
        if ts <= floor:
            ts = floor + 1e-6
        return ts

    def record_edit(self, file_path: str) -> None:
        if file_path:
            self.edit_files.append(file_path)
            self.last_edit_ts = self._next_ts()

    def record_bash(self, command: str, output: str, run_in_background: bool = False) -> None:
        if not command:
            return
        is_test = bool(_TEST_CMD_RE.search(command))
        out_str = str(output)
        # background 任务启动时 output 是 marker 不是真实输出 — 记进 pending 等 catchup
        # 关键：只在 tool_input.run_in_background=True 时识别 marker，
        # 否则任意命令 stdout 含 marker 字面（自指/echo/cat 等）会被假阳 record。
        if run_in_background:
            bg_match = _BG_OUTPUT_FILE_RE.search(out_str)
            if bg_match:
                self.pending_bg_tasks.append({
                    "cmd": command[:100],
                    "output_file": bg_match.group(1).strip(),
                    "started_ts": time.time(),
                })
                # 仍然记一条 snapshot，但 output_passed/failed 留空（待 catchup 补）
                self.recent_bash.append(BashSnapshot(
                    ts=time.time(),
                    command_summary=command[:100],
                    is_test_cmd=is_test,
                    output_passed=False,
                    output_failed=False,
                ))
                self.recent_bash = self.recent_bash[-MAX_RECENT_BASH:]
                return

        passed = bool(_PASS_RE.search(out_str))
        failed = bool(_FAIL_RE.search(out_str))
        self.recent_bash.append(BashSnapshot(
            ts=time.time(),
            command_summary=command[:100],
            is_test_cmd=is_test,
            output_passed=passed,
            output_failed=failed,
        ))
        # 测试通过 → 推进 last_test_pass_ts（严格大于 last_edit_ts，分清先后）
        if is_test and passed and not failed:
            self.last_test_pass_ts = self._next_ts()
        # 保留最近 N 条
        self.recent_bash = self.recent_bash[-MAX_RECENT_BASH:]

    def catchup_pending_bg(self) -> int:
        """扫 pending_bg_tasks — 文件存在且非空就读取并 record_bash。

        返回成功 catch-up 的任务数。文件还没出现的保留在 pending。
        """
        if not self.pending_bg_tasks:
            return 0
        caught_up = 0
        still_pending: list[dict] = []
        for task in self.pending_bg_tasks:
            output_file = task.get("output_file", "")
            cmd = task.get("cmd", "")
            if not output_file:
                continue
            try:
                p = Path(output_file)
                if not p.exists() or p.stat().st_size == 0:
                    still_pending.append(task)
                    continue
                output = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                still_pending.append(task)
                continue
            # 用普通 record_bash 路径处理（已读到真实输出，不会再命中 bg marker）
            self.record_bash(cmd, output)
            caught_up += 1
        self.pending_bg_tasks = still_pending
        return caught_up


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
        last_test_pass_ts=float(d.get("last_test_pass_ts", 0.0) or 0.0),
        last_edit_ts=float(d.get("last_edit_ts", 0.0) or 0.0),
        pending_bg_tasks=list(d.get("pending_bg_tasks", []) or []),
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
        "last_test_pass_ts": state.last_test_pass_ts,
        "last_edit_ts": state.last_edit_ts,
        "pending_bg_tasks": state.pending_bg_tasks,
    }
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    import os
    os.replace(tmp, p)
