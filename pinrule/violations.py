"""violations.jsonl 读写 + 违反检测。

violations.jsonl 是 append-only 文件，每行一条 JSON：
{"ts": int, "session_id": str, "rule_id": str, "trigger": str, "snippet": str}

向后兼容：读 jsonl 时支持老 ``sticky_id`` 字段 (v0.5.0 前格式)，自动映射到
``rule_id``。新写入只用 ``rule_id``。
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

from pinrule.rule import Rule

from pinrule.paths import pinrule_home

DEFAULT_PATH = pinrule_home() / "violations.jsonl"
RECENT_WINDOW_SEC = 24 * 3600  # 24h 内的违反在 sticky 注入时标 ⚠️
SNIPPET_RADIUS = 30  # 触发词前后多少字符当 snippet

# rotation 配置 — 当前 jsonl 超 MAX_LINES 行 → 重命名为 .1，保留最多 KEEP_HISTORY 个历史
MAX_LINES = 5000
KEEP_HISTORY = 3


@dataclass(slots=True, frozen=True)
class Violation:
    ts: int
    session_id: str
    rule_id: str
    trigger: str
    snippet: str
    turn: int = 0  # session 内 turn 序号（user_prompt_submit 每次 +1）。
                   # 0 = 旧记录 / unknown，新写入应填实际 turn。
    # v0.4.34 子 Agent 独立架构：agent_id None=主 Agent / uuid=子 Agent
    # 主 violations.jsonl 含全部违反（不分文件 — 历史 audit 可见全 picture），
    # audit / stats 默认只看 agent_id is None（主 Agent 违反，不算子 Agent 噪音）
    agent_id: str | None = None
    # v0.5.7: locale-agnostic i18n key — audit/stats 用它分组，避免 zh/en locale
    # 切换后同行为被算成两组. 老 jsonl 行无 trigger_key 字段读取 fallback ""，
    # audit 在缺 key 时 fallback 按 trigger 字面分组保证兼容.
    trigger_key: str = ""

    def to_json(self) -> str:
        d: dict[str, object] = {
            "ts": self.ts,
            "session_id": self.session_id,
            "rule_id": self.rule_id,
            "trigger": self.trigger,
            "snippet": self.snippet,
            "turn": self.turn,
        }
        # agent_id 只在子 Agent 触发时写（None 不写省 jsonl 体积 + 向后兼容）
        if self.agent_id:
            d["agent_id"] = self.agent_id
        # trigger_key 只在非空时写（老格式无此字段, 写空字符串无意义浪费空间）
        if self.trigger_key:
            d["trigger_key"] = self.trigger_key
        return json.dumps(d, ensure_ascii=False)


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
    rule_list: list[Rule],
    session_id: str = "unknown",
    now: int | None = None,
    turn: int = 0,
    agent_id: str | None = None,
) -> list[Violation]:
    """扫 response 看违反哪些 rule。

    简单 substring 匹配（不区分大小写）。同一 rule 多关键词命中只记第一个。
    turn = session 内 turn 序号，用于按 turn 距离统计漂移（不是人类时钟）。
    agent_id = 子 Agent uuid（v0.4.34），主 Agent None；写进 Violation.agent_id
    用于 audit 区分主/子 Agent 违反。
    """
    if not response or not rule_list:
        return []
    now = now or int(time.time())
    response_lower = response.lower()
    out: list[Violation] = []
    for r in rule_list:
        for kw in r.violation_keywords:
            idx = response_lower.find(kw.lower())
            if idx < 0:
                continue
            start = max(0, idx - SNIPPET_RADIUS)
            end = min(len(response), idx + len(kw) + SNIPPET_RADIUS)
            # v0.16.10: 真填 trigger_key — 让 audit/stats locale-agnostic 分组
            # (rule_id + 关键词 index) 真生效. 之前 detect() 永远不填, i18n 分组
            # 系统打从 v0.5.7 就空跑 (round-3 audit 视角 11 #1).
            try:
                kw_idx = r.violation_keywords.index(kw)
                trigger_key_val = f"{r.id}#kw{kw_idx}"
            except (ValueError, AttributeError):
                trigger_key_val = ""
            out.append(Violation(
                ts=now,
                session_id=session_id,
                rule_id=r.id,
                trigger=kw,
                trigger_key=trigger_key_val,
                snippet=_sanitize_snippet(response[start:end]),
                turn=turn,
                agent_id=agent_id,
            ))
            break  # 同一 rule 多关键词命中只记第一个
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
    """append 违反到 jsonl。超阈值自动 rotate（阈值从 pinrule.config 读）。
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
        from pinrule.config import load as _load_config
        cfg = _load_config()
        rotate_if_needed(path, max_lines=cfg["violations_max_lines"], keep=cfg["violations_keep_history"])
    except Exception:
        rotate_if_needed(path)  # config 加载失败 fallback 用 module-level defaults


