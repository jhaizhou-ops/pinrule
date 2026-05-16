"""Codex CLI backend — `~/.codex/hooks.json` + hooks feature + protocol normalization.

继承 `JsonHooksBackend`，差异：
① 配置文件名 `hooks.json` 不是 `settings.json`
② hook entry 加 timeout: 30
③ pre_install_setup 调 `codex features enable hooks` 永久启用 feature flag
④ save_settings 写 Codex hook trust state，减少手动 `/hooks` approval
⑤ normalize_tool_name 映射 apply_patch → Edit / exec_command → Bash
⑥ normalize_tool_input 解析 apply_patch envelope 字符串成 canonical Edit shape
   含 multi_file_targets（v0.10.0 把 envelope parser 从 protocol_adapter 搬过来）
⑦ normalize_tool_input 识别 exec_command shell-as-Read，并兼容 desktop `cmd` 字段

参考：
- 官方 hook 协议: https://developers.openai.com/codex/hooks
- 实测 2026-05-16：Codex 0.130 hook 只在 interactive TUI 触发（exec mode 不 fire），
  且每个 hook 必须 TUI `/hooks` 手动 approve（GitHub issue #17532）
- 真捕获的 apply_patch envelope 来自 codex 0.130 + GPT-5.5 session rollout
  (rollout-2026-05-16T13-51-47-...jsonl)

ADR-001: PermissionRequest event 不接入 (2026-05-16)
Codex 0.130 支持 PermissionRequest event (codex agent 申请运行需要审批的
工具时 fire). karma 决策不接入:

- karma 已在 PreToolUse 层用 bypass_karma / testset / read_first 等 check
  拦截危险操作, 跟 PermissionRequest 时机重叠
- 双层拦截只增加假阳率, 不增加新拦截维度
- karma 哲学是行为先验注入 + 工程层拦截, 不是权限审批系统
  (跟 codex 自身 permission_mode 是不同维度)
- 如果后续真需要 PermissionRequest 维度的拦截 (例如"危险 git 操作要 karma
  二次确认"), 应该作为新独立 check 加入, 不是简单挂 PermissionRequest hook.
"""

from __future__ import annotations

import hashlib
import json
import re
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any

from karma.backends._json_hooks import JsonHooksBackend


# Codex → karma canonical tool_name 映射
# apply_patch 是 Codex 主要编辑入口（custom_tool_call 类型），归一化到 Edit；
# exec_command 是 Codex shell 工具，归一化到 Bash，让 Bash 类 check / record_bash
# 走通。
_CODEX_TOOL_MAP: dict[str, str] = {
    "apply_patch": "Edit",
    "exec_command": "Bash",
    # Read/Write 暂未在 Codex 文档明确同名
}


# Codex apply_patch envelope grammar
# 真捕获样本（2026-05-16 13:51:47 CST codex 0.130 + GPT-5.5 session rollout）:
#     "*** Begin Patch\n*** Update File: <path>\n@@\n+...\n*** End Patch\n"
# 多文件支持 — 同一 envelope 串多个 *** Update File: / *** Add File: / *** Delete File: 块
_APPLY_PATCH_OP_RE = re.compile(
    r"^\*\*\*\s+(Update|Add|Delete)\s+File:\s*(.+?)\s*$",
    re.MULTILINE,
)
_APPLY_PATCH_BEGIN = "*** Begin Patch"

_SIMPLE_SHELL_READ_COMMANDS = frozenset({
    "tail",
    "head",
    "cat",
    "less",
    "more",
    "wc",
    "file",
})
_SHELL_COMPLEX_TOKENS = frozenset({
    "|",
    "||",
    "&",
    "&&",
    ";",
    ";;",
    ">",
    ">>",
    "<",
    "<<",
    "<<<",
    "(",
    ")",
})
_SHELL_COMPLEX_COMMANDS = frozenset({"find", "xargs"})
_TAIL_HEAD_OPTIONS_WITH_VALUES = frozenset({
    "-n",
    "--lines",
    "-c",
    "--bytes",
})
_GREP_OPTIONS_WITH_VALUES = frozenset({
    "-A",
    "--after-context",
    "-B",
    "--before-context",
    "-C",
    "--context",
    "-m",
    "--max-count",
})
_GREP_RECURSIVE_FLAGS = frozenset({
    "-r",
    "-R",
    "--recursive",
    "--dereference-recursive",
})

