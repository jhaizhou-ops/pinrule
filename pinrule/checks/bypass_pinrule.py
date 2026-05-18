"""#8 bypass-pinrule — Agent 通过手动改 session_state 等方式绕开检测 检测时拦。

用户痛点：Agent 被 pinrule 反复拦截后，倾向选「手动绕过」（修 last_test_pass_ts /
清 pending_bg_tasks / hack 文件）而不是深挖 pinrule 拦的原因。这违反 sticky #1
「最根本方案」。

检测信号（pre_tool_use Bash command 扫）：
1. 命令含 pinrule 内部敏感字面（last_test_pass_ts / last_edit_ts / pending_bg_tasks /
   ~/.claude/pinrule/session-state）+ 是赋值/写文件操作 → 直接命中
2. 命令含 pinrule 配置/状态文件路径 + 写操作 → 命中

豁免：
- 命令在描述上下文（讨论 pinrule 内部不算执行）— 但 Bash 是执行意图，难豁免
- pinrule 自己维护命令（pinrule reset / pinrule init 等）— 通过命令头识别豁免

设计：宁可严格也不放过 — 用户明确说「绕过是 sticky #1 违反」。
"""

from __future__ import annotations

import re
from pathlib import Path

from pinrule.checks._types import CheckHit
from pinrule.checks.common import is_python_c_command, strip_shell_quoted_literals
from pinrule.checks.description_context import _BASH_REDIR_TARGET_RE
from pinrule.i18n import tr
from pinrule.paths import pinrule_home

_STICKY_ID = "deep-fix-not-bypass"

# pinrule 内部敏感字段名 — 出现在 Bash 命令里多数是 Agent 绕过
_PINRULE_INTERNAL_RE = re.compile(
    r"(?:"
    r"last_test_pass_ts|last_edit_ts|pending_bg_tasks|"
    r"stop_block_count|turn_count|read_files|edit_files"
    r")",
    re.IGNORECASE,
)


def _build_state_path_re() -> re.Pattern[str]:
    """构造 pinrule state 文件路径正则。

    覆盖用户敲的 Bash 命令里可能出现的所有路径写法：
    - 默认 `~/.claude/pinrule/...` mode：相对 fragment `.claude/pinrule/...`
      同时匹配 `~/...` / `/Users/x/...` / 相对 `.claude/pinrule/...` 3 种字面
    - `PINRULE_HOME` env 隔离 mode（跨用户 / CI / 多 profile）：加 PINRULE_HOME 实际
      绝对路径 + 如果在 home 下还加 `~/<rel>` 字面兼容

    文件名集合涵盖 `rules.json` + `config.json` + `session-state` + `violations.jsonl`。
    v0.17.0 起 pinrule 0 runtime deps, 配置/规则文件全 JSON.

    `pinrule_home()` 在 import 时 freeze（paths.py docstring 已明确这点 — `PINRULE_HOME`
    必须在 hook 子进程启动前 set），所以 module-level 编译一次即可。
    """
    from pinrule.paths import SHARED_PINRULE_HOME

    pinrule_dir = pinrule_home()
    paths = [r"\.pinrule"]  # v0.16.0 fresh brand, no legacy karma paths

    if pinrule_dir != SHARED_PINRULE_HOME:
        # PINRULE_HOME 改了路径 — 加 override 路径绝对字面
        paths.append(re.escape(str(pinrule_dir)))
        # PINRULE_HOME 在 home 下时还加 `~/<rel>` 字面（用户敲 ~ 不展开）
        try:
            rel = pinrule_dir.relative_to(Path.home())
            paths.append(rf"~/{re.escape(str(rel))}")
        except ValueError:
            pass

    files = r"(?:session-state|violations\.jsonl|rules\.json|config\.json)"
    return re.compile(rf"(?:{'|'.join(paths)})/{files}", re.IGNORECASE)


# pinrule 状态文件路径 — 工厂动态构造，PINRULE_HOME 隔离 mode 下检测仍生效
_PINRULE_STATE_PATH_RE = _build_state_path_re()

