# Changelog

**[🇬🇧 English (current)](./CHANGELOG.md) · [🇨🇳 中文](./CHANGELOG.zh.md)**

pinrule's release notes, one line per version. Versioning follows [SemVer](https://semver.org/). For full design rationale and root-cause analysis per release, see the [git log](https://github.com/jhaizhou-ops/pinrule/commits/main) — every commit message carries the full reasoning.

Releases from v0.5.1 onward publish bilingually in both files. Earlier history (v0.1.0 – v0.5.0) is in [`CHANGELOG.zh.md`](./CHANGELOG.zh.md) only.

## [Unreleased]

## [0.16.14] — 2026-05-17 — README polish + two external review fixes + `PINRULE_HOME` sandbox regression-test lockdown (851 tests).
## [0.16.13] — 2026-05-17 — 4 check false-positive fixes (long_term negation context / markdown code blocks / chinese_plain inline backtick / full-width punctuation) with ground-truth regression tests.
## [0.16.12] — 2026-05-17 — `pinrule init` reinstall-detection root cause fix (executable-bit check parity with doctor) + verbose "what's missing" reasons.
## [0.16.11] — 2026-05-17 — `PINRULE_HOME` becomes a true sandbox: install root, hook wrappers, settings, skill files, and Cursor rules all anchor under the env path.
## [0.16.10] — 2026-05-17 — 4 audit fixes: dead `trigger_key` populated, post_tool_use catchup loud-failure, unknown-command single-line error, test fixture true sandbox.
## [0.16.9] — 2026-05-17 — Round-3 audit medium-priority batch: `i18n.tr()` stderr warning on format failure, session-state lock cleanup, locale phrasing fix, missing `cursor_timeout` keys.
## [0.16.8] — 2026-05-17 — EN rule template `chinese-plain-no-jargon` → `plain-language-no-jargon` (real localization, not Chinese-rule-with-English-text).
## [0.16.7] — 2026-05-17 — Bilingual default rule symmetry: zh and en templates both ship 7 rules (was 7/5 asymmetric).
## [0.16.6] — 2026-05-17 — 2-round multi-agent code audit P0/P1 batch fix: Stop hook TOCTOU race, fail-open contract for all hook entries, Cursor backend `post_install_message` merge.
## [0.16.5] — 2026-05-17 — Fix issue #12: `karma` → `pinrule` migration residue cleanup (daemon kill, stale .pyc, old CLI entry).
## [0.16.4] — 2026-05-17 — Demo SVG real content corrections + `release-finalize.sh` PyPI verify step.
## [0.16.3] — 2026-05-17 — Demo SVG re-paced for human reading speed (~20s, was 42s).
## [0.16.2] — 2026-05-17 — Demo SVG real timing root-cause fix (termtosvg `-M -m` unit is milliseconds, not seconds — was 0.5s flash).
## [0.16.1] — 2026-05-17 — `install-hooks` defaults to all backends + demo SVG re-pace + scene-5 fixture fix.
## [0.16.0] — 2026-05-17 — **renamed karma → pinrule**: fresh PyPI package, fresh brand, no legacy karma migration.
## [0.15.1] — 2026-05-17 — Branding consistency sweep + reproducible perf measurement script + backend capability matrix.
## [0.15.0] — 2026-05-17 — Codex native hook surface alignment + intervention semantics parity with Claude.
## [0.14.0] — 2026-05-17 — Shared `~/.pinrule` home dir across all backends + Cursor native event surface.
## [0.13.6] — 2026-05-17 — Cursor functional parity with Claude across all 8 hook positions.
## [0.13.3] — 2026-05-17 — Cursor ↔ Claude hook wrapper parity (8/8 wrappers).
## [0.13.2] — 2026-05-17 — Drop Gemini CLI backend, focus on Claude Code / Codex CLI / Cursor.
## [0.13.1] — 2026-05-17 — Cursor dogfood follow-ups: `beforeSubmitPrompt` mapping + transcript requirement.
## [0.13.0] — 2026-05-17 — Anchor optimization: ~10× per-turn token cost reduction via compact anchor format.
## [0.12.3] — 2026-05-17 — Cursor native `hooks.json` schema fixes from real dogfood findings.
## [0.12.2] — 2026-05-17 — Drop `sticky.yaml` legacy fallback (no user migration needed).
## [0.12.0] — 2026-05-17 — Cursor backend support, 4th AI client wired end-to-end.
## [0.11.4] — 2026-05-17 — Bilingual hook output i18n + EN response-level `long-term-fundamental` pattern + first community PR #7 + 5-scene bilingual demo.
## [0.11.3] — 2026-05-16 — `pinrule audit --days N` time-window filter so dogfood decisions aren't diluted by stale data.
## [0.11.2] — 2026-05-16 — CI regression fix from v0.10.6: turn/model advancement must happen before rules loading.
## [0.11.1] — 2026-05-16 — `deep-fix-not-bypass` L3 timing pattern: editing an unread file right after a test failure now blocks.
## [0.11.0] — 2026-05-16 — `long-term-fundamental` engine redesign: response-level phrasing patterns make the engine actually fire.
## [0.10.6] — 2026-05-16 — `emit_context_injection` / `emit_stop_block` backend contracts + `model_from_payload` hook integration tests.
## [0.10.5] — 2026-05-16 — 4-perspective cross-audit sweep: 10 findings fixed across docs / functional / state / boundary.
## [0.10.4] — 2026-05-16 — Prefer Codex payload model + OpenAI/Codex threshold table for cross-platform attention adaptation.
## [0.10.3] — 2026-05-16 — Codex simple pipe-read recognition + `user_stop_hints` "collaborative waiting" category + doc wording fix.
## [0.10.2] — 2026-05-16 — Codex closes gap to Claude parity: SessionStart + `exec_command` → Bash mapping + auto-trust onboarding.
## [0.10.1] — 2026-05-16 — Codex shell-as-Read full integration + cross-backend contract tests.
## [0.10.0] — 2026-05-16 — Backend architecture: `protocol_adapter` delegation layer + 6-method contract + Codex ownership boundary handoff.
## [0.9.16] — 2026-05-16 — Codex `apply_patch` envelope parser via real captured payload; config `DEFAULTS` no longer silent-drops user config.
## [0.9.15] — 2026-05-16 — Cross-model audit (GPT-5.5) caught 3 critical cross-backend protocol bugs (Claude-only assumptions hidden for entire repo lifetime).
## [0.9.14] — 2026-05-16 — Multi-agent cross-audit caught v0.9.13's own regression: `pre_tool_use` `update_state` not wrapped in try/except.
## [0.9.13] — 2026-05-16 — Comprehensive instrumentation audit: agent_id round-trip / turn-window off-by-one / `pre_tool_use` catchup-no-save / zh `weak_claims` coverage gap.
## [0.9.12] — 2026-05-16 — v0.9.11 audit `--by-check` data classification bug: hook fallback was dropping `trigger_key` on Violation write.
## [0.9.11] — 2026-05-16 — Observability: `pinrule audit --by-check` engine-check hit distribution + `/pinrule` no-arg defaults to this view.
## [0.9.10] — 2026-05-16 — Onboarding polish: rule summary shows first paragraph (not half-line) + footer with token-cost reassurance.
## [0.9.9] — 2026-05-16 — Onboarding: `pinrule init` shows default rules summary so Agent-assisted install can relay it.
## [0.9.8] — 2026-05-16 — Cross-process concurrency race + API-enforced atomicity via `update_state(sid, fn)`.
## [0.9.7] — 2026-05-15 — `PINRULE_HOME` isolation broken in bypass detection + v0.6.0 user-facing sticky residue + regression mechanism.
## [0.9.6] — 2026-05-15 — 5th independent CI failure: v0.6.0 BREAKING rename leftover in `verify wheel` step.
## [0.9.5] — 2026-05-15 — 4th independent CI failure: tests assumed zh locale, CI runs en.
## [0.9.4] — 2026-05-15 — 3rd CI failure: mypy type error in `signals.py`.
## [0.9.3] — 2026-05-15 — Actually green up CI: 3 more dead-code items + vulture whitelist.
## [0.9.2] — 2026-05-15 — `test_compact_hooks.py` hardcoded `/Users/jhz/pinrule` path → dynamic resolution (issue #2 from @fyn1320068837-source).
## [0.9.1] — 2026-05-15 — v0.9.0 doc sync: PRD F2 / HOOK_CONFIGURATION_GUIDE / session_start docstring.
## [0.9.0] — 2026-05-15 — Injection architecture redesign: SessionStart full baseline + per-turn anchor + cumulative full reinject (**73% per-turn token saving**).
## [0.8.6] — 2026-05-15 — `agent_saturation` covers bare "真饱和" / English "genuinely saturated" — within-turn dogfood.
## [0.8.5] — 2026-05-15 — 3rd code review pass: 2 high-value cleanups, codebase confirmed clean.
## [0.8.4] — 2026-05-15 — v0.8.x cumulative doc sync + 1 dead-code leftover from v0.8.2 audit.
## [0.8.3] — 2026-05-15 — Long hook main functions split into helpers + cli.py import dedup.
## [0.8.2] — 2026-05-15 — Code audit: dead code purge + `sticky` → `rule` naming consistency + missing i18n + 1 bug fix.
## [0.8.1] — 2026-05-15 — `push_signals` i18n via YAML DSL: cartesian templates + word vocabularies, English Agent push phrases now recognized.
## [0.8.0] — 2026-05-15 — i18n signals: detection phrases externalized, English users fully covered, new languages contributable as a `.txt` file.
## [0.7.4] — 2026-05-15 — `keep_pushing` user-stop hint covers "satisfied / confirmation" phrases, not only "tired / dismissive".
## [0.7.3] — 2026-05-15 — Hand-audit every GitHub-visible doc: marketing fluff → natural, stale commands → current, archive status labeled.
## [0.7.2] — 2026-05-15 — Remove `chinese_plain` Check 3 reactive monitor: source treated, symptom monitor obsolete.
## [0.7.1] — 2026-05-15 — Deeper "真X" cleanup: drop unnecessary modifier synonyms across full repo.
## [0.7.0] — 2026-05-15 — Treat root cause: rewrite "真X" defensive prefixes in pinrule source rule texts.
## [0.6.1] — 2026-05-15 — `record_edit` exempts non-code paths; first real-user bug fix from issue #1.
## [0.6.0] — 2026-05-15 — ⚠️ **BREAKING**: remove backward-compat scaffolding for `sticky` → `rule` rename.
## [0.5.20] — 2026-05-15 — rule-10 self-audit follow-up: sync ARCHITECTURE + HANDOFF for v0.5.19.
## [0.5.18] — 2026-05-15 — `bypass_pinrule` distinguishes "read pinrule + write elsewhere" from "write to pinrule path".
## [0.5.17] — 2026-05-15 — README narrative rewrite: `/pinrule <NL>` skill promoted to top-level section.
## [0.5.16] — 2026-05-15 — `/pinrule <natural language>` skill works for real, multi-backend install.
## [0.5.15] — 2026-05-15 — v0.6.0 preparation: draft plan doc + internal `pinrule.sticky` → `pinrule.rule` import migration.
## [0.5.14] — 2026-05-15 — `pinrule-rule` skill teaches the modify recipe with existing commands, no new CLI added.
## [0.5.13] — 2026-05-15 — Audit-driven dedup: shared `is_python_c_command` + sticky_id alias cleanup + doctor skill check.
## [0.5.12] — 2026-05-15 — `pinrule init` auto-installs `pinrule-rule` skill + new `pinrule install-skill` command.
## [0.5.11] — 2026-05-15 — `skills/pinrule-rule.md` clarity audit, 5 gaps closed.
## [0.5.10] — 2026-05-15 — `pinrule --help` now lists `rule add` / `rule preview` subcommands.
## [0.5.9] — 2026-05-15 — Bash heredoc exemption lifted into `description_context.py`, shared by all Bash-aware checks.
## [0.5.8] — 2026-05-15 — testset check exempts Bash heredoc writes targeting description-context paths.
## [0.5.7] — 2026-05-15 — Locale-agnostic `trigger_key` field on `CheckHit` + `Violation` for cross-locale audit grouping.
## [0.5.6] — 2026-05-15 — `keep_pushing` `_PUSH_SIGNAL_RE` covers "next push point / next step is" planning phrases.
## [0.5.5] — 2026-05-15 — testset check adds `python -c` exemption (parity with `non_blocking` / `bypass_pinrule`).
## [0.5.4] — 2026-05-15 — Phase D wave 3: all 28 `CheckHit.trigger` strings switchable en/zh.
## [0.5.3] — 2026-05-15 — Phase D complete: all 28 check `suggested_fix` strings switchable en/zh.
## [0.5.2] — 2026-05-15 — i18n infrastructure + all hook injection texts switchable en/zh.
## [0.5.1] — 2026-05-15 — `pinrule rule add` natural-language rule input + i18n English-default docs.
## [0.5.0] — 2026-05-15 — **MAJOR BREAKING**: `sticky` → `rule` rename across the codebase.

**Earlier history (v0.1.0 – v0.4.x)** is in [`CHANGELOG.zh.md`](./CHANGELOG.zh.md) only.
