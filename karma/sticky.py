"""sticky.yaml 加载 + schema 验证。

设计：纯工程，无 LLM。yaml 文件足够小所以全量读，不需要 cache。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from karma.paths import karma_home

DEFAULT_PATH = karma_home() / "sticky.yaml"
MAX_STICKY = 10  # 软上限，超过 12 抛错
HARD_MAX = 12  # 注意力拐点，硬上限

_SLUG_RE = re.compile(r"^[a-z][a-z0-9-]*[a-z0-9]$")


@dataclass(slots=True, frozen=True)
class Sticky:
    """单条核心方向。"""

    id: str
    preference: str  # 多行允许
    violation_keywords: tuple[str, ...] = ()
    violation_checks: tuple[str, ...] = ()  # 工程检测函数名列表（从 karma.checks 注册表）
    # force_block 累积强制干预豁免 — 「应该继续推进」类规则不该被「累积太多必须停下」处罚
    # 典型例：keep-pushing-no-stop / non-blocking-parallel（语义反向，累积处罚会自我矛盾）
    force_block_exempt: bool = False


@dataclass(slots=True)
class StickyConfigError(Exception):
    """sticky.yaml 配置错误，hook 拒绝加载（fail loud）。"""

    msg: str

    def __str__(self) -> str:
        return f"sticky config error: {self.msg}"


def load(path: Path | None = None) -> list[Sticky]:
    """从 yaml 加载 + 验证。返回不可变 Sticky 列表。

    文件不存在返回 []（用户还没配置，hook 静默 passthrough）。
    schema 错误抛 StickyConfigError（hook 应该 fail loud 让用户看见）。

    path=None 时动态读 module-level DEFAULT_PATH（支持 monkeypatch）。
    """
    if path is None:
        path = DEFAULT_PATH
    if not path.exists():
        return []
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise StickyConfigError(f"YAML 解析失败: {e}") from e
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise StickyConfigError(f"顶层必须是 list，实际 {type(raw).__name__}")
    if len(raw) > HARD_MAX:
        raise StickyConfigError(
            f"超过硬上限 {HARD_MAX} 条 (实际 {len(raw)})。注意力会下降，拒绝加载。"
        )

    sticky_list: list[Sticky] = []
    seen_ids: set[str] = set()
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise StickyConfigError(f"第 {i+1} 条不是 dict: {type(item).__name__}")
        sid = item.get("id")
        if not sid or not isinstance(sid, str):
            raise StickyConfigError(f"第 {i+1} 条缺 id 或 id 不是 string")
        if not _SLUG_RE.match(sid):
            raise StickyConfigError(
                f"第 {i+1} 条 id={sid!r} 不合法 (kebab-case slug，例: long-term-fundamental)"
            )
        if sid in seen_ids:
            raise StickyConfigError(f"重复 id: {sid!r}")
        seen_ids.add(sid)

        pref = item.get("preference", "").strip()
        if not pref:
            raise StickyConfigError(f"sticky {sid!r} 缺 preference")

        kws = item.get("violation_keywords", []) or []
        if not isinstance(kws, list):
            raise StickyConfigError(f"sticky {sid!r} violation_keywords 必须是 list")
        kws_clean = tuple(str(k).strip() for k in kws if str(k).strip())

        vcs = item.get("violation_checks", []) or []
        if not isinstance(vcs, list):
            raise StickyConfigError(f"sticky {sid!r} violation_checks 必须是 list")
        vcs_clean = tuple(str(v).strip() for v in vcs if str(v).strip())

        fbe_raw = item.get("force_block_exempt", False)
        if not isinstance(fbe_raw, bool):
            raise StickyConfigError(
                f"sticky {sid!r} force_block_exempt 必须是 bool，实际 {type(fbe_raw).__name__}"
            )

        sticky_list.append(Sticky(
            id=sid,
            preference=pref,
            violation_keywords=kws_clean,
            violation_checks=vcs_clean,
            force_block_exempt=fbe_raw,
        ))

    return sticky_list


def format_for_injection(
    sticky_list: list[Sticky],
    recent_violations: dict[str, int] | None = None,
) -> str:
    """渲染 sticky 列表为前置注入的 prompt 文本。

    recent_violations: sticky_id → 最近违反时间戳。出现的规则会标 ⚠️。
    """
    if not sticky_list:
        return ""
    recent_violations = recent_violations or {}
    lines = ["[karma sticky — 用户最高优先级方向，请始终遵守]"]
    for i, s in enumerate(sticky_list, 1):
        marker = " ⚠️ 上次违反！" if s.id in recent_violations else ""
        # preference 多行 → 缩进对齐
        pref_lines = s.preference.strip().split("\n")
        lines.append(f"{i}. {pref_lines[0]}{marker}")
        for extra in pref_lines[1:]:
            lines.append(f"   {extra}")
    lines.append("")
    return "\n".join(lines)
