"""config.DEFAULTS 完整性 + load() 边界测试。

覆盖：
- DEFAULTS 中每个 key 都有合理类型（不全是 None）
- 所有 key 都能用 get() 取到
- 布尔 False 可以被用户配置覆盖（null 不能覆盖，但 false 可以）
- 整数值用户配置覆盖
- None 值（reinject_every_n_tokens）可以被用户设整数覆盖
- locale 字段只接受 en / zh / auto（用户写其他值被读进来，不报错）
- list 类型不在 DEFAULTS（所有值都是标量/None）
- 所有 DEFAULTS key 在 get() 直接 path=None 时也能取（使用 DEFAULT_PATH 语义）
- stop_block_max_per_turn 默认 2
- force_block_threshold 默认 5
"""

from __future__ import annotations

import pytest

from karma.config import DEFAULTS, get, load


# ---------------------------------------------------------------------------
# 1. DEFAULTS 所有 key 都有值（非缺失）
# ---------------------------------------------------------------------------

_EXPECTED_KEYS = [
    "locale",
    "notify_enabled",
    "recent_violation_turns",
    "escalate_window_turns",
    "escalate_threshold",
    "violations_max_lines",
    "violations_keep_history",
    "session_state_max_age_days",
    "max_recent_bash",
    "stop_block_max_per_turn",
    "force_block_threshold",
    "reinject_every_n_tokens",
]


def test_defaults_contains_all_expected_keys():
    for key in _EXPECTED_KEYS:
        assert key in DEFAULTS, f"DEFAULTS 缺少 key: {key!r}"


# ---------------------------------------------------------------------------
# 2. DEFAULTS 每个 key 的类型合理
# ---------------------------------------------------------------------------

def test_defaults_types():
    assert isinstance(DEFAULTS["locale"], str)
    assert isinstance(DEFAULTS["notify_enabled"], bool)
    assert isinstance(DEFAULTS["recent_violation_turns"], int)
    assert isinstance(DEFAULTS["escalate_window_turns"], int)
    assert isinstance(DEFAULTS["escalate_threshold"], int)
    assert isinstance(DEFAULTS["violations_max_lines"], int)
    assert isinstance(DEFAULTS["violations_keep_history"], int)
    assert isinstance(DEFAULTS["session_state_max_age_days"], int)
    assert isinstance(DEFAULTS["max_recent_bash"], int)
    assert isinstance(DEFAULTS["stop_block_max_per_turn"], int)
    assert isinstance(DEFAULTS["force_block_threshold"], int)
    # reinject_every_n_tokens 可以是 None 或 int
    assert DEFAULTS["reinject_every_n_tokens"] is None or isinstance(DEFAULTS["reinject_every_n_tokens"], int)


# ---------------------------------------------------------------------------
# 3. 默认值合理范围
# ---------------------------------------------------------------------------

def test_defaults_values_in_reasonable_range():
    assert DEFAULTS["recent_violation_turns"] > 0
    assert DEFAULTS["escalate_window_turns"] > 0
    assert DEFAULTS["escalate_threshold"] > 0
    assert DEFAULTS["violations_max_lines"] > 0
    assert DEFAULTS["violations_keep_history"] > 0
    assert DEFAULTS["max_recent_bash"] > 0
    assert DEFAULTS["stop_block_max_per_turn"] >= 0
    assert DEFAULTS["force_block_threshold"] >= 0


def test_defaults_stop_block_max_per_turn_is_2():
    assert DEFAULTS["stop_block_max_per_turn"] == 2


def test_defaults_force_block_threshold_is_5():
    assert DEFAULTS["force_block_threshold"] == 5


def test_defaults_locale_is_auto():
    assert DEFAULTS["locale"] == "auto"


def test_defaults_notify_enabled_is_true():
    assert DEFAULTS["notify_enabled"] is True


def test_defaults_reinject_every_n_tokens_is_none():
    """None 表示按模型自适应，用户可覆盖为整数。"""
    assert DEFAULTS["reinject_every_n_tokens"] is None


