"""rule.py schema 验证边界测试。

覆盖：
- 10 条规则 → 软上限，加载成功
- 11 条规则 → 介于软/硬上限，加载成功（HARD_MAX=12）
- 12 条规则 → 恰好硬上限，加载成功
- 13 条规则 → 超过硬上限，RuleConfigError
- 重复 id → RuleConfigError
- 无效 slug 格式（含大写 / 数字开头 / 空格 / 单字符）→ RuleConfigError
- 缺 id 字段 → RuleConfigError
- 缺 preference → RuleConfigError
- preference 仅空白 → RuleConfigError
- violation_keywords 非 list → RuleConfigError
- violation_checks 非 list → RuleConfigError
- force_block_exempt 非 bool → RuleConfigError
- 空 yaml 文件 → []
- yaml 解析失败 → RuleConfigError
- 顶层非 list → RuleConfigError
- 规则条目非 dict → RuleConfigError
- violation_keywords 含空白项 → 被过滤掉
- force_block_exempt=True 正确写入 Rule
- 多行 preference 保留换行
"""

from __future__ import annotations

import pytest
import json

from pinrule.rule import HARD_MAX, MAX_RULES, Rule, RuleConfigError, load


# ---------------------------------------------------------------------------
# 辅助：生成合法 rule yaml 条目
# ---------------------------------------------------------------------------

def _rule(rid: str, pref: str = "合法方向", **extra) -> dict:
    d = {"id": rid, "preference": pref}
    d.update(extra)
    return d


def _write_rules(tmp_path, rules: list[dict]) -> object:
    p = tmp_path / "rules.json"
    p.write_text(json.dumps(rules, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# 边界：条数
# ---------------------------------------------------------------------------

def test_load_ten_rules_succeeds(tmp_path):
    """10 条 = 软上限，应该加载成功。"""
    rules = [_rule(f"rule-{i:02d}") for i in range(1, 11)]
    p = _write_rules(tmp_path, rules)
    loaded = load(p)
    assert len(loaded) == 10


def test_load_eleven_rules_succeeds(tmp_path):
    """11 条介于软/硬上限，应该加载成功（硬上限是 12）。"""
    rules = [_rule(f"rule-{i:02d}") for i in range(1, 12)]
    p = _write_rules(tmp_path, rules)
    loaded = load(p)
    assert len(loaded) == 11


def test_load_twelve_rules_at_hard_max_succeeds(tmp_path):
    """12 条恰好等于 HARD_MAX，加载成功。"""
    rules = [_rule(f"rule-{i:02d}") for i in range(1, 13)]
    p = _write_rules(tmp_path, rules)
    loaded = load(p)
    assert len(loaded) == 12


def test_load_thirteen_rules_exceeds_hard_max_raises(tmp_path):
    """13 条超过 HARD_MAX=12，应抛 RuleConfigError。"""
    rules = [_rule(f"rule-{i:02d}") for i in range(1, 14)]
    p = _write_rules(tmp_path, rules)
    with pytest.raises(RuleConfigError, match="硬上限"):
        load(p)


# ---------------------------------------------------------------------------
# 重复 id
# ---------------------------------------------------------------------------

def test_load_duplicate_id_raises(tmp_path):
    rules = [_rule("same-id", "方向 A"), _rule("same-id", "方向 B")]
    p = _write_rules(tmp_path, rules)
    with pytest.raises(RuleConfigError, match="重复"):
        load(p)


# ---------------------------------------------------------------------------
# 无效 slug 格式
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_id", [
    "HasUppercase",
    "1starts-with-digit",
    "has space",
    "a",          # 单字符（^[a-z][a-z0-9-]*[a-z0-9]$ 要求至少两字符）
    "end-",       # 以 - 结尾
    "-start",     # 以 - 开头
    "has_underscore",
])
def test_load_invalid_slug_raises(tmp_path, bad_id):
    p = _write_rules(tmp_path, [_rule(bad_id)])
    with pytest.raises(RuleConfigError):
        load(p)


def test_load_valid_slug_formats_succeed(tmp_path):
    valid_ids = [
        "ab",
        "long-term-fundamental",
        "rule123",
        "r1",
        "deep-fix-not-bypass",
    ]
    for rid in valid_ids:
        p = _write_rules(tmp_path, [_rule(rid)])
        loaded = load(p)
        assert loaded[0].id == rid, f"slug {rid!r} 应该合法"


# ---------------------------------------------------------------------------
# 缺必须字段
# ---------------------------------------------------------------------------

def test_load_missing_id_raises(tmp_path):
    p = tmp_path / "rules.json"
    p.write_text(json.dumps([{"preference": "方向"}], ensure_ascii=False, indent=2), encoding="utf-8")
    with pytest.raises(RuleConfigError, match="id"):
        load(p)


def test_load_empty_id_raises(tmp_path):
    p = tmp_path / "rules.json"
    p.write_text(json.dumps([{"id": "", "preference": "方向"}], ensure_ascii=False, indent=2), encoding="utf-8")
    with pytest.raises(RuleConfigError):
        load(p)


def test_load_missing_preference_raises(tmp_path):
    p = _write_rules(tmp_path, [{"id": "my-rule"}])
    with pytest.raises(RuleConfigError, match="preference"):
        load(p)


