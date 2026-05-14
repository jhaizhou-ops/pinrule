"""按当前 Agent 模型决定中段 sticky 注入阈值（v0.4.35 自动适配）。

设计意图（用户 v0.4.35 决策驱动）：

中段 sticky 注入是「抵御 attention 衰减区入口前重新锚定」补丁。但不同模型
真衰减区入口差几倍 — 用一刀切阈值（v0.4.32 的 8K）要么对大模型太密扰动表达，
要么对小模型太稀已衰减才提醒。

真当代 Claude 衰减区入口（基于 Anthropic 公开 + RULER/MRCR/NIAH benchmark
2026 数据）：

- Opus 4.x：~70K-100K → 阈值 80K
- Sonnet 4.x：~50K-70K  → 阈值 60K
- Haiku 4.x：~20K-40K   → 阈值 30K
- 老模型 (GPT-3.5 / Claude-1.3 时代)：8K → 阈值 8K（Liu 2023 真数据）
- 未知模型 fallback：60K（按用户「至少 60K」要求保守 — 不至于太密）

特别场景：子 Agent 经常用 Sonnet/Haiku 跑长任务而主 Agent 用 Opus，karma
v0.4.34 子 Agent 独立 state 架构 + 本模块按当前模型阈值真合一 — 各自按真
衰减区独立刷新。
"""

from __future__ import annotations

# 模型衰减区入口阈值表（token，按 attention 真衰减区入口贴近）
# 关键词匹配（不区分大小写）— 模型 ID 含关键词就用对应阈值
# 顺序敏感：先匹配长串避免 sonnet 被 son 误命中
_MODEL_THRESHOLDS: tuple[tuple[str, int], ...] = (
    ("opus", 80_000),
    ("sonnet", 60_000),
    ("haiku", 30_000),
    # 老模型识别（向后兼容 — 老模型真在 8K 衰减）
    ("gpt-3.5", 8_000),
    ("claude-1", 8_000),
    ("claude-2", 16_000),
    ("claude-instant", 8_000),
)

# 未知模型 fallback — 按用户「至少 60K」要求保守
DEFAULT_THRESHOLD = 60_000


def threshold_for_model(model: str | None) -> int:
    """按 model 字符串识别返回中段注入 token 阈值。

    model 例：'claude-opus-4-7' / 'claude-sonnet-4-6' / 'claude-haiku-4-5'。
    None / 空 / 不识别 → DEFAULT_THRESHOLD（60K）。
    """
    if not model:
        return DEFAULT_THRESHOLD
    m = model.lower()
    for keyword, threshold in _MODEL_THRESHOLDS:
        if keyword in m:
            return threshold
    return DEFAULT_THRESHOLD
