"""#5 no-testset-no-future-leakage — 不吃测试集，不用未来数据。

检测的行为模式（pre_tool_use Write/Edit/Bash）：
1. Write/Edit content 含 `gold_cases.append/.extend/.write` (反喂测试集)
2. Write/Edit content 含 `detail.json` + 写文件操作 (eval 结果回流)
3. Bash 跨 split 路径 `cp eval/* train/` 类
4. Write/Edit 含数据 split 边界硬编码 `if turn_idx >= 400`
5. Prompt 文件含长 hash / UUID 字面（疑似测试集 case ID 写死）
"""

from __future__ import annotations

import re

from karma.checks.common import extract_tool_text
from karma.checks.description_context import is_description_context

_STICKY_ID = "no-testset-no-future-leakage"

_PATTERNS = [
    (
        re.compile(r"""\b(gold_cases|gold_data|eval_cases|test_cases)[\w.]*\.(append|extend|update|write\w*)""", re.IGNORECASE),
        "反喂测试集（写回 gold_cases / eval_cases）",
        "禁止把评测结果反喂训练数据。改 prompt / 算法后重跑评测，不要回流。",
    ),
    (
        re.compile(r"""detail[\w.]*\.json[\s\S]{0,80}?(open\s*\([^)]*['"]w['"]|write_text|\.write\b|\.dump\b)""", re.IGNORECASE),
        "把 detail.json (eval 结果) 写回训练数据",
        "禁止把评测 detail 文件作为训练输入。",
    ),
    (
        re.compile(r"""\bcp\s+[^|;\n]*(?:eval|test|gold)[\w/]*[^|;\n]*?(?:train|fit|memory)\b""", re.IGNORECASE),
        "Bash 跨 split 数据复制（eval / test → train）",
        "不要把 eval / test 数据搬到训练目录。保持 split 隔离。",
    ),
    (
        re.compile(r"""cat\s+[^|;\n]*detail[\w.]*\.json[^|;\n]*>>""", re.IGNORECASE),
        "append eval detail 结果到训练文件",
        "禁止把 eval detail 内容追加到训练 / 池子文件。",
    ),
    (
        re.compile(r"""if\s+turn_idx\s*[><=]+\s*\d{2,}"""),
        "数据 split 边界硬编码（turn_idx >= N）",
        "用 train/test split 配置而不是硬编码 turn_idx 阈值。",
    ),
    (
        # 长 hash / UUID 字面要算违反，必须出现在「针对该值的判定 / 赋值给 case_id」位置
        # 而非任意字符串字面（git short hash log / commit_hash 变量赋值等都合法）
        re.compile(
            r"""\b(?:if|elif|while|case|when)\s+\w+\s*==\s*['"][a-f0-9]{16,}-?[a-f0-9]{0,12}['"]"""
            r"""|\b(?:case_id|test_id|eval_id|gold_id|fixture_id)\s*=\s*['"][a-f0-9]{16,}""",
            re.IGNORECASE,
        ),
        "长 hash / UUID 字面在比较或 case_id 赋值里（测试集 case ID 写死）",
        "不要把测试集 case 的 ID 写死到 if 分支或 case_id 常量。用通用判定逻辑。",
    ),
]


def check(*, tool_name: str = "", tool_input: dict | None = None, **_):
    if tool_name not in ("Bash", "Write", "Edit", "NotebookEdit"):
        return None
    # 描述上下文（文档 / 测试目录 / 探针文件）整段豁免
    is_desc, _ = is_description_context(tool_name, tool_input or {})
    if is_desc:
        return None
    text = extract_tool_text(tool_name, tool_input or {})
    if not text:
        return None
    for pat, desc, fix in _PATTERNS:
        m = pat.search(text)
        if m:
            from karma.checks import CheckHit
            snippet = text[max(0, m.start() - 30): m.end() + 30]
            return CheckHit(
                sticky_id=_STICKY_ID,
                trigger=desc,
                snippet=snippet[:200],
                suggested_fix=fix,
            )
    return None