_SED_ADDR = r"(?:\d+|\$|/[^\n/]*/)(?:\s*,\s*(?:\d+|\$|/[^\n/]*/))?"
_SED_PRINT_ONLY_RE = re.compile(rf"^\s*(?:{_SED_ADDR})?\s*p\s*$")
_SED_PRINT_THEN_DELETE_RE = re.compile(rf"^\s*(?:{_SED_ADDR})?\s*p\s*;\s*d\s*$")


def parse_apply_patch_envelope(envelope: str) -> list[dict[str, str]]:
    """Parse codex apply_patch envelope → list of {"op", "path"}.

    op ∈ {"Update", "Add", "Delete"}.

    Returns [] for non-envelope input (malformed / empty / unrelated string).
    Honest scope: handles standard codex envelope grammar; doesn't validate
    @@ hunks or +/- line content (karma only needs file paths for state
    tracking).
    """
    if not envelope or _APPLY_PATCH_BEGIN not in envelope:
        return []
    return [
        {"op": m.group(1), "path": m.group(2).strip()}
        for m in _APPLY_PATCH_OP_RE.finditer(envelope)
    ]


def _extract_codex_patch_text(raw_tool_input: Any) -> str:
    """Codex hook payload 里 apply_patch tool_input 可能是裸字符串或 wrap dict.

    Real codex session rollout (custom_tool_call) 显示 `input` 字段是字符串。
    Hook 层 codex 可能 wrap 成 `{"input": ...}` 或 `{"command": ...}` —
    防御式处理两种 shape（hook-level 真 payload schema 待交互式 codex 真用例
    + TUI /hooks 审批后捕获）。
    """
    if isinstance(raw_tool_input, str):
        return raw_tool_input
    if isinstance(raw_tool_input, dict):
        for key in ("input", "patch", "command", "diff"):
            v = raw_tool_input.get(key)
            if isinstance(v, str) and v.strip():
                return v
    return ""


def _shell_tokens(command: str) -> list[str]:
    """Tokenize a simple shell command without executing it."""
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars="|&;<>()")
        lexer.whitespace_split = True
        return list(lexer)
    except ValueError:
        return []


def _command_basename(token: str) -> str:
    return token.rsplit("/", 1)[-1]


def _has_wildcard(path: str) -> bool:
    return "*" in path or "?" in path


def _is_recordable_path(path: str) -> bool:
    return bool(path) and path != "-" and not _has_wildcard(path)


def _has_complex_shell_shape(tokens: list[str]) -> bool:
    if not tokens:
        return True
    for token in tokens:
        if token in _SHELL_COMPLEX_TOKENS:
            return True
        if _command_basename(token) in _SHELL_COMPLEX_COMMANDS:
            return True
    return False


def _has_complex_pipe_chain_shape(tokens: list[str]) -> bool:
    if not tokens or tokens.count("|") != 1:
        return True
    for token in tokens:
        if token == "|":
            continue
        if token in _SHELL_COMPLEX_TOKENS:
            return True
        if _command_basename(token) in _SHELL_COMPLEX_COMMANDS:
            return True
    return False


def _option_takes_value(token: str, options_with_values: frozenset[str]) -> bool:
    if token in options_with_values:
        return True
    if token.startswith("--") and "=" in token:
        return False
    return token in options_with_values


def _path_operands(
    tokens: list[str],
    *,
    options_with_values: frozenset[str] = frozenset(),
    plus_is_option: bool = False,
) -> list[str]:
    operands: list[str] = []
    i = 1
    while i < len(tokens):
        token = tokens[i]
        if token == "--":
            operands.extend(tokens[i + 1:])
            break
        if _option_takes_value(token, options_with_values):
            i += 2
            continue
        if token.startswith("--") and any(
            token.startswith(f"{opt}=") for opt in options_with_values if opt.startswith("--")
        ):
            i += 1
            continue
        if token.startswith("-") and token != "-":
            i += 1
            continue
        if plus_is_option and token.startswith("+"):
            i += 1
            continue
        operands.append(token)
        i += 1
    return operands


def _single_path(operands: list[str]) -> list[str]:
    if len(operands) != 1:
        return []
    path = operands[0]
    if not _is_recordable_path(path):
        return []
    return [path]


def _sed_write_in_place(tokens: list[str]) -> bool:
    for token in tokens[1:]:
        if token == "--in-place" or token.startswith("--in-place="):
            return True
        if token == "-i" or token.startswith("-i"):
            return True
    return False


