"""Codex CLI backend — `~/.codex/hooks.json` + 启用 `features.hooks` + apply_patch envelope parser。

继承 `JsonHooksBackend`，差异：
① 配置文件名 `hooks.json` 不是 `settings.json`
② hook entry 加 timeout: 30
③ pre_install_setup 调 `codex features enable hooks` 永久启用 feature flag
④ post_install_message 响亮警示 TUI `/hooks` 审批步骤（v0.9.17 引入）
⑤ normalize_tool_name 映射 apply_patch → Edit
⑥ normalize_tool_input 解析 apply_patch envelope 字符串成 canonical Edit shape
   含 multi_file_targets（v0.10.0 把 envelope parser 从 protocol_adapter 搬过来）

参考：
- 官方 hook 协议: https://developers.openai.com/codex/hooks
- 实测 2026-05-16：Codex 0.130 hook 只在 interactive TUI 触发（exec mode 不 fire），
  且每个 hook 必须 TUI `/hooks` 手动 approve（GitHub issue #17532）
- 真捕获的 apply_patch envelope 来自 codex 0.130 + GPT-5.5 session rollout
  (rollout-2026-05-16T13-51-47-...jsonl)
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from karma.backends._json_hooks import JsonHooksBackend


# Codex → karma canonical tool_name 映射
# apply_patch 是 Codex 主要编辑入口（custom_tool_call 类型），归一化到 Edit
# 让 karma 通用 check 比较「tool_name in ('Edit', 'Write')」时识别它。
_CODEX_TOOL_MAP: dict[str, str] = {
    "apply_patch": "Edit",
    # Bash 已 canonical，Read/Write 暂未在 Codex 文档明确同名
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


class CodexBackend(JsonHooksBackend):
    name = "codex"
    display_name = "Codex CLI"
    _CONFIG_DIR_NAME = ".codex"
    _SETTINGS_FILENAME = "hooks.json"
    _CLIENT_CMD = "codex"

    # Codex 6 个 event 中 karma 用 4 个跟 Claude Code 对齐。SessionStart /
    # PermissionRequest karma 暂不用 — 需要时也能加到这个 dict。
    _HOOK_EVENTS: dict[str, str] = {
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
            return steps

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
        import json
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

        非 apply_patch tool_call: passthrough 原 input。
        envelope 解析失败（malformed / 非 envelope 字符串）: passthrough 原 input。
        """
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
        """Codex 0.130+ 必须在 TUI `/hooks` 命令里逐个 approve karma 4 个 wrapper，
        karma 装完 hooks.json 不等于真生效（codex 安全模型不让第三方批量预审）。

        实测 2026-05-16：本机 codex cli 跑 apply_patch 编辑文件**真成功**，但 karma
        violations.jsonl + session-state 完全无新条目 → hook 根本没 fire. 根因
        就是用户没在 TUI `/hooks` 审批. 之前埋 README 第 82 行表格 → 用户装完
        以为生效实际 0 hook fire (rule #4 反方向隐性失败).

        v0.9.17 修法: install 完成时**响亮警示框** + 列 4 个 wrapper 完整路径,
        让用户直接复制到 codex TUI 比对 approval 列表逐个 approve.
        """
        hooks_dir = self.hooks_dir()
        wrappers = [
            f"karma_{basename}.py" for basename in self._HOOK_EVENTS.values()
        ]
        wrapper_paths = [str(hooks_dir / w) for w in wrappers]

        msg: list[str] = [
            "",
            "━" * 70,
            "⚠️  Codex 关键最后一步 — hooks.json 写好了但 codex 还没生效",
            "━" * 70,
            "",
            "Codex 0.130+ 出于安全考虑，**每个 hook 必须在 codex TUI 里手动",
            "approve**，karma 无法替你绕（codex 不公开批量预审 API）。",
            "**没做这步 = karma 在 codex 下完全静默，所有规则不拦截**。",
            "",
            "▶ 操作（30 秒）:",
            "  1. 启动 codex CLI: `codex`",
            "  2. 在 TUI 里输入: /hooks",
            "  3. 逐个 approve 这 4 个 wrapper:",
        ]
        for wp in wrapper_paths:
            msg.append(f"     ✓  {wp}")
        msg.extend([
            "",
            "▶ 验证生效:",
            "  approve 后随便让 codex 改一个你没先 Read 过的文件 — 应该被 karma 🛑 拦截.",
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
