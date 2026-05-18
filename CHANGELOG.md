# Changelog

**[🇬🇧 English (current)](./CHANGELOG.md) · [🇨🇳 中文](./CHANGELOG.zh.md)**

pinrule release notes, grouped by minor version. Versioning follows [SemVer](https://semver.org/). For per-patch detail (CI fixes, false-positive tweaks, audit findings), browse the [git log](https://github.com/jhaizhou-ops/pinrule/commits/main) — every commit message carries the full reasoning.

Releases from v0.5.1 onward publish bilingually. Earlier history (v0.1.0 – v0.4.x) lives in [`CHANGELOG.zh.md`](./CHANGELOG.zh.md) only.

## [Unreleased]

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
