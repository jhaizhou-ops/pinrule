"""Backend 抽象接口 — 描述「把 pinrule hook 装到一个 AI 编程客户端」需要的能力。

每个 backend 负责：
1. 知道客户端的配置文件路径 / 格式（JSON vs TOML，settings.json vs hooks.json）
2. 知道客户端支持的 hook event 名跟 wrapper basename 的映射
3. 知道如何构造 / 识别一条 pinrule hook entry
4. 检测客户端是否装在本机（决定 `pinrule install-hooks` 默认装哪些）
5. 处理客户端特有的启用步骤（如 Codex 的 `[features] hooks = true`）
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class Backend(Protocol):
    """AI 编程客户端 backend 接口。"""

    name: str  # "claude-code" / "codex"
    display_name: str  # "Claude" / "Codex" / "Cursor"

    def client_installed(self) -> bool:
        """检测本机是否装了该客户端（用于 install-hooks 自动选 backend）。"""
        ...

    def hooks_dir(self) -> Path:
        """放 pinrule_*.py wrapper 脚本的目录。"""
        ...

    def settings_path(self) -> Path:
        """客户端的 hook 配置文件（Claude: settings.json / Codex: hooks.json）。"""
        ...

    def settings_backup_path(self) -> Path:
        """首次 install 时备份原配置到这里。"""
        ...

    def hook_events(self) -> dict[str, str]:
        """支持的 hook event 名 → wrapper basename（snake_case）映射。

        Claude 4 个：UserPromptSubmit / PreToolUse / PostToolUse / Stop
        Codex 4 个（同上 — 协议几乎一对一）
        """
        ...

    def build_event_entry(self, hook_name_lower: str, event_name: str) -> dict:
        """构造一条 hook entry，返回写进 settings 的 dict。

        不同 backend 对 matcher 等字段要求可能不同（Claude Stop event 不支持
        matcher；Codex 据官方文档也是 matcher 可选）。
        """
        ...

    def is_pinrule_entry(self, entry: dict) -> bool:
        """判断一条 hook entry 是不是 pinrule 装的（用 wrapper 路径含 pinrule_ 前缀识别）。"""
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

    def post_install_message(self) -> list[str]:
        """install-hooks 全部写完后的「**响亮警示 + 操作步骤**」（v0.9.17 引入）。

        Codex 0.130+ 安全模型要求每个 hook 在 TUI `/hooks` 命令里被用户手动 approve
        才生效 — 第三方包括 pinrule 无法绕。**之前 pinrule 把这条埋 README 第 82 行表格，
        实测用户装完就以为生效了实际 0 hook fire**（rule #4 loud-failure-with-evidence
        反方向 — 不响亮告诉用户限制就是「让用户以为正常」的隐性失败）。

        返回 [] 表示该 backend 装完就生效不需要额外提醒（Claude）。
        Codex 返回完整审批步骤含 4 个 wrapper 完整路径。

        `_install_to_backend` 在装机末尾打印每条 message 为一行 — backend 可加 emoji /
        分隔线让用户视觉上不漏看。
        """
        ...

    # v0.10.0 协议契约（每个 backend 在自己文件 override 这 4 个，默认 JsonHooksBackend
    # 给 Claude-shape 实现）—— 让 hook 通用主逻辑跟具体 backend 解耦.

    def normalize_tool_name(self, raw_tool_name: str, payload: dict) -> str:
        """归一化 tool_name 到 pinrule canonical (Claude 风格)."""
        ...

    def normalize_tool_input(
        self, raw_tool_name: str, raw_tool_input: object, payload: dict,
    ) -> object:
        """归一化 tool_input 到 pinrule canonical shape (codex envelope 解析等)."""
        ...

    def emit_deny(self, reason: str, payload: dict) -> str:
        """生成 deny output JSON string (backend-specific shape)."""
        ...

    def emit_allow(self, payload: dict) -> str:
        """生成 allow output JSON string (backend-specific shape)."""
        ...

    def emit_context_injection(
        self, event_name: str, additional_context: str, payload: dict,
    ) -> str:
        """生成 ContextInjection 类 hook output JSON string (v0.10.6 引入).

        ContextInjection 类 hook 含 SessionStart / UserPromptSubmit /
        PostToolUse / SubagentStart 等向 Agent 注入 additionalContext 的事件.
        Claude 用 hookSpecificOutput.additionalContext shape, 其他
        backend 可能 shape 不同 (Codex / Cursor 没文档化对 ContextInjection
        类 event 的支持 — v0.9.15 同款假设潜伏点).
        """
        ...

    def emit_stop_block(self, reason: str, payload: dict) -> str:
        """生成 Stop hook 强制 block output JSON string (v0.10.6 引入).

        Stop hook 是 pinrule 干预 Agent 最强动作 (force_block / keep_pushing_block).
        Claude 用顶层 {decision: "block", reason} shape, 其他 backend
        可能不接受 (Cursor stop 用 followup_message, Codex Stop event
        是否接受这个 shape 未验证).
        """
        ...

    def skill_install_targets(self, skill_name: str = "pinrule") -> list[tuple[Path, str]]:
        """返回该 backend 装 skill 的目标 [(dest_path, content_format), ...].

        content_format: "markdown" (Markdown 原样写) (v0.13.2 砍 Gemini 后只剩 markdown).

        例:
        - ClaudeCode: [(~/.claude/skills/pinrule/SKILL.md, "markdown")]
        - Codex: [(~/.agents/skills/pinrule/SKILL.md, "markdown")] (注意路径 ~/.agents/ 不是 ~/.codex/)
        """
        ...


class SettingsParseError(Exception):
    """配置文件损坏 — 调用方需要 abort 不能静默覆盖。"""
