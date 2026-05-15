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

from karma.checks._types import CheckHit
from karma.checks.common import extract_tool_text
from karma.checks.description_context import is_description_context
from karma.i18n import tr

_STICKY_ID = "no-testset-no-future-leakage"

# v0.5.5：宿主语言 -c/-e flag 命令头识别 — 跟 non_blocking / bypass_karma 同根因.
# python/node/ruby/perl -c "..." 内 `gold_cases.append` / `if turn_idx >= 400` 等
# 字面是字符串数据不是真执行意图. v0.5.3 dogfooding 真触发: 探针脚本里
# `r = testset_check(..., content='gold_cases.append(x)')` 被错拦. 同 v0.4.18
# non_blocking sleep 探针根因.
_LANG_C_HEAD_RE = re.compile(r"\b(?:python\d?|node|ruby|perl)\s+-[ce]\b", re.IGNORECASE)

_PATTERNS = [
    (
        re.compile(r"""\b(gold_cases|gold_data|eval_cases|test_cases)[\w.]*\.(append|extend|update|write\w*)""", re.IGNORECASE),
        "check.testset.reverse_feed.trigger",
        "check.testset.reverse_feed.fix",
    ),
    (
        re.compile(r"""detail[\w.]*\.json[\s\S]{0,80}?(open\s*\([^)]*['"]w['"]|write_text|\.write\b|\.dump\b)""", re.IGNORECASE),
        "check.testset.detail_writeback.trigger",
        "check.testset.detail_writeback.fix",
    ),
    (
        re.compile(r"""\bcp\s+[^|;\n]*(?:eval|test|gold)[\w/]*[^|;\n]*?(?:train|fit|memory)\b""", re.IGNORECASE),
        "check.testset.cross_split_copy.trigger",
        "check.testset.cross_split_copy.fix",
    ),
    (
        re.compile(r"""cat\s+[^|;\n]*detail[\w.]*\.json[^|;\n]*>>""", re.IGNORECASE),
        "check.testset.detail_append.trigger",
        "check.testset.detail_append.fix",
    ),
    (
        re.compile(r"""if\s+turn_idx\s*[><=]+\s*\d{2,}"""),
        "check.testset.split_hardcode.trigger",
        "check.testset.split_hardcode.fix",
    ),
    (
        # 长 hash / UUID 字面要算违反，必须出现在「针对该值的判定 / 赋值给 case_id」位置
        # 而非任意字符串字面（git short hash log / commit_hash 变量赋值等都合法）
        re.compile(
            r"""\b(?:if|elif|while|case|when)\s+\w+\s*==\s*['"][a-f0-9]{16,}-?[a-f0-9]{0,12}['"]"""
            r"""|\b(?:case_id|test_id|eval_id|gold_id|fixture_id)\s*=\s*['"][a-f0-9]{16,}""",
            re.IGNORECASE,
        ),
        "check.testset.hash_branch.trigger",
        "check.testset.hash_branch.fix",
    ),
    (
        # 变量名带测试集语义 + 列表里至少 1 个长 hex 字面 → 写死 case ID
        # 例 gold_cases = ["a1b2c3d4e5f6a7b8", ...] / known_failing_ids = [...]
        re.compile(
            r"""\b\w*(?:gold|eval|test|fixture|known|case|truth)_?(?:cases?|ids?|set|examples?|failing|skip)\w*\s*=\s*\[[^\]]*['"][a-f0-9]{16,}""",
            re.IGNORECASE,
        ),
        "check.testset.case_list_hash.trigger",
        "check.testset.case_list_hash.fix",
    ),
]


def check(*, tool_name: str = "", tool_input: dict | None = None, **_):
    if tool_name not in ("Bash", "Write", "Edit", "NotebookEdit"):
        return None
    # 描述上下文（文档 / 测试目录 / 探针文件）整段豁免
    is_desc, _label = is_description_context(tool_name, tool_input or {})
    if is_desc:
        return None
    text = extract_tool_text(tool_name, tool_input or {})
    if not text:
        return None
    # v0.5.5：Bash 命令头是宿主语言 + -c/-e 豁免 — python/node 等代码里
    # 含 `gold_cases.append` / `if turn_idx >= N` 字面是字符串数据不是真执行.
    # 跟 non_blocking sleep / bypass_karma write 同根因 fix.
    if tool_name == "Bash":
        cmd_raw = (tool_input or {}).get("command", "") or ""
        if _LANG_C_HEAD_RE.search(cmd_raw):
            return None
    for pat, trigger_key, fix_key in _PATTERNS:
        m = pat.search(text)
        if m:
            snippet = text[max(0, m.start() - 30): m.end() + 30]
            return CheckHit(
                rule_id=_STICKY_ID,
                trigger=tr(trigger_key),
                trigger_key=trigger_key,
                snippet=snippet[:200],
                suggested_fix=tr(fix_key),
            )
    return None
