"""Cross-backend hook protocol adapter — 纯调度层（v0.10.0 重构）.

v0.9.15-v0.9.16 这个模块自己拥有 backend-specific 映射表 + envelope parser 等
**backend-specific 代码**. v0.10.0 把这些归还各自 backend (`pinrule/backends/codex.py`
等) 让 backend 拥有自己的协议私货，本模块退化成只做调度：

1. `detect_backend(payload)` — 看 payload 字段路由到 REGISTRY 里某个 backend 名
2. 其他函数（`normalize_tool_name` / `normalize_tool_input` / `emit_deny` /
   `emit_allow`）只是「路由 → backend.method() 调用」，1 行实现.

为什么不直接让 hook 主逻辑调 `REGISTRY[detect_backend(payload)].method(...)`?
- 调用站点干净度：hook 主逻辑只 import 一组函数名，不直接接触 REGISTRY
- 测试 mock 友好：单元测试可以替换 protocol_adapter 函数不需 mock 整个 REGISTRY
- 加新 method 时改一处不用扫所有 hook 主逻辑

加新 backend 的人:
- 不动 `protocol_adapter.py`（它只是调度，没有 backend 字面）
- 只动自己的 `pinrule/backends/<name>.py`，override 6 个契约方法
  （`pre_install_setup` / `post_install_message` / `normalize_tool_name` /
  `normalize_tool_input` / `emit_deny` / `emit_allow`）
- 默认基类提供 Claude 风格行为，需要才 override

Sources（v0.9.15 还引用，v0.10.0 移到各 backend 文件 docstring）:
- Codex hooks docs: https://developers.openai.com/codex/hooks
- Claude hooks docs: https://code.claude.com/docs/en/hooks

## Back-compat re-exports

v0.9.16 tests + 外部用户可能 import 这些名字 — re-export 保持向后兼容:
- `parse_apply_patch_envelope` ← from `pinrule.backends.codex`
"""

from __future__ import annotations

import sys
from typing import Any, Literal

from pinrule.backends import REGISTRY

# v0.10.5 (Agent 2 F1 fix): protocol_adapter 真"纯调度无 backend 字面" — 删
# 老 re-export `from pinrule.backends.codex import parse_apply_patch_envelope`
# (v0.9.16 back-compat). 测试改成直接 from codex.py import.

Backend = Literal["claude-code", "codex", "cursor"]


# Cursor event 名集合 — camelCase 小开头 (官方 docs 2026-05-17 fetch)
# 跟 Claude PascalCase 不同, 是 Cursor 独有特征
_CURSOR_EVENT_NAMES = frozenset({
    "sessionStart", "sessionEnd",
    "preToolUse", "postToolUse", "postToolUseFailure",
    "beforeSubmitPrompt", "stop",
    "preCompact", "subagentStart", "subagentStop",
    "afterAgentResponse", "afterAgentThought",
    "beforeShellExecution", "afterShellExecution",
    "beforeMCPExecution", "afterMCPExecution",
    "beforeReadFile", "afterFileEdit",
})


def detect_backend(payload: dict) -> str:
    """从 stdin payload 检测当前 hook 跑在哪个 backend.

    Detection 顺序 (v0.13.2 砍 Gemini 后简化):
    1. payload.hook_event_name ∈ Cursor event 名 (camelCase 小开头) → 'cursor'
    2. wrapper 调用路径含 '/.cursor/' → 'cursor' (event name 缺失兜底)
    3. wrapper 调用路径含 '/.codex/' → 'codex'
       (真测试 2026-05-16: codex error "unsupported permissionDecision:allow"
       证实 codex 不接受 Claude allow shape — emit_allow 必须返 {}.)
    4. 否则 fallback 'claude-code'

    返回 backend 名 (REGISTRY key) — 调用方用 `REGISTRY[name]` 拿 backend 实例.
    """
    event = payload.get("hook_event_name", "") or ""
    if event in _CURSOR_EVENT_NAMES:
        return "cursor"
    # Path-based fallback for 协议未在 payload 写 hook_event_name 的边缘情况
    if sys.argv and "/.cursor/" in sys.argv[0]:
        return "cursor"
    if sys.argv and "/.codex/" in sys.argv[0]:
        return "codex"
    return "claude-code"


