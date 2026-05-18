# pinrule Evaluation — Performance Measurement Methodology

**[🇬🇧 English (current)](./EVALUATION.md) · [🇨🇳 中文](./EVALUATION.zh.md)**

Methodology behind the performance claims in README.

---

## Hook latency: ~50-70ms typical

### What's measured

The end-to-end time from the AI client invoking the hook subprocess to pinrule emitting its hook output JSON. Includes:

- Python interpreter cold start (largest single factor — Python 3.11/3.12)
- `pinrule` package import + rule loading from `~/.pinrule/rules.yaml`
- Hook handler dispatch
- Engine check + state update + stdout write

### How to reproduce

```bash
python scripts/measure_perf.py
```

Outputs per-hook median + p95 latency across 100 runs.

### Why "~50-70ms" instead of one number

Latency varies by machine:

- Apple M-series Mac: ~49ms median
- Lower-end Linux box (reported by community): ~67ms
- Older Intel Mac: ~80-100ms

The protocol budget is 200ms; pinrule sits well under that on every machine measured so far.

---

## Token overhead: ~2% of conversation context

### What's measured

The fraction of total conversation tokens (input + output) that pinrule injects into the model's context per turn. This includes:

- `SessionStart` hook: full rule baseline injected once per session (~1.8K tokens for the default 7-rule template, one-time cost)
- `UserPromptSubmit` hook: per-turn compact anchor (~490 tokens average, often **0 tokens** when no rule drifted in the previous response — see "0-anchor passthrough" below)
- `PostToolUse` hook: full reinject on long-context decay, fires only when accumulated context hits the model's decay threshold (Opus 60K / Sonnet 40K / Haiku 30K)

The 2% is **(pinrule injected tokens) / (total conversation tokens)** averaged across 30 real work sessions during pinrule's own development.

### Anchor token distribution across 30 measured sessions

- **60% of sessions: 0 anchor tokens** — no rule drifted in any response, so per-turn anchor is empty (just the `[pinrule reminder]` header line)
- **Median session: 1 rule listed in anchor** (~60 tokens)
- **Worst-case session: 4 rules + drift markers** (~280 tokens per turn)

The 0-anchor passthrough is what makes the average low — most working turns don't trigger any rule, so the per-turn cost is essentially zero. Only when the Agent actually drifts does the next turn's anchor list the drifted rule.

### How the numbers were measured

These figures come from the author's own dogfood during pinrule development — 30 working sessions over ~2 weeks, hand-counted from `~/.pinrule/session-state/*.json` (each file records `tool_byte_seq` accumulation, drift events, reinject triggers) and Claude Code's conversation logs.

**There is no `pinrule audit --token-ratio` helper yet** — automating this is on the roadmap but no user has asked for it, so it stays manual. If you want to measure your own data, the inputs are:

- `~/.pinrule/session-state/<session_id>.json` — per-session pinrule state (read/edit files, byte accumulation, reinject marks)
- Your AI client's conversation log — authoritative source for total token count, since pinrule doesn't track that

If you measure your own ratio and want a reproducible script for it, [file an Issue](https://github.com/jhaizhou-ops/pinrule/issues) — that's the trigger to actually build the helper.

---

## Caveats

- **Methodology is dogfood-internal**, not a peer-reviewed benchmark. Numbers come from the author's own 30-session sample during development; user mileage will vary by:
  - rule count (more rules → bigger baseline + bigger anchor when rules drift)
  - drift rate (Agent drifts more often → bigger per-turn anchor)
  - session length (longer session → more chance to hit decay threshold)
- **No client-side overhead measurement yet** — the AI client itself (Claude / Codex / Cursor) adds latency for spawning the hook subprocess and reading its stdout; pinrule's `scripts/measure_perf.py` measures pinrule's part only.
- **Token overhead doesn't include AI-client-side compression** — if your client compresses long history before sending to the model, the actual prompt size is smaller than what pinrule injected.

If you measure your own pinrule session and the numbers diverge meaningfully from this doc, that's interesting — please share via Issue.
