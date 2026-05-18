"""rules.json 加载 + schema 验证.

设计: 纯工程, 无 LLM, 0 runtime deps. 文件足够小所以全量读, 不需要 cache.

v0.17.0 (2026-05-18): 砍 PyYAML — rules 由 LLM 通过 `pinrule rule add` 维护,
YAML 多行字符串/注释友好度优势没在被消费. JSON 是 Python 标准库, 0 依赖.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from pinrule.i18n import tr
from pinrule.paths import pinrule_home

DEFAULT_PATH = pinrule_home() / "rules.json"
MAX_RULES = 10  # 软上限，超过 12 抛错
HARD_MAX = 12  # 注意力拐点，硬上限

_SLUG_RE = re.compile(r"^[a-z][a-z0-9-]*[a-z0-9]$")


@dataclass(slots=True, frozen=True)
class Rule:
    """单条核心方向规则。"""

    id: str
    preference: str  # 多行允许
    violation_keywords: tuple[str, ...] = ()
    violation_checks: tuple[str, ...] = ()  # 工程检测函数名列表（从 pinrule.checks 注册表）
    # force_block 累积强制干预豁免 — 「应该继续推进」类规则不该被「累积太多必须停下」处罚
    # 典型例：keep-pushing-no-stop / non-blocking-parallel（语义反向，累积处罚会自我矛盾）
    force_block_exempt: bool = False


@dataclass(slots=True)
class RuleConfigError(Exception):
    """rules.json 配置错误，hook 拒绝加载（fail loud）。"""

    msg: str

    def __str__(self) -> str:
        return f"rule config error: {self.msg}"


def load(path: Path | None = None) -> list[Rule]:
    """从 JSON 加载 + 验证。返回不可变 Rule 列表。

    文件不存在返回 []（用户还没配置，hook 静默 passthrough）。
    schema 错误抛 RuleConfigError（hook 应该 fail loud 让用户看见）。

    path=None 时动态读 module-level DEFAULT_PATH（支持 monkeypatch）。
    """
    if path is None:
        path = DEFAULT_PATH
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise RuleConfigError(f"JSON 解析失败: {e}") from e
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise RuleConfigError(f"顶层必须是 list，实际 {type(raw).__name__}")
    if len(raw) > HARD_MAX:
        raise RuleConfigError(
            f"超过硬上限 {HARD_MAX} 条 (实际 {len(raw)})。注意力会下降，拒绝加载。"
        )

    rule_list: list[Rule] = []
    seen_ids: set[str] = set()
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise RuleConfigError(f"第 {i+1} 条不是 dict: {type(item).__name__}")
        rid = item.get("id")
        if not rid or not isinstance(rid, str):
            raise RuleConfigError(f"第 {i+1} 条缺 id 或 id 不是 string")
        if not _SLUG_RE.match(rid):
            raise RuleConfigError(
                f"第 {i+1} 条 id={rid!r} 不合法 (kebab-case slug，例: long-term-fundamental)"
            )
        if rid in seen_ids:
            raise RuleConfigError(f"重复 id: {rid!r}")
        seen_ids.add(rid)

        pref = item.get("preference", "").strip()
        if not pref:
            raise RuleConfigError(f"rule {rid!r} 缺 preference")

        kws = item.get("violation_keywords", []) or []
        if not isinstance(kws, list):
            raise RuleConfigError(f"rule {rid!r} violation_keywords 必须是 list")
        kws_clean = tuple(str(k).strip() for k in kws if str(k).strip())

        vcs = item.get("violation_checks", []) or []
        if not isinstance(vcs, list):
            raise RuleConfigError(f"rule {rid!r} violation_checks 必须是 list")
        vcs_clean = tuple(str(v).strip() for v in vcs if str(v).strip())

        fbe_raw = item.get("force_block_exempt", False)
        if not isinstance(fbe_raw, bool):
            raise RuleConfigError(
                f"rule {rid!r} force_block_exempt 必须是 bool，实际 {type(fbe_raw).__name__}"
            )

        rule_list.append(Rule(
            id=rid,
            preference=pref,
            violation_keywords=kws_clean,
            violation_checks=vcs_clean,
            force_block_exempt=fbe_raw,
        ))

    return rule_list


def format_for_injection(
    rule_list: list[Rule],
    recent_violations: dict[str, int] | None = None,
) -> str:
    """渲染 rule 列表为**完整**前置注入的 prompt 文本（含每条 preference 全文）。

    v0.9.0 用法变更：
    - SessionStart hook 每 session 起手 + compact 重起注入一次（baseline）
    - PostToolUse 中段衰减拐点累积触发时注入一次（抗稀释）
    - **不再每 turn 全量注入**（UserPromptSubmit 改用 format_anchor_only）

    设计哲学：
    - 把规则从「规则系统」改成「合作默契」语气，让 Agent 看到提醒第一反应
      是「调整对齐」而非「防御 / 绕过」
    - 上次有偏离的规则用合作回顾标记（〔...〕），不用红警示词（⚠️ / 违反）
      激活防御反应

    recent_violations: rule_id → 最近违反时间戳。出现的规则会加合作回顾标记。
    """
    if not rule_list:
        return ""
    recent_violations = recent_violations or {}
    # v0.5.2 i18n: header text via tr() lookup (en / zh by locale)
    lines = [
        tr("inject.header.title"),
        tr("inject.header.line1"),
        tr("inject.header.line2"),
        "",
    ]
    drift_marker = tr("inject.drift_marker")
    for i, r in enumerate(rule_list, 1):
        marker = drift_marker if r.id in recent_violations else ""
        # preference 多行 → 缩进对齐
        pref_lines = r.preference.strip().split("\n")
        # Always prefix rule id — Cursor often drops hook-only catalog blocks but
        # keeps narrative preference text; ids must live on the same lines.
        lines.append(f"{i}. [{r.id}] {pref_lines[0]}{marker}")
        for extra in pref_lines[1:]:
            lines.append(f"   {extra}")
    lines.append("")
    return "\n".join(lines)


def format_rule_id_catalog(rule_list: list[Rule]) -> str:
    """Compact rule-id list for Cursor — hooks/rules layer visibility.

    Cursor sessionStart stdout is often invisible; beforeSubmitPrompt used to
    passthrough when no violations (empty anchor). This block is small (~70
    tokens for the default 7 rules, ~100 tokens at soft cap of 10) and
    always safe to inject on Cursor turns.
    """
    if not rule_list:
        return ""
    lines = [
        tr("catalog.header.title"),
        tr("catalog.header.line"),
        "",
    ]
    for r in rule_list:
        lines.append(f"- `{r.id}`")
    lines.append("")
    return "\n".join(lines)


def format_anchor_only(
    rule_list: list[Rule],
    violated_rule_ids: dict[str, int] | set[str] | None = None,
) -> str:
    """渲染 anchor — v0.13.0: 只列本 session 累积违反过的 rule.

    历史 v0.9.0 - v0.12.x: 每 turn 全列 sticky id list (~490 token), 跟
    sessionStart baseline (1.8K) 重复. Prompt-cache 角度 100 turn 累积 raw
    ~2.47M token (effective 1 折 ~290K), 占总 API input 10-15%.

    v0.13.0: 只列 violated_rule_ids 出现过的 rule. 典型 dogfood 累积 3-5 条
    违反规则, anchor 从 ~490 → ~150 token/turn (~70% 节省). 无累积违反返 ""
    走 passthrough (~10% turn 0 token). sticky id list 完全交 sessionStart
    baseline + PostToolUse 中段重注入双层 anti-attention-decay.

    violated_rule_ids 接受 dict[rule_id → turn] (recent_turns / session_violations
    返回值) 或 set[rule_id] — 都按 set 行为.
    """
    if not rule_list:
        return ""
    violated_set = set(violated_rule_ids or [])
    if not violated_set:
        return ""  # session 没累积违反 → passthrough, 不注入 anchor
    # 只 list 违反过的 rule, 保持 rule_list 原顺序
    violated_rules = [r for r in rule_list if r.id in violated_set]
    if not violated_rules:
        return ""  # rule_list 变了 (用户删 rule) 违反对应 rule 不在 → passthrough
    lines = [
        tr("anchor.header.title"),
        tr("anchor.header.line"),
        "",
    ]
    drift_marker = tr("inject.drift_marker")
    for i, r in enumerate(violated_rules, 1):
        first_line = r.preference.strip().split("\n")[0]
        # v0.13.0 anchor 里全是 violated rule, 全加 drift marker
        lines.append(f"{i}. [{r.id}] {first_line}{drift_marker}")
    lines.append("")
    return "\n".join(lines)
