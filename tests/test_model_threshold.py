"""v0.4.35 model_threshold 模块守护测试 — 按模型自动适配中段注入阈值。"""

from __future__ import annotations

from karma.model_threshold import threshold_for_model, DEFAULT_THRESHOLD


def test_opus_returns_80k():
    """Opus 衰减区入口 ~70-100K → 阈值 80K 真贴近。"""
    assert threshold_for_model("claude-opus-4-7") == 80_000
    assert threshold_for_model("claude-opus-4-6") == 80_000
    assert threshold_for_model("opus") == 80_000


def test_sonnet_returns_60k():
    """Sonnet 衰减区入口 ~50-70K → 阈值 60K。"""
    assert threshold_for_model("claude-sonnet-4-6") == 60_000
    assert threshold_for_model("claude-sonnet-4-5") == 60_000
    assert threshold_for_model("sonnet") == 60_000


def test_haiku_returns_30k():
    """Haiku 小模型衰减更快 → 阈值 30K。"""
    assert threshold_for_model("claude-haiku-4-5") == 30_000
    assert threshold_for_model("haiku") == 30_000


def test_old_models_return_8k_backward_compat():
    """老模型 (GPT-3.5 / Claude-1.3 时代) 真在 8K 衰减 — Liu 2023 数据。"""
    assert threshold_for_model("gpt-3.5-turbo") == 8_000
    assert threshold_for_model("claude-1.3") == 8_000
    assert threshold_for_model("claude-instant-1") == 8_000


def test_unknown_model_falls_back_to_60k():
    """未知模型 / None / 空 → 60K 默认（按用户「至少 60K」保守原则）。"""
    assert threshold_for_model(None) == DEFAULT_THRESHOLD
    assert threshold_for_model("") == DEFAULT_THRESHOLD
    assert threshold_for_model("unknown-model-2030") == DEFAULT_THRESHOLD
    assert DEFAULT_THRESHOLD == 60_000


def test_case_insensitive():
    """模型 ID 大小写不影响识别。"""
    assert threshold_for_model("CLAUDE-OPUS-4-7") == 80_000
    assert threshold_for_model("Sonnet-4-6") == 60_000


def test_keyword_priority_long_matches_first():
    """关键词顺序敏感 — opus / sonnet 先于潜在子串误命中。"""
    # 防御性：如果未来加 'son' 类短关键词，'sonnet' 不该被截断
    assert threshold_for_model("claude-sonnet-x") == 60_000