def _extract_sed_read_paths(tokens: list[str]) -> list[str]:
    silent = False
    scripts: list[str] = []
    operands: list[str] = []
    i = 1
    while i < len(tokens):
        token = tokens[i]
        if token == "--":
            operands.extend(tokens[i + 1:])
            break
        if token in ("-n", "--quiet", "--silent"):
            silent = True
            i += 1
            continue
        if token == "-e":
            if i + 1 >= len(tokens):
                return []
            scripts.append(tokens[i + 1])
            i += 2
            continue
        if token.startswith("-e") and len(token) > 2:
            scripts.append(token[2:])
            i += 1
            continue
        if token == "-f" or token.startswith("--file"):
            return []
        if token.startswith("-") and token != "-":
            i += 1
            continue
        if not scripts:
            scripts.append(token)
        else:
            operands.append(token)
        i += 1

    if len(operands) != 1 or not scripts:
        return []
    path = operands[0]
    if not _is_recordable_path(path):
        return []

    if silent and all(_SED_PRINT_ONLY_RE.fullmatch(script.strip()) for script in scripts):
        return [path]
    if not silent and len(scripts) == 1 and _SED_PRINT_THEN_DELETE_RE.fullmatch(scripts[0].strip()):
        return [path]
    return []


def _grep_is_recursive(tokens: list[str]) -> bool:
    for token in tokens[1:]:
        if token in _GREP_RECURSIVE_FLAGS:
            return True
        if token.startswith("--"):
            continue
        if token.startswith("-") and ("r" in token[1:] or "R" in token[1:]):
            return True
    return False


def _extract_grep_read_paths(tokens: list[str]) -> list[str]:
    if _grep_is_recursive(tokens):
        return []

    operands: list[str] = []
    i = 1
    while i < len(tokens):
        token = tokens[i]
        if token == "--":
            operands.extend(tokens[i + 1:])
            break
        # -e / -f make it harder to distinguish pattern files from searched files.
        if token in ("-e", "--regexp", "-f", "--file") or token.startswith(("-e", "-f")):
            return []
        if _option_takes_value(token, _GREP_OPTIONS_WITH_VALUES):
            i += 2
            continue
        if token.startswith("--") and any(
            token.startswith(f"{opt}=") for opt in _GREP_OPTIONS_WITH_VALUES if opt.startswith("--")
        ):
            i += 1
            continue
        if token.startswith("-") and token != "-":
            i += 1
            continue
        operands.append(token)
        i += 1

    if len(operands) != 2:
        return []
    path = operands[1]
    if not _is_recordable_path(path):
        return []
    return [path]


def _extract_awk_read_paths(tokens: list[str]) -> list[str]:
    operands: list[str] = []
    i = 1
    while i < len(tokens):
        token = tokens[i]
        if token == "--":
            operands.extend(tokens[i + 1:])
            break
        if token in ("-f", "-v"):
            return []
        if token.startswith("-") and token != "-":
            i += 1
            continue
        operands.append(token)
        i += 1

    if len(operands) != 2:
        return []
    script, path = operands
    if ">" in script or "|" in script or not _is_recordable_path(path):
        return []
    return [path]


def _extract_head_tail_pipe_read_paths(tokens: list[str]) -> list[str]:
    """Recognize single-file read-only `cat/head/tail file | head/tail` chains.

    Deliberate skips:
    - `find ... | xargs cat` reads unknown files; `read_first` needs exact paths.
    - `grep -r/-R/--recursive` reads a tree; directory prefixes do not satisfy
      karma's per-file read tracking.
    """
    if _has_complex_pipe_chain_shape(tokens):
        return []

    pipe_index = tokens.index("|")
    left = tokens[:pipe_index]
    right = tokens[pipe_index + 1:]
    if not left or not right:
        return []

    left_command = _command_basename(left[0])
    right_command = _command_basename(right[0])
    if left_command not in {"cat", "head", "tail"}:
        return []
    if right_command not in {"head", "tail"}:
        return []

    if _path_operands(
        right,
        options_with_values=_TAIL_HEAD_OPTIONS_WITH_VALUES,
        plus_is_option=True,
    ):
        return []

    options_with_values = (
        _TAIL_HEAD_OPTIONS_WITH_VALUES if left_command in {"head", "tail"} else frozenset()
    )
    return _single_path(_path_operands(
        left,
        options_with_values=options_with_values,
        plus_is_option=left_command in {"head", "tail"},
    ))


