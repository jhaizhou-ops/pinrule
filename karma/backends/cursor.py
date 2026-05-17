"""Cursor IDE backend — `~/.cursor/hooks.json` + `~/.cursor/hooks/`.

Cursor 1.7+ (2025-10 release) 引入 hooks 协议, 字段 schema 跟 Claude Code 高度同构
(`conversation_id` / `tool_name` / `tool_input`), 但 event 名用 camelCase 小开头
(`preToolUse` 而非 `PreToolUse`), output shape 用 `permission` + `user_message`/
`agent_message` 而非 Claude `hookSpecificOutput.permissionDecision`.

参考: https://cursor.com/docs/hooks (2026-05-17 fetch 确认 reality, 不 guess).

跟 Claude Code / Codex / Gemini 的关键差异:

① **没有 UserPromptSubmit 等价 hook**. Cursor `beforeSubmitPrompt` 只能 `{"continue":
   false}` 阻断提交, **不允许注入 additional_context**. karma 通过 `sessionStart`
   一次注入 sticky baseline (跟 Claude Code v0.4.28 SessionStart 模式同) + `postToolUse`
   中段重注入抗稀释 (跟 Claude PostToolUse byte_seq 同) 来替代 every-turn header inject
   能力. 实测含义: Cursor 用户每个 user message header **不会**重出现 sticky rules,
   但 sessionStart `additional_context` 在 prompt cache + system message 里每 turn 都
   读得到, 跟 CLAUDE.md / .cursorrules 同等效.

② **stdin payload 用 `conversation_id` 不是 `session_id`**. karma hook 入口
   (karma/hooks/*.py) hardcode `payload.get("session_id")` — Cursor 装的 wrapper 在
   读 payload 时这个 key 会 miss, 触发 fallback 到 `"default"` 字面. 这是 Cursor
   backend 的真潜在 bug (跟 stop.py 的三路 fallback `transcript_path` /
   `last_assistant_message` / `prompt_response` 同款问题), 通过 install + 真跑一遍
   验证. 不在本文件 patch 通用层 — karma 设计是 hook 入口集中处理跨 backend 字段
   fallback (rule #6 read_first: 改前先观测真行为).

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
from pathlib import Path

from karma.backends._json_hooks import JsonHooksBackend


# Cursor → karma canonical tool_name 映射.
# Cursor 文档列的 preToolUse tool_name: "Shell|Read|Write|Grep|Delete|Task|MCP:*"
# karma 主要消费 canonical: Bash / Read / Write / Edit.
# Cursor 没显式 Edit (Edit 通过 Write 实现), 也没显式 Bash (用 Shell).
_CURSOR_TOOL_MAP: dict[str, str] = {
    "Shell": "Bash",       # Cursor Shell == Claude Bash
    "Read": "Read",         # 同名
    "Write": "Write",       # 同名 (但 Cursor 把 Edit 也归 Write — 见下方说明)
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
    # **协议级缺失**: 没有 UserPromptSubmit 等价 — beforeSubmitPrompt 只能 block
    # 不能注入 additional_context. karma 走 sessionStart 一次注入 + postToolUse
    # 中段重注入两路替代 (参考 v0.4.28 Claude Code SessionStart 模式).
    _HOOK_EVENTS: dict[str, str] = {
        "sessionStart": "session_start",
        "preToolUse": "pre_tool_use",
        "postToolUse": "post_tool_use",
        "stop": "stop",
    }

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
        """Cursor sessionStart / postToolUse 用 snake_case `additional_context`
        (Claude Code 是 camelCase `additionalContext`).

        sessionStart 文档 schema: `{"env": {...}, "additional_context": "..."}`
        postToolUse 文档 schema: `{"updated_mcp_tool_output": {...}, "additional_context": "..."}`

        两个 event 都用同 key, 直接顶层返不需要 hookSpecificOutput envelope.
        """
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
