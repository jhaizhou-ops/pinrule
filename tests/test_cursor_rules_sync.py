"""Tests for karma.cursor_rules_sync."""



from karma.cursor_rules_sync import build_mdc_content, sync_cursor_rules


def test_build_mdc_content_always_apply():
    text = build_mdc_content("Rule one.\nRule two.")
    assert "alwaysApply: true" in text
    assert "karma-managed" in text
    assert "Rule one." in text


def test_sync_cursor_rules_writes_user_dir(monkeypatch, tmp_path):
    rules_file = tmp_path / "rules.yaml"
    monkeypatch.setattr("karma.rule.DEFAULT_PATH", rules_file)
    rules_file.write_text(
        "- id: test-rule\n  preference: |\n    Do the right thing.\n",
        encoding="utf-8",
    )
    rules_dir = tmp_path / "rules"
    monkeypatch.setattr(
        "karma.cursor_rules_sync.cursor_rules_dir",
        lambda user=True, project_root=None: rules_dir if user else None,
    )
    written, logs = sync_cursor_rules(user=True)
    assert len(written) == 1
    assert written[0].name == "karma-sticky.mdc"
    assert written[0].parent == rules_dir
    content = written[0].read_text(encoding="utf-8")
    assert "`test-rule`" in content
    assert "Do the right thing." in content
    assert any("同步 Cursor rule" in line for line in logs)
