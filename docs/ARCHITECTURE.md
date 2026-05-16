# karma Technical Architecture

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

## i18n system — two-way

karma has two i18n surfaces. Both follow the "data not code" philosophy.

### Speaking side: `karma/i18n.py` + `data/locales/{en,zh}.yaml`

What karma **says to the Agent** — hook injection text, suggested_fix strings, audit labels. `tr(key, **fmt)` lookup with `{placeholder}` interpolation, fail-open on missing keys. Locale resolution chain:

```
KARMA_LOCALE env > config.yaml `locale` field > auto-detect (chinese ratio) > en fallback
```

**Injection lifecycle (v0.9.0)** — speaking side coordinates 5 hook surfaces with sharply different token weights:

| Hook | Format | Tokens | Frequency |
|---|---|---|---|
| SessionStart | `format_for_injection` (full, ~1817) | ~1817 | once per session (incl. compact-restart) |
| UserPromptSubmit | `format_anchor_only` (id + first line, ~490) | ~490 | every turn |
| PostToolUse mid-reinject | `format_for_injection` (full) | ~1817 | session byte_seq accumulates to model threshold (Opus 60K / Sonnet 40K / Haiku 30K) |
| Stop hook strong reminder | violation hits + suggested_fix | ~135 / hit | on violation |
| SubagentStart | compact rule list | ~383 | per subagent spawn |

The 73% per-turn saving at UserPromptSubmit is the main reason v0.9.0 cuts 1M Opus session token use from 18.4% to 8.2%.

### Listening side: `karma/signals.py` + `data/signals/<name>/{zh,en}.{txt,yaml}` (v0.8.0 → v0.8.2)

What karma **listens for in dialogue** — detection phrases for `keep_pushing` / `evidence` checks. Two storage formats:

- **`.txt` flat phrases** (one per line, `#` comments): `user_stop_hints` / `agent_saturation` / `stop_hints` / `explicit_handoff` / `weak_claims` / `completion_words`
- **`.yaml` Cartesian DSL**: `push_signals` — `templates` with `{subject}` / `{verb}` placeholders + vocabulary lists + non-Cartesian `phrases`

All 7 detection signals are externalized. Loader (`compile_alternation()`) reads all language files in a signal directory, dedupes, unions, compiles to a single regex (long-phrase priority; `re.escape` for `.txt` literals; raw regex preserved for `.yaml` templates). Cross-language character sets don't overlap → no false matches.

