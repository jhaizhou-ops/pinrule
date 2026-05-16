"""Cross-backend hook protocol adapter — 纯调度层（v0.10.0 重构）.

v0.9.15-v0.9.16 这个模块自己拥有 Gemini / Codex 映射表 + envelope parser 等
**backend-specific 代码**. v0.10.0 把这些归还各自 backend (`karma/backends/codex.py`
/ `gemini_cli.py`) 让 backend 拥有自己的协议私货，本模块退化成只做调度：

1. `detect_backend(payload)` — 看 payload 字段路由到 REGISTRY 里某个 backend 名
2. 其他函数（`normalize_tool_name` / `normalize_tool_input` / `emit_deny` /
   `emit_allow`）只是「路由 → backend.method() 调用」，1 行实现.

为什么不直接让 hook 主逻辑调 `REGISTRY[detect_backend(payload)].method(...)`?
- 调用站点干净度：hook 主逻辑只 import 一组函数名，不直接接触 REGISTRY
- 测试 mock 友好：单元测试可以替换 protocol_adapter 函数不需 mock 整个 REGISTRY
- 加新 method 时改一处不用扫所有 hook 主逻辑

加新 backend 的人:
- 不动 `protocol_adapter.py`（它只是调度，没有 backend 字面）
- 只动自己的 `karma/backends/<name>.py`，override 6 个契约方法
  （`pre_install_setup` / `post_install_message` / `normalize_tool_name` /
  `normalize_tool_input` / `emit_deny` / `emit_allow`）
- 默认基类提供 Claude Code 风格行为，需要才 override

Sources（v0.9.15 还引用，v0.10.0 移到各 backend 文件 docstring）:
- Gemini hooks reference: https://geminicli.com/docs/hooks/reference/
- Codex hooks docs: https://developers.openai.com/codex/hooks
- Claude Code hooks docs: https://code.claude.com/docs/en/hooks

## Back-compat re-exports

v0.9.16 tests + 外部用户可能 import 这些名字 — re-export 保持向后兼容:
- `parse_apply_patch_envelope` ← from `karma.backends.codex`
"""

from __future__ import annotations

import sys
from typing import Any, Literal

from karma.backends import REGISTRY
# v0.9.16 back-compat re-export — 老测试 / 老 import 路径继续工作
from karma.backends.codex import parse_apply_patch_envelope  # noqa: F401

Backend = Literal["claude-code", "codex", "gemini-cli"]


# Gemini event 名集合 — 用于 detect_backend
# 来源：~/.gemini/settings.json 真实 event 名 + 官方 hook 文档
_GEMINI_EVENT_NAMES = frozenset({"BeforeAgent", "BeforeTool", "AfterTool", "AfterAgent"})


def detect_backend(payload: dict) -> str:
    """从 stdin payload 检测当前 hook 跑在哪个 backend.

    Detection 顺序（v0.10.0 升级 — 必须真区分 codex 因为 emit_allow shape 不同）:
    1. payload.hook_event_name ∈ Gemini event 名 → 'gemini-cli'
    2. wrapper 调用路径含 '/.codex/' → 'codex'
       （真测试 2026-05-16: codex error "unsupported permissionDecision:allow"
       证实 codex 不接受 Claude allow shape — emit_allow 必须返 {}.）
    3. 否则 fallback 'claude-code'

    返回 backend 名 (REGISTRY key) — 调用方用 `REGISTRY[name]` 拿 backend 实例.
    """
    event = payload.get("hook_event_name", "") or ""
    if event in _GEMINI_EVENT_NAMES:
        return "gemini-cli"
    # codex wrapper 文件路径含 /.codex/hooks/ — sys.argv[0] 是 hook 入口路径
    # (codex spawn karma_*.py wrapper → wrapper import karma.hooks.* main())
    if sys.argv and "/.codex/" in sys.argv[0]:
        return "codex"
    return "claude-code"


def _backend_for(payload: dict):
    """Helper — 从 payload 路由到对应 backend 实例."""
    return REGISTRY[detect_backend(payload)]


def normalize_tool_name(raw_tool_name: str, payload: dict) -> str:
    """归一化 tool_name 到 karma canonical（Claude 风格 `Bash`/`Read`/`Edit`/`Write`）.

    路由到对应 backend 自己的 `normalize_tool_name` — 让 backend 决定怎么映射.

    特殊情况：Codex 的 `apply_patch` 在 detect_backend 阶段会被识别为
    `claude-code`（因为没 hook_event_name 字段或字段值不是 Gemini）.
    所以 claude-code backend 的默认 normalize_tool_name 也走一次 codex map —
    让 mainstream Claude Code 用户 + Codex 用户都走同一路径. 这是因为
    `apply_patch` 是 Codex 私有 tool_name 不会出现在 Claude payload 里，所以
    映射不会冲突.

    实际实现：把 codex map 也叠加到 claude-code 默认 backend 的 normalize_tool_name
    会让 codex envelope parser 触发条件变成 raw_tool_name == 'apply_patch'，
    这是 codex 私有命名，不会假阳.
    """
    backend = _backend_for(payload)
    # 先走 backend 自己的 normalize（Gemini run_shell_command → Bash 等）
    normalized = backend.normalize_tool_name(raw_tool_name, payload)
    # 再走 codex 映射作为兜底（apply_patch 是 codex 私有，不冲突任何 backend）
    if normalized == raw_tool_name and backend.name != "codex":
        from karma.backends.codex import _CODEX_TOOL_MAP
        normalized = _CODEX_TOOL_MAP.get(raw_tool_name, raw_tool_name)
    return normalized


def normalize_tool_input(
    raw_tool_name: str, raw_tool_input: Any, payload: dict,
) -> Any:
    """归一化 tool_input 到 karma canonical shape.

    路由到对应 backend 自己的 `normalize_tool_input`. Codex `apply_patch` envelope
    解析在 `karma/backends/codex.py:CodexBackend.normalize_tool_input` 里.

    同 normalize_tool_name 的兜底逻辑：raw_tool_name == 'apply_patch' 时
    强制走 codex backend 解析（不依赖 detect_backend 准确性，因为 codex hook
    payload 可能没 hook_event_name 让 detect_backend 误判 claude-code）.
    """
    backend = _backend_for(payload)
    normalized = backend.normalize_tool_input(raw_tool_name, raw_tool_input, payload)
    # apply_patch 是 codex 私有 — 任何 backend 看到这名字都走 codex 解析
    if normalized is raw_tool_input and raw_tool_name == "apply_patch" and backend.name != "codex":
        return REGISTRY["codex"].normalize_tool_input(raw_tool_name, raw_tool_input, payload)
    return normalized


def emit_deny(reason: str, payload: dict) -> str:
    """生成 backend-specific deny output JSON string."""
    return _backend_for(payload).emit_deny(reason, payload)


def emit_allow(payload: dict) -> str:
    """生成 backend-specific allow output JSON string."""
    return _backend_for(payload).emit_allow(payload)
