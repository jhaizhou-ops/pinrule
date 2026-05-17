"""Make pinrule rule IDs visible in Cursor Composer context.

Dogfood finding (2026-05): Cursor hook `beforeSubmitPrompt` / `sessionStart`
stdout **does run** and merges `additionalContext`, but Agent self-report
shows **only** `user_rules` + `available_skills` (~/.claude/skills/) — hook
injection is not surfaced in the model's `<rules>` block for empty-window.

Reliable visibility paths:
1. Companion skill under `~/.claude/skills/` (Cursor loads these as available_skills)
2. Project `.cursor/rules/*.mdc` when workspace has a folder (not ~/.cursor/rules alone)
3. `~/.cursor/projects/<workspaceId>/.cursor/rules/` for virtual workspaces like empty-window
"""

from __future__ import annotations

from pathlib import Path

_SKILL_DIR = "pinrule-rules-catalog"
_SKILL_FILENAME = "SKILL.md"


def build_rules_catalog_skill_body(rule_ids: list[str], pinrule_home: Path) -> str:
    """Skill body: only rule ids + one-line instruction (kept short for skill picker)."""
    lines = [
        "---",
        "name: pinrule-rules-catalog",
        "description: >",
        "  Active pinrule rule IDs (auto-synced). When the user asks for pinrule rule ids,",
        "  visibility, or rules.yaml contents without reading files, list every id below verbatim.",
        "---",
        "",
        f"# pinrule active rule IDs (`PINRULE_HOME={pinrule_home}`)",
        "",
        "If asked whether pinrule rules are visible, answer **yes** and list **all** ids:",
        "",
    ]
    for rid in rule_ids:
        lines.append(f"- `{rid}`")
    lines.extend([
        "",
        "Do not claim the list is empty if this skill is in context.",
        "Full preferences are enforced via Cursor hooks; this skill is the id catalog only.",
        "",
    ])
    return "\n".join(lines)


def sync_claude_skills_catalog(*, pinrule_home: Path | None = None) -> tuple[Path | None, list[str]]:
    """Write ~/.claude/skills/pinrule-rules-catalog/SKILL.md for Cursor visibility."""
    from pinrule.rule import RuleConfigError, load

    logs: list[str] = []
    if pinrule_home is None:
        from pinrule.paths import pinrule_home as _kh
        pinrule_home = _kh()

    try:
        sticky = load()
    except RuleConfigError as e:
        return None, [f"⚠ 跳过 skills catalog: {e}"]

    if not sticky:
        return None, ["⚠ 跳过 skills catalog: rules 为空"]

    rule_ids = [r.id for r in sticky]
    dest_dir = Path.home() / ".claude" / "skills" / _SKILL_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / _SKILL_FILENAME
    dest.write_text(
        build_rules_catalog_skill_body(rule_ids, pinrule_home),
        encoding="utf-8",
    )
    logs.append(f"  同步 Cursor 可见 skill: {dest}")
    logs.append("  (Composer 从 ~/.claude/skills/ 加载 available_skills — hook 注入不进 <rules>)")
    return dest, logs


def sync_empty_window_project_rules(mdc_content: str) -> list[str]:
    """Write rules into Cursor virtual workspace storage (empty-window dogfood)."""
    logs: list[str] = []
    base = Path.home() / ".cursor" / "projects" / "empty-window" / ".cursor" / "rules"
    try:
        base.mkdir(parents=True, exist_ok=True)
        dest = base / "pinrule-sticky.mdc"
        dest.write_text(mdc_content, encoding="utf-8")
        logs.append(f"  同步 empty-window 项目 rule: {dest}")
    except OSError as e:
        logs.append(f"⚠ 无法写入 empty-window 项目 rules: {e}")
    return logs


def sync_all_visibility_layers(*, pinrule_home: Path | None = None) -> list[str]:
    """Run all Composer-visible sync paths."""
    from pinrule.cursor_rules_sync import build_mdc_content, sync_cursor_rules
    from pinrule.rule import RuleConfigError, format_for_injection, format_rule_id_catalog, load

    logs: list[str] = ["→ Cursor Composer 可见性同步（hook 之外）…"]
    if pinrule_home is None:
        from pinrule.paths import pinrule_home as _kh
        pinrule_home = _kh()

    _, skill_logs = sync_claude_skills_catalog(pinrule_home=pinrule_home)
    logs.extend(skill_logs)

    try:
        sticky = load()
        mdc = build_mdc_content(
            format_for_injection(sticky),
            id_catalog=format_rule_id_catalog(sticky),
        )
        logs.extend(sync_empty_window_project_rules(mdc))
    except RuleConfigError as e:
        logs.append(f"⚠ 跳过 empty-window mdc: {e}")

    written, rule_logs = sync_cursor_rules(user=True)
    logs.extend(rule_logs)
    if written:
        logs.append("  (若 alwaysApply 仍不进上下文: Settings → Rules 手动加一条 User Rule)")
    return logs
