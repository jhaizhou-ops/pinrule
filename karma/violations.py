"""violations.jsonl 读写 + 违反检测。

violations.jsonl 是 append-only 文件，每行一条 JSON：
{"ts": int, "session_id": str, "sticky_id": str, "trigger": str, "snippet": str}
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

from karma.sticky import Sticky

DEFAULT_PATH = Path.home() / ".claude" / "karma" / "violations.jsonl"
RECENT_WINDOW_SEC = 24 * 3600  # 24h 内的违反在 sticky 注入时标 ⚠️
SNIPPET_RADIUS = 30  # 触发词前后多少字符当 snippet

# rotation 配置 — 当前 jsonl 超 MAX_LINES 行 → 重命名为 .1，保留最多 KEEP_HISTORY 个历史
MAX_LINES = 5000
KEEP_HISTORY = 3


@dataclass(slots=True, frozen=True)
class Violation:
    ts: int
    session_id: str
    sticky_id: str
    trigger: str
    snippet: str
    turn: int = 0  # session 内 turn 序号（user_prompt_submit 每次 +1）。
                   # 0 = 旧记录 / unknown，新写入应填实际 turn。

    def to_json(self) -> str:
        return json.dumps({
            "ts": self.ts,
            "session_id": self.session_id,
            "sticky_id": self.sticky_id,
            "trigger": self.trigger,
            "snippet": self.snippet,
            "turn": self.turn,
        }, ensure_ascii=False)


def _sanitize_snippet(s: str, max_len: int = 120) -> str:
    """snippet 脱敏 — 用户分享 violations.jsonl 排查时减少隐私泄漏。

    - /Users/<name>/ → ~/    （macOS）
    - /home/<name>/ → ~/     （Linux）
    - 长度上限 max_len（避免响应正文整段进入记录）
    - 换行折叠成空格（一行 jsonl 友好）
    """
    s = re.sub(r"/Users/[^/\s]+", "~", s)
    s = re.sub(r"/home/[^/\s]+", "~", s)
    s = s.replace("\n", " ").replace("\r", " ")
    if len(s) > max_len:
        s = s[: max_len - 1] + "…"
    return s


def detect(
    response: str,
    sticky_list: list[Sticky],
    session_id: str = "unknown",
    now: int | None = None,
    turn: int = 0,
) -> list[Violation]:
    """扫 response 看违反哪些 sticky。

    简单 substring 匹配（不区分大小写）。同一 sticky 多关键词命中只记第一个。
    turn = session 内 turn 序号，用于按 turn 距离统计漂移（不是人类时钟）。
    """
    if not response or not sticky_list:
        return []
    now = now or int(time.time())
    response_lower = response.lower()
    out: list[Violation] = []
    for s in sticky_list:
        for kw in s.violation_keywords:
            idx = response_lower.find(kw.lower())
            if idx < 0:
                continue
            start = max(0, idx - SNIPPET_RADIUS)
            end = min(len(response), idx + len(kw) + SNIPPET_RADIUS)
            out.append(Violation(
                ts=now,
                session_id=session_id,
                sticky_id=s.id,
                trigger=kw,
                snippet=_sanitize_snippet(response[start:end]),
                turn=turn,
            ))
            break  # 同一 sticky 多关键词命中只记第一个
    return out


def _rotation_path(base: Path, index: int) -> Path:
    """构造 rotation 文件名 violations.jsonl.{N} — with_name 而非 with_suffix
    （with_suffix 对多扩展名表现不对）。"""
    return base.with_name(base.name + f".{index}")


def rotate_if_needed(
    path: Path | None = None,
    max_lines: int | None = None,
    keep: int | None = None,
) -> bool:
    """如果 path 行数超过 max_lines，rotate：
    1) 删 path.{keep} (最老的)
    2) path.{keep-1} → path.{keep}, ..., path.1 → path.2
    3) path → path.1
    返回是否真的 rotate 了。"""
    if path is None:
        path = DEFAULT_PATH
    if max_lines is None:
        max_lines = MAX_LINES
    if keep is None:
        keep = KEEP_HISTORY
    if not path.exists():
        return False
    try:
        with path.open("rb") as f:
            n_lines = sum(1 for _ in f)
    except OSError:
        return False
    if n_lines < max_lines:
        return False
    # rotate 从最老往新走
    for i in range(keep, 0, -1):
        old = _rotation_path(path, i)
        if not old.exists():
            continue
        if i == keep:
            try:
                old.unlink()
            except OSError:
                pass
        else:
            try:
                old.rename(_rotation_path(path, i + 1))
            except OSError:
                pass
    try:
        path.rename(_rotation_path(path, 1))
    except OSError:
        return False
    return True


def append(violations: list[Violation], path: Path | None = None) -> None:
    """append 违反到 jsonl。超阈值自动 rotate（阈值从 karma.config 读）。
    path=None 时用 module-level DEFAULT_PATH。"""
    if not violations:
        return
    if path is None:
        path = DEFAULT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for v in violations:
            f.write(v.to_json() + "\n")
    # 从 config 读阈值 — module-level MAX_LINES / KEEP_HISTORY 仍是 fallback default
    try:
        from karma.config import load as _load_config
        cfg = _load_config()
        rotate_if_needed(path, max_lines=cfg["violations_max_lines"], keep=cfg["violations_keep_history"])
    except Exception:
        rotate_if_needed(path)  # config 加载失败 fallback 用 module-level defaults


def recent(
    path: Path | None = None,
    window_sec: int = RECENT_WINDOW_SEC,
    now: int | None = None,
    tail_lines: int = 500,
) -> dict[str, int]:
    """返回最近违反过的 sticky_id → 最近 ts dict。

    只读尾部 N 行（违反频率不会太高，500 行够）。
    """
    if path is None:
        path = DEFAULT_PATH
    if not path.exists():
        return {}
    now = now or int(time.time())
    cutoff = now - window_sec
    out: dict[str, int] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-tail_lines:]
    except OSError:
        return {}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
            ts = int(d.get("ts", 0))
            sid = d.get("sticky_id", "")
        except (json.JSONDecodeError, ValueError):
            continue
        if ts >= cutoff and sid:
            out[sid] = max(out.get(sid, 0), ts)
    return out


def count_recent(
    path: Path | None = None,
    window_sec: int = 1800,
    now: int | None = None,
    tail_lines: int = 500,
) -> dict[str, int]:
    """返回 window_sec 内每条 sticky_id 的违反**次数**计数。

    跟 `recent` 区别：recent 返回最新 ts，本函数返回累积 count。
    用于累积警报判定（如 30 分钟内同 sticky ≥ 3 次升级严重度）。
    """
    if path is None:
        path = DEFAULT_PATH
    if not path.exists():
        return {}
    now = now or int(time.time())
    cutoff = now - window_sec
    out: dict[str, int] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-tail_lines:]
    except OSError:
        return {}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
            ts = int(d.get("ts", 0))
            sid = d.get("sticky_id", "")
        except (json.JSONDecodeError, ValueError):
            continue
        if ts >= cutoff and sid:
            out[sid] = out.get(sid, 0) + 1
    return out


def recent_turns(
    session_id: str,
    current_turn: int,
    window_turns: int = 5,
    path: Path | None = None,
    tail_lines: int = 500,
) -> dict[str, int]:
    """返回**本 session** 最近 window_turns 内违反过的 sticky_id → 最近 turn dict。

    跟 recent() 区别：按 turn 距离而不是 ts。这是「Agent 漂移」的对应视角 —
    漂移按 turn 累积，不按人类时钟（用户去开会 30 分钟回来 Agent 状态没变）。
    """
    if path is None:
        path = DEFAULT_PATH
    if not path.exists():
        return {}
    cutoff_turn = current_turn - window_turns
    out: dict[str, int] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-tail_lines:]
    except OSError:
        return {}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
            sid = d.get("sticky_id", "")
            sess = d.get("session_id", "")
            turn_raw = d.get("turn")
            if turn_raw is None:
                # 老格式没 turn 字段（turn 维度引入前）— 跳过，不要 fallback 成 0
                # 让它落入「当前 turn 窗口」造成假阳
                continue
            turn = int(turn_raw)
        except (json.JSONDecodeError, ValueError, TypeError):
            continue
        if sess != session_id or not sid:
            continue
        if turn >= cutoff_turn:
            out[sid] = max(out.get(sid, 0), turn)
    return out


def count_recent_turns(
    session_id: str,
    current_turn: int,
    window_turns: int = 3,
    path: Path | None = None,
    tail_lines: int = 500,
) -> dict[str, int]:
    """返回本 session 最近 window_turns 内每条 sticky_id 的违反**次数**。

    用于累积警报按 turn 判定（如 3 turn 内同 sticky ≥ 3 次升级严重度）。
    """
    if path is None:
        path = DEFAULT_PATH
    if not path.exists():
        return {}
    cutoff_turn = current_turn - window_turns
    out: dict[str, int] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()[-tail_lines:]
    except OSError:
        return {}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
            sid = d.get("sticky_id", "")
            sess = d.get("session_id", "")
            turn_raw = d.get("turn")
            if turn_raw is None:
                # 老格式没 turn 字段（turn 维度引入前）— 跳过，否则 fallback 成 0
                # 会被当前 turn 窗口（可能 cutoff ≤ 0）误数，触发 force_block 假阳
                continue
            turn = int(turn_raw)
        except (json.JSONDecodeError, ValueError, TypeError):
            continue
        if sess != session_id or not sid:
            continue
        if turn >= cutoff_turn:
            out[sid] = out.get(sid, 0) + 1
    return out


def load_all(path: Path | None = None) -> list[Violation]:
    """读全部 violations（CLI stats 用）。"""
    if path is None:
        path = DEFAULT_PATH
    if not path.exists():
        return []
    out: list[Violation] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
            out.append(Violation(
                ts=int(d["ts"]),
                session_id=d.get("session_id", "unknown"),
                sticky_id=d["sticky_id"],
                trigger=d.get("trigger", ""),
                snippet=d.get("snippet", ""),
                turn=int(d.get("turn", 0)),
            ))
        except (json.JSONDecodeError, KeyError, ValueError):
            continue
    return out
