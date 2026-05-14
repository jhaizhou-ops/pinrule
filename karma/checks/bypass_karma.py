"""#8 bypass-karma — Agent 通过手动改 session_state 等方式绕开检测 检测时拦。

用户痛点：Agent 被 karma 反复拦截后，倾向选「手动绕过」（修 last_test_pass_ts /
清 pending_bg_tasks / hack 文件）而不是深挖 karma 拦的真根因。这违反 sticky #1
「最根本方案」。

检测信号（pre_tool_use Bash command 扫）：
1. 命令含 karma 内部敏感字面（last_test_pass_ts / last_edit_ts / pending_bg_tasks /
   ~/.claude/karma/session-state）+ 是赋值/写文件操作 → 直接命中
2. 命令含 karma 配置/状态文件路径 + 写操作 → 命中

豁免：
- 命令在描述上下文（讨论 karma 内部不算执行）— 但 Bash 是执行意图，难豁免
- karma 自己维护命令（karma reset / karma init 等）— 通过命令头识别豁免

设计：宁可严格也不放过 — 用户明确说「绕过是 sticky #1 违反」。
"""

from __future__ import annotations

import re

from karma.checks._types import CheckHit
from karma.checks.common import strip_shell_quoted_literals

_STICKY_ID = "deep-fix-not-bypass"

# karma 内部敏感字段名 — 出现在 Bash 命令里多数是 Agent 绕过
_KARMA_INTERNAL_RE = re.compile(
    r"(?:"
    r"last_test_pass_ts|last_edit_ts|pending_bg_tasks|"
    r"stop_block_count|turn_count|read_files|edit_files"
    r")",
    re.IGNORECASE,
)

# karma 状态文件路径
_KARMA_STATE_PATH_RE = re.compile(
    r"\.claude/karma/(?:session-state|violations\.jsonl|sticky\.yaml)",
    re.IGNORECASE,
)

# 写文件操作信号 — 不含 cp/mv/rm 这种「合法备份 / 清老 rotation」操作。
# 用户 `cp ~/.claude/karma/sticky.yaml ~/backup/` / `rm ~/karma/violations.jsonl.3`
# 是日常 karma 状态自治，不是绕开检测。攻击者 hack 用 cp/mv 改 karma 状态
# 是极少数 case；为它拦合法操作得不偿失。真 hack 路径（echo > file / python
# 直接写）仍能 catch。
_WRITE_OP_RE = re.compile(
    r"(?:"
    r"\.write_text\b|\.write\b|"          # Python 写文件
    r"write_text\s*\(|write\s*\("
    # shell 重定向写 — `> file`。排除目标 /dev/null 等丢弃路径
    # （`2>/dev/null` stderr 转黑洞不算写）。`2> /tmp/x.log` 写真文件仍算写。
    r"|>\s*(?!/dev/(?:null|zero|stderr|stdout))[/.~\w]"
    r"|\.unlink\b|\.replace\b"            # Python unlink / replace
    r"|json\.dump|p\.write"
    r")",
    re.IGNORECASE,
)

# karma 官方 CLI 命令头 — 豁免（用户用 karma 命令是合法操作）
_KARMA_CLI_RE = re.compile(r"\bkarma\s+(?:init|install-hooks|uninstall-hooks|reset|reset-session|stats|audit|violations|sticky|doctor)\b")


def check(*, tool_name: str = "", tool_input: dict | None = None, **_):
    """Bash 命令含 karma 内部字面 + 写操作 → 命中「绕开检测」违反。

    剥引号字面后扫命令骨架 — git commit message 描述「修了 last_test_pass_ts」
    是描述不是执行（避免本 commit message 自指假阳）。
    """
    if tool_name != "Bash":
        return None
    cmd_raw = (tool_input or {}).get("command", "") or ""
    if not cmd_raw:
        return None

    # 豁免 1：karma 官方 CLI 命令
    if _KARMA_CLI_RE.search(cmd_raw):
        return None

    # 剥 shell 引号字面（commit message / echo 文本）后扫命令骨架
    cmd_stripped = strip_shell_quoted_literals(cmd_raw)

    # 信号 1：剥后命令骨架含 karma 内部字段 / 路径 + 写操作 → 绕开检测
    has_internal = bool(_KARMA_INTERNAL_RE.search(cmd_stripped))
    has_state_path = bool(_KARMA_STATE_PATH_RE.search(cmd_stripped))
    has_write = bool(_WRITE_OP_RE.search(cmd_stripped))

    if (has_internal or has_state_path) and has_write:
        m1 = _KARMA_INTERNAL_RE.search(cmd_stripped)
        m2 = _KARMA_STATE_PATH_RE.search(cmd_stripped)
        trigger_text = m1.group() if m1 else (m2.group() if m2 else "karma 内部状态")
        return CheckHit(
            sticky_id=_STICKY_ID,
            trigger=f"绕开检测 — 手动写 karma 内部状态 ({trigger_text!r})",
            snippet=cmd_raw[:200],
            suggested_fix="不要手动改 karma session_state / violations。如果 karma 拦得不对 "
                          "→ 深挖真根因（pattern 收紧 / catchup race / hook 协议）。"
                          "如果真要绕，明确告诉用户「我打算绕开检测 因为 X」让用户决定。",
        )

    return None
