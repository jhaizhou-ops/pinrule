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
- ✅ v0.5.18 — `bypass_karma` discriminator refinement (dogfood-found false positive): redirect target must actually be a karma path to count as bypass; symmetric tightening for `has_internal` field-name dimension. Caught while grep'ing `violations.jsonl > /tmp/x` for audit — per rule #7, didn't bypass; root-caused and fixed the regex instead
- ✅ v0.5.19 — `keep_pushing` Agent saturation declaration exemption (dogfood-found): strong saturation phrases (`任务饱和` / `卡在 X` / `明天接力` etc.) exempt the reflection nudge, paired with v0.4.41 user-stop exemption. Caught by the very Stop hook nudging this turn — Agent honestly declaring saturation was being blocked, would have incentivized fake "let me push forward" instead of truthful "I'm saturated." 6-month-old paired-asymmetry gap finally closed
- ✅ v0.5.20 — rule-10 self-audit follow-up: synced ARCH + HANDOFF for v0.5.19 (CHANGELOG had it, technical-archive docs lagged; caught by user-prompted self-audit)
- ✅ **v0.6.0 ⚠️ BREAKING** — Removed `karma.sticky` module, `.sticky_id` @property on `CheckHit`+`Violation`, `karma sticky` CLI subcommand, and `karma.rule`/`karma.cli` aliases (`Sticky` / `MAX_STICKY` / `StickyConfigError` / `EXAMPLE_STICKY*`). Data-compat shims stay (`sticky.yaml`→`rules.yaml` auto-migration, `violations.jsonl` `sticky_id` field fallback). Pure-deletion commit — v0.5.13/15 internal cleanup made it work without refactor. Deprecation cycle: 18 v0.5.x releases. 5 deletion-lock regression tests added (`test_v0600_*`).
- ✅ **v0.6.1 — Issue #1 real-user bug fix** — `record_edit` exempts non-code paths (README / CHANGELOG / docs/ / .gitignore etc.) from pushing `last_edit_ts`. Root cause: `has_recent_test_pass()` returns `last_test_pass_ts >= last_edit_ts`; any edit (even docs) flipped it to False, blocking `git commit` after `docker pytest` pass. Reporter's `_TEST_CMD_RE` fix was wrong layer; real fix is at `record_edit` time-tracking layer. 6 regression tests (4 exemption + 2 dual-control). Maintainer's first real-user dogfood loop: real-test in docker confirmed real bug existed but in a different layer than reported.
- ✅ **v0.7.0 — treat-root-cause refactor: rewrite "真X" defensive prefixes in karma source rule texts**. User caught Agent doing in-context mimicry from karma's own rule injection headers. Reverted attempted `defensive_prefix_stacking` engine check (treat-symptom approach) per user direction. ~140 occurrences rewritten across rule templates + locale + user-facing docs.
- ✅ **v0.7.1 — deep "真X" cleanup follow-up**. User sharpened v0.7.0 critique: synonym substitution (`真→实际/确实`) wasn't enough; defensive modifier itself is unnecessary in most contexts. 10-phase perl pipeline across 100 tracked files: 767 → 120 (84% reduction). 120 remaining all legitimate (named concept 真字狂魔 / eval term 真阳 / engineering dualism 真阻塞 / test fixtures / natural collocations 真心 真话). Doubled artifact bug fixed (`任务任务到饱和`). One batched commit per user "一次性修复完再提交" directive.

🔜 Next session — `karma audit` data drives the next refinement pass: chinese-plain 29 violations (English jargon residual), keep-pushing 79 violations (Agent stop-and-ask pattern after rule 8 became more salient). Both are pattern + Agent-behavior tuning, not deprecation cliffs.

## Why Chinese is the primary internal handoff language

The author and the karma project's primary AI collaborator (Claude Code) work in Chinese for thinking depth (the author finds it faster to think in Chinese for design reflection). The handoff document captures these reflections, decision context, and "wrong diagnosis lessons" — translating each lesson loses nuance.

If you're an English contributor and want to understand a specific historical decision, use any LLM-based translation on the relevant section in [HANDOFF.zh.md](./HANDOFF.zh.md), or open an issue asking the author/maintainer to translate a specific section.

## For future English bilingual handoff (post-v0.5.3)

After Phase D (full English content) lands, future handoff entries will be bilingual. The historical Chinese-only entries will remain as-is for accuracy preservation.
