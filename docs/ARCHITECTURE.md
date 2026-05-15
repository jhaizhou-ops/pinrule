# karma Technical Architecture (M3 current state)

**[🇬🇧 English (current)](./ARCHITECTURE.md) · [🇨🇳 中文](./ARCHITECTURE.zh.md)**

## Overview

```
┌───────────────────────────────────────────────────────────┐
│  ~/.claude/karma/                                         │
│  ├── rules.yaml              ← User-maintained core rules │
│  ├── violations.jsonl        ← Violation history (auto-rotation at 5000 lines)│
│  └── session-state/          ← One json per session (auto-cleanup 30 days)│
│      └── {session_id}.json   ← read_files / edit_files /  │
│                                  recent_bash / last_test_pass_ts / │
│                                  pending_bg_tasks ...     │
└───────────────────────────────────────────────────────────┘
                       │ read / write
                       ▼
┌───────────────────────────────────────────────────────────┐
│  Claude Code hooks (~/.claude/hooks/)                     │
│  ├── karma_user_prompt_submit.py   ← Inject rules per msg │
│  ├── karma_pre_tool_use.py         ← Real-time intercept  │
│  ├── karma_post_tool_use.py        ← State tracking       │
│  └── karma_stop.py                 ← Scan violations      │
└───────────────────────────────────────────────────────────┘
                       │
                       │ additionalContext / permissionDecision
                       ▼
              ┌─────────────────────┐
              │   Claude Code       │
              │   (Agent loop)      │
              └─────────────────────┘
```

## Data model

### rules.yaml (user-maintained)

```yaml
- id: long-term-fundamental         # kebab-case slug, used by CLI
  preference: |                     # multi-line allowed; this is what Claude sees
    Use the most fundamental, long-term, universal, elegant solution.
    No patches, no hardcoding, no sacrificing long-term quality for short-term KPIs.
  violation_keywords:               # keyword array (any match = violation)
    - I'll patch this quickly
    - hardcoded
    - temporary solution
  violation_checks:                 # engine-layer check function names (precise patterns)
    - long_term_fundamental
```

Fields:
- `id` — kebab-case short slug, unique
- `preference` — one or multi-line direction description
- `violation_keywords` — keyword array (case-insensitive, substring match)
- `violation_checks` — function names from `karma/checks/__init__.py:REGISTRY`

Soft cap 10, hard cap 12 (hook refuses to load if exceeded, prevents attention dilution).

### violations.jsonl

```jsonl
{"ts":1715617200,"session_id":"abc","rule_id":"long-term-fundamental","trigger":"hardcoded","snippet":"...hardcoded this value..."}
{"ts":1715617250,"session_id":"abc","rule_id":"non-blocking-parallel","trigger":"Bash sleep cmd: 'sleep 30'","snippet":"sleep 30 && echo done"}
```

Append-only; auto-rotation when line count exceeds 5000 (`.1` `.2` `.3` keeps 3 history files, oldest deleted). Old `sticky_id` field still readable for backward compat (v0.5.0+).

### session-state/{session_id}.json

```json
{
  "session_id": "abc",
  "read_files": ["/x/a.py", "/x/b.py"],
  "edit_files": ["/x/a.py"],
  "recent_bash": [
    {"ts":..., "command_summary":"pytest tests/", "is_test_cmd":true, "output_passed":true, "output_failed":false}
  ],
  "last_test_pass_ts": 1715617200.5,
  "last_edit_ts": 1715617100.3,
  "pending_bg_tasks": [
    {"cmd":"pytest > log.txt 2>&1","output_file":"/tmp/log.txt","started_ts":...}
  ]
}
```

Cross-hook shared state:
- `read_files / edit_files` — for read_first detection (Write/NotebookEdit auto-records read)
- `recent_bash` — Bash history summary (PASS/FAIL signals + test command detection)
- `last_test_pass_ts vs last_edit_ts` — `has_recent_test_pass()` uses: "tests run and passed since most recent code change"
- `pending_bg_tasks` — recorded when background task starts; next hook trigger reads output_file via `catchup_pending_bg`

