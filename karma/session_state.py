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

from karma.paths import karma_home

DEFAULT_DIR = karma_home() / "session-state"
MAX_RECENT_BASH = 15  # 保留最近 N 条 Bash 摘要

# Claude Code 真实 background tool_response 是 dict {stdout, stderr, backgroundTaskId, ...}
# 老 marker regex（扫字面 "Command running in background..."）只在文档/示例字面里出现，
# 真实 hook payload 用不上。改成从 dict 提取 backgroundTaskId + 从 command 解析 > 重定向。

# shell stdout 重定向 — `cmd > /path` / `cmd >> /path` 提取目标
# 要求 `>` 前是开头或空白，避开 `2>` `3>` fd 重定向；后面是路径字符
_REDIRECT_RE = re.compile(r"(?:^|\s)>{1,2}\s*([/.\w][^\s|;&]*)")


def _normalize_path(file_path: str) -> str:
    """规范化文件路径用于 read/edit set 比较 — 让 './foo.py' / 'foo.py' /
    '/abs/foo.py' / '~/foo.py' 等价（仅当指向同一文件时）。

    用 abspath 解相对 + 用户目录展开。失败（特殊字符 / OSError）时保留原值。
    """
    if not file_path:
        return file_path
    try:
        import os.path
        return os.path.abspath(os.path.expanduser(file_path))
    except (OSError, ValueError):
        return file_path


def _parse_redirect_target(command: str) -> str | None:
    """从 shell 命令解析最后一个 stdout 重定向路径。

    `cmd > /tmp/x.log 2>&1` → /tmp/x.log
    没重定向返回 None。
    """
    matches = _REDIRECT_RE.findall(command)
    paths = [m for m in matches if not m.startswith("&")]
    return paths[-1] if paths else None

# 测试通过信号 — 出现 N passed / all green / 全绿勾
_PASS_RE = re.compile(
    r"\b\d+\s+passed\b|\ball\s+tests?\s+pass(?:ed)?\b|\ball\s+green\b|✓",
    re.IGNORECASE,
)

# 测试失败信号 — 精确匹配（不要单独的 'error' / 'traceback' 子串，假阳性高）
# - "N failed" (N>=0) pytest 风格计数
# - "FAILED test_x" pytest 单测失败行（行首或空白后）
# - "FAILURES" 章节标题
# - "Traceback (most recent call last)" 真 Python traceback
# - AssertionError / RuntimeError / ImportError 等明确失败异常
# - 行首 "ERROR:" / "FATAL:" 前缀（go test / cargo / 自家测试常见）
# - "N error(s)" 计数 N>=1（明确区分 "0 errors"）
_FAIL_RE = re.compile(
    r"\b\d+\s+failed\b"
    r"|(?:^|\n)FAILED\s"
    r"|\bFAILURES?\b"
    r"|Traceback\s*\(most\s+recent\s+call\s+last\)"
    r"|\b(?:AssertionError|RuntimeError|ImportError)\b"
    r"|(?:^|\n)\s*(?:ERROR|FATAL)\s*:"
    r"|\b[1-9]\d*\s+errors?\b",
    re.IGNORECASE | re.MULTILINE,
)

_TEST_CMD_RE = re.compile(
    r"\b(pytest|jest|cargo test|go test|npm test|tox|mocha|vitest|rspec|phpunit)\b",
    re.IGNORECASE,
)

# v0.6.1: 非代码 edit 路径豁免 — record_edit 不更新 last_edit_ts.
# 真根因（issue #1 dogfooding 真复现）: has_recent_test_pass 语义是
# `last_test_pass_ts >= last_edit_ts`, 测试通过后改 README/docs/.gitignore
# 等非代码文件也无差别让 has_recent_test_pass 翻 False, 导致 git commit
# 被 loud-failure-with-evidence 误拦. 真业务代码改了仍按设计该重测.
#
# 豁免清单（cross-language 通用）:
# - 文档: .md / .rst / .txt / .markdown / .adoc
# - 元数据: .gitignore / .gitattributes / .editorconfig
# - 顶级配置 / 文档目录: docs/ / .github/ / 仓库根的 README / CHANGELOG / LICENSE / CONTRIBUTING
# 不豁免: src/*.py / tests/*.py / *.yaml (生产配置改动该重测) / *.toml (build config) 等
_NON_CODE_EDIT_RE = re.compile(
    r"\.(?:md|rst|txt|markdown|adoc|gitignore|gitattributes|editorconfig)$"
    r"|/(?:docs|\.github)/"
    r"|/(?:CHANGELOG|README|LICENSE|CONTRIBUTING|CODE_OF_CONDUCT|SECURITY|HANDOFF)(?:\.\w+)?$",
    re.IGNORECASE,
)


