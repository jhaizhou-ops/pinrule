"""Gemini CLI backend — `~/.gemini/settings.json` 含 `hooks` 字段。

继承 `JsonHooksBackend`，差异：① event 名跟 Claude Code / Codex 完全不同
（BeforeAgent / AfterAgent / BeforeTool / AfterTool）② hook entry 加 timeout: 5000ms
③ 默认启用（不像 Codex 要 feature flag）。

stdin payload 差异：Gemini AfterAgent 直接给 `prompt_response` 字段（跟 Codex
`last_assistant_message` 同概念），karma stop.py 已统一适配。

参考：https://geminicli.com/docs/hooks/reference/
"""

from __future__ import annotations

import json
from pathlib import Path

from karma.backends._json_hooks import JsonHooksBackend


# Gemini → karma canonical tool_name 映射
# Sources: Gemini hooks reference + Gemini CLI 内建 tool 名清单
_GEMINI_TOOL_MAP: dict[str, str] = {
    "run_shell_command": "Bash",
    "read_file": "Read",
    "read_many_files": "Read",  # 多文件读：当 Read 处理（取 file_path 第一个）
    "write_file": "Write",
    "replace": "Edit",
    "edit": "Edit",
    "edit_file": "Edit",
}


class GeminiCLIBackend(JsonHooksBackend):
    name = "gemini-cli"
    display_name = "Gemini CLI"
    _CONFIG_DIR_NAME = ".gemini"
    _SETTINGS_FILENAME = "settings.json"
    _CLIENT_CMD = "gemini"

    # Gemini event 名跟 Claude Code 完全不同 — 但 wrapper basename 保持 karma 内部
    # 规范，让 hook 入口模块（karma/hooks/*.py）跨 backend 完全复用。
    _HOOK_EVENTS: dict[str, str] = {
        "BeforeAgent": "user_prompt_submit",
        "BeforeTool": "pre_tool_use",
        "AfterTool": "post_tool_use",
        "AfterAgent": "stop",
    }

    def build_event_entry(self, hook_name_lower: str, event_name: str) -> dict:
        """Gemini hook entry 加 timeout 5000ms — 跟 vibe-island 已用格式一致。"""
        wrapper = self.hooks_dir() / f"karma_{hook_name_lower}.py"
        return {
            "hooks": [{"type": "command", "command": str(wrapper), "timeout": 5000}]
        }

    def normalize_tool_name(self, raw_tool_name: str, payload: dict) -> str:
        """Gemini tool_name 归一化 — run_shell_command → Bash 等."""
        return _GEMINI_TOOL_MAP.get(raw_tool_name, raw_tool_name)

    def emit_deny(self, reason: str, payload: dict) -> str:
        """Gemini BeforeTool 要求顶层 `{decision: "deny", reason}`（官方文档）.

        跟 Claude/Codex 的 hookSpecificOutput shape 完全不同 — v0.9.15 cross-model
        audit 抓到这条 bug：karma 之前一直输出 Claude shape 让 Gemini 拦截全失效.
        """
        return json.dumps({"decision": "deny", "reason": reason}, ensure_ascii=False)

    def emit_allow(self, payload: dict) -> str:
        """Gemini 默认 allow — 空 dict passthrough，不需要显式 allow shape."""
        return json.dumps({})

    def emit_stop_block(self, reason: str, payload: dict) -> str:
        """Gemini AfterAgent 没 block 概念 — 返 {} 让通用 stop.py 主逻辑 fail-open
        不阻塞 Agent. Stop block 干预在 Gemini 下不适用 (官方协议无对应 shape).
        """
        return json.dumps({})

    def skill_install_targets(self, skill_name: str = "karma") -> list[tuple[Path, str]]:
        """Gemini CLI 装两个 (双轨支持):

        1. ~/.gemini/skills/<name>/SKILL.md — Agent Skills auto-trigger (描述匹配)
        2. ~/.gemini/commands/<name>.toml — 显式 /<name> slash command (用户主动触发)

        2 套并存是 Gemini CLI 2026 设计 (Issue #21760 计划合并但还没 land).
        karma 同时装两份让用户 auto + 显式都能触发, 体验跟 Claude/Codex 对齐.
        TOML 内容从 SKILL.md Markdown body 转换 ($ARGUMENTS → {{args}}).
        """
        gemini_home = Path.home() / ".gemini"
        return [
            (gemini_home / "skills" / skill_name / "SKILL.md", "markdown"),
            (gemini_home / "commands" / f"{skill_name}.toml", "toml"),
        ]