Files untouched for 30 days auto-cleaned (user_prompt_submit hook runs purge each turn). Save uses `{stem}.{pid}.{ns}.json.tmp` + atomic rename; concurrent writes don't conflict.

## 4 Hooks (Claude Code standard protocol)

### UserPromptSubmit hook

Timing: User sends message → before model sees it.

Input stdin payload (Claude Code protocol):
```json
{"prompt": "...", "session_id": "abc", "transcript_path": "...", "cwd": "..."}
```

Output stdout:
```json
{"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": "...rule injection..."}}
```

Implementation: `karma/hooks/user_prompt_submit.py`
- Load rules.yaml
- Read violations.jsonl by turn-distance to get recently-violated rule_ids (mark with 〔drift〕)
- Format as `[karma — Your long-term agreement with the user]` + numbered rules
- Also runs `purge_old_states` + `catchup_pending_bg` (exceptions swallowed, non-blocking)
- **Strong reminder fallback** (key mechanism): read transcript for last assistant message → run all rules' violation_checks → hits + suggested_fix inject as "strong reminder" section. Covers keep-pushing / chinese-plain / evidence response-class checks. This is the post-fix fallback for "Stop hook may not run when user immediately submits next prompt" scenarios (Stop hook also runs when correctly configured — matcher fix verified 5 real session triggers in trace).

Performance: < 60ms.

### PreToolUse hook (real-time interception, most critical layer)

Timing: Agent decides to call tool, **before execution**.

Input stdin payload:
```json
{"tool_name": "Bash", "tool_input": {"command": "sleep 30"}, "session_id": "abc", ...}
```

Output stdout (allow):
```json
{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}}
```

Output stdout (deny):
```json
{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "..."}}
```

Implementation: `karma/hooks/pre_tool_use.py`

Two-layer detection:
1. **Engine layer** — runs rule's `violation_checks` function set (precise regex patterns)
2. **Keyword layer (fallback)** — scan Bash command skeleton (strip quoted literals + heredoc smart strip) + Write/Edit comments + docstrings

