"""配置系统测试 — 文件不存在 / 字段缺失 / 解析失败都 fail open 用 DEFAULTS。"""

from __future__ import annotations


from pinrule.config import DEFAULTS, get, load


def test_load_missing_returns_defaults(tmp_path):
    cfg = load(tmp_path / "no.yaml")
    assert cfg == DEFAULTS


def test_load_partial_user_config_merges_with_defaults(tmp_path):
    """用户只配了部分字段 → 其他字段用 DEFAULTS。"""
    p = tmp_path / "config.yaml"
    p.write_text("notify_enabled: false\nescalate_threshold: 5\n")
    cfg = load(p)
    assert cfg["notify_enabled"] is False
    assert cfg["escalate_threshold"] == 5
    assert cfg["escalate_window_turns"] == DEFAULTS["escalate_window_turns"]
    assert cfg["violations_max_lines"] == DEFAULTS["violations_max_lines"]


def test_load_unknown_field_ignored(tmp_path):
    """不认识的字段忽略 — 不报错，DEFAULTS 不被污染。"""
    p = tmp_path / "config.yaml"
    p.write_text("notify_enabled: false\nweird_field: 42\n")
    cfg = load(p)
    assert cfg["notify_enabled"] is False
    assert "weird_field" not in cfg


def test_load_bad_yaml_returns_defaults(tmp_path):
    """yaml 解析失败 → 返回 DEFAULTS，不抛错（fail open）。"""
    p = tmp_path / "config.yaml"
    p.write_text("not: [valid yaml: {{ broken")
    cfg = load(p)
    assert cfg == DEFAULTS


def test_load_empty_file_returns_defaults(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("")
    cfg = load(p)
    assert cfg == DEFAULTS


def test_load_null_value_uses_default(tmp_path):
    """user_cfg 字段值为 null → 用 default 不覆盖。"""
    p = tmp_path / "config.yaml"
    p.write_text("notify_enabled: null\nescalate_threshold: 5\n")
    cfg = load(p)
    assert cfg["notify_enabled"] is True  # null 不覆盖 DEFAULTS
    assert cfg["escalate_threshold"] == 5


def test_get_returns_single_field(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("escalate_threshold: 7\n")
    assert get("escalate_threshold", p) == 7
    assert get("notify_enabled", p) == DEFAULTS["notify_enabled"]


def test_reinject_every_n_tokens_in_defaults_and_user_override(tmp_path):
    """v0.9.16: reinject_every_n_tokens 必须在 DEFAULTS — load() 只认 DEFAULTS keys.

    之前漏 DEFAULTS 让用户 config.yaml 写 reinject_every_n_tokens: 4000 也被
    load() 的「for key in DEFAULTS」循环静默丢弃 → 用户调阈值不生效.
    """
    # DEFAULTS 有这个 key
    assert "reinject_every_n_tokens" in DEFAULTS
    assert DEFAULTS["reinject_every_n_tokens"] is None  # 默认 None → 按模型自适应

    # 用户写数字必须被读到
    p = tmp_path / "config.yaml"
    p.write_text("reinject_every_n_tokens: 4000\n")
    cfg = load(p)
    assert cfg["reinject_every_n_tokens"] == 4000
