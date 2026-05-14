"""karma 多 backend 装机抽象 — Claude Code / Codex / 未来其他 AI 编程客户端。

设计哲学：
- hook 入口（karma/hooks/*.py）跟 backend 解耦，靠 stdin payload 字段名兼容
  （Claude Code 跟 Codex 字段大多同名：session_id / prompt / tool_name 等）
- backend 抽象只负责「装机」差异：配置文件路径 / 配置格式 / 是否要启用 feature flag
- karma 状态（violations / session-state / sticky.yaml）跨 backend **共享** —
  ~/.claude/karma/（保留历史路径向后兼容，新装也用这个；未来可加 KARMA_HOME env）

Backend 列表：
- claude-code: ~/.claude/settings.json + ~/.claude/hooks/karma_*.py
- codex: ~/.codex/hooks.json + ~/.codex/hooks/karma_*.py + [features] hooks = true

接口看 `karma/backends/_base.Backend`。
"""

from __future__ import annotations

from karma.backends._base import Backend
from karma.backends.claude_code import ClaudeCodeBackend
from karma.backends.codex import CodexBackend

# 名字 → backend 实例的注册表
REGISTRY: dict[str, Backend] = {
    "claude-code": ClaudeCodeBackend(),
    "codex": CodexBackend(),
}

__all__ = ["Backend", "ClaudeCodeBackend", "CodexBackend", "REGISTRY"]


def detect_installed_backends() -> list[str]:
    """返回本机已装的 client 对应的 backend 名（按 REGISTRY 顺序）。

    用于 `karma install-hooks` 默认行为：检测到啥就装啥（多 client 共存场景）。
    """
    return [name for name, backend in REGISTRY.items() if backend.client_installed()]