def extract_read_paths_from_exec_command(command: str) -> tuple[list[str], bool]:
    """Return (read_file_paths, is_write) for conservative Codex shell reads."""
    tokens = _shell_tokens(command)
    if not tokens:
        return [], False

    command_name = _command_basename(tokens[0])
    if command_name == "sed" and _sed_write_in_place(tokens):
        return [], True
    pipe_read_paths = _extract_head_tail_pipe_read_paths(tokens)
    if pipe_read_paths:
        return pipe_read_paths, False
    if _has_complex_shell_shape(tokens):
        return [], False

    if command_name in _SIMPLE_SHELL_READ_COMMANDS:
        options_with_values = (
            _TAIL_HEAD_OPTIONS_WITH_VALUES if command_name in ("tail", "head") else frozenset()
        )
        return _single_path(_path_operands(
            tokens,
            options_with_values=options_with_values,
            plus_is_option=command_name in ("tail", "head", "less", "more"),
        )), False
    if command_name == "sed":
        return _extract_sed_read_paths(tokens), False
    if command_name == "grep":
        return _extract_grep_read_paths(tokens), False
    if command_name == "awk":
        return _extract_awk_read_paths(tokens), False
    return [], False


def _canonical_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _canonical_json(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_canonical_json(item) for item in value]
    return value


def codex_hook_trusted_hash(event_key: str, command: str, timeout: int = 30) -> str:
    """Return Codex's trust hash for a command hook identity.

    Real Codex 0.130 source evidence:
    `codex-rs/hooks/src/engine/discovery.rs::command_hook_hash` builds a
    normalized identity `{event_name, hooks:[{type, command, timeout, async}]}`
    and `codex-rs/config/src/fingerprint.rs::version_for_toml` hashes its
    canonical JSON with SHA256. We mirror only that small deterministic
    algorithm so karma can pre-trust the karma-owned wrappers it just wrote.
    """
    identity = {
        "event_name": event_key,
        "hooks": [{
            "type": "command",
            "command": command,
            "timeout": timeout,
            "async": False,
        }],
    }
    serialized = json.dumps(
        _canonical_json(identity),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(serialized).hexdigest()}"


def _codex_hook_timeout(raw_timeout: Any) -> int:
    try:
        timeout = int(raw_timeout)
    except (TypeError, ValueError):
        timeout = 600
    return max(timeout, 1)


