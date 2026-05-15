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

- ✅ karma v0.5.0 released — sticky → rule rename complete with backward-compat migration
- ✅ i18n English-default documentation swap complete (this turn 2026-05-15)
- 🔜 v0.5.1 pending — `karma rule add` CLI + Claude Code skill for natural-language rule input
- 🔜 v0.5.2 pending — engineering-layer i18n (`karma/i18n.py` + hook injection text translation)
- 🔜 v0.5.3 pending — full English text for all user-facing strings

## Why Chinese is the primary internal handoff language

The author and the karma project's primary AI collaborator (Claude Code) work in Chinese for thinking depth (the author finds it faster to think in Chinese for design reflection). The handoff document captures these reflections, decision context, and "wrong diagnosis lessons" — translating each lesson loses nuance.

If you're an English contributor and want to understand a specific historical decision, use any LLM-based translation on the relevant section in [HANDOFF.zh.md](./HANDOFF.zh.md), or open an issue asking the author/maintainer to translate a specific section.

## For future English bilingual handoff (post-v0.5.3)

After Phase D (full English content) lands, future handoff entries will be bilingual. The historical Chinese-only entries will remain as-is for accuracy preservation.
