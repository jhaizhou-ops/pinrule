"""SessionStart hook — session 起手注入 sticky baseline（karma v3 第四步）。

Claude Code 协议:
- stdin payload: {source: "startup"|"resume"|"clear"|"compact", session_id, ...}
- stdout: {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "..."}}

设计（v0.4.28 升级 — 之前 stub 只输出摘要文字现在真注入 sticky baseline）：
- 跟 UserPromptSubmit 注入互补 — 后者每 turn 注入完整 sticky + ⚠️ 标记，
  前者 session 级一次注入精简 baseline（id + 第一行 preference）
- compact 场景特别重要 — sticky 在 compact 时被压缩淡化，SessionStart 重起时
  强注入是真根本路径（PostCompact 不支持 additionalContext 走不通）

性能预算：< 30ms（不该卡客户端启动）
Fail open：配置坏 / 异常 → 不注入静默 passthrough。
"""

from __future__ import annotations

import json
import sys

from karma.sticky import StickyConfigError, load as load_sticky


def _passthrough() -> None:
    print(json.dumps({}))


def _emit(additional_context: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": additional_context,
        }
    }, ensure_ascii=False))


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"karma SessionStart: 输入 JSON 解析失败 ({e})", file=sys.stderr)
        _passthrough()
        return 0

    source = payload.get("source", "")  # startup / resume / clear / compact

    # v0.4.36 真协议层 fix：SessionStart payload 真有 model 字段（PreToolUse /
    # PostToolUse / SubagentStart / SubagentStop / Stop 都没）— SessionStart 是
    # Claude Code 本地协议下唯一暴露 model 的事件。拿 model 写主 state 让后续
    # PostToolUse 中段 sticky 注入按真模型阈值（Opus 80K / Sonnet 60K / Haiku 30K）。
    # 子 Agent 模型仍真盲区（SubagentStart 没 model 字段），走 DEFAULT 60K fallback。
    payload_model = payload.get("model")
    session_id = payload.get("session_id", "") or "default"
    if payload_model:
        try:
            from karma import session_state
            state = session_state.load(session_id)
            state.model = payload_model
            session_state.save(state)
        except Exception as e:
            print(f"karma SessionStart: 写 state.model 失败 ({e})", file=sys.stderr)
            # 失败不阻塞 sticky baseline 注入

    try:
        sticky_list = load_sticky()
    except StickyConfigError as e:
        print(f"karma SessionStart: {e}", file=sys.stderr)
        _emit(f"❌ sticky 配置错误：{e}")
        return 0
    except Exception as e:
        print(f"karma SessionStart: sticky 加载失败 ({e})", file=sys.stderr)
        _passthrough()
        return 0

    if not sticky_list:
        _passthrough()
        return 0

    # baseline 注入 — 精简版（每 sticky 一行：id + 第一行 preference）
    # compact 场景加强提醒 + 读 PreCompact 落盘 snapshot
    lines = []
    if source == "compact":
        lines.append("[karma 上下文 compact 后重起 — 这些核心方向必须留在记忆里]")
        # v0.4.29 读 PreCompact 落盘 snapshot — 让 Agent 知道 compact 前撞过哪些
        # sticky 不会因 compact 失忆
        try:
            from karma.paths import karma_home
            snapshot = (karma_home() / "pre_compact_snapshot.md")
            if snapshot.exists():
                content = snapshot.read_text(encoding="utf-8")
                # 提取「compact 前最近 5 turn 违反过的 sticky」段
                if "最近 5 turn 违反过的 sticky" in content:
                    after = content.split("最近 5 turn 违反过的 sticky", 1)[1]
                    violation_lines = [
                        ln.strip() for ln in after.split("\n")
                        if ln.strip().startswith("- ")
                    ]
                    if violation_lines:
                        lines.append("compact 前撞过的 sticky（别在 compact 后又犯）:")
                        for vl in violation_lines[:5]:
                            lines.append(f"  {vl}")
        except Exception:
            pass  # 读 snapshot 失败不阻塞 baseline 注入
    elif source == "resume":
        lines.append("[karma session 恢复 — sticky baseline 重新加载]")
    else:
        lines.append(f"[karma session 起手 sticky baseline — source={source or 'startup'}]")
    for s in sticky_list:
        first_line = s.preference.strip().split("\n")[0]
        lines.append(f"  - {s.id}: {first_line}")
    if source == "compact":
        lines.append("compact 后 sticky 容易被压缩淡化 — 留意你正在按这些方向行为。")
    _emit("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
