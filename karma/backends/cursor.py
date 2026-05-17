"""Cursor IDE backend — `~/.cursor/hooks.json` + `~/.cursor/hooks/`.

Cursor 1.7+ (2025-10 release) 引入 hooks 协议, 字段 schema 跟 Claude Code 高度同构
(`conversation_id` / `tool_name` / `tool_input`), 但 event 名用 camelCase 小开头
(`preToolUse` 而非 `PreToolUse`), output shape 用 `permission` + `user_message`/
`agent_message` 而非 Claude `hookSpecificOutput.permissionDecision`.

参考: https://cursor.com/docs/hooks (2026-05-17 fetch 确认 reality, 不 guess).

跟 Claude Code / Codex / Gemini 的关键差异:

① **每 turn 注入走 `beforeSubmitPrompt` → `user_prompt_submit`**. Cursor 官方
   schema 只文档化 `continue` / `user_message`, 但 third-party hooks 文档确认
   Claude `UserPromptSubmit` 映射到 `beforeSubmitPrompt` 且 **nested
   `hookSpecificOutput.additionalContext` 可用**. karma v0.12.2+ 装此 hook +
   `emit_context_injection` 对 beforeSubmitPrompt 走 nested shape. 另同步
   `~/.cursor/rules/karma-sticky.mdc` (`alwaysApply`) 作模型起手可见的保险层
   (dogfood: hook sessionStart stdout 有、模型起手自检无; Cursor Rules 起手有).

② **stdin payload 用 `conversation_id` 不是 `session_id`**. v0.12.1 起
   `karma.hooks._payload.extract_session_id` 做 `session_id → conversation_id`
   fallback; sessionStart 文档也写 `session_id` 同 `conversation_id`. 两者并存时
   优先 `session_id`.

③ **Stop hook 协议从根本不同**. Cursor `stop` 不接受 `{"decision": "block",
   "reason": ...}`, 接受 `{"followup_message": "..."}` 让 Agent auto-continue. 这正
   对应 karma keep-pushing 的「stop 时塞反思 prompt 让 Agent 继续推」语义 — Cursor
   协议级天然适配, 比 Gemini AfterAgent 没 block 概念回 `{}` fail-open 更优雅.
   `emit_stop_block` override 返 followup_message shape.

④ **Cursor 是 IDE 不是 CLI**. PATH 没有 `cursor` 命令是常态 (除非用户开了 Cursor.app
   的「Shell Command: Install 'cursor' command in PATH」选项). client_installed
   fallback 到 `~/.cursor` 目录存在 — Cursor 装机基本会创建.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from karma.backends._json_hooks import JsonHooksBackend
from karma.backends.native_capabilities import CURSOR_HOOK_EVENTS


# Cursor → karma canonical tool_name 映射.
# Cursor 文档列的 preToolUse tool_name: "Shell|Read|Write|Grep|Delete|Task|MCP:*"
# karma 主要消费 canonical: Bash / Read / Write / Edit.
# Cursor 没显式 Edit (Edit 通过 Write 实现), 也没显式 Bash (用 Shell).
_CURSOR_TOOL_MAP: dict[str, str] = {
    "Shell": "Bash",       # Cursor Shell == Claude Bash
    "Read": "Read",         # 同名
    "Write": "Write",       # 同名 (但 Cursor 把 Edit 也归 Write — 见下方说明)
    "Task": "Agent",        # Cursor Task == Claude Agent (子 Agent 派发)
    # 注: Cursor 没暴露 Edit 作为独立 tool, 文件修改都走 Write 或 afterFileEdit
    # event. karma 的 read_first check 看 Write 等同 Edit 语义 — 在主逻辑层一致.
}


class CursorBackend(JsonHooksBackend):
    name = "cursor"
    display_name = "Cursor"
    _CONFIG_DIR_NAME = ".cursor"
    _SETTINGS_FILENAME = "hooks.json"
    _CLIENT_CMD = "cursor"  # 可能不在 PATH — fallback 到 ~/.cursor 目录检测

    # Cursor event 名是 camelCase 小开头 — 写进 hooks.json 时大小写敏感, 不能
    # 套用 Claude Code 的 PascalCase. wrapper basename 保持 karma 内部规范让
    # hook 入口模块 (karma/hooks/*.py) 跨 backend 完全复用.
    #
    # Native-first surface (see native_capabilities.CURSOR_NATIVE_HOOKS) — not a
    # 1:1 clone of Claude's 8 PascalCase events. Extra gates: beforeShellExecution,
    # beforeMCPExecution, beforeReadFile; audit: afterAgentResponse.
    _HOOK_EVENTS: dict[str, str] = dict(CURSOR_HOOK_EVENTS)

    def build_event_entry(self, hook_name_lower: str, event_name: str) -> dict:
        """Cursor native hooks.json entry — flat `{command: ...}` not Claude nested.

        Cursor docs (https://cursor.com/docs/hooks) use `version: 1` + per-event
        `{command: "..."}` entries. Claude nested `{hooks:[{type,command}]}` works
        via third-party import but native format is required for reliable load.
        Use absolute `sys.executable` + wrapper path — user hooks cwd is `~/.cursor/`.
        """
        wrapper = self.hooks_dir() / f"karma_{hook_name_lower}.py"
        entry: dict[str, Any] = {"command": f"{sys.executable} {wrapper}"}
        if event_name in ("stop", "subagentStop"):
            entry["loop_limit"] = 10
        return entry

    def is_karma_entry(self, entry: dict) -> bool:
        """Recognize karma in native flat entries and legacy Claude nested entries."""
        if "karma_" in entry.get("command", ""):
            return True
        return super().is_karma_entry(entry)

    def save_settings(self, data: dict) -> None:
        """Ensure Cursor hooks.json has schema `version: 1`."""
        data.setdefault("version", 1)
        super().save_settings(data)

    def post_install_setup(self) -> list[str]:
        """Install 后同步 Cursor native rules + 提示 reload."""
        from karma.cursor_rules_sync import sync_cursor_rules

        _written, logs = sync_cursor_rules(user=True)
        logs.append(
            "  → 改 rules 后跑 `karma sync-cursor-rules` 刷新 .mdc;"
            " Reload Cursor window 让 hooks.json 生效."
        )
        return logs

    def normalize_tool_name(self, raw_tool_name: str, payload: dict) -> str:
        """Cursor tool_name 归一化 — Shell → Bash."""
        return _CURSOR_TOOL_MAP.get(raw_tool_name, raw_tool_name)

    def emit_deny(self, reason: str, payload: dict) -> str:
        """Cursor preToolUse deny: 顶层 `permission: "deny"` + agent_message/user_message.

        跟 Claude `hookSpecificOutput.permissionDecision` 和 Gemini `decision: "deny"`
        都不同 — Cursor 官方文档 (https://cursor.com/docs/hooks) 明确指定:
            {"permission": "allow|deny|ask", "user_message": "...", "agent_message": "..."}

        agent_message = 发给 Agent 看的拦截理由 (karma 真想塞的 sticky 反思);
        user_message = 弹给用户看的 (karma 给两者填同内容, 让用户 + Agent 都看到).
        """
        return json.dumps({
            "permission": "deny",
            "user_message": reason,
            "agent_message": reason,
        }, ensure_ascii=False)

    def emit_allow(self, payload: dict) -> str:
        """Cursor allow — 顶层 `permission: "allow"`."""
        return json.dumps({"permission": "allow"})

    def emit_context_injection(
        self, event_name: str, additional_context: str, payload: dict,
    ) -> str:
        """Cursor context injection — event-specific output shape.

        - sessionStart / postToolUse / subagentStart: native `additional_context`.
        - beforeSubmitPrompt: third-party nested `hookSpecificOutput` (Claude
          UserPromptSubmit 映射); empty → `{"continue": true}` per native schema.
        - preCompact: observational `user_message` only (no additional_context).
        """
        text = (additional_context or "").strip()
        if event_name == "preCompact":
            if not text:
                return json.dumps({})
            return json.dumps({"user_message": additional_context}, ensure_ascii=False)
        if event_name == "beforeSubmitPrompt":
            if not text:
                return json.dumps({"continue": True})
            return json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": additional_context,
                }
            }, ensure_ascii=False)
        return json.dumps({"additional_context": additional_context}, ensure_ascii=False)

    def emit_stop_block(self, reason: str, payload: dict) -> str:
        """Cursor stop event 没 block 概念 — 用 `followup_message` auto-continue.

        Cursor 协议: `{"followup_message": "<message text for auto-submit>"}` 会
        让 Cursor 自动以这段文本作为 user 回复继续 Agent 循环. 这正映射 karma
        keep-pushing 的「Agent 想 stop 时塞反思 prompt 让继续推」语义.

        相比 Gemini AfterAgent 没 block 概念被迫返 {} fail-open, Cursor 这个
        协议天然适配 karma 干预 — block 不了但能 redirect 继续, 等效 karma 想要
        的「不让 Agent 草草收工」效果.
        """
        return json.dumps({"followup_message": reason}, ensure_ascii=False)

    def skill_install_targets(self, skill_name: str = "karma") -> list[tuple[Path, str]]:
        """**协议级真限制**: Cursor 只支持 project-scoped skills (`.cursor/skills/`
        在每个项目根目录), **没有 home-level global skills directory**.

        Reality check (2026-05-17, https://cursor.com/help/customization/skills):
        "Unlike some other agents, Cursor doesn't have a personal (global) skills
        directory — all skills are project-scoped. If you want a skill in every
        project, you need to copy it into each project's .cursor/skills/ folder."

        karma 不能跨所有未来 project 一次装 skill — 返空 list 不装. 用户想用 /karma
        自然语言加规则功能, 需手工 cp `data/karma-skill/SKILL.md` 到每个目标项目的
        `.cursor/skills/karma/`. post_install_message 响亮告知这个限制 (rule #4
        loud-failure-with-evidence: 不响亮说出限制 = 让用户以为正常实际 0 fire).

        注: karma 主功能 (sticky 规则注入 + 行为拦截) **不依赖 skill** — skill 只是
        给「用户用自然语言加新规则」走捷径. Cursor 用户没 skill 也能用 karma 全部
        核心能力, 加规则改走 `karma rule add --from-yaml` 或手工编辑 rules.yaml.
        """
        return []

    def post_install_message(self) -> list[str]:
        """Cursor 装完响亮告知 skill 协议限制 (project-scoped only).

        karma rule #4 loud-failure-with-evidence: Cursor 不支持 global skills 这件
        事如果埋 README 表格里, 用户会以为「装完 karma 跟 Claude Code 体验一样」,
        实际 /karma 自然语言加规则功能在 Cursor 0 触发. 在装完时打印响亮一段告知.
        """
        return [
            "",
            "⚠️  Cursor 跟 Claude Code / Codex / Gemini 不一样 — 只支持 project-scoped",
            "    skills (`.cursor/skills/` 在每个项目根目录), **没有 home-level global**.",
            "",
            "    影响: karma 核心能力 (sticky 规则注入 + 行为拦截) 完全可用. 但是",
            "    `/karma <自然语言>` 这种用 skill 走捷径加规则的功能在 Cursor 不能",
            "    跨项目全局生效 — 想用需手工 cp SKILL.md 到每个目标项目:",
            "",
            "        mkdir -p .cursor/skills/karma",
            "        cp $(python -c \"import karma; print(karma.__path__[0])\")/../skills/karma/SKILL.md .cursor/skills/karma/",
            "",
            "    替代路径 (推荐): `karma rule add --from-yaml /tmp/rule.yaml` 直接",
            "    走 CLI 加规则, 不依赖 IDE skill 机制. karma 主流程通过 hooks.json",
            "    跑, 跟 skill 解耦.",
        ]
