"""afterAgentResponse hook — Cursor 每条 assistant 回复后跑 response 级 check.

Cursor 协议 (https://cursor.com/docs/hooks) stdin: {text, conversation_id, ...}
stdout: {} (observational — no followup_message; 续写仍靠 stop hook).

与 Stop 共用 audit_agent_response; 此处不触发 followup_message 干预.
"""

from __future__ import annotations

import json
import sys

from karma.hooks.stop import audit_agent_response
from karma.hooks._transcript import read_last_message_text


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(f"karma afterAgentResponse: JSON 解析失败 ({e})", file=sys.stderr)
        print(json.dumps({}))
        return 0

    response = (payload.get("text") or "").strip()
    if not response:
        print(json.dumps({}))
        return 0

    last_user_prompt = (
        payload.get("user_prompt", "")
        or payload.get("prompt", "")
        or read_last_message_text(payload.get("transcript_path", ""), "user")
    )

    audit_agent_response(
        payload, response, last_user_prompt, allow_stop_interventions=False,
    )
    print(json.dumps({}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
