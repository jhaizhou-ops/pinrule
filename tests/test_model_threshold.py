"""model_threshold 模块守护测试 — 按模型自动适配中段全量 reinject 阈值。

v0.9.0 阈值调整: Opus 80K → 60K / Sonnet 60K → 40K / Haiku 30K 不变 /
DEFAULT 60K → 40K。理由：v0.9.0 架构是 SessionStart 一次全量 baseline +
每 turn 精简 anchor + 累积达阈值中段全量补。SessionStart baseline 在
history 顶部累积久了会被稀释，需要更早补回完整规则维持 attention 锚定。
"""

from __future__ import annotations

from karma.model_threshold import threshold_for_model, DEFAULT_THRESHOLD


def test_opus_returns_60k():
    """Opus 阈值 60K (v0.9.0 从 80K 收紧)。"""
    assert threshold_for_model("claude-opus-4-7") == 60_000
    assert threshold_for_model("claude-opus-4-6") == 60_000
    assert threshold_for_model("opus") == 60_000


def test_sonnet_returns_40k():
    """Sonnet 阈值 40K (v0.9.0 从 60K 收紧)。"""
    assert threshold_for_model("claude-sonnet-4-6") == 40_000
    assert threshold_for_model("claude-sonnet-4-5") == 40_000
    assert threshold_for_model("sonnet") == 40_000


def test_haiku_returns_30k():
    """Haiku 小模型衰减更快 → 阈值 30K (v0.9.0 不变)。"""
    assert threshold_for_model("claude-haiku-4-5") == 30_000
    assert threshold_for_model("haiku") == 30_000


def test_old_models_return_8k_backward_compat():
    """老模型 (GPT-3.5 / Claude-1.3 时代) 实际在 8K 衰减 — Liu 2023 数据。"""
    assert threshold_for_model("gpt-3.5-turbo") == 8_000
    assert threshold_for_model("claude-1.3") == 8_000
    assert threshold_for_model("claude-instant-1") == 8_000


def test_unknown_model_falls_back_to_40k():
    """未知模型 / None / 空 → 40K 默认 (v0.9.0 跟 sonnet 一致)。"""
    assert threshold_for_model(None) == DEFAULT_THRESHOLD
    assert threshold_for_model("") == DEFAULT_THRESHOLD
    assert threshold_for_model("unknown-model-2030") == DEFAULT_THRESHOLD
    assert DEFAULT_THRESHOLD == 40_000


def test_case_insensitive():
    """模型 ID 大小写不影响识别。"""
    assert threshold_for_model("CLAUDE-OPUS-4-7") == 60_000
    assert threshold_for_model("Sonnet-4-6") == 40_000


def test_keyword_priority_long_matches_first():
    """关键词顺序敏感 — opus / sonnet 先于潜在子串误命中。"""
    # 防御性：如果未来加 'son' 类短关键词，'sonnet' 不该被截断
    assert threshold_for_model("claude-sonnet-x") == 40_000


# v0.10.4: OpenAI / Codex 模型族阈值 — 用户研究 (2026-05-16) 后真发现 codex 用户
# 跟 Claude 共用 karma 但 gpt-5.5 等大 context 模型全 fallback 到 DEFAULT 40K
# 太密扰动表达. 加 11 条阈值精确适配.

def test_gpt_5_5_returns_120k_for_1m_context_window():
    """gpt-5.5 是 1,050,000 context window 旗舰 — 120K 节奏 (~12%)."""
    assert threshold_for_model("gpt-5.5") == 120_000


def test_gpt_5_4_returns_120k():
    """gpt-5.4 是 400K context 中段补 120K 节奏."""
    assert threshold_for_model("gpt-5.4") == 120_000


def test_gpt_5_3_codex_returns_80k():
    """gpt-5.3-codex 是 400K context Codex 旗舰 → 80K (跟 Opus 一致级别)."""
    assert threshold_for_model("gpt-5.3-codex") == 80_000