class CodexBackend(JsonHooksBackend):
    name = "codex"
    display_name = "Codex CLI"
    _CONFIG_DIR_NAME = ".codex"
    _SETTINGS_FILENAME = "hooks.json"
    _CLIENT_CMD = "codex"

    # Codex 0.130 支持 6 个 hook event。karma 用 5 个跟 Claude Code baseline /
    # tool / stop 流程对齐；PermissionRequest 暂不用。
    _HOOK_EVENTS: dict[str, str] = {
        "SessionStart": "session_start",
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

    @staticmethod
    def _hook_event_key(event_name: str) -> str:
        key = re.sub(r"(?<!^)([A-Z])", r"_\1", event_name).lower()
        return key

    def codex_hook_state_entries(
        self,
        settings: dict | None = None,
    ) -> dict[str, dict[str, str | bool]]:
        """Build `[hooks.state]` entries that pre-trust karma-owned wrappers.

        Codex treats newly configured user hooks as untrusted until the config
        contains `trusted_hash == current_hash` for the hook key. This method
        mirrors Codex's own key/hash derivation for the entries karma installs
        into `~/.codex/hooks.json`, and intentionally never inspects or trusts
        non-karma hook entries.
        """
        if settings is None:
            settings = self.load_settings()

        settings_path = self.settings_path()
        states: dict[str, dict[str, str | bool]] = {}
        hooks = settings.get("hooks", {})
        for event_name in self._HOOK_EVENTS:
            event_key = self._hook_event_key(event_name)
            for group_index, entry in enumerate(hooks.get(event_name, [])):
                if not self.is_karma_entry(entry):
                    continue
                for handler_index, hook in enumerate(entry.get("hooks", [])):
                    command = hook.get("command", "")
                    if "karma_" not in command:
                        continue
                    timeout = _codex_hook_timeout(hook.get("timeout", 600))
                    key = f"{settings_path}:{event_key}:{group_index}:{handler_index}"
                    states[key] = {
                        "enabled": True,
                        "trusted_hash": codex_hook_trusted_hash(event_key, command, timeout),
                    }
        return states

    def trust_karma_hooks(self, settings: dict | None = None) -> list[str]:
        """Persist Codex hook trust state for karma wrappers in config.toml.

        This is a narrow replacement for the manual `/hooks` review step. It
        only writes `[hooks.state]` entries for karma-generated wrapper paths.
        If Codex changes the hash algorithm, hooks fall back to "modified" or
        "untrusted" rather than silently trusting arbitrary commands.
        """
        config_path = Path.home() / ".codex" / "config.toml"
        trust_entries = self.codex_hook_state_entries(settings)
        if not trust_entries:
            return []
        config_path.parent.mkdir(parents=True, exist_ok=True)
        existing = config_path.read_text(encoding="utf-8") if config_path.exists() else ""

        lines = existing.splitlines()
        output: list[str] = []
        i = 0
        replaced = 0
        seen_keys: set[str] = set()
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            if stripped.startswith("[hooks.state.") and stripped.endswith("]"):
                raw_key = stripped[len("[hooks.state."):-1].strip()
                if raw_key.startswith('"') and raw_key.endswith('"'):
                    raw_key = raw_key[1:-1]
                if raw_key in trust_entries:
                    output.append(line)
                    output.append("enabled = true")
                    output.append(f'trusted_hash = "{trust_entries[raw_key]["trusted_hash"]}"')
                    seen_keys.add(raw_key)
                    replaced += 1
                    i += 1
                    while i < len(lines) and not (
                        lines[i].strip().startswith("[") and lines[i].strip().endswith("]")
                    ):
                        child = lines[i].strip()
                        if not child.startswith(("trusted_hash", "enabled")):
                            output.append(lines[i])
                        i += 1
                    continue
            output.append(line)
            i += 1

        missing = {key: value for key, value in trust_entries.items() if key not in seen_keys}
        if missing:
            if output and output[-1].strip():
                output.append("")
            if not any(line.strip() == "[hooks.state]" for line in output):
                output.append("[hooks.state]")
                output.append("")
            for key, value in missing.items():
                output.append(f'[hooks.state."{key}"]')
                output.append("enabled = true")
                output.append(f'trusted_hash = "{value["trusted_hash"]}"')
                output.append("")

        final = "\n".join(output).rstrip() + "\n"
        config_path.write_text(final, encoding="utf-8")
        total = len(trust_entries)
        added = len(missing)
        return [f"Codex karma hook trust state 已写入 {config_path} ({added} 新增, {replaced} 更新, {total} 总计)"]

    def save_settings(self, data: dict) -> None:
        super().save_settings(data)
        try:
            self.trust_karma_hooks(data)
        except OSError:
            # install-hooks is allowed to finish with hooks.json written; the
            # post-install message tells users how to approve manually if trust
            # state persistence failed.
            pass

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
        else:
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

    def normalize_tool_name(self, raw_tool_name: str, payload: dict) -> str:
        """Codex apply_patch → Edit; 其他 tool_name 透传."""
        return _CODEX_TOOL_MAP.get(raw_tool_name, raw_tool_name)

    def emit_allow(self, payload: dict) -> str:
        """Codex PreToolUse 不接受 `permissionDecision:"allow"` 字面 — 官方文档:

        > "permissionDecision: 'ask', legacy 'decision: 'approve' ... are parsed
        > but not supported yet, so they fail open."
        > "To permit a tool call, either return an empty JSON object (`{}`) or
        > exit with code `0` and no output."

        v0.9.15 cross-model audit 时记错为 "Codex 也接受 hookSpecificOutput shape"
        — 真测试 (2026-05-16 codex 0.130 cli interactive) 报错:
            error: PreToolUse hook returned unsupported permissionDecision:allow

        Allow shape = {}. Deny shape 跟 Claude 一致继续走基类 emit_deny (codex
        接受 permissionDecision:"deny" — 跟 allow 不对称是 codex 本身的设计选择).
        """
        return "{}"

    def emit_deny(self, reason: str, payload: dict) -> str:
        """Codex PreToolUse 接受 hookSpecificOutput.permissionDecision:"deny"
        shape (跟 Claude 一致, 真测试 2026-05-16 确认拦截工作). 但仍要带
        additionalContext 字段防止 codex 在某些版本期望它在 deny shape 里.
        """
        return json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }, ensure_ascii=False)

    def normalize_tool_input(
        self, raw_tool_name: str, raw_tool_input: Any, payload: dict,
    ) -> Any:
        """Codex apply_patch (字符串 envelope) → karma canonical Edit shape dict.

        Output shape:
            {
              "file_path": <primary Update/Add path>,    # read_first single-path 兜底
              "new_string": <full envelope>,             # keyword scan visibility
              "multi_file_targets": [{"op", "path"}...], # v0.10.0 canonical 多文件字段
            }

        exec_command 只读 shell: 保留原 input，并补 read_file_paths 给通用层后续 record_read。
        其他非 apply_patch tool_call: passthrough 原 input。
        envelope 解析失败（malformed / 非 envelope 字符串）: passthrough 原 input。
        """
        if raw_tool_name == "exec_command":
            if not isinstance(raw_tool_input, dict):
                return raw_tool_input
            command = raw_tool_input.get("command")
            if not isinstance(command, str) or not command.strip():
                command = raw_tool_input.get("cmd")
            if not isinstance(command, str) or not command.strip():
                return raw_tool_input
            read_paths, is_write = extract_read_paths_from_exec_command(command)
            needs_command_alias = "command" not in raw_tool_input and "cmd" in raw_tool_input
            if not read_paths and not is_write and not needs_command_alias:
                return raw_tool_input
            normalized = dict(raw_tool_input)
            if needs_command_alias:
                normalized["command"] = command
            if read_paths:
                normalized["read_file_paths"] = read_paths
            if is_write:
                normalized["is_write"] = True
            return normalized
        if raw_tool_name != "apply_patch":
            return raw_tool_input
        envelope = _extract_codex_patch_text(raw_tool_input)
        files = parse_apply_patch_envelope(envelope)
        if not files:
            return raw_tool_input
        primary = next(
            (f["path"] for f in files if f["op"] in ("Update", "Add")),
            files[0]["path"],
        )
        return {
            "file_path": primary,
            "new_string": envelope,
            "multi_file_targets": files,
        }

    def skill_install_targets(self, skill_name: str = "karma") -> list[tuple[Path, str]]:
        """Codex Agent Skills 装到 ~/.agents/skills/<name>/SKILL.md (Markdown 原样).

        注意路径是 ~/.agents/ 不是 ~/.codex/ — 这是 OpenAI 的设计 (跟 Anthropic 共享
        `.agents/skills/` 命名空间). 触发: /skills menu 或 $skill_name inline 或 auto.
        """
        return [(Path.home() / ".agents" / "skills" / skill_name / "SKILL.md", "markdown")]

    def post_install_message(self) -> list[str]:
        """Codex 0.130+ hook 需要 trusted_hash 才会运行。

        实测 2026-05-16：本机 codex cli 跑 apply_patch 编辑文件**真成功**，但 karma
        violations.jsonl + session-state 完全无新条目 → hook 根本没 fire. 根因
        就是用户没在 TUI `/hooks` 审批. v0.10.2 起 karma 按 Codex 0.130 源码
        算法给自己生成的 wrapper 写入 trusted_hash；这里仍提示用户如何核验。
        """
        hooks_dir = self.hooks_dir()
        wrappers = [
            f"karma_{basename}.py" for basename in self._HOOK_EVENTS.values()
        ]
        wrapper_paths = [str(hooks_dir / w) for w in wrappers]

        msg: list[str] = [
            "",
            "━" * 70,
            "Codex hook 状态",
            "━" * 70,
            "",
            "karma 已为自己生成的 Codex wrapper 写入 trusted_hash，正常情况下",
            "不需要再手动逐个 approve。Codex 如果升级了 hook trust 算法，会在",
            "`/hooks` 里显示为 new/modified；这时按下面路径复核并 approve。",
            "",
            "▶ 复核（可选，30 秒）:",
            "  1. 启动 codex CLI: `codex`",
            "  2. 在 TUI 里输入: /hooks",
            f"  3. 确认这 {len(wrapper_paths)} 个 wrapper 状态是 trusted/approved:",
        ]
        for wp in wrapper_paths:
            msg.append(f"     ✓  {wp}")
        msg.extend([
            "",
            "▶ 验证生效:",
            "  安装后随便让 codex 改一个你没先 Read 过的文件 — 应该被 karma 🛑 拦截.",
            "  如果还是不拦，跑 `karma doctor` 看诊断或来 issue 反馈.",
            "",
            "━" * 70,
        ])
        return msg

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
