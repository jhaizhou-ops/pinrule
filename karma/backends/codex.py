"""Codex CLI backend — `~/.codex/hooks.json` + `~/.codex/hooks/` + 启用 `features.hooks`。

Codex hook 协议跟 Claude Code 几乎一对一（同样 stdin JSON / stdout
`hookSpecificOutput.additionalContext` / 同样 4+ event 名），主要差异：

1. 配置文件 `~/.codex/hooks.json`（独立文件不在 settings 里）
2. 默认禁用 — 必须 `[features] hooks = true` 在 `~/.codex/config.toml`
3. hook 只在 interactive TUI session 触发（`codex exec` 非交互模式不触发 —
   官方 GitHub issue #17532 描述的已知行为）
4. Codex Stop hook 直接给 `last_assistant_message` 字段，karma 不用读 transcript
   反向找最后 assistant message（性能优化）

参考：
- 官方 hook 协议: https://developers.openai.com/codex/hooks
- 配置文件位置: https://developers.openai.com/codex/config-advanced
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from karma.backends._base import SettingsParseError


class CodexBackend:
    name = "codex"
    display_name = "Codex CLI"

    # Codex 6 个 hook event 中 karma 用 4 个跟 Claude Code 对齐（SessionStart /
    # PermissionRequest 暂不用 — karma 不需要 session 启动 hook，权限请求由 PreToolUse
    # 拦截即可）。
    _HOOK_EVENTS: dict[str, str] = {
        "UserPromptSubmit": "user_prompt_submit",
        "PreToolUse": "pre_tool_use",
        "PostToolUse": "post_tool_use",
        "Stop": "stop",
    }

    def client_installed(self) -> bool:
        """检测 codex 命令在 PATH 或 `~/.codex/` 目录存在。"""
        return bool(shutil.which("codex")) or (Path.home() / ".codex").exists()

    def hooks_dir(self) -> Path:
        return Path.home() / ".codex" / "hooks"

    def settings_path(self) -> Path:
        return Path.home() / ".codex" / "hooks.json"

    def settings_backup_path(self) -> Path:
        return Path.home() / ".codex" / "hooks.json.before-karma"

    def hook_events(self) -> dict[str, str]:
        return dict(self._HOOK_EVENTS)

    def build_event_entry(self, hook_name_lower: str, event_name: str) -> dict:
        """Codex hook entry 格式 — 跟 Claude Code 类似但不需要 matcher 字段
        （Codex hook 配置没 matcher 概念，每个 entry 都对该 event 所有 tool 触发）。
        """
        wrapper = self.hooks_dir() / f"karma_{hook_name_lower}.py"
        return {
            "hooks": [
                {"type": "command", "command": str(wrapper), "timeout": 30}
            ]
        }

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
                f"hooks.json 解析失败: {e}\n"
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
        """Codex 必须启用 `[features] hooks = true` 才让 hook 真触发。

        通过 `codex features enable hooks` 命令永久写入 `~/.codex/config.toml`
        （这是 Codex 官方推荐方式 — 不直接编辑 config.toml 避免格式错）。
        """
        steps: list[str] = []
        codex_bin = shutil.which("codex")
        if not codex_bin:
            steps.append("⚠️  没找到 codex 命令 — 跳过启用 features.hooks。"
                         "请手动跑 `codex features enable hooks` 后 hook 才会触发。")
            return steps

        # 检查当前状态 — 已启用就跳过
        if self._is_hooks_feature_enabled():
            steps.append("Codex features.hooks 已启用 ✓")
            return steps

        try:
            import subprocess
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

    def _is_hooks_feature_enabled(self) -> bool:
        """读 ~/.codex/config.toml 看 [features] hooks 是不是 true。fail open 当未启用。"""
        config_path = Path.home() / ".codex" / "config.toml"
        if not config_path.exists():
            return False
        try:
            # 用最简单 line scan 不引 toml 依赖（tomllib 是 py3.11+ 标准库但 toml 写较麻烦）
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
