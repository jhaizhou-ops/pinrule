# Changelog

**[🇬🇧 English (current)](./CHANGELOG.md) · [🇨🇳 中文](./CHANGELOG.zh.md)**

Documents karma's important version changes. Versioning follows [SemVer](https://semver.org/).

> 📝 **English changelog status**: historical release notes (v0.1.0 through v0.5.0) are in Chinese-only ([CHANGELOG.zh.md](./CHANGELOG.zh.md)). Future releases (v0.5.1+) will publish bilingually in both files.
>
> The Chinese version is comprehensive (2300+ lines covering every release's design rationale, root-cause analysis, and "wrong diagnosis lessons"). Translation is in progress as part of Phase D (full English content) per [docs/REFACTOR_PLAN_RULE_AND_I18N.md](./docs/REFACTOR_PLAN_RULE_AND_I18N.md).

## [Unreleased]

## [0.5.3] — 2026-05-15 (feat — Phase D complete: all 28 check `suggested_fix` strings switchable en/zh)

### feat — All 8 check functions now locale-aware

All `CheckHit.suggested_fix` strings — the part directly injected into Agent's next-turn context — switched from hard-coded Chinese to `tr()` lookup. Coverage is complete across all 8 check modules.

- **`karma/checks/chinese_plain.py`** (3 entries) — `ratio` / `jargon` / `repeated_prefix`. Note: chinese_plain check itself is opt-in for Chinese users; English default install removes it via rule-template selection.
- **`karma/checks/non_blocking.py`** (4 entries) — `python_block` / `sleep` / `wait` / `long_task` (with `{cmd}` interpolation)
- **`karma/checks/evidence.py`** (3 entries) — `commit` / `completion` / `weak_claim`
- **`karma/checks/keep_pushing.py`** (2 entries) — `stop_hint` / `default`
- **`karma/checks/read_first.py`** (1 entry, with `{file_path}` interpolation)
- **`karma/checks/bypass_karma.py`** (1 entry)
- **`karma/checks/long_term.py`** (7 entries in pattern tuples) — `long_id_branch` / `blacklist_literal` / `uppercase_const_list` / `commit_hack` / `git_skip_verify` / `todo_marker` / `patch_intent`
- **`karma/checks/testset.py`** (7 entries in pattern tuples) — `reverse_feed` / `detail_writeback` / `cross_split_copy` / `detail_append` / `split_hardcode` / `hash_branch` / `case_list_hash`

For `long_term` and `testset`, the `_PATTERNS` tuple structure was preserved with `fix_key` (an `i18n` key string) as the third element instead of literal fix text — the `check()` function calls `tr(fix_key)` at hit time. This keeps the pattern table compact and lets translators edit `data/locales/*.yaml` without touching Python.

### feat — `data/locales/en.yaml` + `data/locales/zh.yaml` add 28 new keys

`check.*.fix` namespace covers all suggested_fix strings. Placeholders (`{term}`, `{prefix}`, `{file_path}`, `{cmd}`) interpolated at runtime via `str.format()`.

### Verification

- `pytest`: 392/392 passing (unchanged from v0.5.2; new keys are additive)
- `ruff`: 0 issues
- Manual EN/ZH switch test confirms all 14 new keys lookup correctly in both locales

### What stays Chinese (intentional, scoped to v0.5.3)

- `CheckHit.trigger` field — internal audit-log classification label, written to `~/.claude/karma/violations.jsonl`. Not in Agent injection path, so prioritization is lower; will migrate in a future minor release alongside trigger-key namespace design.

## [0.5.2] — 2026-05-15 (feat — i18n infrastructure + all hook injection texts switchable en/zh)

### feat — Engineering-layer i18n MVP

- **`karma/i18n.py` module** — `tr(key, **fmt)` translation lookup with `{placeholder}` interpolation; fail-open (missing key returns key itself, never crashes hook)
- **Locale resolution** — `KARMA_LOCALE` env var > `config.yaml` `locale` field > `karma.locale_detect.is_chinese_user()` auto-detect > fallback `en`
- **`config.yaml` `locale` field** — `"auto"` (default) / `"en"` / `"zh"`
- **`data/locales/en.yaml` + `data/locales/zh.yaml`** — Translation dicts covering all user-visible hook-injection strings (header / drift marker / mid-injection / strong reminder / Stop reason / SessionStart variants / SubagentStart)

### feat — 5 hooks injection texts now locale-aware

All hook injection texts switched from hard-coded Chinese to `tr()` lookup:

- `karma/rule.py format_for_injection` — header title + 2 description lines + drift marker
- `karma/hooks/post_tool_use.py` — mid-injection "anchoring refresh" 3 lines
- `karma/hooks/stop.py` — Stop hook `decision=block` reason (with `{count}/{max}` interpolation)
- `karma/hooks/user_prompt_submit.py` — strong reminder header + footer
- `karma/hooks/subagent_start.py` — SubAgent baseline title + tail
- `karma/hooks/session_start.py` — 3 source branches (compact/resume/startup) + compact prior-drift header + tail

### Manual verification

- `KARMA_LOCALE=en` → `[karma — Your long-term agreement with the user]` / `[karma — Last response didn't show a next-step push signal]` ...
- `KARMA_LOCALE=zh` → `[karma — 你跟用户的长期默契]` / `[karma — 上一回应没看到下一步推进信号]` ...

### Pending in v0.5.3 (Phase D — English content completion)

8 built-in check functions still have hard-coded Chinese `suggested_fix` text (~14 entries):
- chinese_plain (3 / non_blocking (4) / evidence (3) / keep_pushing (2) / long_term (7) / testset (7) / read_first (1) / bypass_karma (1)

Phase D will abstract these behind `tr()` keys + provide English translations. Hook injection texts are user-visible critical path (covered in v0.5.2); `suggested_fix` only shown when violations trigger (less critical) — phased separately.

### Verification

- Tests: 392/392 all green
- 4-check: ruff / mypy / vulture / pytest all green
- Manual run: EN/ZH locale switching truly produces different injection text

## [0.5.1] — 2026-05-15 (feat — `karma rule add` natural-language rule input + i18n English-default docs)

### feat

- **`karma rule add` / `karma rule preview` CLI commands** — Natural-language rule input via Claude Code skill collaboration. User invokes `/karma rule <description>` in Claude Code → Agent refines to karma's validated tone/structure (per `skills/karma-rule.md` template) → calls `karma rule preview` to test → user confirms → calls `karma rule add` to write
- **`skills/karma-rule.md`** — Claude Code skill template for natural-language rule creation. Install: copy to `~/.claude/skills/karma-rule.md`
  - Workflow: understand intent → check existing rules → refine yaml → preview test → user confirm → write → report results (optimized content + tests passed + current rule library count + suggest deletions/modifications)
  - Critical constraints: collaborative-agreement tone (not rule-system), intent-prefix + action keyword format, optional engine-layer `violation_checks`, schema test before write
- Rule add validation: schema check + id duplicate check + soft/hard cap (10/12) check + `violation_checks` function existence check in REGISTRY

### docs (i18n English-default complete)

- **English-default documentation swap** (per user input: "the world's 90%+ future users are English") — switched main documentation language from Chinese to English. Chinese versions preserved as `.zh.md` alternatives:
  - README.md / SECURITY.md / CODE_OF_CONDUCT.md / CLAUDE.md
  - docs/PRD.md / docs/ARCHITECTURE.md / docs/REFACTOR_PLAN_RULE_AND_I18N.md / docs/RULES_REDESIGN_PROPOSAL.md / docs/HANDOFF.md
  - karma/backends/HOWTO.md
  - .github/ISSUE_TEMPLATE/bug_report.md / .github/ISSUE_TEMPLATE/feature_request.md / .github/PULL_REQUEST_TEMPLATE.md
  - CHANGELOG.md (this file)
- **Rule templates English-default**: `data/rules.dev.example.yaml` is now English-default; `.zh.yaml` is Chinese alternative. `karma init` auto-selects based on `karma/locale_detect.py` system-language detection
- **GitHub repo description** switched to English

### docs (i18n complete)

- **English-default documentation swap** (2026-05-15) — switched main documentation language from Chinese to English (per user input: "the world's 90%+ future users are English"). Chinese versions preserved as `.zh.md` alternatives. All English `.md` files are now the GitHub-default entry; `.zh.md` files are linked in headers as alternative-language versions.
- **Swapped files** (English-default + .zh.md backup):
  - README.md / SECURITY.md / CODE_OF_CONDUCT.md / CLAUDE.md
  - docs/PRD.md / docs/ARCHITECTURE.md / docs/REFACTOR_PLAN_RULE_AND_I18N.md / docs/RULES_REDESIGN_PROPOSAL.md / docs/HANDOFF.md
  - karma/backends/HOWTO.md
  - .github/ISSUE_TEMPLATE/bug_report.md / .github/ISSUE_TEMPLATE/feature_request.md / .github/PULL_REQUEST_TEMPLATE.md
  - CHANGELOG.md (this file)
- **Rule templates English-default**:
  - `data/rules.dev.example.yaml` is now English-default
  - `data/rules.dev.example.zh.yaml` (Chinese version, was previous default)
  - `data/rules.dev.minimal.example.yaml` same pattern
  - `karma init` auto-selects based on `karma/locale_detect.py` system-language detection
- **GitHub repo description** switched to English: "Make AI Agents never violate your rules in long tasks — auto-correct violations before they frustrate you. Pure-engineering zero-LLM hook system for Claude Code / Codex CLI / Gemini CLI. Measured violation rate ≈ 0%."

## [0.5.0] — 2026-05-15 (major breaking change — sticky → rule rename)

User authorized: "rename all `sticky` references in karma's code and files to `rule`."

Phase A complete: sticky → rule rename + backward-compat migration. Phase B (natural-language rule input via `karma rule add` CLI + Claude Code skill) / C (i18n infrastructure) / D (full English content) are pending in subsequent releases.

Key changes:
- Core classes: `class Sticky` → `class Rule`, `StickyConfigError` → `RuleConfigError`, `MAX_STICKY` → `MAX_RULES` (all preserved as aliases until v0.6.0)
- Module: `karma/sticky.py` → `karma/rule.py` (git mv preserved history), legacy `karma/sticky.py` became a compat shim
- Fields: `Violation.sticky_id` → `Violation.rule_id` (property `sticky_id` alias preserved), `CheckHit.sticky_id` → `CheckHit.rule_id`
- CLI: `karma sticky list/edit/remove` → `karma rule list/edit/remove`, legacy `karma sticky` as deprecated alias
- Config: `~/.claude/karma/sticky.yaml` → `~/.claude/karma/rules.yaml`, auto-migration via `karma init`
- Data templates: `data/sticky.dev.example.yaml` → `data/rules.dev.example.yaml`

Tests: 392/392 + 4-check (ruff / mypy / vulture / pytest) all green.

For detailed pre-v0.5.0 release notes (v0.1.0 through v0.4.44), see [CHANGELOG.zh.md](./CHANGELOG.zh.md).

## Pre-v0.5.0 releases

For all release history from karma's earliest version (v0.1.0) through v0.4.44, see [CHANGELOG.zh.md](./CHANGELOG.zh.md). Each release includes:

- Trigger context (what prompted the change)
- Root-cause analysis
- Implementation details
- Backward-compatibility notes
- Empirical verification (test counts, dogfooding hours, etc.)
- Lessons learned (for major fixes)

Notable releases:
- **v0.4.42** — "Collaborative agreement" tone refactor (see [docs/RULES_REDESIGN_PROPOSAL.md](./docs/RULES_REDESIGN_PROPOSAL.md))
- **v0.4.43 / v0.4.44** — Stop / SubagentStop / PreCompact hook schema compliance fixes
- **v0.4.39** — Per-model adaptive injection threshold (`karma/model_threshold.py`)
- **v0.4.34** — Subagent independent state architecture
- **v0.4.28 / v0.4.29 / v0.4.30** — v3 evolution: SessionStart baseline + PreCompact dump + SubagentStart/Stop
- **v0.4.0** — Multi-backend (Gemini CLI added) + JsonHooksBackend abstraction
- **v0.3.0** — Codex CLI backend
- **v0.1.0** — Initial Claude Code backend

## Versioning policy

- **Major** (X.0.0) — breaking changes (e.g., v0.5.0 sticky → rule rename, even with backward-compat aliases)
- **Minor** (0.X.0) — new features without breaking existing APIs
- **Patch** (0.0.X) — bug fixes, doc updates, performance improvements

Breaking changes are clearly marked with **major breaking change** prefix; deprecated aliases preserved for at least one minor version cycle before removal.
