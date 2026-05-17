#!/usr/bin/env python3
"""pinrule 性能真测脚本 — 跑在你本机出你这台机的真实数字.

用法:
    source .venv/bin/activate
    python scripts/measure_perf.py

会测:
  1. Claude / Codex / Cursor 三家 wrapper 端到端 wall-clock latency
     (UserPromptSubmit + PreToolUse, n=50 次/wrapper).
  2. Anchor 注入字符数 / 典型 turn 字符数 (=token 占比 ballpark).
     基于当前 rules.yaml + 典型 800 字 user prompt + 3000 字 agent reply.

复现 README "Performance" 段 ~50-70ms / ~2% token 这些数字的开源方法.
没装的 backend 显示 "未装" 跳过, 没冲突.
"""
from __future__ import annotations

import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from pinrule.rule import format_anchor_only, load as load_rules  # noqa: E402

N_SAMPLES = 50
TYPICAL_USER_CHARS = 800
TYPICAL_AGENT_CHARS = 3000
TYPICAL_TURN_CHARS = TYPICAL_USER_CHARS + TYPICAL_AGENT_CHARS


def measure_hook_ms(wrapper: Path, payload: dict, n: int = N_SAMPLES) -> list[float]:
    """n 次执行 wrapper 返回每次 ms."""
    payload_bytes = json.dumps(payload).encode("utf-8")
    samples = []
    for _ in range(n):
        t0 = time.perf_counter()
        subprocess.run(
            [sys.executable, str(wrapper)],
            input=payload_bytes,
            capture_output=True,
            timeout=5,
        )
        samples.append((time.perf_counter() - t0) * 1000)
    return samples


def fmt_stats(samples: list[float]) -> str:
    p50 = statistics.median(samples)
    avg = statistics.mean(samples)
    p95 = statistics.quantiles(samples, n=20)[18] if len(samples) >= 20 else max(samples)
    return f"p50={p50:5.1f}  avg={avg:5.1f}  p95={p95:5.1f}"


def measure_latency() -> None:
    print("=" * 70)
    print(f"# Hook 端到端 latency (ms, n={N_SAMPLES} 次/wrapper)")
    print("=" * 70)
    print()
    print(f"{'backend':10}  {'status':10}  {'UserPromptSubmit':30}  {'PreToolUse':30}")
    print("-" * 90)
    backends = [
        ("Claude", Path.home() / ".claude" / "hooks"),
        ("Codex", Path.home() / ".codex" / "hooks"),
        ("Cursor", Path.home() / ".cursor" / "hooks"),
    ]
    ups_payload = {"session_id": "perf-test", "prompt": "你好测试一下"}
    ptu_payload = {
        "session_id": "perf-test",
        "tool_name": "Bash",
        "tool_input": {"command": "ls"},
    }
    for name, hooks_dir in backends:
        if not hooks_dir.exists():
            print(f"{name:10}  {'未装':10}  {'-':30}  {'-':30}")
            continue
        ups_wrapper = hooks_dir / "pinrule_user_prompt_submit.py"
        ptu_wrapper = hooks_dir / "pinrule_pre_tool_use.py"
        if not ups_wrapper.exists():
            print(f"{name:10}  {'wrapper 缺':10}  {'-':30}  {'-':30}")
            continue
        ups_ms = measure_hook_ms(ups_wrapper, ups_payload)
        ptu_str = (
            fmt_stats(measure_hook_ms(ptu_wrapper, ptu_payload))
            if ptu_wrapper.exists()
            else "-"
        )
        print(f"{name:10}  {'✓':10}  {fmt_stats(ups_ms):30}  {ptu_str:30}")
    print()


def measure_token_overhead() -> None:
    print("=" * 70)
    print("# Anchor token 占比 ballpark")
    print(f"  (典型 turn = {TYPICAL_USER_CHARS} 字 user + {TYPICAL_AGENT_CHARS} 字 agent)")
    print("=" * 70)
    print()
    rules = load_rules()
    if not rules:
        print("(rules.yaml 没规则 — 跑 `pinrule init` 装 example 规则后再测)")
        return
    rule_ids = [r.id for r in rules]
    print(f"  当前 rules.yaml 装了 {len(rules)} 条规则: {', '.join(rule_ids[:3])}...")
    print()
    print(f"{'violated_count':18}  {'anchor 字符':12}  {'占典型 turn':14}  {'场景':30}")
    print("-" * 80)
    for k, scene in [
        (0, "无累积违反 (~60% 工作 session)"),
        (1, "median dogfood 场景"),
        (3, "重 drift session"),
        (len(rules), "全 fire (理论上限)"),
    ]:
        violated = set(rule_ids[:k])
        anchor = format_anchor_only(rules, violated)
        chars = len(anchor)
        pct = chars / TYPICAL_TURN_CHARS * 100
        print(f"{k:18}  {chars:12}  {pct:13.1f}%  {scene:30}")
    print()
    print("  注: Anthropic prompt-cache hit 时 token cost 折 ~10x (10% rate).")
    print("      median session ~1 违反 + 高 cache hit → 真实 ~2% overhead.")
    print()


if __name__ == "__main__":
    measure_latency()
    measure_token_overhead()