def _scan_tail_jsonl(path: Path, tail_lines: int):
    """真 tail 读 jsonl 尾部 N 行（不是 read_text + 切片），逐行 yield 解析 dict。

    用 `collections.deque(f, maxlen=N)` 流式只保留尾部 N 行，避免大文件
    全文件读入内存。当前 rotation 阈值 5000 行内差异不大，但消除潜在隐患。
    解析失败的行静默跳过。
    """
    if not path.exists():
        return
    try:
        from collections import deque
        with path.open(encoding="utf-8") as f:
            tail = deque(f, maxlen=tail_lines)
    except OSError:
        return
    for line in tail:
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def extract_rule_id(d: dict) -> str:
    """读 violation dict 的 rule_id 字段，向后兼容老 ``sticky_id`` 字段。

    v0.5.0 改名 sticky → rule 后，新写入 jsonl 用 rule_id；老 jsonl 行仍用
    sticky_id。读取时优先 rule_id fallback sticky_id 保证兼容。
    """
    return d.get("rule_id") or d.get("sticky_id", "")


# 内部别名 — module 内多处调用
_extract_rule_id = extract_rule_id


def _extract_turn(d: dict) -> int | None:
    """读 violation dict 的 turn 字段。

    老格式（turn 维度引入前）无 turn key → 返回 None 让调用方跳过；
    不要用 `.get('turn', 0)` fallback 0，否则落入当前 turn 窗口造成假阳。
    """
    turn_raw = d.get("turn")
    if turn_raw is None:
        return None
    try:
        return int(turn_raw)
    except (ValueError, TypeError):
        return None


def recent(
    path: Path | None = None,
    window_sec: int = RECENT_WINDOW_SEC,
    now: int | None = None,
    tail_lines: int = 500,
) -> dict[str, int]:
    """返回最近违反过的 rule_id → 最近 ts dict（按人类时钟）。"""
    if path is None:
        path = DEFAULT_PATH
    now = now or int(time.time())
    cutoff = now - window_sec
    out: dict[str, int] = {}
    for d in _scan_tail_jsonl(path, tail_lines):
        try:
            ts = int(d.get("ts", 0))
        except (ValueError, TypeError):
            continue
        sid = _extract_rule_id(d)
        if ts >= cutoff and sid:
            out[sid] = max(out.get(sid, 0), ts)
    return out


def count_recent(
    path: Path | None = None,
    window_sec: int = 1800,
    now: int | None = None,
    tail_lines: int = 500,
) -> dict[str, int]:
    """返回 window_sec 内每条 rule_id 的违反**次数**（按人类时钟）。"""
    if path is None:
        path = DEFAULT_PATH
    now = now or int(time.time())
    cutoff = now - window_sec
    out: dict[str, int] = {}
    for d in _scan_tail_jsonl(path, tail_lines):
        try:
            ts = int(d.get("ts", 0))
        except (ValueError, TypeError):
            continue
        sid = _extract_rule_id(d)
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
    """返回**本 session** 最近 window_turns 内违反过的 rule_id → 最近 turn dict。

    跟 recent() 区别：按 turn 距离而不是 ts。这是「Agent 漂移」的对应视角 —
    漂移按 turn 累积，不按人类时钟（用户去开会 30 分钟回来 Agent 状态没变）。
    """
    if path is None:
        path = DEFAULT_PATH
    # v0.9.13 fix off-by-one: 之前 cutoff = current_turn - window_turns 让
    # turn >= cutoff 匹配 [cur-window, cur] 共 window+1 个 turn，跟 config.json
    # 用户面文案「最近 N turn 内」字面意思（N 个 turn）不一致。force_block
    # 累积阈值会被多 1 turn 历史误算 → 假阳干预。Now 真匹配 N 个 turn：
    # cutoff = current - (window - 1) 让 [cur-(window-1), cur] 共 window 个 turn.
    cutoff_turn = current_turn - (window_turns - 1)
    out: dict[str, int] = {}
    for d in _scan_tail_jsonl(path, tail_lines):
        if d.get("session_id") != session_id:
            continue
        sid = _extract_rule_id(d)
        if not sid:
            continue
        turn = _extract_turn(d)
        if turn is None:
            continue
        if turn >= cutoff_turn:
            out[sid] = max(out.get(sid, 0), turn)
    return out