# 写文件操作信号 — 不含 cp/mv/rm 这种「合法备份 / 清老 rotation」操作。
# 用户 `cp ~/.claude/pinrule/rules.json ~/backup/` / `rm ~/pinrule/violations.jsonl.3`
# 是日常 pinrule 状态自治，不是绕开检测。攻击者 hack 用 cp/mv 改 pinrule 状态
# 是极少数 case；为它拦合法操作得不偿失。真 hack 路径（echo > file / python
# 直接写）仍能 catch。
#
# 拆成两类（v0.4.13 dogfooding 治理）：
# 1. 跨语言通用写（python `.write` / `json.dump` 等）— shell + python 都扫
# 2. shell-only 重定向（`>` 写文件）— 命令头是 python/node/ruby/perl -c 时跳，
#    避免 python 代码里 `cutoff > 0` 比较运算符被错算成 shell 重定向（触发：
#    `python -c "... 'ts', 0) > cutoff ..."` 读 violations.jsonl 时被错拦）
_PYTHON_OR_SHELL_WRITE_RE = re.compile(
    r"(?:"
    r"\.write_text\b|\.write\b|"          # Python 写文件
    r"write_text\s*\(|write\s*\("
    r"|\.unlink\b|\.replace\b"            # Python unlink / replace
    # word boundary 关键 — 否则 `json.dumps` (序列化为字符串纯读) 被误判为
    # `json.dump` (写 file-like) 假阳爆发；`p.writeable` 类字面也会被 `p.write`
    # 误匹配。v0.4.32 dogfooding 触发 fix
    r"|json\.dump\b|p\.write\b"
    # v0.4.22：补 python 调 shell 绕过接口（v0.4.13 漏拦原因）
    r"|os\.(?:system|remove|unlink|rmdir|rename|popen)\b"
    r"|subprocess\.(?:run|call|Popen|check_output|check_call)\b"
    r"|shutil\.(?:rmtree|move|copy|copy2|copyfile)\b"
    r"|Path\([^)]*\)\.(?:unlink|rmdir|rename|replace|write)"
    r")",
    re.IGNORECASE,
)
_SHELL_REDIR_WRITE_RE = re.compile(
    # shell 重定向写 — `> file`。排除目标 /dev/null 等丢弃路径
    # （`2>/dev/null` stderr 转黑洞不算写）。`2> /tmp/x.log` 写真文件仍算写。
    r">\s*(?!/dev/(?:null|zero|stderr|stdout))[/.~\w]",
    re.IGNORECASE,
)
# v0.5.13: _LANG_C_HEAD_RE 下沉到 pinrule.checks.common.is_python_c_command() —
# 跟 testset / non_blocking 共享. 这里用 is_python_c_command(cmd_raw) 调用.

# pinrule 官方 CLI 命令头 — 豁免（用户用 pinrule 命令是合法操作）
_PINRULE_CLI_RE = re.compile(r"\bpinrule\s+(?:init|install-hooks|uninstall-hooks|reset|reset-session|stats|audit|violations|sticky|doctor)\b")


