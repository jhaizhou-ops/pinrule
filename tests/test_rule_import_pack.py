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
    """import 成功后 .rules.json.*.tmp 不应该留 — atomic os.replace 已 rename."""
    pack_file = tmp_path / "pack.json"
    pack_file.write_text(json.dumps([{"id": "ok", "preference": "x"}]), encoding="utf-8")

    rc = cmd_rule_import_pack(str(pack_file), mode="replace")
    assert rc == 0
    # v0.18.1: tmp 文件用 NamedTemporaryFile 唯一名 (.rules.json.*.tmp) — 检查没残留
    tmp_residues = list(sandbox_rules.parent.glob(".rules.json.*.tmp"))
    assert not tmp_residues, f"atomic rename 后 tmp 不该留, 实际残留: {tmp_residues}"


def test_schema_fail_byte_for_byte_unchanged(sandbox_rules, tmp_path):
    """v0.18.1 (Codex A Round 1): schema fail 时 rules.json byte-for-byte 真没动.

    之前测试只比 JSON 语义 (json.loads 相等), 不能证明真 "一字没动" — 真用户可能加了
    注释 / 自定义空白格式 / 等. byte-for-byte 才是 atomic guarantee 真证据.
    """
    original_bytes = b'[\n  {"id": "original", "preference": "byte for byte test"}\n]\n'
    sandbox_rules.parent.mkdir(parents=True, exist_ok=True)
    sandbox_rules.write_bytes(original_bytes)

    # bad pack 真挂 schema (id 含非法字符)
    pack_file = tmp_path / "bad-schema.json"
    pack_file.write_text(json.dumps([
        {"id": "OK_HERE", "preference": "x"},  # 'OK_HERE' 大写 _ → schema reject
    ]), encoding="utf-8")

    rc = cmd_rule_import_pack(str(pack_file), mode="replace")
    assert rc == 1

    # byte-for-byte 真验证 (不只是 JSON 语义)
    after_bytes = sandbox_rules.read_bytes()
    assert after_bytes == original_bytes, \
        f"schema fail 时 rules.json 真该一字没动\n  before: {original_bytes!r}\n  after:  {after_bytes!r}"


def test_duplicate_id_rejected_atomic(sandbox_rules, tmp_path):
    """v0.18.1 (Codex A Round 1): pack 内 duplicate id 应该拒 + rules.json 不动."""
    original_bytes = b'[\n  {"id": "original", "preference": "x"}\n]\n'
    sandbox_rules.parent.mkdir(parents=True, exist_ok=True)
    sandbox_rules.write_bytes(original_bytes)

    pack_file = tmp_path / "dup-id.json"
    pack_file.write_text(json.dumps([
        {"id": "same-id", "preference": "first"},
        {"id": "same-id", "preference": "second"},  # 真 duplicate
    ]), encoding="utf-8")

    rc = cmd_rule_import_pack(str(pack_file), mode="replace")
    assert rc == 1
    assert sandbox_rules.read_bytes() == original_bytes


def test_concurrent_import_pack_no_tmp_collision(sandbox_rules, tmp_path):
    """v0.18.1 (Codex A Round 1): 两个 import-pack 同时跑不该共用 tmp 文件名.

    固定 tmp 文件 `rules.json.tmp` 真有并发竞态. v0.18.1 用 NamedTemporaryFile 唯一名,
    所以 tmp 文件名互不冲突 — 这测验证 tmp 文件 prefix `.rules.json.` 是 unique 的.
    """
    import threading

    sandbox_rules.parent.mkdir(parents=True, exist_ok=True)
    sandbox_rules.write_text(json.dumps([{"id": "shared", "preference": "x"}]))

    pack_a = tmp_path / "pack-a.json"
    pack_a.write_text(json.dumps([{"id": "from-a", "preference": "a"}]))
    pack_b = tmp_path / "pack-b.json"
    pack_b.write_text(json.dumps([{"id": "from-b", "preference": "b"}]))

    results = []
    errors = []

    def run(pack_file):
        try:
            results.append(cmd_rule_import_pack(str(pack_file), mode="replace"))
        except Exception as e:
            errors.append(e)

    threads = [
        threading.Thread(target=run, args=(pack_a,)),
        threading.Thread(target=run, args=(pack_b,)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    # 真验证: 两个都成功 (没相互踩坏 tmp), 且 rules.json 是 A 或 B 之一
    # (race winner 谁先 os.replace 谁赢, 都合法 atomic outcome)
    assert not errors, f"concurrent import 出现真异常: {errors}"
    assert all(rc == 0 for rc in results), f"concurrent import 真不该有 rc=1: {results}"
    final = json.loads(sandbox_rules.read_text())
    final_ids = {r["id"] for r in final}
    assert final_ids in [{"from-a"}, {"from-b"}], \
        f"final rule pack 真该是 A or B winner, 实际: {final_ids}"

    # 任何 tmp 文件都不该残留
    tmp_residues = list(sandbox_rules.parent.glob(".rules.json.*.tmp"))
    assert not tmp_residues, f"concurrent import 后 tmp 真不该留: {tmp_residues}"


def test_backup_filename_has_pid_random_suffix(sandbox_rules, tmp_path):
    """v0.18.1 (Codex A Round 1): backup 文件名加 pid + random suffix, 真避免同秒覆盖.

    之前秒级 ts 同秒两个 import-pack 会覆盖对方 backup. v0.18.1 加 pid+random 真唯一.
    """
    sandbox_rules.parent.mkdir(parents=True, exist_ok=True)
    sandbox_rules.write_text(json.dumps([{"id": "before-backup", "preference": "x"}]))

    pack_file = tmp_path / "pack.json"
    pack_file.write_text(json.dumps([{"id": "after-backup", "preference": "y"}]))

    rc = cmd_rule_import_pack(str(pack_file), mode="replace", backup=True)
    assert rc == 0

    backups = list(sandbox_rules.parent.glob("rules.json.before-scenario-*"))
    assert len(backups) == 1
    # 真验证文件名格式: rules.json.before-scenario-<ts>-<pid>-<random>
    name = backups[0].name
    parts = name.replace("rules.json.before-scenario-", "").split("-")
    assert len(parts) >= 4, \
        f"backup 文件名真该含 ts (YYYYMMDD-HHMMSS) + pid + random_hex, 实际 {name}"
