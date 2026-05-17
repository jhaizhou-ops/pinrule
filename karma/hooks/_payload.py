"""跨 backend stdin payload 字段抽取 helper (v0.12.1 引入).

不同 AI 客户端 hook 协议对同款语义字段用**不同字段名** — karma 主流程
hardcode 一个名字会让 backend 适配每次新增都要扫 8 处 hook 入口. 集中
到 helper 函数让 fallback 链跨 backend 一处维护.

当前 fallback 链:
- session_id: Claude Code / Codex 都用 `session_id` 字段; Cursor 用
  `conversation_id` (https://cursor.com/docs/hooks). 命中顺序 session_id →
  conversation_id → 'default' 字面 fail-open.

加新 backend 用别的字段名时, 改这里一处.
"""

from __future__ import annotations


def extract_session_id(payload: dict) -> str:
    """跨 backend 提 session_id. fallback 链 fail-open 到 'default' 让 hook 跑通.

    Cursor 1.7+ stdin 用 `conversation_id` 而非 `session_id` — karma 不在这条
    上失败, 让 hook 主逻辑能跑. 命中 'default' fallback 意味着 session_state
    会归到同一 default bucket (turn count / drift marker 共享), 这是 backend
    协议级 unknown 时的合理 graceful degradation.
    """
    return (
        payload.get("session_id", "")
        or payload.get("conversation_id", "")
        or "default"
    )