def test_load_blank_preference_raises(tmp_path):
    p = _write_rules(tmp_path, [{"id": "my-rule", "preference": "   "}])
    with pytest.raises(RuleConfigError, match="preference"):
        load(p)


# ---------------------------------------------------------------------------
# violation_keywords 类型校验
# ---------------------------------------------------------------------------

def test_load_violation_keywords_not_list_raises(tmp_path):
    p = _write_rules(tmp_path, [_rule("my-rule", violation_keywords="not-a-list")])
    with pytest.raises(RuleConfigError, match="list"):
        load(p)


def test_load_violation_keywords_empty_list_ok(tmp_path):
    p = _write_rules(tmp_path, [_rule("my-rule", violation_keywords=[])])
    loaded = load(p)
    assert loaded[0].violation_keywords == ()


def test_load_violation_keywords_whitespace_items_filtered(tmp_path):
    """violation_keywords 里全空白的项应被过滤掉。"""
    p = _write_rules(tmp_path, [_rule("my-rule", violation_keywords=["  ", "有效词", ""])])
    loaded = load(p)
    assert loaded[0].violation_keywords == ("有效词",)


# ---------------------------------------------------------------------------
# violation_checks 类型校验
# ---------------------------------------------------------------------------

def test_load_violation_checks_not_list_raises(tmp_path):
    p = _write_rules(tmp_path, [_rule("my-rule", violation_checks="scalar")])
    with pytest.raises(RuleConfigError, match="list"):
        load(p)


# ---------------------------------------------------------------------------
# force_block_exempt 类型校验
# ---------------------------------------------------------------------------

def test_load_force_block_exempt_non_bool_raises(tmp_path):
    p = _write_rules(tmp_path, [_rule("my-rule", force_block_exempt="yes")])
    with pytest.raises(RuleConfigError, match="bool"):
        load(p)


def test_load_force_block_exempt_true_persisted(tmp_path):
    p = _write_rules(tmp_path, [_rule("my-rule", force_block_exempt=True)])
    loaded = load(p)
    assert loaded[0].force_block_exempt is True


def test_load_force_block_exempt_false_default(tmp_path):
    p = _write_rules(tmp_path, [_rule("my-rule")])
    loaded = load(p)
    assert loaded[0].force_block_exempt is False


# ---------------------------------------------------------------------------
# 空文件 / None yaml → []
# ---------------------------------------------------------------------------

def test_load_empty_file_returns_empty(tmp_path):
    """空文件解析失败按 JSON 走会抛 RuleConfigError — 这是合理 fail-loud，老 yaml 行为是
    json.loads('') → JSONDecodeError. 现在测真期望: 抛 RuleConfigError."""
    p = tmp_path / "rules.json"
    p.write_text("", encoding="utf-8")
    with pytest.raises(RuleConfigError, match="JSON"):
        load(p)


def test_load_null_returns_empty(tmp_path):
    p = tmp_path / "rules.json"
    p.write_text("null", encoding="utf-8")
    assert load(p) == []


def test_load_missing_file_returns_empty(tmp_path):
    p = tmp_path / "rules.json"
    assert load(p) == []


# ---------------------------------------------------------------------------
# 解析失败 → RuleConfigError
# ---------------------------------------------------------------------------

def test_load_bad_json_raises(tmp_path):
    p = tmp_path / "rules.json"
    p.write_text("- { bad json {{ }}", encoding="utf-8")
    with pytest.raises(RuleConfigError, match="JSON"):
        load(p)


# ---------------------------------------------------------------------------
# 顶层非 list → RuleConfigError
# ---------------------------------------------------------------------------

def test_load_top_level_dict_raises(tmp_path):
    p = tmp_path / "rules.json"
    p.write_text(json.dumps({"id": "my-rule", "preference": "x"}), encoding="utf-8")
    with pytest.raises(RuleConfigError, match="list"):
        load(p)


# ---------------------------------------------------------------------------
# 规则条目非 dict → RuleConfigError
# ---------------------------------------------------------------------------

def test_load_item_not_dict_raises(tmp_path):
    p = tmp_path / "rules.json"
    p.write_text(json.dumps(["not a dict"]), encoding="utf-8")
    with pytest.raises(RuleConfigError, match="dict"):
        load(p)


# ---------------------------------------------------------------------------
# 多行 preference 保留换行
# ---------------------------------------------------------------------------

def test_load_multiline_preference_preserved(tmp_path):
    pref = "第一行\n第二行\n第三行"
    p = _write_rules(tmp_path, [_rule("my-rule", pref=pref)])
    loaded = load(p)
    assert "\n" in loaded[0].preference
    assert "第二行" in loaded[0].preference


# ---------------------------------------------------------------------------
# Rule dataclass 不可变（frozen=True）
# ---------------------------------------------------------------------------

def test_rule_is_immutable():
    r = Rule(id="my-rule", preference="x")
    with pytest.raises(Exception):
        r.preference = "y"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# HARD_MAX 常量值
# ---------------------------------------------------------------------------

def test_hard_max_is_12():
    assert HARD_MAX == 12


def test_max_rules_is_10():
    assert MAX_RULES == 10
