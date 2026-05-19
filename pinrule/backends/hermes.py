"""Hermes Agent backend — `~/.hermes/config.yaml` + `~/.hermes/agent-hooks/`.

NousResearch Hermes Agent v0.14.0+ (2026-05-16) — persistent server agent with
plugin hooks. Docs: https://hermes-agent.nousresearch.com/docs/user-guide/features/hooks

跟 Claude / Codex / Cursor 关键差异:

① **配置是 YAML 不是 JSON** (`~/.hermes/config.yaml`). pinrule v0.17.0 已 drop
   PyYAML 真承诺 0 runtime deps, 所以本 module 内联**最简 YAML subset
   emitter/parser** — 只支持 mapping + sequence + scalar (str/int/bool/null)
   三种 node type, 不支持 anchors / aliases / flow style / multi-line strings /
   multi-doc. 用户 config.yaml 含 advanced YAML 时 pinrule loud-fail with clear
   message — 不静默把用户 config 改坏 (rule #4 loud-failure-with-evidence).

② **Event 名 snake_case**: `pre_tool_call` / `post_tool_call` / `pre_llm_call` /
   `on_session_start` / `on_session_end` / `agent:end` (mapped to pinrule
   canonical wrapper basenames via HERMES_HOOK_EVENTS).

③ **stdin payload nested user_message**: Hermes 顶层 `session_id` / `tool_name` /
   `tool_input` / `cwd` 跟 Claude/Codex 同名, 但 user prompt 在 `extra.user_message`
   nested. pinrule 主流程对 prompt 内容不依赖 (只注入 context), 所以这条暂不影响
   核心功能. 真 stop/audit 类 message extraction 字段待 user 本机捕获 payload
   再补 fallback 链 (TODO 见下).

④ **Output shape 跟 Claude 兼容**: Hermes docs 真接受
   `{"decision": "block", "reason": ...}` (Claude shape) 或
   `{"action": "block", "message": ...}` — pinrule emit Claude 同款省事.
   pre_llm_call 接受顶层 `{"context": "..."}` 注入 (比 Claude 简单).

⑤ **Hook 脚本目录**: pinrule wrapper 放 `~/.hermes/agent-hooks/pinrule_*.py`
   (Hermes docs 示例用 agent-hooks/ 子目录避免跟 Hermes 自带 hook 撞名空间).

未验证的真 unknown (等 user 真本机装 Hermes 捕获 stdin payload 才能定):
- `agent:end` / `on_session_end` payload 是否含 last assistant message / 字段名?
- `pre_llm_call` payload 的 `extra.user_message` 真存在 vs 其他位置?
- matcher regex 真匹配 tool_name 还是 normalize 前的 raw? (pinrule 不用 matcher
  绕过这个 unknown)
- Hermes config.yaml 真允许的 schema 变体 (一些 yaml linters 严格 / 宽松不同)
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pinrule.backends._base import SettingsParseError
from pinrule.backends._json_hooks import JsonHooksBackend, hook_command_str
from pinrule.backends.native_capabilities import HERMES_HOOK_EVENTS


# Hermes tool_name → pinrule canonical 映射.
# Hermes 47+ built-in tools 多数 pinrule 不关心 (Web search / scheduled tasks 等
# 不触发文件 IO 或 shell). 真要 normalize 的是会触发 pinrule check 的 tool 类:
# Bash / Read / Write / Edit / Agent.
_HERMES_TOOL_MAP: dict[str, str] = {
    "terminal": "Bash",      # Hermes terminal == Claude Bash (shell exec)
    "shell": "Bash",          # alias
    "execute_shell": "Bash",  # alias
    "read_file": "Read",
    "write_file": "Write",
    "patch_file": "Edit",
    "edit_file": "Edit",
    "create_file": "Write",
    # 其他 Hermes tool (web_search / schedule_task / send_message 等) passthrough —
    # pinrule check 见 unknown tool_name 不会命中 (跟现有 Claude PreToolUse 行为一致).
}


class HermesBackend(JsonHooksBackend):
    """NousResearch Hermes Agent backend — persistent server agent w/ plugin hooks."""

    name = "hermes"
    display_name = "Hermes Agent"
    _CONFIG_DIR_NAME = ".hermes"
    _SETTINGS_FILENAME = "config.yaml"
    _CLIENT_CMD = "hermes"

    _HOOK_EVENTS: dict[str, str] = dict(HERMES_HOOK_EVENTS)

    def hooks_dir(self) -> Path:
        """Hermes hook 脚本目录 `~/.hermes/agent-hooks/` (不是 hooks/).

        跟 Claude/Codex/Cursor 都用 `~/.X/hooks/` 不同 — Hermes 文档示例
        用 `~/.hermes/agent-hooks/block-rm-rf.sh` 避免跟自带 hook 撞名空间.
        """
        from pinrule.paths import pinrule_install_root
        return pinrule_install_root() / self._CONFIG_DIR_NAME / "agent-hooks"

    def build_event_entry(self, hook_name_lower: str, event_name: str) -> dict:
        """Hermes hook entry: `{command: str, timeout?: int, matcher?: str}`.

        Per docs (https://hermes-agent.nousresearch.com/docs/user-guide/features/hooks):
            hooks:
              pre_tool_call:
                - matcher: "terminal"
                  command: "~/.hermes/agent-hooks/block-rm-rf.sh"
                  timeout: 5

        pinrule 不用 matcher (要拦所有 tool call, 让 pinrule check 内部
        识别 Bash / Read / Write / Edit 真路径 — 跟现有 Claude PreToolUse 行为一致).
        timeout 30s 跟 Codex 一致 (60 是 Hermes 默认, 收紧避免长 hook 阻塞 Agent).
        """
        wrapper = self.hooks_dir() / f"pinrule_{hook_name_lower}.py"
        return {
            "command": hook_command_str(wrapper),
            "timeout": 30,
        }

    def is_pinrule_entry(self, entry: dict) -> bool:
        """识别 pinrule entry — `command` 含 `pinrule_` 前缀."""
        return "pinrule_" in entry.get("command", "")

    def load_settings(self) -> dict:
        """读 `~/.hermes/config.yaml` — line-based surgical, 只 extract `hooks:` 段.

        v0.19.0 fix: 之前真 parse 整个 yaml 文件撞 hermes default config 的
        multi-line string 续行 / unicode escape continuation. 真根因不是 yaml
        parser 不够强 — 是 pinrule 真不应该 parse 整个 hermes config (它只关心
        hooks 段). 本方法 line-based 找顶层 `hooks:` 段提取出来 parse 成 dict,
        其他 yaml 段一律不读不碰 — 真无视 user config 含啥高级语法.
        """
        p = self.settings_path()
        if not p.exists():
            return {}
        raw = p.read_text(encoding="utf-8")
        hooks_block = _extract_hooks_section(raw)
        if not hooks_block:
            return {}
        try:
            return _parse_yaml_subset("hooks:\n" + hooks_block)
        except _YamlSubsetError as e:
            raise SettingsParseError(
                f"{self._SETTINGS_FILENAME} 的 `hooks:` 段含 pinrule 不支持的 YAML 子集语法: {e}\n"
                f"路径: {p}\n"
                f"pinrule 用 0 runtime deps 不依赖 PyYAML, hooks 段仅支持基础语法 "
                f"(mapping / sequence / scalar). pinrule 自己生成的 hooks 段一定能 parse — "
                f"如果失败说明 hooks 段被 user 手工改过或 hermes 升级后 schema 变了, "
                f"开 GitHub issue 反馈."
            ) from e

    def save_settings(self, data: dict) -> None:
        """原子写 `~/.hermes/config.yaml` — line-based surgical 只动 `hooks:` 段.

        真**不重写整个文件**, 只:
        1. 读原始 raw text
        2. 找顶层 `hooks:` 段起止行号, surgical 删掉旧 hooks 段
        3. 把新 hooks 段 emit 出来 append 到末尾
        4. 其他 yaml 段 (model / terminal / agent / personalities / etc.)
           全部原样保留 — anchors / multi-line / unicode escape 都不破坏

        atomic: tmp + os.replace 防中断 truncate.
        """
        p = self.settings_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        existing_raw = p.read_text(encoding="utf-8") if p.exists() else ""
        stripped = _strip_hooks_section(existing_raw)
        new_hooks_text = _emit_yaml_subset({"hooks": data.get("hooks", {})})
        if stripped.strip():
            final = stripped.rstrip() + "\n\n" + new_hooks_text
        else:
            final = new_hooks_text
        tmp = p.with_suffix(p.suffix + f".pinrule-tmp.{os.getpid()}")
        tmp.write_text(final, encoding="utf-8")
        os.replace(tmp, p)

    def normalize_tool_name(self, raw_tool_name: str, payload: dict) -> str:
        """Hermes tool_name → pinrule canonical (Bash / Read / Write / Edit)."""
        return _HERMES_TOOL_MAP.get(raw_tool_name, raw_tool_name)

    def emit_deny(self, reason: str, payload: dict) -> str:
        """Hermes block — Claude 同款 `{decision: block, reason: ...}` shape.

        Hermes docs 明确接受两种 shape (normalize):
            {"decision": "block", "reason": ...}
            {"action": "block", "message": ...}
        pinrule 用 Claude 同款省事 (跨 backend output 一致).
        """
        return json.dumps(
            {"decision": "block", "reason": reason}, ensure_ascii=False
        )

    def emit_allow(self, payload: dict) -> str:
        """Hermes pass-through — 空 JSON object (按 docs "no-op / pass-through")."""
        return json.dumps({})

    def emit_context_injection(
        self, event_name: str, additional_context: str, payload: dict,
    ) -> str:
        """Hermes context injection.

        - `pre_llm_call`: 顶层 `{"context": "..."}` (Hermes 文档明确支持)
        - 其他 inject 类 event (`on_session_start` / `post_tool_call`):
          Hermes docs 没明确说支持 context 字段, 安全 fallback 空 `{}`
          (让 agent 见无变化, 不主动注 — 等 user 真测试反馈再扩展)
        """
        text = (additional_context or "").strip()
        if not text:
            return json.dumps({})
        if event_name == "pre_llm_call":
            return json.dumps({"context": additional_context}, ensure_ascii=False)
        return json.dumps({})

    def emit_stop_block(self, reason: str, payload: dict) -> str:
        """Hermes agent:end / Stop event 真无明确 block 机制 (docs 未详).

        安全 fallback: 输出到 stderr (pinrule notification 走 stderr 仍可见),
        return empty JSON. 等 user 本机捕获 agent:end 真行为后再增强.
        """
        return json.dumps({})

    def skill_install_targets(self, skill_name: str = "pinrule") -> list[tuple[Path, str]]:
        """Hermes Agent skill 装机目标: `~/.hermes/skills/<skill_name>/SKILL.md`.

        Source-grounded: `hermes_constants.get_skills_dir() = get_hermes_home() / "skills"`.
        Hermes Agent docs 提到 skills "compatible with agentskills.io open standard"
        — pinrule SKILL.md 真按这个标准装到 ~/.hermes/skills/pinrule/SKILL.md.
        """
        from pinrule.paths import pinrule_install_root
        skills_dir = pinrule_install_root() / self._CONFIG_DIR_NAME / "skills" / skill_name
        return [(skills_dir / "SKILL.md", "markdown")]


# ---------------------------------------------------------------------- #
# YAML subset emitter / parser — 无 PyYAML 依赖.                         #
# 只支持 pinrule 真要的最小语法 (mapping + sequence + scalar).            #
# 不支持: anchors / flow style / multi-line / multi-doc / tags.          #
# ---------------------------------------------------------------------- #


class _YamlSubsetError(Exception):
    """Raised when input YAML uses features outside pinrule's subset support."""


# ---------------------------------------------------------------------- #
# Line-based surgical operator (v0.19.0) — 只动 `hooks:` 段, 不 parse 整 file.
# Hermes 默认 config.yaml 含 multi-line string 续行 + unicode escape 等真
# 复杂语法 pinrule subset parser 处理不了 — 但 pinrule 也真没必要 parse
# 整个 hermes config, 它只关心 hooks 段. 这俩 helper 用 line-based 操作
# 把 hooks 段从 raw 文本里 extract / strip 出来, 其他段一律不碰.
# ---------------------------------------------------------------------- #


def _extract_hooks_section(raw: str) -> str:
    """从 raw config.yaml 文本里 extract 顶层 `hooks:` 段内容 (不含 `hooks:` 行).

    返回 hooks 段下面真所有 indented 行 (含空行) join 起来的 string.
    没有 `hooks:` 顶层 key 返空 string.

    真识别规则:
    - 顶层 key = 行首无 indent + 含 `:` + 非 comment
    - 注意 `hooks:` vs `hooks_auto_accept:` 真严格区分 — 用 `hooks:` 后跟空或空白.
    """
    lines = raw.splitlines()
    in_hooks = False
    out: list[str] = []
    for line in lines:
        if not in_hooks:
            stripped = line.rstrip()
            # 真严格匹配顶层 `hooks:` (不是 hooks_auto_accept 等)
            if stripped == "hooks:" or stripped.startswith("hooks: "):
                in_hooks = True
                # inline `hooks: {}` 真特殊 case — 返空 (空 hooks)
                inline_val = stripped[len("hooks:"):].strip()
                if inline_val == "{}":
                    return ""
                continue
        else:
            # 真段内: indented 行 (含空行) 都属于 hooks 段
            if not line.strip():
                # 空行: 真可能段内 (yaml 段间分隔) 或段后, 安全起见 keep 直到撞真新 top-level key
                out.append(line)
                continue
            # 行首无 whitespace 且非 comment → 新顶层 key, hooks 段结束
            if line[0] not in (" ", "\t", "#"):
                break
            out.append(line)
    # 去掉真 trailing 空行
    while out and not out[-1].strip():
        out.pop()
    return "\n".join(out)


def _strip_hooks_section(raw: str) -> str:
    """从 raw config.yaml 真删掉顶层 `hooks:` 段, 其他全保留 verbatim.

    用于 save_settings 真重写: strip 旧 hooks 段 → append 新 hooks 段.
    """
    lines = raw.splitlines()
    out: list[str] = []
    in_hooks = False
    for line in lines:
        if not in_hooks:
            stripped = line.rstrip()
            if stripped == "hooks:" or stripped.startswith("hooks: "):
                in_hooks = True
                continue
            out.append(line)
        else:
            if not line.strip():
                # 段内空行真 skip (它属于被删的段)
                continue
            if line[0] not in (" ", "\t", "#"):
                # 新顶层 key — hooks 段结束, 这行真保留
                in_hooks = False
                out.append(line)
            # else: indented (段内) → skip
    return "\n".join(out)


def _emit_yaml_subset(data: Any, indent: int = 0) -> str:
    """Emit dict/list/scalar as subset YAML string. Recursive."""
    lines: list[str] = []
    pad = "  " * indent
    if isinstance(data, dict):
        if not data:
            return f"{pad}{{}}\n" if indent == 0 else "{}"
        for k, v in data.items():
            if isinstance(v, dict):
                if not v:
                    lines.append(f"{pad}{k}: {{}}")
                else:
                    lines.append(f"{pad}{k}:")
                    lines.append(_emit_yaml_subset(v, indent + 1).rstrip("\n"))
            elif isinstance(v, list):
                if not v:
                    lines.append(f"{pad}{k}: []")
                else:
                    lines.append(f"{pad}{k}:")
                    for item in v:
                        lines.append(_emit_list_item(item, indent + 1))
            else:
                lines.append(f"{pad}{k}: {_emit_scalar(v)}")
        return "\n".join(lines) + "\n"
    return _emit_scalar(data) + "\n"


def _emit_list_item(item: Any, indent: int) -> str:
    """Emit a single sequence entry: `  - key: val` style."""
    pad = "  " * indent
    if isinstance(item, dict):
        if not item:
            return f"{pad}- {{}}"
        parts: list[str] = []
        first = True
        for ik, iv in item.items():
            prefix = f"{pad}- " if first else f"{pad}  "
            first = False
            if isinstance(iv, dict):
                if not iv:
                    parts.append(f"{prefix}{ik}: {{}}")
                else:
                    parts.append(f"{prefix}{ik}:")
                    parts.append(_emit_yaml_subset(iv, indent + 2).rstrip("\n"))
            elif isinstance(iv, list):
                if not iv:
                    parts.append(f"{prefix}{ik}: []")
                else:
                    parts.append(f"{prefix}{ik}:")
                    for sub in iv:
                        parts.append(_emit_list_item(sub, indent + 2))
            else:
                parts.append(f"{prefix}{ik}: {_emit_scalar(iv)}")
        return "\n".join(parts)
    return f"{pad}- {_emit_scalar(item)}"


def _emit_scalar(v: Any) -> str:
    """Emit scalar value. Quote string if contains special chars."""
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    s = str(v)
    if not s:
        return '""'
    needs_quote = (
        ":" in s or "#" in s
        or s.startswith(("-", "?", "!", "&", "*", "{", "[", '"', "'", "|", ">"))
        or s.strip() != s
        or s in ("null", "true", "false", "~")
    )
    if needs_quote:
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return s


def _parse_yaml_subset(text: str) -> dict:
    """Parse subset YAML text to dict. Raise _YamlSubsetError on unsupported syntax."""
    lines: list[tuple[int, str]] = []
    for raw_line in text.splitlines():
        stripped_right = raw_line.rstrip()
        if not stripped_right or stripped_right.lstrip().startswith("#"):
            continue
        leading = stripped_right[: len(stripped_right) - len(stripped_right.lstrip())]
        if "\t" in leading:
            raise _YamlSubsetError("tabs in indent not supported — use spaces")
        indent = len(leading)
        content = stripped_right.strip()
        # Reject unsupported markers (must look at full content, not just substrings)
        if content.startswith(("---", "...", "!!", "&", "*")):
            raise _YamlSubsetError(f"unsupported YAML feature in line: {content!r}")
        # Strip inline comment (only when ` #` separator, preserving `#` in quoted strings)
        if " #" in content and not (
            content.startswith('"') or content.startswith("'")
        ):
            content = content[: content.index(" #")].rstrip()
        lines.append((indent, content))
    if not lines:
        return {}
    result, consumed = _parse_block(lines, 0, lines[0][0])
    if consumed != len(lines):
        raise _YamlSubsetError(f"trailing content not parsed at line {consumed}")
    if not isinstance(result, dict):
        raise _YamlSubsetError("top-level YAML must be a mapping")
    return result


def _parse_block(
    lines: list[tuple[int, str]], start: int, expected_indent: int,
) -> tuple[Any, int]:
    """Recursive descent: parse block starting at lines[start] at given indent.

    Returns (parsed_value, next_line_index). Caller checks indent expectation.
    """
    if start >= len(lines):
        return {}, start
    indent, first = lines[start]
    if indent < expected_indent:
        return {}, start
    if first.startswith("- "):
        return _parse_sequence(lines, start, expected_indent)
    return _parse_mapping(lines, start, expected_indent)


def _parse_sequence(
    lines: list[tuple[int, str]], start: int, expected_indent: int,
) -> tuple[list[Any], int]:
    """Parse `- item` sequence at given indent."""
    items: list[Any] = []
    idx = start
    while idx < len(lines):
        ind, content = lines[idx]
        if ind != expected_indent or not content.startswith("- "):
            break
        body = content[2:].strip()
        if not body:
            raise _YamlSubsetError("empty sequence item not supported")
        # Inline mapping item: `- key: value` or `- key:` then nested
        if (
            ":" in body
            and not body.startswith(('"', "'"))
            and not body.startswith("{")
        ):
            item_dict, idx = _parse_dash_mapping(lines, idx, expected_indent)
            items.append(item_dict)
        else:
            items.append(_parse_scalar(body))
            idx += 1
    return items, idx


def _parse_dash_mapping(
    lines: list[tuple[int, str]], start: int, dash_indent: int,
) -> tuple[dict[str, Any], int]:
    """Parse a mapping item under `- ` line. First key on dash line, sibling
    keys aligned at dash_indent + 2 (i.e. 'aligned after the dash')."""
    sibling_indent = dash_indent + 2
    ind, content = lines[start]
    body = content[2:].strip()
    first_key, first_rest = body.split(":", 1)
    first_key = first_key.strip()
    first_rest = first_rest.strip()
    item_dict: dict[str, Any] = {}
    idx = start + 1
    if first_rest:
        item_dict[first_key] = _parse_inline_value(first_rest)
    else:
        nested, idx = _parse_block(lines, idx, sibling_indent + 2)
        item_dict[first_key] = nested
    # Collect sibling keys aligned at sibling_indent
    while idx < len(lines):
        sib_ind, sib_content = lines[idx]
        if sib_ind != sibling_indent or sib_content.startswith("- "):
            break
        if ":" not in sib_content:
            raise _YamlSubsetError(
                f"expected key:value at sibling indent, got: {sib_content!r}"
            )
        sib_key, sib_rest = sib_content.split(":", 1)
        sib_key = sib_key.strip()
        sib_rest = sib_rest.strip()
        if sib_rest:
            item_dict[sib_key] = _parse_inline_value(sib_rest)
            idx += 1
        else:
            nested, idx = _parse_block(lines, idx + 1, sibling_indent + 2)
            item_dict[sib_key] = nested
    return item_dict, idx


def _parse_mapping(
    lines: list[tuple[int, str]], start: int, expected_indent: int,
) -> tuple[dict[str, Any], int]:
    """Parse mapping (`key: value` lines) at given indent."""
    result: dict[str, Any] = {}
    idx = start
    while idx < len(lines):
        ind, content = lines[idx]
        if ind != expected_indent or content.startswith("- "):
            break
        if ":" not in content:
            raise _YamlSubsetError(f"expected key:value, got: {content!r}")
        key, rest = content.split(":", 1)
        key = key.strip()
        rest = rest.strip()
        if rest:
            result[key] = _parse_inline_value(rest)
            idx += 1
        else:
            child, idx = _parse_block(lines, idx + 1, expected_indent + 2)
            result[key] = child
    return result, idx


def _parse_inline_value(s: str) -> Any:
    """Parse inline value: empty dict/list / quoted str / scalar.

    Reject anchors (`&name`), aliases (`*name`), tags (`!!type`) — pinrule
    YAML subset 不支持这些 high-level features. 也 reject flow style ({} / []
    with content) 因为 emitter 真不用.
    """
    if s == "{}":
        return {}
    if s == "[]":
        return []
    if s.startswith(("{", "[")):
        raise _YamlSubsetError(f"flow style not supported: {s!r}")
    if s.startswith(("&", "*", "!!", "!")):
        raise _YamlSubsetError(f"anchors/aliases/tags not supported: {s!r}")
    return _parse_scalar(s)


def _parse_scalar(s: str) -> Any:
    """Parse scalar literal: null / bool / int / quoted str / bare str."""
    if s in ("null", "~", "Null", "NULL"):
        return None
    if s in ("true", "True", "TRUE"):
        return True
    if s in ("false", "False", "FALSE"):
        return False
    if (s.startswith('"') and s.endswith('"') and len(s) >= 2) or (
        s.startswith("'") and s.endswith("'") and len(s) >= 2
    ):
        inner = s[1:-1]
        if s.startswith('"'):
            inner = inner.replace('\\"', '"').replace("\\\\", "\\")
        return inner
    try:
        return int(s)
    except ValueError:
        return s
