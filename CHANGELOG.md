# Changelog

**[🇬🇧 English (current)](./CHANGELOG.md) · [🇨🇳 中文](./CHANGELOG.zh.md)**

pinrule release notes, grouped by minor version. Versioning follows [SemVer](https://semver.org/). For per-patch detail (CI fixes, false-positive tweaks, audit findings), browse the [git log](https://github.com/jhaizhou-ops/pinrule/commits/main) — every commit message carries the full reasoning.

Releases from v0.5.1 onward publish bilingually. Earlier history (v0.1.0 – v0.4.x) lives in [`CHANGELOG.zh.md`](./CHANGELOG.zh.md) only.

## [Unreleased]

## [0.19.0] — 2026-05-19 — **Hermes Agent backend — 4th client supported (source-grounded)**. NousResearch Hermes Agent v0.14.0+ (persistent server agent with plugin hooks) added as the 4th backend alongside Claude / Codex / Cursor. Built by cloning `NousResearch/hermes-agent` source and grounding every protocol detail in `agent/shell_hooks.py` (`_serialize_payload`, `_parse_response`) + `agent/conversation_loop.py` (`pre_llm_call`, `on_session_end` kwargs) rather than docs alone — payload shape (`{hook_event_name, tool_name, tool_input, session_id, cwd, extra}`), block output (`{decision: block, reason: ...}` Claude shape accepted + normalized), `pre_llm_call` context injection (`{context: "..."}` top-level), config at `~/.hermes/config.yaml`, skills at `~/.hermes/skills/`, wrappers at `~/.hermes/agent-hooks/`. Tool name normalization: `terminal` / `shell` / `execute_shell` → `Bash`, `read_file` → `Read`, `write_file` → `Write`, `patch_file` / `edit_file` → `Edit`. Event mapping (5 events): `pre_tool_call` → gate, `pre_llm_call` → context inject, `post_tool_call` → audit, `on_session_start` → baseline inject, `on_session_end` → stop wrapper (no transcript_path so violation detection is graceful no-op, matching Gemini AfterAgent's earlier lifecycle limitation). `protocol_adapter.detect_backend` now routes by snake_case event names (`_HERMES_EVENT_NAMES` frozenset) + `/.hermes/` sys.argv path fallback. Real local dogfood verified end-to-end: `hermes -z "Use terminal: sleep 30"` → `pre_tool_call` hook fires → pinrule emits block decision → hermes refuses execution → `violations.jsonl` records `non-blocking-parallel` rule hit. Tests: 35 new Hermes unit tests + 16 contract parametrized tests + updated `client_installed` mocks across 4-backend fixtures = 952 passing total. **Config-write strategy** — line-based surgical operator instead of full YAML parse: `pinrule install-hooks --backend hermes` runs `_extract_hooks_section` / `_strip_hooks_section` to surgically operate only on the top-level `hooks:` block, leaving Hermes's other sections (`model:`, `agent.personalities:` with multi-line string continuations and unicode-escape continuations, etc.) verbatim. Real deep-fix instead of strengthening the YAML parser — pinrule has no reason to parse Hermes config sections it doesn't own. Zero-runtime-deps promise preserved; install is fully automatic (no manual append step).

## [0.18.3] — 2026-05-18 — **真假阳 fix: Cursor Shell `block_until_ms` 默认值不再误拦**. Friend's Cursor dogfood revealed: Cursor SDK passes `block_until_ms=30000` as a default field on every Shell call (semantic: "wait up to 30s before backgrounding the tool call"). After `normalize_tool_name` mapped Shell → Bash, `non_blocking.py` line 116-127 used `block_until_ms >= 30_000` as a proxy for "command will block" — but the field is a tool-call timeout ceiling, not a command duration prediction. Result: every Cursor Shell command (including `pinrule doctor` running <1s) got blocked. **Fix**: deleted the `block_until_ms` proxy check entirely; command-content detection (`_SLEEP_RE` / `_LONG_TASK_RE` / `_PYTHON_REAL_BLOCK_RE`) already correctly identifies real blocking — those stay. 2 regression tests pin: (a) Cursor SDK default payload with `block_until_ms=30000` + short commands (`pinrule doctor`, `ls`, `echo`, `git status`) not flagged; (b) real `sleep 60` under same Cursor payload still caught by command-content check. Also cleared 5 residual `sticky` references in `docs/ARCHITECTURE.zh.md` (ASCII diagram annotation, violations.jsonl examples, body text, CheckHit signature) and `docs/PRD.zh.md` body text — leftover from the v0.6.0 `sticky → rule` rename.

## [0.18.2] — 2026-05-18 — **docs / skill polish for first-friend dogfood wave** — 6 docs commits between v0.18.1 and this release, no runtime behavior change. (1) **Path B Execution Checklist condensed from 10 lines → 8-line skeleton** (reviewer feedback: inline annotations on each step were distracting low-capability models; 2-round haiku 4.5 dogfood verified the v0.18.1 fixes — Backends-detected 3-line template / Source A honesty / no self-intro prefix — still stick after condensation). 2 new lockdown tests pin the 8-step skeleton + ≤100-char-per-line constraint. (2) **Runtime boundary precision**: hero `> Pure engineering · zero LLM · zero network ...` → `> **Runtime**: pure engineering · zero LLM ...` with explicit "(Scenario rule pack generation runs in your Agent — see Path B below.)" — two independent reviewers flagged the same ambiguity. (3) **Honest tool boundaries** section switches from prose disclaimers to a table with reproducible test scripts: `pytest tests/test_check_fp_fixes_v0_16_13.py` (4 historical FP lockdowns) + `pytest tests/test_false_negative_regression.py` (30+ FN cases). Skeptics reproduce, not read prose. (4) **Version-anchor cleanup**: removed `v0.17.1+ / new in v0.17.1 / v0.18.0+` references from README + SKILL.md — users see current state, not implementation history. (5) **`os.rename` → `os.replace + fsync` references aligned**: CHANGELOG 0.18.0 entry + `cmd_rule_import_pack` docstring updated to reflect actual implementation. (6) **Walkthrough deletion**: removed 114-line ML-research walkthrough from Path B (was over-specifying example details that biased Agent away from user's actual scenario).

## [0.18.1] — 2026-05-18 — **6-evaluator cross-review P0/P1 fixes** — closes real bugs three independent reviewers flagged. (1) **`_STICKY_ID` data corruption fix**: 8 engine check functions now use `rule_id` from caller (with `_STICKY_ID` fallback), so Path B cross-scenario rules write user's real rule id to `violations.jsonl` instead of hardcoded `read-before-write` / `loud-failure-with-evidence` etc — previously every Path B rule with engine check was silently shipping ghost rule ids that `pinrule audit --by-check` couldn't trace back. (2) **`import-pack` atomic hardening**: tmp file now uses `tempfile.mkstemp` (unique name, same dir) instead of fixed `rules.json.tmp` → no concurrent-write race; added `os.fsync` for crash durability before `os.replace`; backup file name adds pid + random suffix to prevent same-second collisions. Test suite gets 4 new atomic-guarantee cases (byte-for-byte / duplicate-id / concurrent / backup uniqueness). (3) **`cursor_transcript_doctor` cross-platform**: adds Linux (`~/.config/Cursor/logs`) + Windows (`%APPDATA%/Cursor/logs`) path dispatch; transcript_path regex accepts both POSIX and Windows paths. (4) **Engine check honesty**: README + SKILL.md replace `≡ same pattern` / 「同行为 pattern」 with `partially maps to operational pattern`, explicitly noting `loud_failure_with_evidence`'s `_ACTION_CONTEXT_RE` is dev-word-biased and non-code scenarios should rely on keyword fallback. (5) **Positioning sharpened**: README opening goes from "universal AI behavior rule framework" → "universal AI behavior-rule runtime, with a dev preset and Agent-generated scenario packs" — runtime vs content boundary explicit. (6) **Path B Execution Checklist**: 10-step short route added at top of Path B section so Agents can follow the canonical path without parsing 800+ lines of detail first. (7) **Doc cleanup**: SECURITY.zh.md `rules.yaml` → `rules.json`, ARCHITECTURE.zh.md `sticky #N` → `rule #N`, SKILL.md fixes `os.rename` → `os.replace` correctness, stale `cp backup` instruction → `--backup` flag reference.

## [0.18.0] — 2026-05-18 — **`pinrule rule import-pack` — atomic batch write CLI for Path B scenario switching**. Closes a real atomicity gap reviewers flagged in v0.17.1: previously Agent串 `pinrule rule remove A && rule remove B && rule add new1 && rule add new2 ...` to swap rule packs — if any step failed (schema reject / disk full / permission), `rules.json` was left in half-replaced state. New CLI: `pinrule rule import-pack --from-json <pack> --mode replace|append [--backup]` validates entire pack (schema / id uniqueness / hard cap / `violation_checks` registry) **before any write**, then atomic temp-write + swap (later hardened in 0.18.1 to `os.replace` + `fsync`). If validation fails anywhere, `rules.json` is byte-for-byte unchanged. Path B Step 10 in SKILL.md updated to use this primitive — Agent calls one command, the engine guarantees atomicity. 12 new tests cover the atomic guarantee for schema-fail / unknown-check / hard-cap / empty-pack / missing-file paths. Net effect: scenario switching can never leave you with a half-replaced rule library again.

## [0.17.1] — 2026-05-18 — **`/pinrule` becomes universal entry point** — scenario rule pack generation + engineering-first skill design. `/pinrule` is now the single command for everything: no-args → audit dashboard (fast-path, 0 LLM synthesis); `/pinrule <single rule>` → Path A refine + add (existing 7-step); `/pinrule <scenario>` → Path B two-phase generation (NEW) — Agent synthesizes 5-7 rules from 4 signals (your local `CLAUDE.md` / `AGENTS.md` / `.cursor/rules`, online best practices via WebSearch, Karpathy CLAUDE.md baseline, session context), Phase 1 = content draft + approval, Phase 2 = mechanism config (keywords + cross-scenario engine check semantic mapping) + approval, Step 10 atomic batch write with backup. SKILL.md design principle: engineering-first — when pinrule has a primitive (`pinrule doctor` / `pinrule rule preview` / `pinrule rule add` / etc.), Agent calls it directly; doesn't reinvent. Backend detection works via `pinrule doctor` (powered by new `pinrule.cursor_transcript_doctor` parsing Cursor Hooks log to distinguish 桌面 Agent / CLI / transcript state), enforced via Phase 1 preview mandatory "Backends detected" field — engineering constraint that 6-round dogfood proved more reliable than prompt-level "mandatory first action" wording. pinrule itself stays 0 runtime deps / 0 network / 0 LLM — all research happens in Agent's existing toolset. Effect: pinrule = framework / runtime, rules = Agent generates per-user-scenario. The promise "1 command for any AI workflow scenario" is now literal.

## [0.17.0] — 2026-05-18 — ⚠️ BREAKING — **Zero runtime dependencies**. Drop PyYAML; all config / rules / locales / examples switch from YAML to JSON (Python stdlib only). `push_signals/{en,zh}.yaml` cartesian templates move to Python modules (`{en,zh}.py`) — semantically clearer than JSON for nested template data. CLI flag rename `--from-yaml` → `--from-json`. Config / state files: `~/.pinrule/config.yaml` → `config.json`, `rules.yaml` → `rules.json`. No auto-migration: this is a clean reboot, reinstall to pick up. Why: dogfood feedback found YAML's multi-line-string / comment advantages weren't being consumed — rules are LLM-maintained via `pinrule rule add`, not hand-edited. Net effect: README now honestly claims "0 runtime deps", wheel size smaller, install faster, one less dependency-version-conflict risk.

## [0.16.18] — 2026-05-18 — **Windows zh-CN GBK console fix** (real user dogfood issue): `pinrule init` no longer crashes on default Chinese Windows console with `UnicodeEncodeError: 'gbk' codec can't encode character '▸'`. Added `pinrule/_io_encoding.py::force_utf8_stdio()` shared helper called at every entry point (`__main__`, `cli.main()`, hook wrappers). CI adds Windows GBK default-console smoke test step (no PYTHONIOENCODING) to lock down the regression. Also fixed: `settings.json.before-pinrule` no longer saves pinrule-modified state when fresh-install path skipped initial backup (uninstall path was effectively broken); init's auto-install-hooks message rephrased; README one-liner trimmed to `pip install pinrule && pinrule init` (init auto-fires install-hooks for detected clients).

## [0.16.17] — 2026-05-18 — **Windows native support**. Hook command goes from bare `wrapper-path` (Unix shebang-dependent) to `python.exe wrapper-path` via `subprocess.list2cmdline` — cross-platform, handles paths with spaces. CI matrix adds `windows-latest`; 3 new lockdown tests cover sys.executable prefix + space-quoting + all-3-backends consistency (857 tests).

## [0.16.16] — 2026-05-17 — README full redesign (203 lines bilingual, paced to aider / open-interpreter / mem0 patterns) + PyPI metadata polish (description aligned with slogan, keywords drop `dogfooding`, add `pinrule` / `claude-code` / `agent-rules`).

## [0.16.x] — 2026-05-17 (current)

- **Renamed karma → pinrule** with a fresh PyPI package and clean brand boundary; no automatic legacy migration.
- `PINRULE_HOME` becomes a **true sandbox** — install root, hook wrappers, settings files, skill paths, and Cursor rules all anchor under the env path; real `~/.claude/` / `~/.codex/` / `~/.cursor/` stay untouched, locked behind regression tests.
- Two rounds of external review polish (8.8 → 9.1/10): sharper slogan, accurate install boundary docs, soften "supported clients" wording, FAQ contrasting pinrule vs memory systems.
- Round-1/2/3 multi-agent code audits + community issue #8 close: 4 check false-positive fixes with ground-truth lockdown, init reinstall-detection root cause, fail-open contract on every hook entry, demo SVG re-paced for human reading speed. **854 tests, all green on CI matrix.**

## [0.15.0] series — 2026-05-17

- Codex native hook surface aligned with Claude intervention semantics.
- Backend capability matrix + reproducible perf script.

## [0.14.0] series — 2026-05-17

- Shared `~/.pinrule` home directory across all backends.
- Cursor native event surface (12 events end-to-end).

## [0.13.0] series — 2026-05-17

- **~10× per-turn token cost reduction** via compact anchor injection format.
- Drop Gemini CLI backend, focus on Claude / Codex / Cursor.
- Cursor functional parity with Claude (8/8 hook wrappers).

## [0.12.0] series — 2026-05-17

- **Cursor backend support** — 4th AI client wired end-to-end (later expanded to 12 native events in v0.13.x).

## [0.11.0] series — 2026-05-16 / 17

- `long-term-fundamental` engine redesign: response-level phrasing patterns make the engine actually fire.
- Bilingual hook output i18n + English `long-term-fundamental` response patterns.
- `pinrule audit --days N` time-window filter so dogfood decisions aren't diluted by stale data.

## [0.10.0] series — 2026-05-16

- Backend architecture refactor: `protocol_adapter` delegation layer + 6-method backend contract + Codex ownership boundary handoff.
- Cross-model audit (GPT-5.5) caught 3 critical cross-backend protocol bugs (Claude-only assumptions hidden for the entire repo lifetime).

## [0.9.0] series — 2026-05-15 / 16

- Injection architecture redesign: SessionStart full baseline + per-turn anchor + cumulative full reinject — **73% per-turn token saving**.
- Observability: `pinrule audit --by-check` shows engine-check hit distribution; `/pinrule` no-arg defaults to this view.
- Cross-process concurrency race fix via API-enforced atomicity in `update_state(sid, fn)`.

## [0.8.0] series — 2026-05-15

- **i18n signals**: detection phrases externalized, English users fully covered, adding a new language is a `.txt` contribution.
- `push_signals` YAML DSL: cartesian templates + word vocabularies for English push-phrase recognition.

## [0.7.0] series — 2026-05-15

- Treat root cause: rewrite "真X" defensive prefix stacking in pinrule source rule texts.
- Deep refactor + doc audit across all GitHub-visible files.

## [0.6.0] series — 2026-05-15 ⚠️ BREAKING

- **Remove backward-compat scaffolding** from the v0.5.0 `sticky` → `rule` rename.
- First real-user bug closed via issue #1 (`record_edit` exempts non-code paths).

## [0.5.0] series — 2026-05-15 ⚠️ MAJOR BREAKING

- **`sticky` → `rule` rename** across the whole codebase.
- `pinrule rule add` natural-language rule input, full i18n infrastructure with English-default docs (all 28 `suggested_fix` + 28 `trigger` strings switchable en/zh).
- `/pinrule <natural language>` skill auto-installed on every detected backend.

**Earlier history (v0.1.0 – v0.4.x)** is in [`CHANGELOG.zh.md`](./CHANGELOG.zh.md) only.
