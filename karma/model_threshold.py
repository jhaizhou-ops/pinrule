"""按当前 Agent 模型决定中段 sticky 注入阈值（v0.4.35 自动适配）。

设计意图（用户 v0.4.35 决策驱动）：

中段 sticky 注入是「抵御 attention 衰减区入口前重新锚定」补丁。但不同模型
衰减区入口差几倍 — 用一刀切阈值（v0.4.32 的 8K）要么对大模型太密扰动表达，
要么对小模型太稀已衰减才提醒。

当代 Claude 衰减区入口（基于 Anthropic 公开 + RULER/MRCR/NIAH benchmark
2026 数据）：

- Opus 4.x：~70K-100K → 阈值 80K
- Sonnet 4.x：~50K-70K  → 阈值 60K
- Haiku 4.x：~20K-40K   → 阈值 30K
- 老模型 (GPT-3.5 / Claude-1.3 时代)：8K → 阈值 8K（Liu 2023 数据）
- 未知模型 fallback：60K（按用户「至少 60K」要求保守 — 不至于太密）

特别场景：子 Agent 经常用 Sonnet/Haiku 跑长任务而主 Agent 用 Opus，karma
v0.4.34 子 Agent 独立 state 架构 + 本模块按当前模型阈值合一 — 各自按真
衰减区独立刷新。
"""

from __future__ import annotations

# 模型衰减区入口阈值表（token，按 attention 衰减区入口贴近）
# 关键词匹配（不区分大小写）— 模型 ID 含关键词就用对应阈值
# 顺序敏感：先匹配长串避免短串误命中（gpt-5.5 必须在 gpt-5 前 / sonnet 在 son 前）
#
# v0.9.0 调整：Claude 族从 80K / 60K / 30K 收紧到 60K / 40K / 30K
# v0.10.4 加入 OpenAI / Codex 模型族阈值（用户研究 + 官方 model spec
# context window 数据）— Codex 用户跟 Claude 用户共用同一套自适应阈值，
# karma 不再让 gpt-5.5 / gpt-5.4 这类 1M-context 大模型 fallback 到默认 40K
# （对 1M context 太密扰动表达）。
#
# 模型族阈值参考（基于 attention 衰减区入口 + 官方 context window）：
# - gpt-5.5 / gpt-5.4: 1,050,000 / 400,000 context → 120K 阈值（中段补 ~12% 节奏）
# - gpt-5.3-codex / gpt-5.2-codex / gpt-5.1-codex-max: 400K context → 80K
# - gpt-5.4-mini / gpt-5.1-codex-mini: 中型 → 40K
# - gpt-5.4-nano / gpt-5.3-codex-spark / codex-mini: 小型 → 30K
_MODEL_THRESHOLDS: tuple[tuple[str, int], ...] = (
    # OpenAI / Codex 族 — 长串在前避免短串误命中
    ("gpt-5.5", 120_000),
    ("gpt-5.4-mini", 40_000),
    ("gpt-5.4-nano", 30_000),
    ("gpt-5.4", 120_000),
    ("gpt-5.3-codex-spark", 30_000),
    ("gpt-5.3-codex", 80_000),
    ("gpt-5.2-codex", 80_000),
    ("gpt-5.1-codex-max", 80_000),
    ("gpt-5.1-codex-mini", 40_000),
    ("codex-mini", 30_000),
    ("gpt-5", 80_000),  # gpt-5.x 系列兜底（在 5.5/5.4/5.3/5.1 之后才命中）
    # Claude 族
    ("opus", 60_000),
    ("sonnet", 40_000),
    ("haiku", 30_000),
    # 老模型识别（向后兼容 — 老模型实际在 8K 衰减）
    ("gpt-3.5", 8_000),
    ("claude-1", 8_000),
    ("claude-2", 16_000),
    ("claude-instant", 8_000),
)

# 未知模型 fallback — v0.9.0 跟 sonnet 一致 40K
DEFAULT_THRESHOLD = 40_000


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


def model_from_payload(payload: dict) -> str | None:
    """v0.10.4 统一 model 解析 — payload.model 优先, transcript_path fallback.

    设计动机:

    Codex 官方 hook docs (https://developers.openai.com/codex/hooks) 明确说每个
    command hook stdin 都有 `model` 字段 (active model slug) — 而 `transcript_path`
    虽然也在 payload 里但 transcript 格式不是稳定 hook 接口. 所以 Codex backend
    应该**优先用 payload.model**, transcript 反扫只作 fallback (主要给 Claude Code
    用 — Claude SessionStart 之外的 event 没 model 字段, 只能反扫 transcript jsonl).

    Claude Code 行为不变: payload.model 大概率没有 (除 SessionStart), 自然走
    transcript fallback — 跟 v0.4.39 之后路径一致.
    Codex 行为升级: payload.model 直接拿到, 不依赖 transcript 格式稳定性.
    `/model` 中途切换也立刻被识别 (codex 每个 hook payload 都刷新 model 字段).

    跳过 `<synthetic>` 跟 extract_model_from_transcript 一致（Claude Code 内部
    生成的注入 message，不是真 model）.
    """
    model = payload.get("model")
    if isinstance(model, str) and model and model != "<synthetic>":
        return model
    return extract_model_from_transcript(payload.get("transcript_path"))


def extract_model_from_transcript(transcript_path: str | None) -> str | None:
    """v0.4.39 根本本路径：从 hook payload.transcript_path 读 jsonl 找当前 model。

    Hook payload 协议层 limitation：SessionStart 才直接含 model 字段，
    PreToolUse / PostToolUse / user_prompt_submit / SubagentStart / SubagentStop
    都没 model 字段（manual run 验证）。但**所有 hook payload 有
    transcript_path 字段** — Claude Code 把对话历史完整存 jsonl，每条
    assistant message 含 model 字段。

    karma 路径：reverse scan transcript jsonl 找最后一条非合成 model 字面。
    跳过 `<synthetic>`（Claude Code 内部生成的注入 message，不是真 model）。

    返回 None 时 fallback DEFAULT_THRESHOLD 60K（保守，向前兼容）。
    """
    if not transcript_path:
        return None
    try:
        from pathlib import Path
        p = Path(transcript_path)
        if not p.exists():
            return None
        # reverse scan jsonl 找最后一条真 model（性能：长 session 可能几 MB，
        # 全文 read + reverse iter 是简单方案；优化版可用 tail seek 但当前
        # 文件大小（典型 < 10 MB）真不是瓶颈）
        import re
        # 性能保守：用 regex 扫 raw 内容比逐行 json.parse 快 10x
        content = p.read_text(encoding="utf-8", errors="ignore")
        # 找所有 "model":"xxx" 字面 — reverse 取最后一个非 <synthetic>
        matches = re.findall(r'"model"\s*:\s*"([^"]+)"', content)
        for m in reversed(matches):
            if m and m != "<synthetic>":
                return m
    except Exception:
        return None
    return None
