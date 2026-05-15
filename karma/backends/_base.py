"""Backend 抽象接口 — 描述「把 karma hook 装到一个 AI 编程客户端」需要的能力。

每个 backend 负责：
1. 知道客户端的配置文件路径 / 格式（JSON vs TOML，settings.json vs hooks.json）
2. 知道客户端支持的 hook event 名跟 wrapper basename 的映射
3. 知道如何构造 / 识别一条 karma hook entry
4. 检测客户端是否装在本机（决定 `karma install-hooks` 默认装哪些）
5. 处理客户端特有的启用步骤（如 Codex 的 `[features] hooks = true`）
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class Backend(Protocol):
    """AI 编程客户端 backend 接口。"""

    name: str  # "claude-code" / "codex"
    display_name: str  # "Claude Code" / "Codex CLI"

    def client_installed(self) -> bool:
        """检测本机是否装了该客户端（用于 install-hooks 自动选 backend）。"""
        ...

    def hooks_dir(self) -> Path:
        """放 karma_*.py wrapper 脚本的目录。"""
        ...

    def settings_path(self) -> Path:
        """客户端的 hook 配置文件（Claude Code: settings.json / Codex: hooks.json）。"""
        ...

    def settings_backup_path(self) -> Path:
        """首次 install 时备份原配置到这里。"""
        ...

    def hook_events(self) -> dict[str, str]:
        """支持的 hook event 名 → wrapper basename（snake_case）映射。

        Claude Code 4 个：UserPromptSubmit / PreToolUse / PostToolUse / Stop
        Codex 4 个（同上 — 协议几乎一对一）
        """
        ...

    def build_event_entry(self, hook_name_lower: str, event_name: str) -> dict:
        """构造一条 hook entry，返回写进 settings 的 dict。

        不同 backend 对 matcher 等字段要求可能不同（Claude Code Stop event 不支持
        matcher；Codex 据官方文档也是 matcher 可选）。
        """
        ...

    def is_karma_entry(self, entry: dict) -> bool:
        """判断一条 hook entry 是不是 karma 装的（用 wrapper 路径含 karma_ 前缀识别）。"""
        ...

    def load_settings(self) -> dict:
        """读客户端配置文件，损坏抛 SettingsParseError（绝不静默覆盖用户配置）。"""
        ...

    def save_settings(self, data: dict) -> None:
        """原子写客户端配置文件（tmp + os.replace 防中断 truncate）。"""
        ...

    def pre_install_setup(self) -> list[str]:
        """install-hooks 写 settings 之前的额外步骤（如 Codex 启用 features.hooks）。

        返回给用户看的步骤日志（每条一行）。空 list 表示无额外步骤。
        """
        ...

    def skill_install_targets(self, skill_name: str = "karma") -> list[tuple[Path, str]]:
        """返回该 backend 装 skill 的目标 [(dest_path, content_format), ...].

        content_format: "markdown" (Markdown 原样写) 或 "toml" (Markdown 转 Gemini commands TOML 写).

        例:
        - ClaudeCode: [(~/.claude/skills/karma/SKILL.md, "markdown")]
        - Codex: [(~/.agents/skills/karma/SKILL.md, "markdown")] (注意路径 ~/.agents/ 不是 ~/.codex/)
        - Gemini: [
            (~/.gemini/skills/karma/SKILL.md, "markdown"),     # auto-trigger
            (~/.gemini/commands/karma.toml, "toml"),           # 显式 /karma 触发
          ]
        """
        ...


class SettingsParseError(Exception):
    """配置文件损坏 — 调用方需要 abort 不能静默覆盖。"""
