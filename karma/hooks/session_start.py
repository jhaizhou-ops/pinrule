"""SessionStart hook — session 起手注入规则 baseline（karma v9 注入架构核心）。

Claude Code 协议:
- stdin payload: {source: "startup"|"resume"|"clear"|"compact", session_id, ...}
- stdout: {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "..."}}

v0.9.0 设计（架构重设计）:
- SessionStart 是 session 唯一一次**全量** baseline 注入（format_for_injection
  完整 preference）— 进 conversation history 持续可见
- UserPromptSubmit 每 turn 只注入**精简 anchor**（id + 第一行 + 偏离标记，
  format_anchor_only ~490 token）— 跟 SessionStart 互补
- PostToolUse 累积达模型衰减拐点（Opus 60K / Sonnet 40K / Haiku 30K）后
  全量 reinject 抗稀释
- compact 场景特别重要 — 规则在 compact 时被压缩淡化，SessionStart compact
  source 重起时读 pre_compact_snapshot.md 强注入

历史: v0.4.28 设计每 turn 全量, v0.9.0 改成 session 一次全量 + 每 turn 精简。

性能预算：< 30ms（不该卡客户端启动）
Fail open：配置坏 / 异常 → 不注入静默 passthrough。
"""

from __future__ import annotations

import json
import sys

from karma.rule import RuleConfigError, format_for_injection, load as load_sticky


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

    # v0.4.36 协议层 fix：SessionStart payload 有 model 字段（PreToolUse /
    # PostToolUse / SubagentStart / SubagentStop / Stop 都没）— SessionStart 是
    # Claude Code 本地协议下唯一暴露 model 的事件。拿 model 写主 state 让后续
    # PostToolUse 中段 sticky 注入按模型阈值（Opus 80K / Sonnet 60K / Haiku 30K）。
    # 子 Agent 模型仍盲区（SubagentStart 没 model 字段），走 DEFAULT 60K fallback。
    payload_model = payload.get("model")
    session_id = payload.get("session_id", "") or "default"
    if payload_model:
        try:
            # v0.9.8: update_state 跨进程并发安全（之前直接 load+save 在多
            # Claude Code 进程同时启动场景下可能丢更新）
            from karma import session_state

            def _set_model(state):
                state.model = payload_model
            session_state.update_state(session_id, _set_model)
        except Exception as e:
            print(f"karma SessionStart: 写 state.model 失败 ({e})", file=sys.stderr)
            # 失败不阻塞 sticky baseline 注入

    try:
        rule_list = load_sticky()
    except RuleConfigError as e:
        print(f"karma SessionStart: {e}", file=sys.stderr)
        _emit(f"❌ 规则配置错误：{e}")
        return 0
    except Exception as e:
        print(f"karma SessionStart: 规则加载失败 ({e})", file=sys.stderr)
        _passthrough()
        return 0

    if not rule_list:
        _passthrough()
        return 0

    # v0.5.2 i18n: 合作默契语气切 locale (en/zh)
    from karma.i18n import tr
    lines = []
    if source == "compact":
        lines.append(tr("session_start.compact.title"))
        # v0.4.29 读 PreCompact 落盘 snapshot — 让 Agent 知道 compact 前撞过哪些
        # 规则不会因 compact 失忆
        try:
            from karma.paths import karma_home
            snapshot = (karma_home() / "pre_compact_snapshot.md")
            if snapshot.exists():
                content = snapshot.read_text(encoding="utf-8")
                # 提取「compact 前最近 5 turn 违反过的 sticky」段（snapshot 内部
                # 还是用中文 marker，因为是 PreCompact 写的 — 这里 i18n 不影响）
                if "最近 5 turn 违反过的 sticky" in content:
                    after = content.split("最近 5 turn 违反过的 sticky", 1)[1]
                    violation_lines = [
                        ln.strip() for ln in after.split("\n")
                        if ln.strip().startswith("- ")
                    ]
                    if violation_lines:
                        lines.append(tr("session_start.compact.prior_drift_header"))
                        for vl in violation_lines[:5]:
                            lines.append(f"  {vl}")
        except Exception:
            pass  # 读 snapshot 失败不阻塞 baseline 注入
    elif source == "resume":
        lines.append(tr("session_start.resume.title"))
    else:
        lines.append(tr("session_start.startup.title", source=source or "startup"))
    # v0.9.0: 注入**完整 baseline**（含每条 preference 全文）— 这是 session
    # 唯一一次全量注入进 conversation history 持续可见。每 turn UserPromptSubmit
    # 只注入精简 anchor，累积达模型阈值后 PostToolUse 中段全量补一次抗稀释。
    # 旧 v0.4.28 精简版（id + 第一行）在 v0.9.0 之前因为 UserPromptSubmit 每
    # turn 全量, 这里精简就够；现在 UserPromptSubmit 精简了, 这里必须扛起
    # 完整 preference 的注入责任。
    lines.append(format_for_injection(rule_list))
    if source == "compact":
        lines.append(tr("session_start.compact.tail"))
    _emit("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
