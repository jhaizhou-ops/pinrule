"""Tests for pinrule.cursor_rules_sync."""

import json

from pinrule.cursor_rules_sync import build_mdc_content, sync_cursor_rules


def test_build_mdc_content_always_apply():
    text = build_mdc_content("Rule one.\nRule two.")
    assert "alwaysApply: true" in text
    assert "pinrule-managed" in text
    assert "Rule one." in text


def test_sync_cursor_rules_writes_user_dir(monkeypatch, tmp_path):
    rules_file = tmp_path / "rules.json"
    monkeypatch.setattr("pinrule.rule.DEFAULT_PATH", rules_file)
    rules_file.write_text(
        json.dumps([{"id": "test-rule", "preference": "Do the right thing."}], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    rules_dir = tmp_path / "rules"
    monkeypatch.setattr(
        "pinrule.cursor_rules_sync.cursor_rules_dir",
        lambda user=True, project_root=None: rules_dir if user else None,
    )
    written, logs = sync_cursor_rules(user=True)
    assert len(written) == 1
    assert written[0].name == "pinrule-sticky.mdc"
    assert written[0].parent == rules_dir
    content = written[0].read_text(encoding="utf-8")
    assert "`test-rule`" in content
    assert "Do the right thing." in content
    assert any("同步 Cursor rule" in line for line in logs)