def _is_non_code_edit_path(file_path: str) -> bool:
    """文档 / 元数据 / 顶级文本文件 edit 不该让 has_recent_test_pass 翻 False."""
    if not file_path:
        return False
    return bool(_NON_CODE_EDIT_RE.search(file_path))


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
    # v0.4.34 子 Agent 独立架构：agent_id 区分主/子 Agent state 文件路径
    # 主 Agent agent_id=None（state 文件名 <session_id>.json）
    # 子 Agent agent_id=<uuid>（state 文件名 <session_id>__<agent_id>.json）
    # 子 Agent state 在 SubagentStop 时被 purge_subagent_state 销毁
    agent_id: str | None = None
    # v0.4.35 模型自适应阈值：当前 Agent 模型 ID（如 claude-opus-4-7）
    # SessionStart hook 从 payload.model 写入主 state（v0.4.36 修：只 SessionStart
    # payload 真有 model，PreToolUse / PostToolUse 等都没）。中段 sticky 注入用
    # model_threshold.threshold_for_model(state.model) 按真模型阈值（Opus 80K /
    # Sonnet 60K / Haiku 30K / 未知 fallback 60K）。
    model: str | None = None
    # v0.4.37 子 Agent model 真捕获：主 Agent 派子 Agent 时 PreToolUse(tool_name=
    # "Agent") payload tool_input 真含 model 字段（manual run 实验真验证）。
    # karma 主 PreToolUse 把 model 入队 pending_subagent_models，SubagentStart
    # 触发时 pop 队首写子 Agent state.model。并行 Task 按 FIFO 队列对应（dogfooding
    # 验证 SubagentStart 触发顺序跟 PreToolUse 入队顺序一致）。
    pending_subagent_models: list[str] = field(default_factory=list)
    read_files: set[str] = field(default_factory=set)         # 本 session Read 过的 file_path
    edit_files: list[str] = field(default_factory=list)        # Edit/Write 顺序记录（重复也保留）
    recent_bash: list[BashSnapshot] = field(default_factory=list)
    last_test_pass_ts: float = 0.0   # 最近一次测试通过的时间戳（0 = 从未通过）
    last_edit_ts: float = 0.0        # 最近一次代码 Edit/Write 的时间戳（0 = 本 session 未改代码）
    # background 任务 pending list — 启动时无真实输出，等下次 hook 触发 catchup 读 output file
    pending_bg_tasks: list[dict] = field(default_factory=list)
    # session 内 turn 序号 — user_prompt_submit hook 每次 +1
    # 用于按 turn 距离统计漂移（不是人类时钟，对 Agent 注意力更准）
    turn_count: int = 0
    # Stop hook 本 turn 累积 block 次数 — 防 keep-pushing 干预死循环
    # 每个 user_prompt_submit 重置 0；累积 ≥ max 后 Stop hook 放 Agent 停
    stop_block_count: int = 0
    # v0.4.32 中段注入 token 启发式（锚定刷新阈值，不是「衰减阈值」）：
    # tool_byte_seq 累积主 Agent 真看到的 tool_input + tool_response 字节数
    # （估算 token = bytes // 3，粗略中英文混合）。每个 PostToolUse +=
    # _estimate_tokens(...)。每 turn 起手 user_prompt_submit hook 重置 0。
    # last_reinject_byte_seq 跟踪「上次中段注入时的累积值」— 累积差 >= 阈值
    # （sticky.yaml reinject_every_n_tokens 默认 8000）下个 PostToolUse 注入。
    #
    # 设计意图（v0.4.34 叙事对齐 — web 调研真验证）:
    # 当代 Claude Sonnet/Opus 4.6 真衰减拐点是 70K-200K（不是 8K）。Anthropic
    # 200K 是原生可靠边界。8K 阈值不是「模型开始忘」的判据，是「sticky 在
    # attention 里被新上下文稀释到该重新锚定」的判据 — 真价值是抗稀释不是
    # 抗遗忘。Liu 2023 的 8K 衰减数据来自 GPT-3.5/Claude-1.3 旧模型时代，
    # 拿来撑当代模型阈值依据是错的，但 8K 抗稀释频率在工程层仍合理。
    tool_byte_seq: int = 0
    last_reinject_byte_seq: int = 0

    def has_read(self, file_path: str) -> bool:
        return _normalize_path(file_path) in self.read_files

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
            self.read_files.add(_normalize_path(file_path))

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
        if not file_path:
            return
        self.edit_files.append(_normalize_path(file_path))
        # v0.6.1: 非代码 edit (README / docs / .gitignore 等) 不推 last_edit_ts.
        # 否则 docker pytest 1190 passed 后改 README 再 commit 会被 evidence
        # check 误拦 (issue #1 真复现根因). 业务代码 edit 仍正常推, 设计 by
        # intent 让「改完没重测」拦截保留.
        if _is_non_code_edit_path(file_path):
            return
        self.last_edit_ts = self._next_ts()

    def record_bash(self, command: str, output, run_in_background: bool = False,
                    force_ts: float | None = None) -> None:
        """force_ts: catchup 用 log file mtime 强制 ltp = mtime，避免多次 catchup
        通过 _next_ts(max(ltp, le)+epsilon) 把 ltp 推到 future 的 race。"""
        if not command:
            return
        is_test = bool(_TEST_CMD_RE.search(command))

        # Claude Code 真实 tool_response 是 dict {stdout, stderr, backgroundTaskId, ...}
        # 老协议 / 同步直传 string 也要兼容
        if isinstance(output, dict):
            stdout = str(output.get("stdout", "") or "")
            stderr = str(output.get("stderr", "") or "")
            out_str = stdout if not stderr else (stdout + "\n" + stderr)
        else:
            out_str = str(output or "")

        # background 任务启动 — stdout/stderr 是空的，真实输出在用户重定向文件
        # 推 pending 等 catchup 读重定向目标文件
        if run_in_background:
            redirect_target = _parse_redirect_target(command)
            if redirect_target:
                self.pending_bg_tasks.append({
                    "cmd": command[:200],
                    "output_file": redirect_target,
                    "started_ts": time.time(),
                })
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
        # 测试通过 → 推进 last_test_pass_ts
        # catchup 用 force_ts (log file mtime) 设定，避免重复 catchup race
        # 正常路径用 _next_ts (严格大于 last_edit_ts，分清先后)
        if is_test and passed and not failed:
            if force_ts is not None:
                # catchup 路径：只在 force_ts > 当前 ltp 时推（不倒退也不重复推 future）
                if force_ts > self.last_test_pass_ts:
                    self.last_test_pass_ts = force_ts
            else:
                self.last_test_pass_ts = self._next_ts()
        # 保留最近 N 条
        self.recent_bash = self.recent_bash[-MAX_RECENT_BASH:]

    def catchup_pending_bg(self) -> int:
        """扫 pending_bg_tasks — 文件存在且非空就读取并 record_bash。

        返回成功 catch-up 的任务数。文件还没出现的保留在 pending。

        task #8.1（dogfooding 观察的 race condition）：
        - 处理后 pending entry 应该从 pending_bg_tasks 移除 (still_pending 没含)
        - 但若多个 hook 几乎同时跑（如 cat 命令 PostToolUse + 紧跟 git commit
          PreToolUse），两个 hook 都 load 旧 state → 都跑 catchup → 都处理同一
          entry → 都 record_bash → ltp 被推到 _next_ts() max(ltp, le) + epsilon
        - 实际 race 表现：手动 update ltp 到 future 后，下次 hook 把 ltp 拉回
          到 max(已 update ltp, le) + epsilon — 即 ltp >= le + epsilon
          但小于 update 的 future 值
        - TODO（已知边界）：极少数情况下多 hook 同时跑会让 ltp 时序略偏，
          但 has_recent_test_pass 用 ltp >= le 比较，偏移在 epsilon 量级
          不影响实际判定。要彻底消除可加 atomic file lock。
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
            # 用普通 record_bash 路径处理 + force_ts=log mtime 防 race
            # 多次 catchup 同一 log → ltp 永远 = mtime 不倒退也不重复推 future
            try:
                log_mtime = p.stat().st_mtime
            except OSError:
                log_mtime = None
            self.record_bash(cmd, output, force_ts=log_mtime)
            caught_up += 1
        self.pending_bg_tasks = still_pending
        return caught_up


def _state_path(session_id: str, base_dir: Path | None = None, agent_id: str | None = None) -> Path:
    """计算 state 文件路径。

    v0.4.34（用户「子 Agent 独立 karma 监控」架构）：agent_id 给的话 path 加
    `__<agent_id>` 后缀让子 Agent 有独立 state 文件不污染主 session。
    主 Agent (agent_id=None) 路径不变保持向后兼容。
    """
    base = base_dir or DEFAULT_DIR
    # session_id / agent_id 可能含 /，清洗成单文件名安全字符
    safe_sid = re.sub(r"[^\w.-]", "_", session_id) or "default"
    if agent_id:
        safe_aid = re.sub(r"[^\w.-]", "_", agent_id)
        return base / f"{safe_sid}__{safe_aid}.json"
    return base / f"{safe_sid}.json"


def load(session_id: str, base_dir: Path | None = None, agent_id: str | None = None) -> SessionState:
    """加载 session 状态。文件不存在 → 返回空 state。

    v0.4.34：agent_id 给的话加载子 Agent 独立 state（不污染主 session）。
    """
    p = _state_path(session_id, base_dir, agent_id=agent_id)
    if not p.exists():
        return SessionState(session_id=session_id, agent_id=agent_id)
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return SessionState(session_id=session_id, agent_id=agent_id)
    state = SessionState(
        session_id=session_id,
        agent_id=agent_id,
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
        turn_count=int(d.get("turn_count", 0) or 0),
        stop_block_count=int(d.get("stop_block_count", 0) or 0),
        tool_byte_seq=int(d.get("tool_byte_seq", 0) or 0),
        last_reinject_byte_seq=int(d.get("last_reinject_byte_seq", 0) or 0),
        model=d.get("model") or None,
        pending_subagent_models=list(d.get("pending_subagent_models", []) or []),
    )
    return state


def get_current_session_id(base_dir: Path | None = None) -> str | None:
    """从 session-state 目录读最新 mtime 文件的 session_id，作为「当前活跃 session」。

    比从 violations.jsonl 推「最后一条违反所在 session」更权威 — 当前 session
    可能完全没产生违反，但 session-state 文件每 turn 都写入，mtime 总是最新。

    排除子 Agent state（文件名含 `__<agent_id>` 后缀），只取主 Agent session。

    base_dir 不存在 / 目录为空 / OSError → 返回 None（调用方按需 fallback）。
    """
    base = base_dir or DEFAULT_DIR
    if not base.exists():
        return None
    try:
        files = [p for p in base.glob("*.json") if "__" not in p.stem]
    except OSError:
        return None
    if not files:
        return None
    try:
        latest = max(files, key=lambda p: p.stat().st_mtime)
    except OSError:
        return None
    return latest.stem


def purge_subagent_state(session_id: str, agent_id: str, base_dir: Path | None = None) -> bool:
    """SubagentStop 时销毁子 Agent 临时 state（v0.4.34 子 Agent 独立架构）。

    返回 True 真删了文件，False 文件不存在。失败抛 OSError 让调用方决定如何处理。
    """
    if not agent_id:
        return False
    p = _state_path(session_id, base_dir, agent_id=agent_id)
    if not p.exists():
        return False
    p.unlink()
    return True


def purge_old_states(max_age_days: int = 30, base_dir: Path | None = None) -> int:
    """删 base_dir 下 mtime 老于 max_age_days 的 session-state json 文件。

    返回删除数量。base_dir 不存在返回 0。
    每 turn user_prompt_submit hook 调一次，避免 session-state 长期累积。
    """
    base = base_dir or DEFAULT_DIR
    if not base.exists():
        return 0
    cutoff = time.time() - max_age_days * 86400
    deleted = 0
    try:
        files = list(base.glob("*.json"))
    except OSError:
        return 0
    for p in files:
        try:
            if p.stat().st_mtime < cutoff:
                p.unlink()
                deleted += 1
        except OSError:
            continue
    return deleted


def save(state: SessionState, base_dir: Path | None = None) -> None:
    """保存 session 状态（atomic rewrite）。v0.4.34 透传 state.agent_id 到路径。"""
    p = _state_path(state.session_id, base_dir, agent_id=state.agent_id)
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
        "turn_count": state.turn_count,
        "stop_block_count": state.stop_block_count,
        "tool_byte_seq": state.tool_byte_seq,
        "last_reinject_byte_seq": state.last_reinject_byte_seq,
        "model": state.model,
        "pending_subagent_models": state.pending_subagent_models,
    }
    # tmp 名加 pid + nanosecond 避免并发 PostToolUse 同 session 写冲突
    import os
    tmp = p.parent / f"{p.stem}.{os.getpid()}.{time.time_ns()}.json.tmp"
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)