def check(*, tool_name: str = "", tool_input: dict | None = None, session_state=None, rule_id: str = "", **_):
    """两路检测同 rule_id `deep-fix-not-bypass`:

    1. Bash 命令含 pinrule 内部字面 + 写操作 → 「绕开 pinrule 检测」违反
    2. v0.11.1: 测试失败 → 立刻 Edit 没读过的文件 → 「报错没看源就改」草草了事

    第 2 路只是「行为时序 pattern」, 工程化上限有限（认知深度 L4 拦不到，
    详 [[feedback-language-preference-no-engine]] memory 解释 deep_fix 类天花板).
    """
    # v0.11.1 路径 2: Edit + 上一 Bash 测试失败 + 当前 file_path 没读过
    # = 「报错信号紧跟 Edit 没看源代码」草草了事 pattern
    if tool_name == "Edit" and session_state is not None:
        edit_fp = (tool_input or {}).get("file_path", "")
        recent_bash = getattr(session_state, "recent_bash", []) or []
        if edit_fp and recent_bash:
            last_bash = recent_bash[-1]
            # 限定: 最近一条 Bash 是**测试命令**且**失败** (output_failed True)
            # 且 Agent 没读过这文件 → 拦. 没读过 + 测试挂了立刻改 = 没看源代码
            is_test_fail = getattr(last_bash, "is_test_cmd", False) and \
                getattr(last_bash, "output_failed", False)
            if is_test_fail and not session_state.has_read(edit_fp):
                return CheckHit(
                    rule_id=rule_id or _STICKY_ID,
                    trigger=tr("check.deep_fix.edit_after_test_fail_no_read.trigger", file_path=edit_fp),
                    trigger_key="check.deep_fix.edit_after_test_fail_no_read.trigger",
                    snippet=f"Edit({edit_fp!r}) after test fail without reading source",
                    suggested_fix=tr("check.deep_fix.edit_after_test_fail_no_read.fix", file_path=edit_fp),
                )

    if tool_name != "Bash":
        return None
    cmd_raw = (tool_input or {}).get("command", "") or ""
    if not cmd_raw:
        return None

    # 豁免 1：pinrule 官方 CLI 命令
    if _PINRULE_CLI_RE.search(cmd_raw):
        return None

    # 剥 shell 引号字面（commit message / echo 文本）后扫命令骨架
    cmd_stripped = strip_shell_quoted_literals(cmd_raw)

    # 信号 1：剥后命令骨架含 pinrule 内部字段 / 路径 + 写操作 → 绕开检测
    has_internal = bool(_PINRULE_INTERNAL_RE.search(cmd_stripped))
    has_state_path = bool(_PINRULE_STATE_PATH_RE.search(cmd_stripped))
    # 写检测拆两类：跨语言通用 python 写（.write/.unlink 等）+ shell-only 重定向
    # 宿主语言 + -c 跳 shell 重定向（python 代码里 `>` 是比较运算符不是写）
    has_python_write = bool(_PYTHON_OR_SHELL_WRITE_RE.search(cmd_stripped))
    is_lang_c = is_python_c_command(cmd_raw)

    # v0.5.18 原因 fix（dogfooding session 触发假阳驱动）：state_path 维度
    # 要求 redirect target 是 pinrule 路径才拦, 不能「pinrule 路径出现 + 任何
    # write op」一刀切. 触发: `grep ~/.claude/pinrule/violations.jsonl > /tmp/x`
    # 读 pinrule state 写 tmp 是合法 audit 用途, 之前被错算「写 pinrule 内部状态」拦.
    # 区分:
    #   ✗ 违反: `echo "..." > ~/.claude/pinrule/foo` (redirect target = pinrule 路径)
    #   ✗ 违反: `python -c "open('.claude/pinrule/x', 'w')..."` (python 写接口)
    #   ✓ 合法: `cat ~/.claude/pinrule/foo > /tmp/x` (redirect target = 非 pinrule 路径)
    redir_targets = _BASH_REDIR_TARGET_RE.findall(cmd_stripped) if not is_lang_c else []
    state_path_in_redir_target = any(
        _PINRULE_STATE_PATH_RE.search(t) for t in redir_targets
    )
    write_to_pinrule_state = has_python_write or state_path_in_redir_target

    # 一致判定: 不论 pinrule 引用是 field name 还是 path, 都要求 write target
    # 是 pinrule state (path) 才算绕过. 写到 /tmp/foo 不影响 pinrule 状态 —
    # 即使命令含 `last_test_pass_ts` 类内部 schema 字段名也不是绕过.
    pinrule_referenced = has_internal or has_state_path
    is_bypass = pinrule_referenced and write_to_pinrule_state

    if is_bypass:
        m1 = _PINRULE_INTERNAL_RE.search(cmd_stripped)
        m2 = _PINRULE_STATE_PATH_RE.search(cmd_stripped)
        trigger_text = m1.group() if m1 else (m2.group() if m2 else "pinrule 内部状态")
        return CheckHit(
            rule_id=rule_id or _STICKY_ID,
            trigger=tr("check.bypass_pinrule.trigger", target=trigger_text),
            trigger_key="check.bypass_pinrule.trigger",
            snippet=cmd_raw[:200],
            suggested_fix=tr("check.bypass_pinrule.fix"),
        )

    return None
