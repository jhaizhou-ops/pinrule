# karma Internal Development Handoff

**[🇬🇧 English (current)](./HOWTO.md) · [🇨🇳 中文](./HANDOFF.zh.md)**

> 📝 **Internal development handoff document.** This is a Chinese-primary handoff doc used by the author and Claude Code Agents collaborating on karma development. Records each milestone's known bugs / wrong-diagnosis lessons / TODOs for the next session.
>
> The Chinese version ([HANDOFF.zh.md](./HANDOFF.zh.md)) contains the complete handoff history. This English page provides only an entry point — for full internal context, refer to the Chinese version.

## Quick context for new contributors

If you're a new contributor reading this:

- **For user-facing docs**, see [README.md](../README.md) / [docs/PRD.md](./PRD.md) / [docs/ARCHITECTURE.md](./ARCHITECTURE.md)
- **For adding new AI client backend**, see [karma/backends/HOWTO.md](../karma/backends/HOWTO.md)
- **For understanding why current design is what it is**, see [docs/RULES_REDESIGN_PROPOSAL.md](./RULES_REDESIGN_PROPOSAL.md) + [docs/REFACTOR_PLAN_RULE_AND_I18N.md](./REFACTOR_PLAN_RULE_AND_I18N.md)
- **For change history**, see [CHANGELOG.md](../CHANGELOG.md)

## Current status

All v0.5.x phases delivered as of 2026-05-15 (12 releases v0.5.3 → v0.5.14 shipped in one focused session):

- ✅ v0.5.0 — `sticky` → `rule` rename across entire codebase, backward-compat `.sticky_id` alias preserved until v0.6.0
- ✅ i18n English-default documentation swap (README / PRD / ARCHITECTURE / SECURITY / CODE_OF_CONDUCT / CLAUDE / HOWTO / .github templates all English primary + `.zh.md` backup)
- ✅ v0.5.1 — `karma rule add` / `karma rule preview` CLI + Claude Code skill template at `skills/karma-rule.md` for natural-language rule input
- ✅ v0.5.2 — engineering-layer i18n: `karma/i18n.py` module with `tr(key, **fmt)` lookup + locale resolution chain + 5 hook injection paths switchable en/zh
- ✅ v0.5.3 + v0.5.4 — i18n full coverage: 28 `suggested_fix` + 28 `CheckHit.trigger` audit-log strings tr()-driven
- ✅ v0.5.5–v0.5.9 — dogfood-driven correctness fixes: testset `python -c` literal exemption, keep_pushing "next push point" planning phrases, locale-agnostic `trigger_key` audit grouping, Bash heredoc description-context exemption (testset local helper → `description_context.py` shared layer)
- ✅ v0.5.10–v0.5.12 — UX polish: `karma --help` lists `rule add/preview` subcommands, `skills/karma-rule.md` clarity audit (5 gaps closed), `karma init` auto-installs skill + new `karma install-skill [--force]` command
- ✅ v0.5.13 — audit-driven dedup: `is_python_c_command` helper extracted to `karma/checks/common.py` (was duplicated across 3 check files), 34 `.sticky_id` callsites cleaned to `.rule_id`, `karma doctor` reports skill installation status
- ✅ v0.5.14 — `karma-rule` skill teaches the modify recipe (`rule preview` → `rule remove && rule add`) via existing commands; no new CLI added, by user principle: don't grow surface area for rare flows
- ✅ v0.5.15 — v0.6.0 preparation; `docs/V0_6_0_PLAN.md` draft + internal 11+4 `from karma.sticky` import migration to `from karma.rule` so v0.6.0 can ship as pure deletion commit
- ✅ v0.5.16 — **`/karma <natural language>` skill actually triggers for the first time**; multi-backend install (Claude Code / Codex / Gemini with Markdown → TOML adaptation); honest disclosure that v0.5.1–v0.5.15 shipped skill at wrong path (`<name>.md` flat instead of required `<name>/SKILL.md` directory) so it never triggered
- ✅ v0.5.17 — README narrative rewrite (skill promoted to top-level section, not patch-style mention); PRD F5 rewritten; ARCHITECTURE + HANDOFF synced to v0.5.16 reality

🔜 v0.6.0 — remove the `.sticky_id` backward-compat alias on `CheckHit` + `Violation` (all internal callsites migrated in v0.5.13; external user code had one release cycle to update)

## Why Chinese is the primary internal handoff language

The author and the karma project's primary AI collaborator (Claude Code) work in Chinese for thinking depth (the author finds it faster to think in Chinese for design reflection). The handoff document captures these reflections, decision context, and "wrong diagnosis lessons" — translating each lesson loses nuance.

If you're an English contributor and want to understand a specific historical decision, use any LLM-based translation on the relevant section in [HANDOFF.zh.md](./HANDOFF.zh.md), or open an issue asking the author/maintainer to translate a specific section.

## For future English bilingual handoff (post-v0.5.3)

After Phase D (full English content) lands, future handoff entries will be bilingual. The historical Chinese-only entries will remain as-is for accuracy preservation.
