"""Claude Code backend — `~/.claude/settings.json` + `~/.claude/hooks/`。

跟 cli.py 之前内联写死的行为完全一致，仅做 refactor 抽出来。
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from karma.backends._base import SettingsParseError


class ClaudeCodeBackend:
    name = "claude-code"
    display_name = "Claude Code"

    _HOOK_EVENTS: dict[str, str] = {
        "UserPromptSubmit": "user_prompt_submit",
        "PreToolUse": "pre_tool_use",
        "PostToolUse": "post_tool_use",
        "Stop": "stop",
    }

    def client_installed(self) -> bool:
        """`~/.claude/` 目录存在视为装了 Claude Code。也接受 `claude` 命令在 PATH。"""
        import shutil
        return (Path.home() / ".claude").exists() or bool(shutil.which("claude"))

    def hooks_dir(self) -> Path:
        return Path.home() / ".claude" / "hooks"

    def settings_path(self) -> Path:
        return Path.home() / ".claude" / "settings.json"

    def settings_backup_path(self) -> Path:
        return Path.home() / ".claude" / "settings.json.before-karma"

    def hook_events(self) -> dict[str, str]:
        return dict(self._HOOK_EVENTS)

    def build_event_entry(self, hook_name_lower: str, event_name: str) -> dict:
        """Claude Code 的 hook entry 格式。

        Stop / SessionStart / SessionEnd 等不支持 matcher 字段（matcher 字段会被
        Claude Code 无声忽略可能导致 hook 不生效）。只对 PreToolUse / PostToolUse /
        UserPromptSubmit 等工具相关 hook 加 `matcher: "*"`。
        """
        wrapper = self.hooks_dir() / f"karma_{hook_name_lower}.py"
        entry: dict[str, object] = {
            "hooks": [{"type": "command", "command": str(wrapper)}]
        }
        if event_name in ("PreToolUse", "PostToolUse", "UserPromptSubmit"):
            entry["matcher"] = "*"
        return entry

    def is_karma_entry(self, entry: dict) -> bool:
        for h in entry.get("hooks", []):
            if "karma_" in h.get("command", ""):
                return True
        return False

    def load_settings(self) -> dict:
        p = self.settings_path()
        if not p.exists():
            return {}
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise SettingsParseError(
                f"settings.json 解析失败: {e}\n"
                f"路径: {p}\n"
                f"karma 不会覆盖损坏的配置。请手工修复 JSON 后重跑 install-hooks。"
            ) from e

    def save_settings(self, data: dict) -> None:
        """原子写 — tmp + os.replace 防中断 truncate 半文件。"""
        p = self.settings_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + f".karma-tmp.{os.getpid()}")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, p)

    def pre_install_setup(self) -> list[str]:
        """Claude Code 无额外启用步骤 — settings.json hook 配置就够。"""
        return []