def _backend_for(payload: dict):
    """Helper — 从 payload 路由到对应 backend 实例."""
    return REGISTRY[detect_backend(payload)]


def normalize_tool_name(raw_tool_name: str, payload: dict) -> str:
    """归一化 tool_name 到 pinrule canonical（Claude 风格 `Bash`/`Read`/`Edit`/`Write`）.

    路由到对应 backend 自己的 `normalize_tool_name` — 让 backend 决定怎么映射.

    特殊情况：Codex 的 `apply_patch` 在 detect_backend 阶段会被识别为
    `claude-code`（因为没 hook_event_name 字段或字段值不属于已知 backend）.
    所以 claude-code backend 的默认 normalize_tool_name 也走一次 codex map —
    让 mainstream Claude 用户 + Codex 用户都走同一路径. 这是因为
    `apply_patch` 是 Codex 私有 tool_name 不会出现在 Claude payload 里，所以
    映射不会冲突.

    实际实现：把 codex map 也叠加到 claude-code 默认 backend 的 normalize_tool_name
    会让 codex envelope parser 触发条件变成 raw_tool_name == 'apply_patch'，
    这是 codex 私有命名，不会假阳.
    """
    backend = _backend_for(payload)
    # 先走 backend 自己的 normalize（Cursor Shell → Bash 等）
    return backend.normalize_tool_name(raw_tool_name, payload)


def normalize_tool_input(
    raw_tool_name: str, raw_tool_input: Any, payload: dict,
) -> Any:
    """归一化 tool_input 到 pinrule canonical shape.

    路由到对应 backend 自己的 `normalize_tool_input`. v0.10.5 (Agent 2 F1 fix):
    之前这层有「raw_tool_name == 'apply_patch' 时强制走 codex 解析」的 codex
    字面兜底, 违反 v0.10.0 设计自述 (本模块不该含 backend 字面). detect_backend
    现在通过 sys.argv `/.codex/` 路径真识别 codex backend, 这条兜底无意义.
    删除让 protocol_adapter 真守住「纯调度无 backend 字面」边界.
    """
    backend = _backend_for(payload)
    return backend.normalize_tool_input(raw_tool_name, raw_tool_input, payload)


def emit_deny(reason: str, payload: dict) -> str:
    """生成 backend-specific deny output JSON string."""
    return _backend_for(payload).emit_deny(reason, payload)


def emit_allow(payload: dict) -> str:
    """生成 backend-specific allow output JSON string."""
    return _backend_for(payload).emit_allow(payload)


def emit_context_injection(
    event_name: str, additional_context: str, payload: dict,
) -> str:
    """生成 backend-specific ContextInjection hook output JSON string (v0.10.6).

    SessionStart / UserPromptSubmit / PostToolUse / SubagentStart 等向 Agent
    注入 additionalContext 的事件统一走这个调度入口, 不再 4 个 hook 各自
    直 print Claude shape (v0.9.15 同款潜伏点).
    """
    return _backend_for(payload).emit_context_injection(event_name, additional_context, payload)


def emit_stop_block(reason: str, payload: dict) -> str:
    """生成 backend-specific Stop hook block output JSON string (v0.10.6).

    Stop hook force_block / keep_pushing_block 走这个调度入口. Claude
    顶层 `{decision: block, reason}`; Cursor override 返 followup_message
    (AfterAgent 没 block 概念); Codex 跟 Claude shape 一致 (待验证).
    """
    return _backend_for(payload).emit_stop_block(reason, payload)
