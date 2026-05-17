"""Cursor Composer visibility sync (skills catalog path)."""

from __future__ import annotations

from pathlib import Path

from karma.cursor_visibility import build_rules_catalog_skill_body, sync_claude_skills_catalog


def test_build_rules_catalog_skill_lists_ids():
    body = build_rules_catalog_skill_body(
        ["rule-a", "rule-b"],
        Path("/tmp/karma-home"),
    )
    assert "rule-a" in body
    assert "rule-b" in body
    assert "karma-rules-catalog" in body


def test_sync_claude_skills_catalog_writes_file(monkeypatch, tmp_path):
    rules_file = tmp_path / "rules.yaml"
    monkeypatch.setattr("karma.rule.DEFAULT_PATH", rules_file)
    rules_file.write_text(
        "- id: dogfood-marker-cursor-v12\n  preference: |\n    marker\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "karma.cursor_visibility.Path.home",
        lambda: tmp_path,
    )
    dest, logs = sync_claude_skills_catalog(karma_home=tmp_path / "karma")
    assert dest is not None
    assert dest == tmp_path / ".claude" / "skills" / "karma-rules-catalog" / "SKILL.md"
    assert "dogfood-marker-cursor-v12" in dest.read_text(encoding="utf-8")
    assert any("可见 skill" in line for line in logs)
