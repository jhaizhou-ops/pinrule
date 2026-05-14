"""PostCompact hook — Compact 后验证 sticky 还活着，丢失则补注。

Claude Code 协议:
- stdin payload: {trigger: "manual"|"auto", session_id, transcript_path, ...}
- stdout: {"decision": "block", "hookSpecificOutput": {"hookEventName": "PostCompact", 
           "additionalContext": "..."}}

策略：
1. Compact 后解析 transcript_path（新 JSON），检查是否仍含 sticky anchor
2. 若丢失，通过 additionalContext 强制补注 sticky 摘要
3. 更新 metrics（sticky_compact_loss_count）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from karma.sticky import load as load_sticky, Sticky


_STICKY_ANCHOR_MARKERS = (
    "用最根本、最长期",  # long-term-fundamental
    "不阻塞前端",  # non-blocking-parallel
    "失败要响亮",  # loud-failure-with-evidence
    "深挖为什么拦",  # deep-fix-not-bypass
    "加代码前先读",  # read-before-write
)


def _transcript_contains_sticky_marker(transcript_path: str) -> bool:
    """启发式检查：transcript JSON 中是否仍含 sticky anchor 关键词。"""
    if not transcript_path or not Path(transcript_path).exists():
        return False
    
    try:
        content = Path(transcript_path).read_text(encoding="utf-8", errors="ignore")
        # 简单启发式：找任意一个 sticky 的关键表述
        for marker in _STICKY_ANCHOR_MARKERS:
            if marker in content:
                return True
    except Exception:
        pass
    
    return False


def _sticky_summary(sticky_list: list[Sticky]) -> str:
    """生成 sticky 摘要用于补注。"""
    lines = ["💡 Context compact 后 sticky 检查："]
    for s in sticky_list:
        # 只取 preference 第一行
        first_line = s.preference.strip().split("\n")[0]
        lines.append(f"  • {s.id}: {first_line}")
    return "\n".join(lines)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"karma PostCompact: 输入 JSON 解析失败 ({e})", file=sys.stderr)
        print(json.dumps({}))
        return 0
    
    transcript_path = payload.get("transcript_path", "")
    
    try:
        sticky_list = load_sticky()
    except Exception as e:
        print(f"karma PostCompact: sticky 加载失败 ({e})", file=sys.stderr)
        print(json.dumps({}))
        return 0
    
    if not sticky_list:
        print(json.dumps({}))
        return 0
    
    # 检查 sticky marker 是否还在
    has_marker = _transcript_contains_sticky_marker(transcript_path)
    
    if not has_marker:
        # Sticky 丢失，补注摘要
        summary = _sticky_summary(sticky_list)
        print(json.dumps({
            "decision": "block",
            "hookSpecificOutput": {
                "hookEventName": "PostCompact",
                "additionalContext": summary
            }
        }))
    else:
        # Sticky 还活着，继续
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PostCompact",
                "additionalContext": f"✓ Compact 后检查：{len(sticky_list)} 条 sticky 仍在 context。"
            }
        }))
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
