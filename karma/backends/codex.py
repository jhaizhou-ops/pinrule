"""Codex CLI backend — `~/.codex/hooks.json` + 启用 `features.hooks`。

继承 `JsonHooksBackend`，差异：① 配置文件名 `hooks.json` 不是 `settings.json`
② hook entry 加 timeout: 30 ③ pre_install_setup 调 `codex features enable hooks`
跑永久启用 feature flag（Codex 默认禁用 hooks）。

参考：
- 官方 hook 协议: https://developers.openai.com/codex/hooks
- 实测：Codex 0.130 hook 只在 interactive TUI 触发（GitHub issue #17532）
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from karma.backends._json_hooks import JsonHooksBackend


class CodexBackend(JsonHooksBackend):
    name = "codex"
    display_name = "Codex CLI"
    _CONFIG_DIR_NAME = ".codex"
    _SETTINGS_FILENAME = "hooks.json"
    _CLIENT_CMD = "codex"

    # Codex 6 个 event 中 karma 用 4 个跟 Claude Code 对齐。SessionStart /
    # PermissionRequest karma 暂不用 — 需要时也能加到这个 dict。
    _HOOK_EVENTS: dict[str, str] = {
        "UserPromptSubmit": "user_prompt_submit",
        "PreToolUse": "pre_tool_use",
        "PostToolUse": "post_tool_use",
        "Stop": "stop",
    }

    def build_event_entry(self, hook_name_lower: str, event_name: str) -> dict:
        wrapper = self.hooks_dir() / f"karma_{hook_name_lower}.py"
        return {
            "hooks": [{"type": "command", "command": str(wrapper), "timeout": 30}]
        }

    def pre_install_setup(self) -> list[str]:
        """Codex 必须启用 `[features] hooks = true` 才让 hook 触发。

        用 `codex features enable hooks` 命令永久写入 `~/.codex/config.toml`
        （Codex 官方推荐方式 — 不直接编辑 config.toml 避免 TOML 格式错）。
        """
        steps: list[str] = []
        codex_bin = shutil.which("codex")
        if not codex_bin:
            steps.append("⚠️  没找到 codex 命令 — 跳过启用 features.hooks。"
                         "请手动跑 `codex features enable hooks` 后 hook 才会触发。")
            return steps

        if self._is_hooks_feature_enabled():
            steps.append("Codex features.hooks 已启用 ✓")
            return steps

        try:
            result = subprocess.run(
                [codex_bin, "features", "enable", "hooks"],
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )
            if result.returncode == 0:
                steps.append(f"启用 Codex features.hooks: {result.stdout.strip()}")
            else:
                steps.append(f"⚠️  `codex features enable hooks` 失败 (exit "
                             f"{result.returncode})：{result.stderr.strip() or '未知错误'}。"
                             f"请手动跑后 hook 才会触发。")
        except (OSError, subprocess.TimeoutExpired) as e:
            steps.append(f"⚠️  调用 codex 命令异常：{e}。"
                         "请手动 `codex features enable hooks`。")
        return steps

    def skill_install_targets(self, skill_name: str = "karma") -> list[tuple[Path, str]]:
        """Codex Agent Skills 装到 ~/.agents/skills/<name>/SKILL.md (Markdown 原样).

        注意路径是 ~/.agents/ 不是 ~/.codex/ — 这是 OpenAI 的设计 (跟 Anthropic 共享
        `.agents/skills/` 命名空间). 触发: /skills menu 或 $skill_name inline 或 auto.
        """
        return [(Path.home() / ".agents" / "skills" / skill_name / "SKILL.md", "markdown")]

    def _is_hooks_feature_enabled(self) -> bool:
        """读 ~/.codex/config.toml 看 [features] hooks 是不是 true。fail open 当未启用。"""
        config_path = Path.home() / ".codex" / "config.toml"
        if not config_path.exists():
            return False
        try:
            in_features = False
            for line in config_path.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped.startswith("[features"):
                    in_features = True
                    continue
                if stripped.startswith("[") and stripped.endswith("]"):
                    in_features = False
                    continue
                if in_features and stripped.startswith("hooks"):
                    return "true" in stripped.lower()
            return False
        except OSError:
            return False
