"""violations.jsonl 读写 + 违反检测。

violations.jsonl 是 append-only 文件，每行一条 JSON：
{"ts": int, "session_id": str, "sticky_id": str, "trigger": str, "snippet": str}
"""

from __future__ import annotations

import json
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

    def to_json(self) -> str:
        return json.dumps({
            "ts": self.ts,
            "session_id": self.session_id,
            "sticky_id": self.sticky_id,
            "trigger": self.trigger,
            "snippet": self.snippet,
        }, ensure_ascii=False)


def detect(
    response: str,
    sticky_list: list[Sticky],
    session_id: str = "unknown",
    now: int | None = None,
) -> list[Violation]:
    """扫 response 看违反哪些 sticky。

    简单 substring 匹配（不区分大小写）。同一 sticky 多关键词命中只记第一个。
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
                snippet=response[start:end],
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
    """append 违反到 jsonl。超 MAX_LINES 自动 rotate。
    path=None 时用 module-level DEFAULT_PATH。"""
    if not violations:
        return
    if path is None:
        path = DEFAULT_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for v in violations:
            f.write(v.to_json() + "\n")
    # rotate 用 module-level 配置（测试可 monkeypatch MAX_LINES / KEEP_HISTORY）
    rotate_if_needed(path)


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
            ))
        except (json.JSONDecodeError, KeyError, ValueError):
            continue
    return out
