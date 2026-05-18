"""pinrule 多 backend 装机抽象 — Claude / Codex / Cursor。

设计哲学：
- hook 入口（pinrule/hooks/*.py）跟 backend 解耦，靠 stdin payload 字段名兼容
  （Claude / Codex / Cursor 字段大多同名：session_id / prompt / tool_name 等，
  跨家差异在 backend 层 protocol_adapter 抹平）
- backend 抽象只负责「装机」差异：配置文件路径 / 配置格式 / 是否要启用 feature flag
- pinrule 状态（violations / session-state / rules.json）跨 backend **共享** —
  ~/.pinrule/（v0.14+ 共享规则库；`PINRULE_HOME` env 可覆盖）

Backend 列表：
- claude-code: ~/.claude/settings.json + ~/.claude/hooks/pinrule_*.py (8 events)
- codex: ~/.codex/hooks.json + ~/.codex/hooks/pinrule_*.py + [features] hooks = true (6 events)
- cursor: ~/.cursor/hooks.json + ~/.cursor/hooks/pinrule_*.py (12 events, 1.7+ 需要)

接口看 `pinrule/backends/_base.Backend`。
"""

from __future__ import annotations

from pinrule.backends._base import Backend
from pinrule.backends.claude_code import ClaudeCodeBackend
from pinrule.backends.codex import CodexBackend
from pinrule.backends.cursor import CursorBackend

# 名字 → backend 实例的注册表
REGISTRY: dict[str, Backend] = {
    "claude-code": ClaudeCodeBackend(),
    "codex": CodexBackend(),
    "cursor": CursorBackend(),
}

__all__ = [
    "Backend", "ClaudeCodeBackend", "CodexBackend",
    "CursorBackend", "REGISTRY",
]


def detect_installed_backends() -> list[str]:
    """返回本机已装的 client 对应的 backend 名（按 REGISTRY 顺序）。

    用于 `pinrule install-hooks` 默认行为：检测到啥就装啥（多 client 共存场景）。
    """
    return [name for name, backend in REGISTRY.items() if backend.client_installed()]
