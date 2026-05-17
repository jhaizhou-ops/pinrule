"""Sync karma rules into Cursor native `.mdc` rules (model-visible layer).

Cursor hook `sessionStart.additional_context` is confirmed to reach karma stdout
but dogfood showed the model's self-reported「起手上下文」does not always include
hook-injected text — while Cursor **Rules** (`alwaysApply` project/user rules)
do appear in agent startup context.

This module mirrors `format_for_injection()` into `~/.cursor/rules/karma-sticky.mdc`
so Cursor parity with Claude's per-turn sticky visibility has a reliable path
alongside hooks (`beforeSubmitPrompt` + `postToolUse` reinject).
"""

from __future__ import annotations

from pathlib import Path

_RULE_FILENAME = "karma-sticky.mdc"
_MANAGED_MARKER = "<!-- karma-managed: do not hand-edit; run `karma sync-cursor-rules` -->"


def cursor_rules_dir(user: bool = True, project_root: Path | None = None) -> Path | None:
    """Target directory for synced rules. Prefer project `.cursor/rules` when given."""
    if project_root is not None:
        return (project_root / ".cursor" / "rules").resolve()
    if user:
        return (Path.home() / ".cursor" / "rules").resolve()
    return None


def build_mdc_content(rule_text: str, *, id_catalog: str = "") -> str:
    """Wrap karma injection text as Cursor always-on rule file."""
    parts = [p.strip() for p in (id_catalog, rule_text) if p and p.strip()]
    body = "\n\n".join(parts)
    if not body:
        return ""
    return (
        "---\n"
        "description: karma long-term collaboration agreements (auto-synced)\n"
        "alwaysApply: true\n"
        "---\n\n"
        f"{_MANAGED_MARKER}\n\n"
        f"{body}\n"
    )


def sync_cursor_rules(
    *,
    user: bool = True,
    project_root: Path | None = None,
) -> tuple[list[Path], list[str]]:
    """Write karma rules to Cursor `.mdc` file(s). Returns (paths_written, log_lines)."""
    from karma.rule import (
        RuleConfigError,
        format_for_injection,
        format_rule_id_catalog,
        load,
    )

    logs: list[str] = []
    written: list[Path] = []

    try:
        sticky_list = load()
    except RuleConfigError as e:
        return [], [f"⚠ 跳过 Cursor rules 同步: {e}"]

    if not sticky_list:
        return [], ["⚠ 跳过 Cursor rules 同步: rules 为空"]

    rule_text = format_for_injection(sticky_list)
    catalog = format_rule_id_catalog(sticky_list)
    mdc = build_mdc_content(rule_text, id_catalog=catalog)
    if not mdc:
        return [], ["⚠ 跳过 Cursor rules 同步: 渲染结果为空"]

    targets: list[Path] = []
    if user:
        d = cursor_rules_dir(user=True)
        if d is not None:
            targets.append(d)
    if project_root is not None:
        d = cursor_rules_dir(user=False, project_root=project_root)
        if d is not None:
            targets.append(d)

    for directory in targets:
        directory.mkdir(parents=True, exist_ok=True)
        dest = directory / _RULE_FILENAME
        dest.write_text(mdc, encoding="utf-8")
        written.append(dest)
        logs.append(f"  同步 Cursor rule: {dest}")

    if not written:
        logs.append("⚠ 未写入任何 Cursor rules 路径")
    return written, logs
