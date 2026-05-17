"""JSON-hooks backend 通用基类 — 让加新 AI 客户端 backend 变成「填表」工作。

设计动机：vibe-island 这种「跨 AI 客户端通用桥」实证 8+ 个客户端都用类似模式：
- 配置文件 JSON 含顶层 `hooks` 字段
- 每个 event 是 array of entry，每个 entry 含 `hooks` array 含命令
- karma wrapper 路径含 `karma_` 前缀识别自己装的

3 个现有 backend（Claude / Codex / Cursor）共用以下逻辑：
- load_settings / save_settings JSON 原子写
- is_karma_entry 用前缀识别
- client_installed 检测命令在 PATH 或配置目录存在

v0.10.0 加入 4 个**协议契约方法**默认实现，让 backend 私有协议适配
（tool_name 映射、tool_input 解析、output shape）作为 backend 本身的责任：

- `normalize_tool_name(raw, payload)` — 默认 passthrough
- `normalize_tool_input(raw_name, raw_input, payload)` — 默认 passthrough
- `emit_deny(reason, payload)` — 默认 Claude 风格 hookSpecificOutput shape
- `emit_allow(payload)` — 默认 Claude 风格

Codex / Cursor / 任何后续 backend 在自己的文件 override 这些方法 — 通用层
`karma/hooks/*.py` 不再含 backend 字面。

抽到基类后，加新 backend 只需填 6 个类属性 + 可选 override 这 4 个契约 +
build_event_entry / pre_install_setup / post_install_message。

参考 vibe-island 实证的 9 家清单（详 CHANGELOG v0.4.0+ notes）：
Cursor / Factory / Qoder / Copilot / CodeBuddy / Kimi 等都能继承本基类。
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from karma.backends._base import SettingsParseError


class JsonHooksBackend:
    """AI 客户端 JSON hooks 配置 backend 共用实现。

    子类需填以下类属性：

    - `name`: str — backend 注册名（如 'claude-code' / 'codex' / 'cursor'）
    - `display_name`: str — 给用户看的名字（如 'Claude'）
    - `_CONFIG_DIR_NAME`: str — `~/` 下配置目录名（如 '.claude' / '.codex' / '.cursor'）
    - `_SETTINGS_FILENAME`: str — 配置文件名（如 'settings.json' / 'hooks.json'）
    - `_CLIENT_CMD`: str — 客户端命令名用于 PATH 检测（如 'claude' / 'codex' / 'cursor'）
    - `_HOOK_EVENTS`: dict[str, str] — backend native event 名 → karma wrapper basename

    子类可选 override：
    - `build_event_entry(hook_name, event_name)` — 不同 backend matcher / timeout 不同
    - `pre_install_setup()` — Codex 类需要启用 feature flag
    """

    # 子类必填的类属性（默认空，让 mypy 不报 attribute access）
    name: str = ""
    display_name: str = ""
    _CONFIG_DIR_NAME: str = ""
    _SETTINGS_FILENAME: str = "settings.json"
    _CLIENT_CMD: str = ""
    _HOOK_EVENTS: dict[str, str] = {}

    def client_installed(self) -> bool:
        """检测客户端：命令在 PATH 或 ~/<config_dir> 存在。"""
        if self._CLIENT_CMD and shutil.which(self._CLIENT_CMD):
            return True
        return (Path.home() / self._CONFIG_DIR_NAME).exists()

    def hooks_dir(self) -> Path:
        return Path.home() / self._CONFIG_DIR_NAME / "hooks"

    def settings_path(self) -> Path:
        return Path.home() / self._CONFIG_DIR_NAME / self._SETTINGS_FILENAME

    def settings_backup_path(self) -> Path:
        return Path.home() / self._CONFIG_DIR_NAME / f"{self._SETTINGS_FILENAME}.before-karma"

    def hook_events(self) -> dict[str, str]:
        return dict(self._HOOK_EVENTS)

    def build_event_entry(self, hook_name_lower: str, event_name: str) -> dict:
        """默认 entry 格式 — 无 matcher / 无 timeout，子类 override 加 backend 特有字段。"""
        wrapper = self.hooks_dir() / f"karma_{hook_name_lower}.py"
        return {"hooks": [{"type": "command", "command": str(wrapper)}]}

    def is_karma_entry(self, entry: dict) -> bool:
        for h in entry.get("hooks", []):
            if "karma_" in h.get("command", ""):
                return True
        return False

    def load_settings(self) -> dict:
        p = self.settings_path()
        if not p.exists():
            return {}
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise SettingsParseError(
                f"{self._SETTINGS_FILENAME} 解析失败: {e}\n"
                f"路径: {p}\n"
                f"karma 不会覆盖损坏的配置。请手工修复 JSON 后重跑 install-hooks。"
            ) from e

    def save_settings(self, data: dict) -> None:
        """原子写 — tmp + os.replace 防中断 truncate。"""
        p = self.settings_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + f".karma-tmp.{os.getpid()}")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, p)

    def pre_install_setup(self) -> list[str]:
        """默认无需启用 — Codex 类 override 启用 features 标志。"""
        return []

    def post_install_message(self) -> list[str]:
        """默认装完即生效，无额外提醒（Claude 这样）。

        Codex 类 override 返回审批步骤（v0.9.17 引入）— codex 0.130+ 安全模型
        要求每个 hook 在 TUI `/hooks` 命令里被用户手动 approve 才生效，karma
        无法绕；不响亮告诉用户这步等于让 user 装完就以为正常实际 0 hook fire.
        """
        return []

    # ------------------------------------------------------------------ #
    # v0.10.0 协议契约 — 让 hook 通用主逻辑跟具体 backend 解耦                    #
    # 默认是 Claude 风格（pass-through name + hookSpecificOutput shape）。 #
    # Codex / Cursor / 其他 backend 在自己文件 override 需要的方法。              #
    # ------------------------------------------------------------------ #

    def normalize_tool_name(self, raw_tool_name: str, payload: dict) -> str:
        """归一化 tool_name 到 karma canonical（Claude 风格 `Bash`/`Read`/`Edit`/`Write`）。

        默认 passthrough — Claude 自身用 canonical 名字所以不需要映射。
        Codex / Cursor 在自己 backend 文件 override 映射各自 tool_name 到 canonical。
        """
        return raw_tool_name

    def normalize_tool_input(
        self, raw_tool_name: str, raw_tool_input: Any, payload: dict,
    ) -> Any:
        """归一化 tool_input 到 karma canonical shape。

        默认 passthrough — Claude tool_input 已经是 karma 期望的 dict shape:
        `{"file_path": ..., "new_string": ..., "command": ...}`。

        Codex apply_patch 在 codex.py override 把 envelope 字符串解成 canonical
        Edit shape + 多文件 `multi_file_targets` 列表。Cursor 也 passthrough（字段名
        几乎跟 Claude 同源）。
        """
        return raw_tool_input

    def emit_deny(self, reason: str, payload: dict) -> str:
        """生成 deny output JSON string。

        默认 Claude 风格 `{hookSpecificOutput: {permissionDecision: "deny"}}`。
        Codex 接受同样 shape 所以也用这个默认（codex docs 实验证）；Cursor override 到顶层 `{permission, agent_message, user_message}`（cursor 官方文档要求）。
        """
        return json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }, ensure_ascii=False)

    def emit_allow(self, payload: dict) -> str:
        """生成 allow output JSON string.

        默认 Claude 风格 `{hookSpecificOutput: {permissionDecision: "allow"}}`。
        Cursor override 到 `{permission: allow}`（cursor 文档要求）。
        """
        return json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
            }
        })

    def emit_context_injection(
        self, event_name: str, additional_context: str, payload: dict,
    ) -> str:
        """生成 ContextInjection 类 hook output JSON (v0.10.6 引入).

        默认 Claude shape: `{hookSpecificOutput: {hookEventName, additionalContext}}`.
        Codex 等 backend 文档没明确说对 SessionStart / UserPromptSubmit
        类 ContextInjection event 接受什么 shape — 默认这个跟 PreToolUse Claude
        shape 一致, 各 backend 真测到失败时各自 override.
        """
        return json.dumps({
            "hookSpecificOutput": {
                "hookEventName": event_name,
                "additionalContext": additional_context,
            }
        }, ensure_ascii=False)

    def emit_stop_block(self, reason: str, payload: dict) -> str:
        """生成 Stop hook 强制 block output JSON (v0.10.6 引入).

        默认 Claude 顶层 shape: `{decision: "block", reason}`.
        Stop event 通常跨 backend 不一致 — Cursor stop 用 followup_message,
        Codex Stop 接受未验证. 默认 Claude shape, Cursor override 返 followup_message
        让通用 stop.py 主逻辑 fail-open 不阻塞 Agent.
        """
        return json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False)