def session_violations(
    session_id: str,
    path: Path | None = None,
    tail_lines: int = 5000,
) -> dict[str, int]:
    """返回本 session **全程累积**违反过的 rule_id → 最近 turn dict (v0.13.0).

    跟 recent_turns 区别: 没 turn window 限制, session 起始到现在所有违反都算入.
    用于 UserPromptSubmit anchor v0.13.0 改造 — 只在 anchor 里列本 session 内
    真正违反过的规则, 不再每 turn 全列 sticky id list (那部分 sessionStart
    baseline 已覆盖, 全列是 prompt-cache 累积 token 浪费).

    tail_lines 给 5000 因 long session 累积 violation 可能多 (500-turn dogfood
    累积 100+ violation 真实场景), 比 recent_turns 的 500 大一个数量级.
    """
    if path is None:
        path = DEFAULT_PATH
    out: dict[str, int] = {}
    for d in _scan_tail_jsonl(path, tail_lines):
        if d.get("session_id") != session_id:
            continue
        sid = _extract_rule_id(d)
        if not sid:
            continue
        turn = _extract_turn(d)
        if turn is None:
            continue
        out[sid] = max(out.get(sid, 0), turn)
    return out


def count_recent_turns(
    session_id: str,
    current_turn: int,
    window_turns: int = 3,
    path: Path | None = None,
    tail_lines: int = 500,
) -> dict[str, int]:
    """返回本 session 最近 window_turns 内每条 rule_id 的违反**次数**。

    用于累积警报按 turn 判定（如 3 turn 内同一规则 ≥ 3 次升级严重度）。
    """
    if path is None:
        path = DEFAULT_PATH
    # v0.9.13 fix off-by-one: 跟 recent_turns 同步收紧到真 N turn 窗口
    # （之前 cutoff = current - window 让窗口实际是 N+1 个 turn，stop hook
    # force_block / escalation 阈值会被多 1 turn 历史误算 → 假阳干预）
    cutoff_turn = current_turn - (window_turns - 1)
    out: dict[str, int] = {}
    for d in _scan_tail_jsonl(path, tail_lines):
        if d.get("session_id") != session_id:
            continue
        sid = _extract_rule_id(d)
        if not sid:
            continue
        turn = _extract_turn(d)
        if turn is None:
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
            rid = _extract_rule_id(d)
            if not rid:
                continue  # 没 rule_id / sticky_id → 跳过无效行
            out.append(Violation(
                ts=int(d["ts"]),
                session_id=d.get("session_id", "unknown"),
                rule_id=rid,
                trigger=d.get("trigger", ""),
                snippet=d.get("snippet", ""),
                turn=int(d.get("turn", 0)),
                # v0.4.34 子 Agent 独立架构：子 Agent 违反写 agent_id 字段
                # v0.9.13 fix: load_all() 之前漏读这个字段，audit/stats 无法
                # 真正按主/子 Agent 分组（to_json 写了但 load 读不到 → 字段往返
                # 不对称）。Now properly read back，default None 跟 to_json 一致
                # （主 Agent agent_id=None 时 to_json 不写 → load 也得 None）。
                agent_id=d.get("agent_id"),
                trigger_key=d.get("trigger_key", ""),  # v0.5.7: 老格式无字段 → ""
            ))
        except (json.JSONDecodeError, KeyError, ValueError):
            continue
    return out