def test_gpt_5_4_mini_returns_40k():
    """gpt-5.4-mini 中型 → 40K (跟 Sonnet 同档)."""
    assert threshold_for_model("gpt-5.4-mini") == 40_000


def test_gpt_5_3_codex_spark_returns_30k():
    """gpt-5.3-codex-spark 小型 → 30K (跟 Haiku 同档)."""
    assert threshold_for_model("gpt-5.3-codex-spark") == 30_000


def test_gpt_5_4_nano_returns_30k():
    """gpt-5.4-nano 小型 → 30K."""
    assert threshold_for_model("gpt-5.4-nano") == 30_000


def test_codex_mini_returns_30k():
    """codex-mini 小型 → 30K."""
    assert threshold_for_model("codex-mini") == 30_000


def test_gpt_5_1_codex_max_returns_80k():
    """gpt-5.1-codex-max → 80K."""
    assert threshold_for_model("gpt-5.1-codex-max") == 80_000


def test_gpt_5_1_codex_mini_returns_40k():
    """gpt-5.1-codex-mini → 40K (mini 中型档不是 nano)."""
    assert threshold_for_model("gpt-5.1-codex-mini") == 40_000


def test_gpt_5_generic_returns_80k_as_fallback():
    """gpt-5 (没具体子版本) → 80K 兜底, 别 fallback 到 DEFAULT 40K."""
    assert threshold_for_model("gpt-5") == 80_000


def test_codex_keyword_priority_long_matches_first():
    """关键词顺序敏感 — gpt-5.3-codex-spark 必须在 gpt-5.3-codex 前匹配,
    gpt-5.4-mini/nano 必须在 gpt-5.4 前匹配, 避免短串误命中 120K 大模型阈值."""
    assert threshold_for_model("gpt-5.3-codex-spark") == 30_000  # 不是 80K
    assert threshold_for_model("gpt-5.4-mini") == 40_000  # 不是 120K
    assert threshold_for_model("gpt-5.4-nano") == 30_000  # 不是 120K
    assert threshold_for_model("gpt-5.1-codex-mini") == 40_000  # 不是 80K


def test_model_from_payload_prefers_payload_model():
    """v0.10.4 model_from_payload — payload.model 优先 transcript fallback.

    Codex 官方文档明确说每个 hook stdin 含 model 字段是 active model slug,
    transcript_path 不是稳定 hook 接口. 所以优先 payload.model.
    """
    from karma.model_threshold import model_from_payload
    # payload 含 model → 直接用, 不读 transcript (即便 transcript_path 是坏路径)
    assert model_from_payload(
        {"model": "gpt-5.5", "transcript_path": "/nonexistent/bad"}
    ) == "gpt-5.5"
    # payload 含 model 但无 transcript_path → 仍工作
    assert model_from_payload({"model": "gpt-5.4-mini"}) == "gpt-5.4-mini"


def test_model_from_payload_falls_back_to_transcript_when_no_model_field(tmp_path):
    """Claude payload (除 SessionStart) 没 model 字段 → 走 transcript fallback."""
    from karma.model_threshold import model_from_payload
    # 写一条假 transcript jsonl 含 model
    transcript = tmp_path / "fake_transcript.jsonl"
    transcript.write_text(
        '{"type":"assistant","message":{"model":"claude-opus-4-7","content":[]}}\n',
        encoding="utf-8",
    )
    assert model_from_payload(
        {"transcript_path": str(transcript)}
    ) == "claude-opus-4-7"


def test_model_from_payload_skips_synthetic_model_value():
    """model='<synthetic>' (Claude 内部生成 message) 不算真 model → fallback transcript."""
    from karma.model_threshold import model_from_payload
    assert model_from_payload({"model": "<synthetic>"}) is None
    assert model_from_payload({"model": ""}) is None
    assert model_from_payload({}) is None


def test_model_from_payload_empty_payload_returns_none():
    """完全空 payload → None (不抛)."""
    from karma.model_threshold import model_from_payload
    assert model_from_payload({}) is None
