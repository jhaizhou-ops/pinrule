"""SubagentStop hook — Subagent 完成时检查违反溅回。

Claude Code 协议:
- stdin payload: {agent_id, agent_type, session_id, transcript_path, ...}
- stdout: {"continue": false/true, "hookSpecificOutput": {"hookEventName": "SubagentStop", 
           "additionalContext": "..."}}

策略：
- Subagent 完成后检查其 transcript 中有无违反
- 若有违反，通过 additionalContext 提醒主 agent
- v0.6.0 first pass：简单检查子 agent transcript 中是否有违反关键词
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from karma.sticky import load as load_sticky


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"karma SubagentStop: 输入 JSON 解析失败 ({e})", file=sys.stderr)
        print(json.dumps({}))
        return 0
    
    agent_id = payload.get("agent_id", "")
    transcript_path = payload.get("transcript_path", "")
    
    try:
        sticky_list = load_sticky()
    except Exception as e:
        print(f"karma SubagentStop: sticky 加载失败 ({e})", file=sys.stderr)
        print(json.dumps({}))
        return 0
    
    if not sticky_list or not transcript_path:
        print(json.dumps({}))
        return 0
    
    # 检查子 agent transcript 中是否有违反关键词
    violations = []
    try:
        content = Path(transcript_path).read_text(encoding="utf-8", errors="ignore")
        for sticky in sticky_list:
            for keyword in sticky.violation_keywords:
                if keyword in content:
                    violations.append((sticky.id, keyword))
    except Exception:
        # Transcript 不存在或读失败，继续
        pass
    
    if violations:
        violation_text = "\n".join(
            f"  • {sticky_id} 违反词: {keyword!r}"
            for sticky_id, keyword in violations[:3]  # 只显示前 3 个
        )
        context = f"""⚠️ Subagent {agent_id} 完成时检查：

发现 {len(violations)} 条核心方向违反：
{violation_text}

主 Agent 应审视子 Agent 的行为是否偏离约束。"""
        
        print(json.dumps({
            "continue": True,
            "hookSpecificOutput": {
                "hookEventName": "SubagentStop",
                "additionalContext": context
            }
        }))
    else:
        print(json.dumps({
            "continue": True,
            "hookSpecificOutput": {
                "hookEventName": "SubagentStop",
                "additionalContext": f"✓ Subagent {agent_id} 完成，未发现核心方向违反。"
            }
        }))
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
