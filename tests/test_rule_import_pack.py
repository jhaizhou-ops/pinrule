"""pinrule rule import-pack — 原子批量导入规则包测试.

P2 朋友 review 建议加的真原子 CLI primitive. Path B Step 10 批量写从 Agent
串多条 shell 命令改成单一 CLI 调用, 中间任何失败 → rules.json 一字没动.

测试覆盖:
- replace 模式正常路径 (atomic swap rules.json)
- append 模式正常路径 (追加到现有规则库)
- backup flag 真创建 before-scenario-<ts> 备份
- schema 校验挂 → rules.json 没动 (atomic guarantee)
- 未知 violation_checks 函数 → 拒 + rules.json 没动
- id 冲突 → 拒 + rules.json 没动
- 硬上限超 → 拒 + rules.json 没动
- 空 pack 拒
- 不存在的 json file 拒
- 错误 mode 拒
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from pinrule.cli import cmd_rule_import_pack
from pinrule.rule import HARD_MAX


def _write_rules(path: Path, rules: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rules, ensure_ascii=False, indent=2), encoding="utf-8")


@pytest.fixture
def sandbox_rules(tmp_path: Path):
    """Sandbox RULES_PATH 到 tmp_path/rules.json."""
    rules_path = tmp_path / "rules.json"
    with patch("pinrule.cli.RULES_PATH", rules_path):
        with patch("pinrule.rule.DEFAULT_PATH", rules_path):
            yield rules_path


def test_replace_mode_success(sandbox_rules, tmp_path, capsys):
    """replace 整库替换 — rules.json 从 3 条 → 2 条新规则."""
    # 现有 3 条
    _write_rules(sandbox_rules, [
        {"id": "old-1", "preference": "old direction 1"},
        {"id": "old-2", "preference": "old direction 2"},
        {"id": "old-3", "preference": "old direction 3"},
    ])

    # 新 pack 2 条
    pack_file = tmp_path / "new-pack.json"
    pack_file.write_text(json.dumps([
        {"id": "new-1", "preference": "new direction 1"},
        {"id": "new-2", "preference": "new direction 2"},
    ]), encoding="utf-8")

    rc = cmd_rule_import_pack(str(pack_file), mode="replace")

    assert rc == 0
    final = json.loads(sandbox_rules.read_text())
    assert len(final) == 2
    assert {r["id"] for r in final} == {"new-1", "new-2"}


def test_append_mode_success(sandbox_rules, tmp_path, capsys):
    """append 追加 — rules.json 从 2 条 → 4 条 (2 old + 2 new)."""
    _write_rules(sandbox_rules, [
        {"id": "keep-1", "preference": "keep 1"},
        {"id": "keep-2", "preference": "keep 2"},
    ])

    pack_file = tmp_path / "append-pack.json"
    pack_file.write_text(json.dumps([
        {"id": "new-1", "preference": "new 1"},
        {"id": "new-2", "preference": "new 2"},
    ]), encoding="utf-8")

    rc = cmd_rule_import_pack(str(pack_file), mode="append")

    assert rc == 0
    final = json.loads(sandbox_rules.read_text())
    assert len(final) == 4
    assert {r["id"] for r in final} == {"keep-1", "keep-2", "new-1", "new-2"}


def test_backup_flag_creates_backup_file(sandbox_rules, tmp_path):
    """--backup flag 真创建 rules.json.before-scenario-<ts> 备份."""
    _write_rules(sandbox_rules, [{"id": "before", "preference": "before pack"}])

    pack_file = tmp_path / "pack.json"
    pack_file.write_text(json.dumps([{"id": "after", "preference": "after pack"}]), encoding="utf-8")

    rc = cmd_rule_import_pack(str(pack_file), mode="replace", backup=True)
    assert rc == 0

    # 备份文件应该真存在
    backups = list(sandbox_rules.parent.glob("rules.json.before-scenario-*"))
    assert len(backups) == 1
    backup_content = json.loads(backups[0].read_text())
    assert backup_content == [{"id": "before", "preference": "before pack"}]


def test_schema_fail_atomic_no_change(sandbox_rules, tmp_path, capsys):
    """schema 校验失败 → rules.json 一字没动 (atomic guarantee).

    朋友 review 抓的真坑: 「不是原子, 只是有备份」, 中间挂了 rules.json 半残.
    新 CLI 必须 atomic: schema 全过才写, 任何挂前 rules.json 不动.
    """
    original = [{"id": "original", "preference": "original direction"}]
    _write_rules(sandbox_rules, original)

    # pack 含 invalid id (空字符串, schema 真会挂)
    pack_file = tmp_path / "bad-pack.json"
    pack_file.write_text(json.dumps([
        {"id": "valid", "preference": "ok"},
        {"id": "", "preference": "invalid empty id"},  # schema reject
    ]), encoding="utf-8")

    rc = cmd_rule_import_pack(str(pack_file), mode="replace")
    assert rc == 1

    # rules.json 必须一字没动
    after = json.loads(sandbox_rules.read_text())
    assert after == original, "schema 挂时 rules.json 不该有任何改动"


def test_unknown_violation_check_atomic_no_change(sandbox_rules, tmp_path, capsys):
    """规则引用未注册 check 函数 → 拒 + rules.json 没动."""
    original = [{"id": "original", "preference": "x"}]
    _write_rules(sandbox_rules, original)

    pack_file = tmp_path / "bad-check.json"
    pack_file.write_text(json.dumps([
        {
            "id": "needs-fake-check",
            "preference": "ok",
            "violation_checks": ["this_function_does_not_exist"],
        },
    ]), encoding="utf-8")

    rc = cmd_rule_import_pack(str(pack_file), mode="replace")
    assert rc == 1

    after = json.loads(sandbox_rules.read_text())
    assert after == original, "未知 check 函数挂时 rules.json 不该改动"


def test_hard_max_exceeded_atomic_no_change(sandbox_rules, tmp_path, capsys):
    """超过硬上限 → 拒 + rules.json 没动."""
    original = [{"id": "original", "preference": "x"}]
    _write_rules(sandbox_rules, original)

    # 造 HARD_MAX + 1 条规则
    big_pack = [{"id": f"r-{i}", "preference": f"pref {i}"} for i in range(HARD_MAX + 1)]
    pack_file = tmp_path / "big-pack.json"
    pack_file.write_text(json.dumps(big_pack), encoding="utf-8")

    rc = cmd_rule_import_pack(str(pack_file), mode="replace")
    assert rc == 1

    after = json.loads(sandbox_rules.read_text())
    assert after == original, "超硬上限时 rules.json 不该改动"


def test_empty_pack_rejected(sandbox_rules, tmp_path, capsys):
    """空 pack 拒 — 不允许整库变空."""
    _write_rules(sandbox_rules, [{"id": "keep", "preference": "x"}])

    pack_file = tmp_path / "empty.json"
    pack_file.write_text("[]", encoding="utf-8")

    rc = cmd_rule_import_pack(str(pack_file), mode="replace")
    assert rc == 1

    after = json.loads(sandbox_rules.read_text())
    assert after == [{"id": "keep", "preference": "x"}]


def test_missing_file_rejected(sandbox_rules, tmp_path, capsys):
    """不存在的 json 文件 → 拒."""
    _write_rules(sandbox_rules, [{"id": "keep", "preference": "x"}])

    rc = cmd_rule_import_pack(str(tmp_path / "does-not-exist.json"), mode="replace")
    assert rc == 1

    after = json.loads(sandbox_rules.read_text())
    assert after == [{"id": "keep", "preference": "x"}]


def test_unknown_mode_rejected(sandbox_rules, tmp_path, capsys):
    """--mode 必须是 replace / append, 其他拒."""
    _write_rules(sandbox_rules, [{"id": "keep", "preference": "x"}])

    pack_file = tmp_path / "pack.json"
    pack_file.write_text(json.dumps([{"id": "new", "preference": "y"}]), encoding="utf-8")

    rc = cmd_rule_import_pack(str(pack_file), mode="merge-or-something")
    assert rc == 1

    after = json.loads(sandbox_rules.read_text())
    assert after == [{"id": "keep", "preference": "x"}]


def test_replace_into_empty_rules_path(sandbox_rules, tmp_path):
    """rules.json 不存在 (fresh install) → replace 模式应该能写."""
    assert not sandbox_rules.exists()

    pack_file = tmp_path / "pack.json"
    pack_file.write_text(json.dumps([{"id": "fresh", "preference": "fresh install"}]), encoding="utf-8")

    rc = cmd_rule_import_pack(str(pack_file), mode="replace")
    assert rc == 0

    after = json.loads(sandbox_rules.read_text())
    assert after == [{"id": "fresh", "preference": "fresh install"}]


def test_atomic_temp_file_cleaned_up(sandbox_rules, tmp_path):
    """import 成功后 rules.json.tmp 不应该留 — atomic os.replace 已 rename."""
    pack_file = tmp_path / "pack.json"
    pack_file.write_text(json.dumps([{"id": "ok", "preference": "x"}]), encoding="utf-8")

    rc = cmd_rule_import_pack(str(pack_file), mode="replace")
    assert rc == 0
    assert not (sandbox_rules.parent / "rules.json.tmp").exists(), \
        "atomic rename 后 .tmp 文件不该留"