Engine layer prioritized (more precise); hit → deny. Fail-open principle (config error / payload parse failure → allow, doesn't block Agent).

Performance: < 100ms.

### PostToolUse hook (state tracking + catchup)

Timing: After tool call completes.

Input stdin payload:
```json
{"tool_name": "Bash", "tool_input": {...}, "tool_response": {"stdout": "...", "stderr": "...", "backgroundTaskId": "..."}, "session_id": "abc"}
```

Implementation: `karma/hooks/post_tool_use.py`

Main logic:
1. First runs `state.catchup_pending_bg()` — reads previous-turn background task log to integrate pass evidence
2. Checks `_tool_failed(tool_response)` (dict `isError`/`interrupted` or string prefix)
3. Successful Read → `record_read`; Successful Write/NotebookEdit → `record_edit + record_read`; Successful Edit → `record_edit`; Bash always records (PASS/FAIL internally judged)
4. Failed tools don't record (prevents Read failure from also record_read bypassing read_first)

Performance: < 30ms.

### Stop hook (response scan + real-time intervention)

Timing: Agent response complete (this turn ends).

Input stdin payload (**no** response field — must read transcript):
```json
{"session_id": "abc", "transcript_path": "/path/to/transcript.jsonl", "cwd": "..."}
```

Implementation: `karma/hooks/stop.py`
1. Read transcript_path JSONL, find last `type=assistant` and take all text content
2. Scan violation_keywords (keyword layer) + engine-layer violation_checks (chinese_plain / evidence / keep_pushing primarily here)
3. Hits write to `violations.jsonl` + stderr notify + desktop notify + cumulative alerts
4. **keep-pushing-no-stop hit → output `{"decision": "block", "reason": "..."}`** to keep Agent from immediately stopping (intervenes rule #7 "don't auto-stop"). Safeguard: cumulative block ≥ N within single turn (`stop_block_max_per_turn` default 2) → let Agent stop, prevents loops
5. Otherwise outputs passthrough (Stop hook doesn't support `hookSpecificOutput` per Claude Code protocol — fixed in v0.4.43)

Performance: < 200ms.

**⚠️ Stop hook config note**: Stop / SessionStart / SessionEnd etc. **don't support `matcher` field** — Claude Code silently ignores entire hook entry if matcher present. `karma install-hooks` fixed this: Stop entry has no matcher; PreToolUse/PostToolUse/UserPromptSubmit do. If `/tmp/karma_stop_trace.log` has 0 entries for real sessions, check `~/.claude/settings.json` Stop entry for matcher field.

## 8 violation_check functions (engine-layer precise detection)

`karma/checks/__init__.py:REGISTRY` maps rules.yaml's `violation_checks` strings → functions:

| check name | rule | Detects |
|---|---|---|
| `long_term_fundamental` | long-term solutions | Long-hash if branches / blacklist-whitelist literals / all-caps constant lists / TODO actual comments / intent literal comments / commit message hack words |
| `non_blocking_parallel` | non-blocking | sleep / wait / long tasks without background / indirect shell execution |
| `chinese_plain_no_jargon` | plain Chinese | Chinese ratio (denominator strips dotted engineering identifiers / path literals / commit message quote blocks) + jargon detection (strip code blocks / inline code) + same-prefix-char ≥ 5/response triggers self-check (whitelist exemptions: 一/不/是/有/没/我/你/他/这/那/在) |
| `loud_failure_with_evidence` | completion evidence | Completion words / weak claims in code-task context + no test evidence |
| `no_testset_no_future_leakage` | no testset feedback | gold_cases backfeeding / cross-split copying / long hashes in comparison or assignment positions |
| `read_before_write` | read before write | Edit/Write before Read on same file_path (new file Write exempt) |
| `keep_pushing_no_stop` | no silent stop | Priority: 0) **user prompt contains stop-words** (no need / let's rest / tomorrow / etc.) → exempt entire turn (highest priority); 1) response-tail 80-char push signal (I'll now/next + verb) → exempt; 2) question mark → exempt (reasonable decision-seeking encouraged); 3) pause-tone words (next time / let's stop / wrap up) → hit; 4) default hit (pure statement-ending with no push/no question) |
| `bypass_karma_detection` | no bypass | Bash command contains karma internal literals (last_test_pass_ts / pending_bg_tasks / session-state json paths) + write operations → "bypass karma" hit. Exemptions: karma official CLI / read-only inspection / commit message quoted literals (post-strip skeleton doesn't contain sensitive literals) |

Each check function signature: `def check(*, tool_name, tool_input, response, session_state, **_) -> CheckHit | None`.

Returns `None` = no violation; `CheckHit(rule_id, trigger, snippet, suggested_fix)` = violation hit.

## Shared helpers (`karma/checks/common.py`)

Shared across check functions + hooks:

- `extract_tool_text(tool_name, tool_input)` — Different tools extract different fields (Bash.command / Write.content / Edit.new_string)
- `strip_code_blocks(text)` — Strip markdown ``` code blocks + ` inline code
- `strip_shell_quoted_literals(cmd)` — Strip shell `'...'` `"..."` quoted literals + heredoc smart strip (distinguishes head-command bash/sh keep-scan vs. python/cat strip) + indirect shell (`bash -c '...'` inside keep-scan)
- `extract_natural_language(content, file_path)` — Extract code comment lines (# / // / --) + docstrings (""" ''' /* */)

## Unified description-context exemption (`karma/checks/description_context.py`)

`is_description_context(tool_name, tool_input) → (bool, reason)`:

| Dimension | Judgment |
|---|---|
| Doc suffix | `.md` / `.rst` / `.txt` / `.markdown` / `.adoc` |
| Test directory | path contains `tests/` `test/` `__tests__` `spec` |
| Test filenames | `test_*.py` / `*_test.py` / `*_test.go` etc. |
| Temp probes | `/tmp/` / `/var/tmp/` paths |
| Probe/sample naming | filename contains `probe / scratch / sample / playground / fixture` |

Hit = full exemption from engine-layer `long_term` / `testset` + keyword layer (keyword layer for Write/Edit also calls this).

## CLI tools (`karma/cli.py`)

```bash
# Initialize
karma init                       # Create ~/.claude/karma/ + copy rule templates

# Rule management
karma rule list                  # List all rules
karma rule edit                  # Open rules.yaml with $EDITOR
karma rule remove <id>           # Remove one
# Legacy alias (deprecated, removed v0.6.0): karma sticky list/edit/remove

# Observation
karma stats                      # Per-rule violation stats
karma violations recent [N]      # Recent N violation details
karma violations clear           # Clear violation history (confirmation required)

# Installation
karma install-hooks              # Generate wrapper + auto-write settings.json (Claude Code 8 events)
karma uninstall-hooks            # Delete wrapper + clean karma entries from settings.json
karma doctor                     # Check environment + all hook install status (Claude Code 8)
```

`install-hooks` key features:
- Idempotent — multiple runs produce same result
- First run backs up `settings.json` to `settings.json.before-karma`
- Preserves all non-karma hooks (vibe-island / rtk / codex-review etc. coexist)
- Uses wrapper paths with `karma_` prefix to identify karma entries

## Configuration

`~/.claude/karma/config.yaml` adjusts thresholds without modifying code. `karma doctor` shows current effective values. All missing fields use `karma/config.py:DEFAULTS` (fail open); you can configure only the fields you care about.

| Field | Default | Meaning |
|---|---|---|
| `notify_enabled` | `true` | Desktop notification toggle (also `KARMA_NO_NOTIFY=1` env var) |
| `recent_violation_turns` | `5` | Drift marker window — rules violated in last N turns marked at next injection |
| `escalate_window_turns` | `3` | Cumulative alert window (by turn distance) |
| `escalate_threshold` | `3` | Cumulative alert count threshold — same rule hit ≥ N times in window → 🚨 severe notification |
| `stop_block_max_per_turn` | `2` | Stop hook `decision=block` cap per turn (prevents keep-pushing intervention loops). `0` disables intervention entirely |
| `force_block_threshold` | `5` | Cumulative force-block threshold — same rule violated ≥ N times in window → Stop hook outputs `decision=block` forcing root-cause fix. `0` disables. Can be exempted per-rule with `force_block_exempt: true` |
| `violations_max_lines` | `5000` | `violations.jsonl` line cap triggering rotation |
| `violations_keep_history` | `3` | rotation history files retained |
| `session_state_max_age_days` | `30` | `session-state/*.json` auto-cleanup period (days) |
| `max_recent_bash` | `15` | `SessionState` recent Bash count to retain |

`karma init` copies `data/config.example.yaml` template.

### Debug environment variables

- `KARMA_NO_NOTIFY=1` — Disable desktop notifications (CI / mute scenarios)
- `KARMA_DEBUG=1` — `run_checks` exceptions print traceback to stderr (debug custom checks)
- `KARMA_DEBUG_TRACE=<path>` — Append trace line to file when Stop hook fires (verify Stop hook actually triggers; production keeps disabled)

## State directory path (`KARMA_HOME` env var)

karma state defaults to `~/.claude/karma/` (contains `rules.yaml` / `violations.jsonl` / `session-state/` / `config.yaml`). The `KARMA_HOME` env var changes the path — useful for dry-run / CI / multi-profile isolation:

```bash
KARMA_HOME=/tmp/karma-test karma init           # Doesn't touch ~/.claude/karma/
KARMA_HOME=~/karma-profile-A karma rule list    # Multi-profile isolation
```

Note: paths freeze at module-level constant import time, so `KARMA_HOME` must be set **before** launching the karma process. Hook-wrapper-invoked karma doesn't read this env (wrapper doesn't pass env), so actual usage primarily uses `~/.claude/karma/`.

Single source of truth: `karma/paths.py:karma_home()` — all 5 modules (rule / violations / session_state / config / cli) use it to read env.

## Performance budget

| Path | Budget | Measured |
|---|---|---|
| UserPromptSubmit | < 60ms | 5-15ms (yaml load + violations read 200 lines) |
| PreToolUse | < 100ms | 10-30ms (regex scan + check function set) |
| PostToolUse | < 30ms | 5-15ms (state write atomic rename) |
| Stop | < 200ms | 20-50ms (transcript reverse-scan for assistant + violation scan) |

Performance hasn't been a bottleneck — measured far below budget.

## Security / privacy

- All data local in `~/.claude/karma/`
- No data uploaded
- No LLM calls (karma v2 strictly no LLM, even v1+ won't introduce)
- Users can `rm -rf ~/.claude/karma/` anytime to clear state
- `karma uninstall-hooks` clean removal (deletes wrappers + cleans settings.json)

## v0 boundaries (explicitly excluded)

- ❌ Introducing LLM — all engineering (regex / counting / context judgment)
- ❌ Database — `violations.jsonl` + `session-state/*.json` text IO is enough
- ❌ Auto-distilling new rules — user-controlled
- ❌ retrieval / cosine / scene rule selection — 5-10 rules always-on
- ❌ Cross-platform support (v0.4+ supports Claude Code / Codex CLI / Gemini CLI)
- ❌ Web UI / TUI — CLI + $EDITOR is enough

## Delivered milestones

| Milestone | Status |
|---|---|
| M0 Skeleton + 4 docs | ✅ |
| M1 Rule loading + 2 hook prototypes + CLI skeleton | ✅ |
| M1.5 PreToolUse real-time interception | ✅ |
| M2 6 engine checks + session_state | ✅ |
| M2.1 Adapt to Claude Code real protocol | ✅ |
| M2.2 Long-term check by-tool grouping + doc exemption | ✅ |
| M3 1-6 waves comprehensive false-positive reduction + false-negative pairs + install automation + long-term quality + description context completeness + audit strictening | ✅ |
| v0.4.x v3 evolution (mid-injection / SessionStart baseline / PreCompact dump / SubagentStart+Stop / per-model adaptive thresholds / "collaborative agreement" tone refactor / hook schema strict compliance) | ✅ |
| v0.5.0 sticky → rule rename + backward-compat migration | ✅ |
| v0.5.1 `karma rule add` / `rule preview` CLI + Claude Code skill template for natural-language rule input | ✅ |
| v0.5.2 i18n MVP — `karma/i18n.py` + 5 hook injection paths switchable en/zh | ✅ |
| v0.5.3 + v0.5.4 i18n full coverage — 28 `suggested_fix` + 28 `CheckHit.trigger` strings tr()-driven | ✅ |
| v0.5.5 testset check `python -c` literal exemption (dogfood-found false positive) | ✅ |
| v0.5.6 `keep_pushing._PUSH_SIGNAL_RE` covers "next push point / next step is" planning phrases | ✅ |
| v0.5.7 `trigger_key` field on `CheckHit` + `Violation` — locale-agnostic `karma audit` grouping | ✅ |
| v0.5.8 + v0.5.9 Bash heredoc → description-context path exemption, lifted into `description_context.py` shared layer | ✅ |
| v0.5.10 `karma --help` lists `rule add` / `rule preview` subcommands (doc-only) | ✅ |
| v0.5.11 `skills/karma-rule.md` clarity audit — 5 gaps closed (anchor-vs-scope / overlap decision table / inline draft review / locale-aware tone / when-takes-effect) | ✅ |
| v0.5.12 `karma init` auto-installs `karma-rule` skill + new `karma install-skill [--force]` command | ✅ |
| v0.5.13 audit-driven dedup — shared `is_python_c_command` helper + 34 `.sticky_id` callsites → `.rule_id` + `karma doctor` reports skill status | ✅ |
| v0.5.14 skill teaches modify recipe via existing `remove + add` composition (no new CLI; user principle: don't grow surface area for rare flows) | ✅ |
| v0.5.15 v0.6.0 preparation — plan doc `docs/V0_6_0_PLAN.md` + internal 11+4 `from karma.sticky` import migration to `from karma.rule` so v0.6.0 can ship as pure deletion commit | ✅ |
| v0.5.16 `/karma <natural language>` skill actually works — first release; multi-backend install (Claude Code / Codex / Gemini) with Markdown → TOML format adaptation for Gemini commands path; v0.5.1-15 honest disclosure (wrong install path → skill never triggered before) | ✅ |
| v0.5.17 README narrative rewrite — `/karma <NL>` skill promoted to top-level section instead of patch-style mention; PRD F5 rewritten; ARCHITECTURE + HANDOFF synced to v0.5.16 reality | ✅ |
| v0.5.18 `bypass_karma` false-positive fix (dogfood-found) — redirect target must actually be a karma path to count as bypass, not just "command mentions karma path + any write op"; symmetric tightening for `has_internal` field-name dimension | ✅ |
| v0.5.19 `keep_pushing` Agent saturation exemption (dogfood-found) — strong "saturation declaration" phrases (`任务饱和` / `卡在 X` / `明天接力` etc.) exempt from the reflection nudge, paired with v0.4.41 user-stop exemption; soft stop phrases (`今天到此为止` / `就这样吧`) without saturation signal still blocked per v0.4.22 design | ✅ |
| v0.5.20 rule-10 self-audit follow-up — sync ARCHITECTURE + HANDOFF for v0.5.19 (caught by user-prompted self-audit; CHANGELOG had it but technical-archive docs lagged) | ✅ |
| **v0.6.0** ⚠️ BREAKING — Remove `karma.sticky` module, `.sticky_id` @property on `CheckHit`+`Violation`, `karma sticky` CLI subcommand, and `karma.rule`/`karma.cli` internal aliases (`Sticky` / `MAX_STICKY` / `StickyConfigError` / `EXAMPLE_STICKY*`). Data-compat shims (`sticky.yaml`→`rules.yaml` auto-migration, `violations.jsonl` `sticky_id` field fallback) stay permanently. Deprecation cycle: 18 v0.5.x releases. Pure-deletion commit — no logic refactor needed thanks to v0.5.13/15 internal cleanup. 5 deletion-lock tests added. | ✅ |
| v0.6.1 issue #1 real-user bug fix — `record_edit` exempts non-code paths (README / CHANGELOG / docs/ / .gitignore etc.) from pushing `last_edit_ts`, so `docker pytest` pass + edit README + git commit is no longer blocked by `loud-failure-with-evidence`. Real-test reproduced root cause was `last_edit_ts > last_test_pass_ts` after non-code edit, not regex layer as reporter initially diagnosed. | ✅ |
| v0.7.0 treat-root-cause refactor — rewrite "真X" defensive prefixes in karma source rule texts. User caught Agent stacking "真X" mimicry from karma's own rule injection headers (in-context mimicry). Reverted attempted `defensive_prefix_stacking` engine check (treat-symptom) in favor of cleaning the source. ~140 occurrences rewritten across rule templates + locale + user-facing docs. | ✅ |
| v0.7.1 deep "真X" cleanup follow-up — user pointed out v0.7.0's synonym substitution (`真→实际/确实`) wasn't enough; defensive modifier itself is unnecessary in most contexts. 10-phase perl pipeline across 100 files: 767 → 120 (84% reduction). 120 remaining are all legitimate (named concept 真字狂魔 / eval term 真阳 / engineering dualism 真阻塞 / test fixtures / natural collocations 真心 真话). Fixed doubled artifact `任务任务到饱和` bug. One batched commit per user directive. | ✅ |

Details in [CHANGELOG.md](../CHANGELOG.md) for per-release rationale; [HANDOFF.md](./HANDOFF.md) for internal context.

## Continuous observation = continuous development

User's own words: "We keep pushing — that IS the observation period." Every push has Claude running with karma installed; every commit goes through hook interception. M3 accumulated 30+ real violations; all 7-8 rules triggered.

karma isn't "develop first, observe later" — it's "development is dogfooding."