**Adding a new language**: drop in `xx.txt` / `xx.yaml` per signal directory. Zero Python code, zero LLM in the loop.

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
| v0.7.2 remove `chinese_plain` Check 3 reactive monitor — source treated via v0.7.0+v0.7.1, monitor obsolete. Check 3 was v0.4.40's reactive treat-symptom hedge ("治症状不治根因" — own code comment said so). `karma audit` confirmed 0 triggers in 168 violations after root-cause cleanup. Same logic user applied to `defensive_prefix_stacking` in v0.7.0; v0.7.2 closes the parallel loop on the older symptom monitor. Removed: `_check_repeated_prefix()` + 2 locale keys + 2 dedicated tests. | ✅ |
| v0.7.3 hand-audit every GitHub-visible doc — user directive to read each file individually (33 markdowns reviewed, 22 touched, no batch find/replace). Removed marketing fluff ("≈ 0%" overclaim / "500+ hours real-world tuning") + cleared stale `sticky` command names that survived v0.6.0 + corrected hard-cap from 14 → 12 + dropped frozen "M3" / "v0.5.x" milestone tags + relabeled shipped plan docs as archive + rewrote outdated `HOOK_CONFIGURATION_GUIDE.md` (9 hooks listed including non-existent `PostCompact` → corrected to actual 8). Net −63 lines. | ✅ |
| v0.7.4 `keep_pushing` stop-hint covers "satisfied / confirmation" phrases — within-turn dogfood: after shipping v0.7.3, user said "感觉已经挺稳定了，不错不错" (satisfied stop signal), but the reflection hook still fired because `_USER_STOP_HINT_RE` only covered "tired / dismissive" phrases (`休息吧 / 算了 / 够了`). Per rule #7 treat-root: extended the regex with a second category — `不错不错 / 挺稳定 / 就这样吧 / 这就行 / 可以了 / OK 了` etc. Both categories now exempt the reflection hook. 7 new test fixtures including the literal user phrase that triggered this release. | ✅ |
| **v0.8.0 i18n signals — detection phrases externalized to `data/signals/<name>/{zh,en}.txt`**. User identified: until now, 5 detection regexes (`_USER_STOP_HINT_RE` / `_AGENT_SATURATION_RE` / `_STOP_HINT_RE` / `_EXPLICIT_USER_HANDOFF_RE` / `_WEAK_CLAIM_RE`) were Chinese-hardcoded; English users got false-positive `keep_pushing` nudges and missed `weak_claim` detection. New `karma/signals.py` loader reads all language files in a signal directory, dedupes, unions, compiles (long-phrase priority). Different languages' character sets don't overlap → no cross-language false matches. **Adding a new language = zero Python code, just one `.txt` per signal directory.** English coverage shipped for all 5 signals. 13 new signal unit tests + 4 English coverage tests in keep_pushing / evidence. `_PUSH_SIGNAL_RE` (Cartesian structure) deferred to v0.8.1. | ✅ |
| **v0.8.1 `push_signals` i18n via YAML DSL — Cartesian templates + word vocabularies + flat phrases**. v0.8.0's `.txt` flat-phrase format didn't fit `_PUSH_SIGNAL_RE`'s `主语 + 副词 + 动词` Cartesian structure. New `.yaml` schema: `templates` field with `{subject}` `{verb}` placeholders, `subjects` / `verbs` vocabulary lists for Cartesian expansion, plus `phrases` for non-Cartesian flat fallback. `karma/signals.py` adds `load_patterns()` + `_expand_yaml_signals()` (singular → plural placeholder resolution; raw-regex preservation from yaml templates while .txt phrases get `re.escape`). 1106 expanded phrases (zh + en combined). Historical `(?!\s*[吧行])` lookahead moved out of regex into `check()` post-processing as `_PUSHBACK_TAIL_RE` — yaml stays simple. **All 6 detection signals now i18n-externalized**; adding a new language = ~6 small files, zero Python. 6 new signals tests + 2 English push tests. | ✅ |
| **v0.8.2 code audit — dead code + naming consistency + bug fix**. User-requested audit pass. Tools clean (vulture / ruff) but manual grep found 3 dead-code items whose own comments said "removed in v0.6.0" but were never actually removed (`KARMA_RULE_SKILL_SRC`, `_claude_skills_dir`, `_install_karma_rule_skill`). Also broad `sticky` → `rule` naming cleanup that v0.6.0 BREAKING left behind: `cmd_sticky_*` → `cmd_rule_*`, `STICKY_PATH` → `RULES_PATH` (18 callsites), user-facing strings in `doctor` / `audit` / `violations clear` / `rule list` / 3 hook stderr outputs. Real bug found: `cmd_violations_clear` was reading `d.get("sticky_id")` directly, bypassing the v0.5.0+ rule_id/sticky_id compat shim — fixed via `extract_rule_id()` helper. i18n consistency: added `completion_words` signal (v0.8.0 missed it alongside `weak_claims`); **7 of 7 detection signals now i18n-externalized**. 3 new tests. | ✅ |
| **v0.8.3 internal refactor — long hook main split + cli.py import dedup**. `stop.py:main` 223→123 (3 helpers: `_emit_notifications`/`_handle_force_block`/`_handle_keep_pushing_block`), `user_prompt_submit.py:main` 159→68 (2 helpers: `_advance_turn_state`/`_build_strong_reminder`), `pre_tool_use.py:main` 128→90 (2 helpers deduping parallel deny logic). cli.py: 4 function-level duplicate imports removed; module-top now aliases `load as load_rules` + `format_for_injection` once; bare `load()` → `load_rules()` standardized at 3 callsites. 455/455 passing, 0 behavior change. | ✅ |
| **v0.8.4 v0.8.x cumulative doc sync + 1 dead-code v0.8.2 audit missed**. Stale "6 signals" counts in README / PRD / ARCHITECTURE (v0.8.0+v0.8.1 numbers; should be 7 after v0.8.2 added `completion_words`) all updated to 7. `karma/checks/__init__.py:run_checks()` had `sticky_id` parameter whose own comment said "v0.6.0 removed" but never was — 0 callers, removed parameter + the `rule_id or sticky_id` fallback line. 4th instance of the v0.8.2 "comment says removed but actually alive" dead-code pattern. 455/455 passing. | ✅ |
| **v0.8.5 3rd code review pass — 2 high-value cleanups + clean-state confirmation**. User-requested 3rd audit round. Tools clean (vulture/ruff/455 tests); manual audit found 2 high-value items: `rule.py:format_for_injection` function-level `from karma.i18n import tr` hoisted to module top (i18n is leaf module, no circular risk); `chinese_plain.py:L179` inline magic `< 30` extracted as `_JARGON_PAREN_MAX_DIST = 30` constant. Honestly skipped middle/low-value polish (cli.py 10 function-level imports — some serve test-mock friendliness; 4 cli long functions — coordinators with no dead code). Doc consistency audit: test count 455 + signal count 7 + 0 dead links across 16 key docs. v0.8.x series ends in 3-way-confirmed clean state. | ✅ |
| **v0.8.6 `agent_saturation` bare-phrase coverage — within-turn dogfood**. v0.8.5 release notes used "真饱和" and "optimization for its own sake" — both legitimate saturation declarations that `agent_saturation` signal missed. Same pattern as v0.7.4 user_stop_hints coverage gap. Added zh phrases: bare `真饱和` / `彻底饱和` / `系列收官` / `干净状态收官`; added en phrases: `genuinely saturated` / `truly saturated` / `diminishing returns` / `optimization for its own sake`. 1 new test covering 6 fixtures. 456/456 passing. | ✅ |
| **v0.9.0 injection architecture redesign — 73% per-turn token saving**. User insight after v0.8.6: "session 初始 + 不同模型默认锚定阈值就近注入 + 违规注入 + 压缩后注入 + 子 Agent 注入" — don't re-inject full rules every turn (duplicates conversation history). Three coordinated changes: (1) SessionStart now full baseline injection covering all 4 sources (was精简 baseline); (2) UserPromptSubmit per turn injects compact anchor (id + first-line preference + drift marker, ~490 tok vs 1817 — `format_anchor_only()` new function); (3) PostToolUse mid-reinject triggers on session-global byte accumulation (not per-turn) hitting tightened model threshold (Opus 60K / Sonnet 40K / Haiku 30K). State semantic: `tool_byte_seq` no longer per-turn reset. **460/460 passing**. Measured 1M Opus saving: 18.4% → 8.2% of context (~100K tokens / 55% reduction). | ✅ |
| **v0.9.1 v0.9.0 doc-sync follow-up**. User dogfooded v0.9.0 in a fresh session, saw compact-anchor format working correctly, requested follow-up doc sync. Updated `docs/PRD.md` / `docs/PRD.zh.md` F2 (compact anchor description) + new F2.5 5-hook injection lifecycle table; `docs/HOOK_CONFIGURATION_GUIDE.md` per-hook descriptions; `karma/hooks/session_start.py` docstring (had reversed description of v0.9.0 architecture — "UserPromptSubmit every turn full, SessionStart one-time compact" is exactly opposite of v0.9.0). Pure doc patch, 0 behavior change. | ✅ |
| **v0.9.2 `test_compact_hooks.py` hardcoded `/Users/jhz/karma` path → dynamic resolution (issue #2)**. @fyn1320068837-source's 2nd report. 20 hardcoded refs to maintainer's local path across all 9 test functions → tests pass locally but fail with `FileNotFoundError` on any other machine **including CI**. Verified after issue filed: **GitHub Actions CI had been failing since v0.8.6** (3 releases). I shipped "pytest 460/460 passing" without running `gh run list` — same rule-4 violation pattern as v0.6.1's first external dogfood. Fixed exactly as reporter suggested: `PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent` + `PYTHON = sys.executable`. 460/460 still passing locally, now portable. | ✅ |
| **v0.9.3 actually green up CI — v0.9.2 wasn't the whole story**. After v0.9.2 push, ran `gh run list` (per new checklist): CI **still red**. Different root cause: CI runs `vulture karma/ --min-confidence 60` but my local checks use `--min-confidence 70`. 60-confidence flags 4 truly-dead items I never saw (`EXAMPLE_RULES`/`EXAMPLE_RULES_MINIMAL` aliases in cli.py, `current_locale()`/`reset_cache()` in i18n.py) + 1 vulture false positive (`signals.reset_cache` used by tests but vulture only scans `karma/`). Deleted 4 dead items, added `whitelist.py` referencing `signals.reset_cache`, updated `ci.yml` to pass whitelist. Local-vs-CI gate mismatch was the deep root cause for the v0.8.6 → v0.9.2 CI red streak. Added to checklist: run `vulture` with `--min-confidence 60` (matching CI) before tagging. | ✅ |
| **v0.9.4 CI still red — 3rd root cause: `mypy` strict mode catches `signals.py` `Optional[list]` narrowing**. After v0.9.3 push: CI **still red on `mypy karma/`**. CI runs mypy; my local checklist never did. `signals.py:_expand_yaml_signals` had `[v for _, v in resolved]` after `any(v is None for _, v in resolved): continue` guard — runtime-safe but mypy can't see the guard, infers `list[list \| None]` → `product(*word_lists)` type incompatible. Fix: explicit `[v for _, v in resolved if v is not None]` narrows to `list[list]`. Added `mypy karma/ && mypy tests/` to local checklist matching CI exactly. | ✅ |
| **v0.9.5 CI still red — 4th root cause: tests assume zh locale, CI runs en**. After v0.9.4 push: CI **still red on `pytest`** (16 failures). My Mac `LANG=zh_CN.UTF-8` → `karma.locale_detect.is_chinese_user()` True → i18n picks zh → fixtures pass. CI runner default `en_US.UTF-8` → False → en → fixtures asserting `"默契"` / `"偏离"` / `"纯陈述"` literal Chinese fail. Fix: new `tests/conftest.py:pytest_configure` does `os.environ.setdefault("KARMA_LOCALE", "zh")` before any karma import. Tests now always run zh locale regardless of host. Added `LANG=en_US.UTF-8 pytest -q` to local checklist (the 5th gate, catches locale-coupled bugs). Series of 4 patch releases (v0.9.2 → v0.9.5) each fixed an independent CI failure root cause my local checklist missed. | ✅ |
| **v0.9.6 CI still red — 5th root cause: v0.6.0 BREAKING rename leftover in `verify wheel` step**. After v0.9.5 push: CI **still red on `Verify wheel contains yaml templates`** across all 4 matrix jobs. CI verify checks the wheel contains `data/sticky.dev.example.yaml` — but v0.6.0 BREAKING renamed `sticky.*` → `rules.*`. **This step has been failing since v0.6.0 (~9 releases)** — earlier steps (vulture/mypy/pytest) kept failing first and hiding it. Fix: update `ci.yml` `expected` list to current wheel layout (`data/rules.dev.example.yaml` / `data/rules.dev.example.zh.yaml` / `data/locales/{en,zh}.yaml` / `data/config.example.yaml` / `skills/karma/SKILL.md`). Added 6th local checklist gate: `python -m build --wheel + verify` — local checklist now a strict superset of CI step order. Meta-lesson: I'd been declaring each fix "the root cause" without verifying CI reached terminal green. The actual deepest layer is the structural mismatch between local checklist and CI pipeline coverage. | ✅ |
| **v0.9.7 KARMA_HOME isolation broken in bypass detection + user-facing sticky residue + regression mechanism**. Audit driven by user question on v0.9.6 sub-agent report's "legitimately preserved" list. Verified sub-agent's CLI migration-shim verdict was correct, but full-repo grep surfaced 2 actual bugs the rename sweep had been missing: (1) `karma/checks/bypass_karma.py:_KARMA_STATE_PATH_RE` hardcoded `\.claude/karma/...` literal — user running `KARMA_HOME=/tmp/foo` then `rm /tmp/foo/session-state/*.json` (bypass) is **completely missed** by the check because the regex only matches default path. Fixed via `_build_state_path_re()` factory using `karma_home()`. Filename set also expanded to catch both `rules.yaml` and `sticky.yaml`. (2) `karma/cli.py:257` hardcoded hint string `"vim ~/.claude/karma/config.yaml"` misleads `KARMA_HOME` users to a non-existent file — fixed via f-string with `config_path` variable. Plus 5 user-facing `sticky` residue in `data/locales/zh.yaml` / `data/config.example.yaml` / `data/rules.dev.example.zh.yaml` / `data/rules.dev.minimal.example.zh.yaml` / 4 `violations.py` API docstrings claiming `sticky_id` returns. **Regression mechanism**: new `tests/test_no_sticky_in_user_facing.py` locks 7 user-facing files with whitelist-style exceptions — next time someone introduces an old name in these files CI fails. Whitelist is "exact line literal" not "file-level exemption" — granular and auditable. Dev-facing residue (cli/hook/notify module docstrings, tests/ variable names — ~10 places) deferred to v0.10.x for a single mass sweep. 4 new KARMA_HOME isolation tests in `test_bypass_karma.py`. 466/466 passing both locales. | ✅ |
| **v0.9.8 cross-process concurrency race fix + API-enforced atomicity via `update_state(sid, fn)`**. Audit prep for contributor's stress test ("怎么可能测不出问题") read-before-write surfaced session_state.py's own TODO (line 276-286): "极少数情况下多 hook 同时跑会让 ltp 时序略偏... 要彻底消除可加 atomic file lock" — never added. Real scope broader than the TODO suggests: multi-process / multi-hook `load → modify → save` second save overwrites first across ALL fields (not just ltp). **Anti-shortcut alignment moment**: first pass chose contextmanager approach A ("v0.9.8 务实，留 v0.10/v1 走 B" framing), user caught it ("咱们要做长期方案，你忘了么？") — karma's checks are pure-engineering regex and can't catch design-intent shortcuts (zero-LLM principle's known limit); human review is the backstop. Rolled back + redesigned via approach C in alignment with user: keep `load`/`save` public (tests/ 58 sites legitimate lower-level primitive users); add `update_state(sid, fn) -> tuple[state, T]` as production API bundling `_state_lock` (fcntl.flock advisory lock, Windows no-op fallback); add `read_state(sid)` as explicit read-only (atomic `os.replace` writes make read-only lock-free). 6 hook entry points migrated to `update_state`. `cli.py` 2 read-only sites migrated to `read_state`. 7 new tests including **N=20 subprocess concurrent stress test verifying no lost updates** — real race-fix evidence. 473/473 passing both locales. **The invariant ("load → modify → save must be atomic per session") now lives in API shape, not calling convention** — new hooks can't accidentally skip the lock. | ✅ |
| **v0.9.9 onboarding feedback — `karma init` ends with a default-rules summary block**. User-driven product-direction call after v0.9.8 reliability work: "Can `karma init` give clear feedback at the end — when the Agent helps install karma, the user should be told which default rules are enabled without typing any command themselves." Added `_print_default_rules_summary()` helper called at end of `cmd_init`: one line per rule (`id` + first line of `preference`), header text bilingual via `init.summary.header` locale key. Agent running `karma init` sees the block on stdout and naturally relays it to the user. **Design choice — deliberately no "next steps: run X" command tips**: first-pass implementation included `karma rule edit / list / remove` tip block. User pushback: "I don't want the user to type any command manually." Removed tips. Principle: after Agent has relayed the rule summary, modify intents go through Agent ("remove rule X" / "change rule Y" → Agent uses `/karma` skill or `karma rule edit`), not user typing command syntax. 2 new tests including a lockdown test ensuring future PRs can't reintroduce command tips into the summary block. 477/477 passing both locales. | ✅ |
| **v0.9.10 onboarding polish — first-paragraph summary + footer (token cost reassurance + `/karma` in-chat entry)**. User acceptance review of v0.9.9 surfaced two refinements: (1) `split("\n")[0]` cut at YAML visual wrap producing half-sentences (e.g. `long-term-fundamental` showed only "...When facing hard problems" without "they want you to pause and think..."). User picked option (b): switched to first-paragraph (`split("\n\n")[0]`) so each summary entry is a complete meaning unit. Length tradeoff: zh full 7 ≈ 33 lines; en minimal 5 ≈ 37 lines — still single-screen for Agent relay. (2) User wanted reassurance footer: "Tested: rule injection accounts for under 3% of per-session token spend; to add or modify rules, just type `/karma <natural-language>` in your AI client." Added `init.summary.footer` bilingual locale key, follows `_resolve_locale()` (Chinese-system users see Chinese footer, English-system users see English automatically). `/karma` is a slash command in the AI client chat box (not a shell command) — typing it in chat is equivalent to "just tell the Agent what rule you want", so it doesn't violate v0.9.9's "no shell-command tips" rule. 2 new tests including `test_init_summary_footer_matches_user_locale` locking the cross-language footer invariant. 479/479 passing both locales. | ✅ |
| **v0.9.11 observability — `karma audit --by-check` engine-check hit distribution + `/karma` no-arg defaults to this view**. After v0.9.10 polish, asked user which direction to push: check-firing observability or weekly trend. **User design insight**: "skill 的增加会造成额外的用户使用成本... 第一个方向是不是直接做成 /karma 指令不带内容时候的默认输出就比较好?" — avoid inventing new entry points; reuse `/karma` (user already knows from v0.9.10 footer) as the in-chat data-dashboard handle. Implementation: (a) new `_cmd_audit_by_check()` aggregates by `Violation.trigger_key` (existing v0.5.7 i18n key, format `check.<name>[.<sub>].trigger`) — top-level per-check counts + sub-variant breakdown (`evidence.commit` vs `evidence.completion`, etc) + dedicated keyword-only bucket. **No schema change**: reused trigger_key, historical jsonl without it falls into keyword-only bucket. (b) `karma/cli.py` main dispatch parses `--by-check` flag, default audit unchanged for backward compat. (c) `skills/karma/SKILL.md` adds "No-argument flow" section: `/karma` empty `$ARGUMENTS` → Agent runs `karma audit --by-check` and relays with brief interpretation (high-firing check / high keyword-only ratio / sub-variant FP suspicion), then asks "want to tune?". **Closes the dogfood feedback loop** without inventing new commands: violations.jsonl → audit → user sees pattern → decides to tune. Real-data validation: author's 187-violation dogfood data produces meaningful distribution (`keep_pushing.default` 69% of engine hits, 86% keyword-only fallback) on first run. 2 new tests including backward-compat lockdown. 481/481 passing both locales. ⚠️ **Data interpretation pitfall surfaced by v0.9.12**: the "86% keyword-only" reading was an instrumentation artifact (see v0.9.12). | ✅ |
| **v0.9.12 data-pipeline bug fix — `_build_strong_reminder` hook fallback was dropping `trigger_key`**. v0.9.11's first-run dogfood showed "86% keyword-only / 14% engine" which I confidently interpreted as user behavior signal. **User's follow-up question — "are 1-trigger checks (`bypass_karma` / `evidence.completion` / `testset`) redundant or missing real signal?" — was the prompt that exposed an instrumentation bug**: reading raw jsonl found two violations with identical `trigger` text (the i18n output of `check.keep_pushing.default.trigger`) where one had `trigger_key` set and one didn't. Pure field-presence difference. Root cause: `user_prompt_submit.py:_build_strong_reminder` (v0.4.41 fallback path for when user submits new prompt before Stop hook runs) built `Violation` objects without `trigger_key=h.trigger_key`, while `pre_tool_use.py` and `stop.py` both passed it correctly. So engine-check hits that flowed through this fallback path got recorded with empty `trigger_key`, and v0.9.11's `--by-check` view bucketed them as keyword-only. **Reanalysis with the bug accounted for**: true `keep_pushing` engine hits ≈ 99 (not 20); true `bypass_karma` ≈ 7 (not 1); `evidence.completion` ≈ 10; `testset.*` ≈ 5 — none of the "1-trigger checks" were actually redundant, they were under-counted by the data-pipeline bug. Fix: added `trigger_key=h.trigger_key` in `_build_strong_reminder`. **Regression lockdown**: new `test_all_hook_violation_writes_pass_trigger_key` statically scans `karma/hooks/*.py` and requires every `Violation(...)` or `_V(...)` construction with `rule_id=...` to also have `trigger_key=...` in the same call — invariant now in the test suite. **Did not backfill historical jsonl** (rule #5 [no-testset-no-future-leakage]: rewriting old records to make a dashboard look better is the kind of "modify past to validate present" pattern this project rejects). Instead, `cmd_audit --by-check` view footer now prints a caveat that pre-v0.9.12 historical data may be misclassified, and only v0.9.12+ writes are accurate. **Meta-lesson**: rule #4 [loud-failure-with-evidence] applies in both directions — claim a result, then verify the result isn't instrument artifact. 482/482 passing both locales. | ✅ |
| **v0.9.13 comprehensive instrumentation audit — 4 correctness bugs caught using v0.9.12's pattern as template**. After v0.9.12, user asked "全面排查下，还有没有这种 bug，直接影响 karma 运行准确性和统计准确性的". Launched audit across Type A (field-missing) / B (off-by-one) / C (race) / D (i18n inconsistency). Sub-agent reported 5 findings; per rule #4 each was hand-verified — 1 was sub-agent misjudgment (agent_id encoded in filename not payload), 4 were real bugs. **A1**: `load_all()` dropped `agent_id` on read (write side did include it); audit/stats can't truly group main vs sub Agent. Fix: `agent_id=d.get("agent_id")` in `load_all`. **B1**: turn window `cutoff = cur - window` produced `[cur-window, cur]` = N+1 turns, not N. Worst impact: `stop.py:162 force_block` with `force_window=3, threshold=5` would force-block on already-fixed old violations (4th-turn-old still counted). User-facing config.yaml comment literally says "最近 N turn 内", so N+1 is wrong. Fix: `cutoff = cur - (window - 1)` across `recent_turns`, `count_recent_turns`, and `cli.py:836` drift view. One existing fixture `test_stop_hook_force_blocks_on_accumulated_violations` razor-edge satisfied threshold=5 only under old cutoff — fixture strengthened to 6 violations (not 5) with honest comment explaining "fixture reflects fix correctness, not tweak to pass". **C1**: `pre_tool_use.py:98-100` did `load + catchup_pending_bg + no save`. I had previously read this in v0.9.8 work and classified as design choice ("PreToolUse is decision-side"); sub-agent caught my error — `catchup_pending_bg()` mutates pending_bg_tasks/recent_bash, not persisting means next hook does redundant catchup. Migrated to `update_state(sid, lambda s: s.catchup_pending_bg(), agent_id=...)` matching v0.9.8 architecture. **D1**: `data/signals/weak_claims/zh.txt` had 8 hedge phrases vs en's 23 — Chinese users had ~35% evidence-check recall. Expanded to 25 phrases covering "应该" family / "大概率" / "可能/也许" / "推测/我猜/估计" / "看起来/似乎/好像". 3 new lockdown tests including `test_weak_claims_zh_en_coverage_parity` (locks zh/en count diff < 30%) and `test_recent_turns_window_lockdown_v0913` (explicit `window=N → N turns`). 485/485 passing both locales. **Meta-pattern confirmed**: v0.9.12's "86% keyword-only artifact" wasn't a one-off — it was symptomatic of "intent vs implementation instrumentation drift accumulated over years". A single high-quality follow-up question to a confident interpretation can surface a cluster of related peer bugs, not just one. | ✅ |

| **v0.9.14 multi-agent cross-audit catches v0.9.13's own regression — `pre_tool_use` `update_state` not wrapped in try/except**. User: "每次多 Agent 交叉互审就能挖出很深的 bug 也是很有趣的一件事。再来一轮。" Launched 3 parallel audit agents with **viewpoint diversity** (avoid v0.9.13's already-scanned surface): viewpoint 1 (8 engine-check logic correctness — FP/FN/logic), viewpoint 2 (config defaults drift), viewpoint 3 (fail-open/fail-closed contract). Per rule #4 each finding was verified. **Viewpoint 1 mostly noise**: 6 of 8 findings were design choices misjudged by sub-agent (chinese_plain table-jargon counting is intentional per v0.4.22 comment; `_LONG_TASK_RE` skipping `npm run` is intentional). **Viewpoint 2 clean** (`DEFAULTS` consistent across all fallback sites). **Viewpoint 3 caught the real bug** — v0.9.13's own C1 migration introduced a regression: I changed `pre_tool_use.py:98-100` from `load + catchup_pending_bg + no save` to `update_state(sid, lambda s: s.catchup_pending_bg(), agent_id=...)` but **forgot to wrap in try/except**. Original `load + catchup` was implicitly fail-safe; `update_state` introduces new failure paths (fcntl.flock acquire errors, save OSError). Any exception → bubble → `pre_tool_use.main()` returns non-zero → Claude Code sees hook fail → **user is blocked from the tool call** (fail-closed, opposite of karma design). **Fix**: wrap in try/except with fallback to bare `load()` (state lost for this turn but PreToolUse can still make decisions). **Plus minor fix from viewpoint 1**: `_LONG_TASK_RE` added `pip install` pattern (real FN — pip install always takes ≥30s). 2 new regression tests including fail-open lockdown for PreToolUse. **Audit signal-to-noise comparison**: v0.9.13 had 5 findings / 4 true bugs (high SNR — accumulated drift); v0.9.14 had ~9 findings / 2 true bugs (1 critical + 1 minor; low SNR — repo already clean post-v0.9.13). **Diminishing returns confirmed**: subsequent audits' marginal value is mostly catching the prior round's own regressions. **Rule #4 now applies in three directions**: forward (claim+evidence) / backward (verify not artifact, v0.9.12 lesson) / **self-verify post-fix** (claim a fix, verify the fix didn't introduce regression — v0.9.14 lesson, multi-agent cross-audit is one way). 487/487 both locales. | ✅ |

| **v0.9.15 cross-model audit (GPT-5.5) catches 3 cross-backend protocol bugs + critical wheel-packaging miss**. User: "再来一轮 cross-audit, 本机配置了 codex cli, 也配置好了 gpt 5.5 模型, 你委派 codex cli 做一次多 Agent 交叉评审." Ran `codex exec` GPT-5.5 xhigh reasoning twice — high-level audit + full-repo code review. **Cross-model viewpoint exposed bugs every Claude-side audit had missed**: (1) Gemini BeforeTool needs top-level `{decision: "deny", reason}` not Claude's `hookSpecificOutput` shape — karma's Gemini intercepts were no-ops (wrote violations + stderr but dangerous tools executed). (2) Gemini tool_name uses `run_shell_command`/`read_file`/etc — karma checks compared against Claude-style `Bash`/`Read`/`Edit` so zero checks fired on Gemini. (3) Codex `apply_patch` is the canonical edit tool_name per Codex docs but karma never handled it — `apply_patch` edits bypassed `read_first`/`evidence`/`long_term`/`testset`, `last_edit_ts` never advanced. **WebFetch Gemini hooks ref + Codex hooks docs + Claude Code hooks docs** triple-verified the protocol assumptions and caught one codex-audit misjudgment (Codex actually accepts the new `hookSpecificOutput` shape too — Claude/Codex sides of karma are fine; only `apply_patch` needed handling). **Fix**: new `karma/backends/protocol_adapter.py` centralizes `detect_backend()` (via `hook_event_name`) + `normalize_tool_name()` (Gemini/Codex → Claude canonical) + `emit_deny()`/`emit_allow()` (backend-specific output shape). pre_tool_use + post_tool_use entries route through adapter. **Second full-repo codex review caught a separate critical wheel-packaging bug**: `pyproject.toml` force-include never listed `data/signals/`, so pip-installed wheels lacked the signal vocabulary tree → `compile_alternation()` returned never-match → evidence/keep_pushing/non_blocking keyword-fallback layer was silently dead **for every pip-install user including the Claude Code mainstream path**. The 6-gate local checklist had wheel verify but only locked 6 expected files; the signal subtree was never in the lockdown list. Fixed via force-include of the whole `data/signals` directory + CI smoke test (build wheel + pip install into clean venv + assert `compile_alternation()` returns non-empty regex for 4 key signals). Real validation post-fix: `weak_claims` 497 chars / `push_signals` 16653 chars / etc all functional. **User caught me misjudging during this round** ("你没有探查就下结论这很不好") when I was about to ask for fix direction without verifying the cross-backend bugs against real local config + official docs — rule #6 read-before-write applies to docs too. **Meta-pattern**: cross-model audit value is real when in-house model has systematic blind spots. Claude wrote karma + reviewed 12+ times this session; the blind spot was "assume Claude's own protocol is universal." GPT-5.5 (different training exposure to Gemini/Codex official refs) flagged this assumption precisely. Single-model rounds (v0.9.13/14) had diminishing returns; cross-model opened a new audit surface. The bug had been latent for karma's entire "3-backend support" claim history — every dogfooding case was Claude Code, so cross-backend protocol never got tested. 11 new tests including Gemini-style payload integration lockdowns for both pre_tool_use deny shape and post_tool_use state advancement. 498/498 passing. Phase 2 (apply_patch multi-file diff parsing for full read_first/record_edit support) deferred to v0.9.16+. | ✅ |

| **v0.9.16 codex apply_patch envelope true parser via real captured payload + config DEFAULTS silent-drop + test asserts tightened**. Closes v0.9.15's deferred phase 2 of cross-backend protocol normalization. v0.9.15 normalized `tool_name` only because the real codex `apply_patch` envelope shape wasn't yet captured; v0.9.16 captures it from a real `custom_tool_call.input` literal in a fresh codex 0.130.0 + GPT-5.5 session rollout (`/Users/jhz/.codex/sessions/2026/05/16/rollout-2026-05-16T13-51-47-...jsonl`). **Shape**: codex passes the entire `*** Begin Patch ... *** End Patch` envelope as a single string in `custom_tool_call.input`; multi-file patches concatenate `*** Update File:` / `*** Add File:` / `*** Delete File:` blocks. Two new functions in `karma/backends/protocol_adapter.py`: `parse_apply_patch_envelope()` returns `[{"op", "path"}, ...]`; `normalize_tool_input()` synthesizes karma canonical `{file_path, new_string, _codex_patch_files}` for codex apply_patch (passthrough otherwise). Wired into pre_tool_use + post_tool_use entries; `karma/checks/read_first.py` iterates `_codex_patch_files` for multi-file coverage (catches the case where only the primary file was Read). post_tool_use iterates Update/Add paths → `record_edit` + `record_read` each, so `last_edit_ts` truly advances for multi-file codex commits — closes the v0.9.15-era evidence/commit gate gap. **Investigation footnote**: `codex exec` non-interactive mode does not fire user hooks even with `--enable hooks` (verified via `KARMA_DEBUG_DUMP_PAYLOAD` instrumentation + `codex features list`). Payload was captured from session rollout instead. Interactive codex (production path) is expected to fire hooks normally; defensive `_extract_codex_patch_text()` handles both bare-string (verified) and dict-wrap shapes. Plus **Minor #4**: `karma/config.py:load()` iterates `for key in DEFAULTS` so user-config knobs not in DEFAULTS are silently dropped — `reinject_every_n_tokens` was documented as user-tunable but missing from DEFAULTS, fixed (None → "auto by model" preserved). Plus **Minor #5**: 3 `tests/test_compact_hooks.py` sites with `if "hookSpecificOutput" in output:` conditional branches silently passed if hooks regressed to the (Claude-Code-unsupported) `hookSpecificOutput` shape on PreCompact / SubagentStop — tightened to strict `assert output == {}`. 12 new tests in `test_protocol_adapter.py` (22 total in file) + config DEFAULTS test + tightened compact_hooks asserts. 510/510 passing both locales (was 498). All 6 local gates pass + wheel smoke test in clean venv. | ✅ |

| **v0.10.0 backend architecture split: protocol_adapter delegation + 6-method contract + codex ownership handoff**. After v0.9.16 real-codex testing exposed 2 new bugs (Codex rejects `permissionDecision:"allow"` per official docs — v0.9.15 was wrong; codex shell-as-Read gap because codex reads files via `exec_command`+`tail`/`sed`/`cat` which karma's `record_read` doesn't see → `read_first` false-positive denials), user proposed backend ownership split: karma maintainer owns hooks/checks/contract/base + claude_code + gemini_cli + GitHub docs; **Codex CLI itself owns `karma/backends/codex.py` via PRs from Codex sessions**. v0.10.0 formalizes: `Backend` Protocol declares 6 contract methods (`pre_install_setup`, `post_install_message`, `normalize_tool_name`, `normalize_tool_input`, `emit_deny`, `emit_allow`), `_json_hooks.py` provides Claude-shape defaults. `protocol_adapter.py` retired to pure dispatch — all backend-specific code (`_GEMINI_TOOL_MAP`, `_CODEX_TOOL_MAP`, envelope parser) moved into each backend's own file. `detect_backend()` routes by `hook_event_name` (Gemini) or `sys.argv[0]` literal `/.codex/` (codex). `checks/read_first.py` removed `_codex_patch_files` field — renamed to backend-neutral `multi_file_targets`. **Bug A fixed**: `CodexBackend.emit_allow() → "{}"` per official codex hooks docs; locked test prevents regression. v0.9.17 work integrated: post_install_message loud `/hooks` approval reminder + karma doctor codex-specific section + README codex alert box. New `docs/CODEX_BACKEND.md` + `.zh.md` defines ownership boundary + known TODO agenda for Codex backend owner (shell-as-Read, real hook payload capture, other tool_name mapping, approval state detection). 512/512 both locales + all 6 gates + wheel smoke. **Meta-pattern**: when in-house model has systematic blind spot guessing another platform's protocol (v0.9.15 + v0.9.16 + v0.10.0 Bug A all same pattern), right fix is contributor ownership split not more cross-model audits. | ✅ |

Details in [CHANGELOG.md](../CHANGELOG.md) for per-release rationale; [HANDOFF.md](./HANDOFF.md) for internal context.

## Continuous observation = continuous development

User's own words: "We keep pushing — that IS the observation period." Every push has Claude running with karma installed; every commit goes through hook interception. M3 accumulated 30+ real violations; all 7-8 rules triggered.

karma isn't "develop first, observe later" — it's "development is dogfooding."
