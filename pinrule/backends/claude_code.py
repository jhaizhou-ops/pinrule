"""Claude backend — `~/.claude/settings.json` + `~/.claude/hooks/`。

继承 `JsonHooksBackend` 通用基类，只填差异：matcher 字段（Stop 不加 matcher）。
"""

from __future__ import annotations

from pathlib import Path

from pinrule.backends._json_hooks import JsonHooksBackend, hook_command_str


class ClaudeCodeBackend(JsonHooksBackend):
    name = "claude-code"
    display_name = "Claude"
    _CONFIG_DIR_NAME = ".claude"
    _SETTINGS_FILENAME = "settings.json"
    _CLIENT_CMD = "claude"

    _HOOK_EVENTS: dict[str, str] = {
        "UserPromptSubmit": "user_prompt_submit",
        "PreToolUse": "pre_tool_use",
        "PostToolUse": "post_tool_use",
        "Stop": "stop",
        # v0.4.28（pinrule v3 第四步）: SessionStart 注入 sticky baseline，每次
        # session 起手 sticky 就在 context 里。`source` 字段区分 startup /
        # resume / clear / compact —— compact 场景特别重要（compact 后 sticky
        # 被压缩淡化，SessionStart 重起时强注入是根本本路径）。
        "SessionStart": "session_start",
        # v0.4.29（pinrule v3 第五步）: PreCompact 触发前落盘 sticky 完整状态到
        # ~/.claude/pinrule/pre_compact_snapshot.md，让 SessionStart(source=compact)
        # 重起时读盘加强提醒。两端夹击 compact 失忆。
        # 注：不用 exit 2 阻止 compact — compact 是 Claude 保护机制，pinrule
        # 不该干扰，只做纯落盘 + 提醒。
        "PreCompact": "pre_compact",
        # v0.4.30（pinrule v3 第六步）: SubagentStart / SubagentStop 让 sticky 跨
        # 子 Agent 边界传递。SubagentStart 注入 sticky baseline（子 Agent 跑
        # 任务时也按这些方向）；SubagentStop 给主 Agent 一行透明度提醒（不扫
        # transcript 内容 — substring match 假阳爆发，违反检测交给主 Agent
        # 处理子 Agent 结果时的 PreToolUse / PostToolUse / Stop 三道 hook）。
        # 注：PostCompact 不支持 additionalContext 协议层走不通，pinrule 不装。
        "SubagentStart": "subagent_start",
        "SubagentStop": "subagent_stop",
    }

    def build_event_entry(self, hook_name_lower: str, event_name: str) -> dict:
        """Claude 特有：PreToolUse / PostToolUse / UserPromptSubmit 加
        `matcher: "*"`；PreCompact matcher 区分 manual / auto（用 `*` 匹配两种）；
        Stop / SessionStart / SubagentStart / SubagentStop 等 lifecycle event
        不加 matcher（加了会被无声忽略）。
        """
        wrapper = self.hooks_dir() / f"pinrule_{hook_name_lower}.py"
        entry: dict[str, object] = {
            "hooks": [{"type": "command", "command": hook_command_str(wrapper)}]
        }
        if event_name in ("PreToolUse", "PostToolUse", "UserPromptSubmit", "PreCompact"):
            entry["matcher"] = "*"
        return entry

    def skill_install_targets(self, skill_name: str = "pinrule") -> list[tuple[Path, str]]:
        """Claude skill 装到 `<install_root>/.claude/skills/<name>/SKILL.md` (Markdown 原样).

        触发: 用户在 Claude 输 `/<skill_name> <NL>`, $ARGUMENTS 接全部.

        v0.16.15: 走 `pinrule_install_root()` 而不是直接 `Path.home()` — 之前漏走
        install_root 让 PINRULE_HOME sandbox 承诺破口 (设了 sandbox, Codex skill
        进 sandbox 但 Claude skill 还写真 ~/.claude/skills/). 朋友外部 review
        9.1/10 抓的真不一致.
        """
        from pinrule.paths import pinrule_install_root
        return [(pinrule_install_root() / ".claude" / "skills" / skill_name / "SKILL.md", "markdown")]
