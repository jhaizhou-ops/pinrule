# Changelog

**[🇬🇧 English (current)](./CHANGELOG.md) · [🇨🇳 中文](./CHANGELOG.zh.md)**

Documents karma's important version changes. Versioning follows [SemVer](https://semver.org/).

> 📝 **English changelog status**: historical release notes (v0.1.0 through v0.5.0) are in Chinese-only ([CHANGELOG.zh.md](./CHANGELOG.zh.md)). Future releases (v0.5.1+) will publish bilingually in both files.
>
> The Chinese version is comprehensive (2300+ lines covering every release's design rationale, root-cause analysis, and "wrong diagnosis lessons"). Translation is in progress as part of Phase D (full English content) per [docs/REFACTOR_PLAN_RULE_AND_I18N.md](./docs/REFACTOR_PLAN_RULE_AND_I18N.md).

## [Unreleased]

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
