"""karma 配置系统 — 让用户调阈值不用改代码。

读 ~/.claude/karma/config.yaml，缺失字段用 DEFAULTS。
每次调用 load() 实时读（hook 进程 ephemeral，无 cache 担忧）。

字段:
    notify_enabled                  桌面通知开关
    recent_violation_turns          ⚠️ 标记窗口（最近 N turn 内违反过的 sticky 标）
    escalate_window_turns           累积告警窗口（按 turn 距离）
    escalate_threshold              累积告警次数阈值
    violations_max_lines            violations.jsonl 行数上限触发 rotation
    violations_keep_history         保留几个历史 .jsonl 文件
    session_state_max_age_days      session-state json 保留天数
    max_recent_bash                 SessionState 保留最近 Bash 数量
    stop_block_max_per_turn         Stop hook 单 turn 干预上限（防死循环）
    force_block_threshold           累积强制 block 阈值（同 sticky ≥ N 次）
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from karma.paths import karma_home

DEFAULT_PATH = karma_home() / "config.yaml"

DEFAULTS: dict[str, Any] = {
    "notify_enabled": True,
    # 按 turn 距离统计 — Agent 注意力漂移按 turn 累积（不是人类时钟）
    "recent_violation_turns": 5,    # ⚠️ 标记窗口（最近 N turn 内违反过的 sticky 标）
    "escalate_window_turns": 3,     # 累积告警窗口
    "escalate_threshold": 3,        # 累积告警触发次数
    "violations_max_lines": 5000,
    "violations_keep_history": 3,
    "session_state_max_age_days": 30,
    "max_recent_bash": 15,
    # Stop hook keep-pushing 干预上限 — 单 turn 内最多 block N 次让 Agent 继续
    # 累积超阈值后真放 Agent 停（防死循环）。0 = 完全关闭干预。
    "stop_block_max_per_turn": 2,
    # 累积强制 block 阈值 — 同 sticky 违反 ≥ N 次（窗口内） → Stop hook 输出 decision=block
    # 强制 Agent fix 真根因，不允许继续绕（机制 2）。0 = 关闭。
    "force_block_threshold": 5,
}


def load(path: Path | None = None) -> dict[str, Any]:
    """读 config.yaml，缺失字段用 DEFAULTS。

    文件不存在 / 解析失败 → 完全返回 DEFAULTS 副本（fail open）。
    用户配置文件里有不认识的字段 → 忽略（不报错）。
    """
    if path is None:
        path = DEFAULT_PATH
    cfg = dict(DEFAULTS)
    if not path.exists():
        return cfg
    try:
        user_cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError):
        return cfg
    if not isinstance(user_cfg, dict):
        return cfg
    for key in DEFAULTS:
        if key in user_cfg and user_cfg[key] is not None:
            cfg[key] = user_cfg[key]
    return cfg


def get(key: str, path: Path | None = None) -> Any:
    """便捷取单个字段。"""
    return load(path).get(key, DEFAULTS.get(key))