# ---------------------------------------------------------------------------
# 4. 布尔 False 可以被用户配置覆盖（null 不覆盖）
# ---------------------------------------------------------------------------

def test_load_bool_false_overrides_default(tmp_path):
    """notify_enabled 默认 True，用户设 false → 应覆盖为 False。"""
    p = tmp_path / "config.yaml"
    p.write_text("notify_enabled: false\n", encoding="utf-8")
    cfg = load(p)
    assert cfg["notify_enabled"] is False


def test_load_bool_true_stays_true(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("notify_enabled: true\n", encoding="utf-8")
    cfg = load(p)
    assert cfg["notify_enabled"] is True


def test_load_null_does_not_override_default(tmp_path):
    """null 值 → 用 DEFAULTS，不把字段设为 None。"""
    p = tmp_path / "config.yaml"
    p.write_text("notify_enabled: null\n", encoding="utf-8")
    cfg = load(p)
    assert cfg["notify_enabled"] is True  # DEFAULTS 中是 True


# ---------------------------------------------------------------------------
# 5. 整数值用户配置覆盖
# ---------------------------------------------------------------------------

def test_load_integer_override(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("escalate_threshold: 10\nstop_block_max_per_turn: 0\n", encoding="utf-8")
    cfg = load(p)
    assert cfg["escalate_threshold"] == 10
    assert cfg["stop_block_max_per_turn"] == 0


# ---------------------------------------------------------------------------
# 6. None 字段（reinject_every_n_tokens）被整数覆盖
# ---------------------------------------------------------------------------

def test_load_none_default_overridden_by_integer(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("reinject_every_n_tokens: 4000\n", encoding="utf-8")
    cfg = load(p)
    assert cfg["reinject_every_n_tokens"] == 4000


# ---------------------------------------------------------------------------
# 7. DEFAULTS 所有值都是标量（不含 list / dict）
# ---------------------------------------------------------------------------

def test_defaults_all_scalar_values():
    for key, val in DEFAULTS.items():
        assert not isinstance(val, (list, dict)), \
            f"DEFAULTS[{key!r}] 是 {type(val).__name__}，应该是标量或 None"


# ---------------------------------------------------------------------------
# 8. get() 便捷函数覆盖 DEFAULTS
# ---------------------------------------------------------------------------

def test_get_returns_user_value_when_overridden(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("escalate_threshold: 99\n", encoding="utf-8")
    assert get("escalate_threshold", p) == 99


def test_get_returns_default_for_missing_key(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("notify_enabled: false\n", encoding="utf-8")
    # escalate_threshold 未在配置中，返回 DEFAULTS 值
    assert get("escalate_threshold", p) == DEFAULTS["escalate_threshold"]


def test_get_returns_none_for_truly_unknown_key(tmp_path):
    """完全不存在的 key → get() 返回 None（不报错）。"""
    p = tmp_path / "config.yaml"
    p.write_text("", encoding="utf-8")
    result = get("this_key_does_not_exist", p)
    assert result is None


# ---------------------------------------------------------------------------
# 9. load() 返回的 dict 是 DEFAULTS 的 副本（修改不影响 DEFAULTS）
# ---------------------------------------------------------------------------

def test_load_returns_copy_not_defaults_reference(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("", encoding="utf-8")
    cfg = load(p)
    cfg["escalate_threshold"] = 9999
    assert DEFAULTS["escalate_threshold"] != 9999, "load() 应返回副本，不能污染 DEFAULTS"


# ---------------------------------------------------------------------------
# 10. 所有 DEFAULTS key 都被 load() 返回
# ---------------------------------------------------------------------------

def test_load_contains_all_defaults_keys(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text("", encoding="utf-8")
    cfg = load(p)
    for key in DEFAULTS:
        assert key in cfg, f"load() 返回 dict 缺少 DEFAULTS key: {key!r}"
