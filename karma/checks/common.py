"""check 函数共用工具。"""

from __future__ import annotations

import re

# code block ``` 包裹的内容（多种语言标记）
_CODE_BLOCK_RE = re.compile(r"```[\w]*\n.*?\n```", re.DOTALL)
# inline `code` 包裹
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")


def extract_tool_text(tool_name: str, tool_input: dict) -> str:
    """从 tool_input 提取要扫违反的关键文本。

    不同 tool 不同字段：
    - Bash: command
    - Write: content
    - Edit: new_string (只看 Agent 加的，不看已有 old_string)
    - 其他: JSON dump
    """
    if not tool_input:
        return ""
    if tool_name == "Bash":
        return str(tool_input.get("command", "") or "")
    if tool_name == "Write":
        return str(tool_input.get("content", "") or "")
    if tool_name == "Edit":
        return str(tool_input.get("new_string", "") or "")
    if tool_name == "NotebookEdit":
        return str(tool_input.get("new_source", "") or "")
    try:
        import json
        return json.dumps(tool_input, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(tool_input)


def strip_code_blocks(text: str) -> str:
    """剔除 markdown ``` 包裹的 code block 和 `inline` code。

    用于 chinese_plain 类检查 — 自然语言部分才算 jargon 对话。
    """
    no_block = _CODE_BLOCK_RE.sub("", text)
    no_inline = _INLINE_CODE_RE.sub("", no_block)
    return no_inline


def chinese_char_count(text: str) -> int:
    return sum(1 for c in text if "一" <= c <= "鿿")


def total_visible_char_count(text: str) -> int:
    return sum(1 for c in text if not c.isspace())
