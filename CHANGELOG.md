# Changelog

**[🇬🇧 English (current)](./CHANGELOG.md) · [🇨🇳 中文](./CHANGELOG.zh.md)**

Documents karma's important version changes. Versioning follows [SemVer](https://semver.org/).

> 📝 **English changelog status**: historical release notes (v0.1.0 through v0.5.0) are in Chinese-only ([CHANGELOG.zh.md](./CHANGELOG.zh.md)). Releases from v0.5.1 onward publish bilingually in both files.
>
> The Chinese version is comprehensive (2300+ lines covering every release's design rationale, root-cause analysis, and "wrong diagnosis lessons"). Backfilling the pre-v0.5.1 English history is a separate documentation effort, not part of the i18n refactor (which is fully complete — see [docs/REFACTOR_PLAN_RULE_AND_I18N.md](./docs/REFACTOR_PLAN_RULE_AND_I18N.md)).

## [Unreleased]

## [0.7.0] — 2026-05-15 (refactor — treat root cause: rewrite "真X" defensive prefixes in karma source rule texts)

### Root cause user identified

User caught a real architectural failure mode: I (the Agent under karma) was repeatedly stacking "真X" prefixes ("真根因 / 真违反 / 真饱和 / 真测") as defensive-evidence language. User's diagnosis was sharp — adding a `defensive_prefix_stacking` check function would have been **treating the symptom** while leaving the **source of the mimicry** untouched.

The source: karma's own rule texts and locale strings used "真X" patterns throughout (e.g. `rules.dev.example.zh.yaml` line "想清楚是真违反 / 修真根因", `data/locales/zh.yaml` reflection prompts mentioned "任务真饱和"). LLMs read the karma headers every turn and copied the prefix style in their responses — in-context mimicry of the rule text itself.

### Fix — multi-diversified rewrite of "真X" prefixes

Replaced ~140 occurrences across user-facing docs and templates with diversified natural expressions (avoiding new single-prefix mimicry pattern):

| Before | After |
|---|---|
| 真根因 | 根本原因 |
| 真违反 | 实际违反 |
| 真饱和 | 任务到饱和 |
| 真测 | 实测 |
| 真用户 | 真实用户 |
| 真完成 | 完整完成 |
| 真触发 | 实际触发 |
| 真生效 | 实际生效 |
| 真证据 | 实际证据 |
| 真复现 | 端到端复现 |
| 真识别 | 正确识别 |
| 真匹配 | 正确匹配 |
| 真豁免 | 实际豁免 |
| 真闭环 | 完整闭环 |
| 真深挖 | 深挖到底 |
| 真痛点 | 实际痛点 |
| 真做 | 真正做 |
| 真推 | 继续推 |
| ... | ... (30+ diversified substitutions) |

**Preserved as natural Chinese expressions** (NOT mimicry): `真实 / 真心 / 真人 / 真技术专名 / 真不确定 / 真读 / 真踩` — these are adjective/adverb modifiers in natural collocations, removing them would harm readability.

### Files touched

- Rule templates: `data/rules.dev.example.zh.yaml`, `data/rules.dev.minimal.example.zh.yaml`
- i18n locale: `data/locales/zh.yaml` (hook injection strings, reflection prompts, suggested_fix texts)
- User-facing docs (Chinese): `README.zh.md`, `CLAUDE.zh.md`, `SECURITY.zh.md`, `CODE_OF_CONDUCT.zh.md`
- Internal docs (Chinese): `docs/PRD.zh.md`, `docs/ARCHITECTURE.zh.md`, `docs/V0_6_0_PLAN.zh.md`, `docs/REFACTOR_PLAN_RULE_AND_I18N.zh.md`, `docs/RULES_REDESIGN_PROPOSAL.zh.md`, `karma/backends/HOWTO.zh.md`

### What did NOT happen (correctness restraint)

- **Did not add `defensive_prefix_stacking` engine-layer check** — initially started but reverted after user pointed out it's a treat-symptom reaction. The reactive monitor would have caught Agent symptoms while leaving the karma-itself-induced mimicry source intact. Correct fix is at the source text level.
- **Did not touch `karma/*.py` source code comments** (~200 occurrences) — these don't enter Agent prompt context, so they don't drive mimicry. Lower-priority cleanup deferred to v0.7.1+.
- **Did not touch CHANGELOG / HANDOFF historical entries** — rule 5 (eval cleanliness) applies metaphorically: historical archive entries shouldn't be rewritten retroactively.

### Verification

- `pytest`: 429/429 passing (no code change to test logic — pure text content of templates / docs)
- `ruff`: 0 issues
- Mimicry source reduction: rule text + i18n + user-facing docs total "真X" mimicry-style prefixes from ~140 → ~60 (natural language modifiers, not mimicry)

### Real karma value

User identified this as a **真根因 vs 真表征** distinction (... using the exact pattern karma was inducing — confirming the source is the rule text itself, not the Agent's instinct). The fact that even a careful Agent under heavy rule context drifts toward "真X" style speaks to how strong in-context mimicry is from rule text → response text. Cleaning the source is the only durable fix.

## [0.6.1] — 2026-05-15 (fix — `record_edit` exempts non-code paths; first real-user bug from issue #1)

### Real-user bug fix — docker pytest + edit README + git commit no longer blocked

**Bug** (issue #1, real user `@fyn1320068837-source`): `docker exec <container> python -m pytest tests/` passes (e.g. 1190 passed) → user edits any file (even README.md / .gitignore / IDE auto-save) → `git commit` blocked by `loud-failure-with-evidence` with "no recent passing-test evidence."

**Root cause** (real-test reproduced): `has_recent_test_pass()` returns `last_test_pass_ts >= last_edit_ts`. Any `record_edit()` call pushes `last_edit_ts` to "now," instantly flipping `has_recent_test_pass` to False — including edits to documentation, `.gitignore`, `LICENSE` etc. that have zero impact on whether pytest needs re-running. The by-intent design ("changed code without re-testing → block commit") was over-applied to non-code edits.

The reporter's proposed fix (`_TEST_CMD_RE` adding optional docker prefix) addressed the wrong layer — the regex already matches `docker exec ... pytest` correctly (4-layer end-to-end test confirms). Real fix needed at the `record_edit` time-tracking layer.

### Fix

`karma/session_state.py` adds `_NON_CODE_EDIT_RE` exemption list — `record_edit()` no longer pushes `last_edit_ts` when the file is documentation / metadata / top-level repo text:

- Documentation suffixes: `.md` / `.rst` / `.txt` / `.markdown` / `.adoc`
- Metadata files: `.gitignore` / `.gitattributes` / `.editorconfig`
- Top-level path patterns: `docs/` / `.github/` directories; root-level `CHANGELOG` / `README` / `LICENSE` / `CONTRIBUTING` / `CODE_OF_CONDUCT` / `SECURITY` / `HANDOFF` (with any extension)

**Still invalidates** (by-intent preserved):
- `src/**/*.py` / business code → must re-run pytest before commit
- `tests/**/*.py` / test files → changed tests means tests haven't run on the new versions
- `*.yaml` / `*.toml` / production config / build files → re-test before commit

### Verification

- 6 new regression tests in `tests/test_session_state.py` (`test_v061_*`):
  - 4 exemption cases: README.md / CHANGELOG.md / docs/*.md / .gitignore all keep `has_recent_test_pass = True` after edit
  - 2 dual-control cases: src/*.py and tests/*.py still flip to False (preserve by-intent design)
- `pytest`: 429/429 passing (423 prior + 6 new)
- `ruff`: 0 issues

### Real-user collaboration value

karma's first real outside contributor (`@fyn1320068837-source`) reported a bug they actually hit in their `henghai-backend` workflow — `docker exec container python -m pytest` + edit + commit. Their initial root-cause diagnosis ("regex doesn't match docker prefix") was wrong, but the bug itself was real. End-to-end docker pytest testing on the maintainer's machine reproduced the actual bug in Candidate A scenario (`last_edit_ts > last_test_pass_ts` after non-code edit). v0.6.1 fixes the real root cause at the right layer.

Issue #1 closed by this release — full thread documents the real-user collaboration → real-test → real-root-cause arc.

## [0.6.0] — 2026-05-15 ⚠️ BREAKING — Remove backward-compat scaffolding for `sticky` → `rule` rename

### What's removed (breaking)

- **`karma.sticky` module** — `from karma.sticky import ...` now raises `ModuleNotFoundError`. Migration: `from karma.rule import ...` (identical exports).
- **`Violation.sticky_id` @property** — `violation.sticky_id` raises `AttributeError`. Migration: use `.rule_id`.
- **`CheckHit.sticky_id` @property** — `hit.sticky_id` raises `AttributeError`. Migration: use `.rule_id`.
- **`karma sticky <subcommand>` CLI** — exits 1 with hint: `💡 你是不是想用 karma rule？`. Migration: use `karma rule list / edit / remove / add / preview`.
- **`karma.rule` aliases** — `Sticky`, `MAX_STICKY`, `StickyConfigError` removed. Migration: `Rule`, `MAX_RULES`, `RuleConfigError`.
- **`karma.cli` aliases** — `EXAMPLE_STICKY`, `EXAMPLE_STICKY_MINIMAL` removed (internal symbols, unlikely to affect users).

### What stays (data-compat preserved forever)

These are not deprecation aliases — they handle real on-disk user data and stay in karma indefinitely:

- **`sticky.yaml` → `rules.yaml` auto-migration** in `karma init` — users upgrading from v0.4.x still have `sticky.yaml`; karma silently moves it to `rules.yaml` with `.bak` backup.
- **`violations.jsonl` `sticky_id` field fallback** — historical jsonl rows from v0.4.x have `sticky_id` instead of `rule_id`; `karma audit` / `stats` still read them correctly via `_extract_rule_id`.
- **`STICKY_PATH` internal constant** in `karma.cli` — backward-compat path alias to `rule.DEFAULT_PATH`. Used by tests; no migration required.

### Why this release

v0.5.0 (2026-05-15 earlier today) renamed `sticky` → `rule` codebase-wide and shipped backward-compat aliases so user scripts wouldn't break immediately. The deprecation warning ran for one full release cycle (v0.5.x: 18 releases). v0.6.0 cliff arrives per the plan in [`docs/V0_6_0_PLAN.md`](./docs/V0_6_0_PLAN.md).

Internal karma code stopped using the aliases entirely in v0.5.13 (`.sticky_id` attribute access) and v0.5.15 (`from karma.sticky` imports). v0.6.0 is a **pure deletion commit** — no refactor logic, just removal.

### Migration cookbook for external users

Most user scripts using karma are 1-line mechanical fixes:

```python
# Before (any v0.5.x — warned)
from karma.sticky import Sticky, MAX_STICKY, StickyConfigError
violation.sticky_id  # works with warning

# After (v0.6.0+)
from karma.rule import Rule, MAX_RULES, RuleConfigError
violation.rule_id  # required
```

```bash
# Before
karma sticky list

# After
karma rule list
```

### Verification

- 5 new deletion-lock tests in `tests/test_sticky.py` (`test_v0600_*`):
  - `import karma.sticky` raises `ModuleNotFoundError` ✓
  - `Violation.sticky_id` raises `AttributeError` ✓
  - `CheckHit.sticky_id` raises `AttributeError` ✓
  - `karma.rule.Sticky` / `MAX_STICKY` / `StickyConfigError` are `hasattr() == False` ✓
  - `karma sticky list` subprocess exits 1 with `"karma rule"` in stderr ✓
- `pytest`: 423/423 passing (418 prior + 5 new)
- `ruff`: 0 issues
- Cumulative: from this morning's v0.5.0 rename to tonight's v0.6.0 cliff, **20 releases shipped in a single day** — the full sticky → rule rename + 1-cycle deprecation + cliff arc lives in `git log v0.5.0..v0.6.0`.

## [0.5.20] — 2026-05-15 (docs — rule-10 self-audit follow-up: sync ARCHITECTURE + HANDOFF for v0.5.19)

### Why this micro-release

User asked me to self-audit whether the past 4 releases honored rule 10 ("after every commit, sync all affected docs to latest"). The audit found one real omission: **v0.5.19 shipped without updating `docs/ARCHITECTURE.md` milestone table or `docs/HANDOFF.md` current status**. The CHANGELOG had the entry, but the technical-archive docs did not. Rule 10's exception ("internal refactor → only update CHANGELOG + HANDOFF") was misapplied — HANDOFF was specifically called out as still-required.

### What changed

- `docs/ARCHITECTURE.md` + `.zh.md` — milestone table gains v0.5.19 row (saturation exemption rationale + paired-asymmetry note with v0.4.41)
- `docs/HANDOFF.md` — current status section gains v0.5.19 entry (dogfood trigger context: caught by the same Stop hook v0.5.19 was fixing)

### Audit summary (full)

| Rule-10 requirement | v0.5.16–19 result |
|---|---|
| ① after-commit doc audit | ✅ for v0.5.16/17/18; ❌ for v0.5.19 (fixed by this release) |
| ② "feature as subject, version as clause" | ✅ in README hero, `/karma` section, PRD F5; ARCHITECTURE milestone table is patch-style by format (acceptable — milestone tables are chronological by nature) |
| ③ flagship features in README top | ✅ v0.5.16 skill promoted to hero + Real-problems row + new top-level section |
| ④ bilingual `.md` + `.zh.md` sync | ✅ for README/PRD/ARCH/HANDOFF on v0.5.16-18; ❌ for v0.5.19 (fixed) |
| ⑤ internal-refactor exception | ✅ v0.5.18/19 correctly skipped README/PRD (no user-visible CLI change), but HANDOFF was still required and missed for v0.5.19 |

Net: 4/5 honored across the 4 releases. The miss was caught by explicit rule-10 self-audit and fixed within minutes — exactly the dogfood-driven correction loop rule 10 was written to enable.

### Verification

- `pytest`: 418/418 passing (pure docs, no code change)
- `ruff`: 0 issues

## [0.5.18] — 2026-05-15 (fix — `bypass_karma` distinguishes "read karma + write elsewhere" from "write to karma path")

### Root-cause fix triggered by live dogfooding false-positive

While inspecting `karma audit` data for today's violation patterns, ran `grep deep-fix ~/.claude/karma/violations.jsonl > /tmp/df_audit.jsonl` to extract a few rows for analysis — got blocked by `bypass_karma` as "writing to karma internal state." Per rule #7, didn't bypass; root-cause-fixed instead.

**What was wrong**: the old `bypass_karma` rule was `(has_internal OR has_state_path) AND has_write` — any command containing a karma path AND any redirect/write op triggered the rule, even if the redirect target was `/tmp/`. Reading karma state into a tmp file for analysis is a legitimate audit pattern, but the rule conflated "karma path appears in command" with "writing to karma path."

**Fix**: extracted redirect targets via `_BASH_REDIR_TARGET_RE` (already shared in `description_context.py` from v0.5.9), check whether any target matches `_KARMA_STATE_PATH_RE`. The new rule becomes `(has_internal OR has_state_path) AND write_to_karma_state` where `write_to_karma_state = has_python_write OR (any redirect target IS a karma path)`.

**Behavior diff** (verified by 4 new regression tests):

| Command | v0.5.17 | v0.5.18 |
|---|---|---|
| `grep ~/.claude/karma/violations.jsonl > /tmp/x` | ❌ blocked (false positive) | ✓ exempt |
| `cat ~/.claude/karma/violations.jsonl \| python3 -m json.tool > /tmp/pretty.json` | ❌ blocked | ✓ exempt |
| `echo '{}' >> ~/.claude/karma/violations.jsonl` | ✓ blocked | ✓ blocked (real write-to-karma) |
| `python -c "open('.claude/karma/x', 'w').write(...)"` | ✓ blocked | ✓ blocked (python write API) |
| `echo 'last_test_pass_ts=999' > /tmp/inject.txt` | ✓ blocked | ✓ exempt (target is /tmp, not karma) — symmetric with state_path dimension |

The `has_internal` (field-name reference) dimension also tightened symmetrically: writing `last_test_pass_ts=...` to `/tmp/` doesn't affect karma state, so it's now exempted. Writing the same string to `~/.claude/karma/...` is still blocked because the redirect target is a karma path.

### Why this matters

This was karma's own false-positive blocking real audit work — exactly the kind of "karma overcorrects → user forced to bypass" failure mode rule #7 was written to prevent. Caught the trigger, didn't bypass, dug into the regex, fixed the discriminator. Two new test cases lock in both the new exemption (`test_v0518_read_karma_state_write_tmp_exempted`) and the preserved blocking (`test_v0518_redirect_target_is_karma_path_still_blocked`).

### Verification

- 4 new regression tests in `tests/test_bypass_karma.py` covering: read-karma-write-tmp exempted, pipe-to-python exempted, write-to-karma still blocked, internal-field-name + write-to-tmp now exempted (symmetric with state_path fix), internal-field-name + write-to-karma still blocked
- `pytest`: 416/416 passing (411 prior + 5 new — Wait, math: 411 + 4 added but one renamed = net 4 new). Actually 411 → 416 = 5 new. Two were `internal_field_name_*` variants (one expects exempt, one expects blocked); other three: `read_karma_state_write_tmp_exempted`, `cat_karma_pipe_to_python_exempted`, `redirect_target_is_karma_path_still_blocked`.
- `ruff`: 0 issues
- All 4 prior `test_*_real_bypass_*` tests remain green — the fix didn't loosen real-write detection

## [0.5.17] — 2026-05-15 (docs — README narrative rewrite: `/karma <NL>` skill promoted to top-level section, not patch-style mention)

### Why this release

v0.5.16 shipped the working skill but README still treated it as a patch-style mention buried inside the "Customize your own rules" section — the "Agent writes the rule for you" capability was a one-line aside while the "Agent complies with rules" capability owned the entire hero/pitch. This release rewrites README narrative so both sides of karma's loop get equal billing on the landing page, per user principle:

> "对外说明文档一定不要只是打补丁，要很「爆款」的融入整体说明，重要亮点和功能说明展示好。"
> (Don't just patch — fold new capabilities into the overall narrative; flagship features deserve flagship presentation.)

### What changed (README + README.zh.md, symmetric)

**1. Hero opening rewritten** — was a single "monitor Agent" paragraph + violation-rate stat. Now explicitly frames karma as "two sides of the same loop": 🛡️ pin rules / Agent complies + ✨ tell karma in plain words / Agent writes the rule. Both with concrete one-liners.

**2. Table of contents** — adds `/karma natural-language rule input` as a top-level entry alongside install / how-it-works / customize.

**3. Real-problems table** — adds a 7th row covering the actual pain point that v0.5.16 solves ("I want to add a rule but writing yaml is too heavy / my phrasing doesn't make Agent comply"), so the value-prop appears in the same comparative format as the other 6 pains.

**4. Quick install section** — adds a one-line callout that `karma init` auto-installs the skill across all three backends (no extra step), so users know it ships ready-to-use, not as an opt-in upgrade.

**5. New top-level section `/karma <natural language>` — Agent writes the rule for you** — replaces the 20-line "Recommended:" sub-section that v0.5.15 had patched into "Customize." New section is 55+ lines: 7-step workflow visualization, "what the skill handles for you" 6-row table (tone / format / overlap / scope / locale / modify), "three backends, one command" install table, upgrade flow (`karma install-skill --force` / `--backend`).

**6. "Customize your own rules" reduced to a 1-line pointer** — directs users to the new top-level skill section, with a note that the manual-yaml fallback is for advanced users / no-skill environments. The yaml example block remains as fallback reference; the duplicated "Recommended:" content from v0.5.15 is removed (no more redundancy).

### Other docs synced

- **`docs/PRD.md` + `.zh.md` F5** — Rewritten with v0.5.16 multi-backend reality. Old version still claimed "v0.5.1+" availability; new version flags "v0.5.16+ — first release where the skill actually triggers" with the honest history disclosure.
- **`docs/ARCHITECTURE.md` + `.zh.md`** — Milestone table gains v0.5.15 / v0.5.16 / v0.5.17 rows.
- **`docs/HANDOFF.md`** — Current status updated to v0.5.17.

### Verification

- `pytest`: 411/411 passing (pure docs, no code change)
- `ruff`: 0 issues
- Manual sanity: TOC anchor `#karma-natural-language--agent-writes-the-rule-for-you` resolves; sectioning makes sense for a first-time reader landing on the README

### Trigger

This release was triggered by user typing `/karma 每次commit以后必须更新所有 github 文档至最新版本...要很「爆款」的融入整体说明` — the karma skill's first live end-to-end use added rule 10 (`docs-sync-after-commit`), and this commit is the immediate first application of that newly-added rule.

## [0.5.16] — 2026-05-15 (feat — `/karma <natural language>` skill works for real, multi-backend install)

### Why this release is big

Live-session deep audit (driven by user asking "can we simplify `/karma rule X` to just `/karma X`?") surfaced that **karma skill has not actually been triggering since v0.5.1**. Root cause: Claude Code skill mechanism requires `<name>/SKILL.md` directory structure (not flat `<name>.md` file), the `name:` frontmatter field, and a single-token slash command (not multi-word `/karma rule`). v0.5.1 through v0.5.15 all shipped with the wrong assumption — manual CLI testing worked but skill auto-trigger never did.

This release rebuilds skill installation correctly across **3 backends**:

| Backend | Path | Format | Trigger |
|---|---|---|---|
| Claude Code | `~/.claude/skills/karma/SKILL.md` | Markdown + YAML frontmatter | `/karma <args>` |
| Codex CLI | `~/.agents/skills/karma/SKILL.md` (note: `~/.agents/` not `~/.codex/`) | Markdown | `/skills` menu, `$karma <args>` inline, or auto |
| Gemini CLI | `~/.gemini/skills/karma/SKILL.md` + `~/.gemini/commands/karma.toml` (dual-track) | Markdown (skill) + TOML (commands) | auto-trigger via skill, explicit `/karma <args>` via commands |

### What changed

**1. Repository skill source restructured** — `skills/karma-rule.md` (flat file, wrong) → `skills/karma/SKILL.md` (correct directory structure). Added required `name: karma` + `description: ...` frontmatter. Updated all `/karma rule X` references inside the skill body to `/karma X` to match the simplified trigger.

**2. New module `karma/skill_packaging.py`** — handles format conversion:
- `parse_frontmatter(md_text)` — extracts YAML frontmatter without requiring PyYAML dependency
- `markdown_to_toml(md_text)` — converts Markdown skill to Gemini CLI's `commands/*.toml` format (`description = "..."` + `prompt = """..."""`). Auto-translates `$ARGUMENTS` (Claude/Codex) ↔ `{{args}}` (Gemini) so the same skill source works across all three.

**3. `Backend` Protocol extended** with `skill_install_targets(skill_name="karma") -> list[tuple[Path, str]]`. Each backend declares its own install paths + content formats. Three implementations:
- `ClaudeCodeBackend` → 1 target (Markdown)
- `CodexBackend` → 1 target (Markdown, `~/.agents/` path)
- `GeminiCLIBackend` → 2 targets (Markdown skill + TOML commands)

**4. CLI multi-backend support**:
- `_install_karma_skill_multi_backend(force, backend_filter)` — central install function; iterates all detected backends and writes each target with format-appropriate content
- `cmd_install_skill(force, backend)` — `karma install-skill` now installs to all by default; `--backend claude-code|codex|gemini-cli` targets one
- `cmd_init` — auto-installs to all backends, prints `创建 [<backend>] karma skill: <path>` per target
- `cmd_doctor` — reports multi-backend skill status (✓ 最新 / ⚠ 跟当前版本不一致 / 未装), one line per (backend, path) pair

**5. `pyproject.toml`** — `force-include` updated `skills/karma/SKILL.md` so `pip install karma` ships the correct file.

### Live verification (this session)

After installing v0.5.16 on the author's machine, the Claude Code session running this very release surfaced this message in `SessionStart` hook context:

> The following skills are available for use with the Skill tool:
> - **karma**: Natural-language karma rule input — refine user's plain description into karma's validated rule structure, preview, confirm, and add to rules.yaml. Use when the user types `/karma <natural language describing a rule preference>`.

**This is the first time karma skill has actually been seen by Claude Code in any session.** v0.5.1 through v0.5.15 it sat in the wrong path silently.

### Verification

- 7 new regression tests in `tests/test_cli.py` (`test_v0516_*`):
  - 4 backends in init flow / second-run idempotency / user-modified preservation / force-overwrite / `--backend` filter / missing source / doctor multi-backend reporting
- `pytest`: 411/411 passing (404 prior + 7 new)
- `ruff`: 0 issues
- Live install on author's machine: 4 paths verified (Claude/Codex/Gemini-skill/Gemini-toml all present, sizes 16944/16944/16944/16941 bytes — toml slightly smaller from removed frontmatter)

### Migration notes for v0.5.15 → v0.5.16 users

- Old `~/.claude/skills/karma-rule.md` (flat file from v0.5.12-15 install) is dead weight; you can `rm` it
- New skill auto-installs on next `karma init` or `karma install-skill`
- The `/karma rule X` slash command never worked (despite docs saying it did); the new `/karma X` does, in Claude Code at least
- Codex / Gemini support is best-effort — Codex needs `/skills` menu or `$karma` inline; Gemini supports explicit `/karma` via the TOML commands path

### What v0.5.1 to v0.5.15 docs claimed vs. reality (sticky #4 honest disclosure)

The v0.5.1 release notes claimed "Claude Code skill template at `skills/karma-rule.md` for natural-language rule input." It described a `/karma rule <NL>` trigger. **None of that actually worked end-to-end** until this release. Skill flow worked only when the user manually invoked the underlying `karma rule add --from-yaml` CLI — the natural-language → skill auto-refinement path was vapor. Apologies for the misleading docs.

## [0.5.15] — 2026-05-15 (chore — v0.6.0 preparation: draft plan doc + internal `karma.sticky` → `karma.rule` import migration)

### Why this release

v0.5.13 audit ostensibly "cleaned all `.sticky_id` callsites" but only at the attribute level. A follow-up audit while drafting the v0.6.0 plan surfaced a deeper miss: **11 internal `from karma.sticky import ...` statements** still lived in karma's own source code (4 in `cli.py`, 6 in `hooks/*.py`, plus self-references) — plus parallel imports in 4 test files. v0.6.0 cannot safely delete `karma/sticky.py` until karma itself stops importing it. This release fixes that.

### Two things in this release

**1. Draft v0.6.0 plan doc** ([`docs/V0_6_0_PLAN.md`](./docs/V0_6_0_PLAN.md) + [`.zh.md`](./docs/V0_6_0_PLAN.zh.md))

Spelled-out deprecation contract before the cliff. Three categories:

- **Group A** — internal scaffolding (aliases referenced only by karma itself). Zero external impact.
- **Group B** — public API breaking changes (`karma.sticky` module / `.sticky_id` @property / `karma sticky` CLI alias). Each deprecated since v0.5.0; v0.6.0 cliff.
- **Group C** — on-disk data migration (`sticky.yaml` → `rules.yaml`, legacy `violations.jsonl` `sticky_id` field fallback). **Stays forever** — these handle real user data, not API surface.

Includes execution order, test coverage expectations, risk assessment, and 2 open questions (whether `karma sticky` CLI alias deserves an extra release cycle of grace; whether `chinese_plain_no_jargon` default behavior for non-Chinese users is in scope — answered "no" to both, deferred).

**2. Pre-v0.6.0 import migration** (executed this release)

Replaced `from karma.sticky import X` → `from karma.rule import X` across:

- `karma/cli.py` (4 occurrences)
- `karma/hooks/post_tool_use.py`, `karma/hooks/stop.py`, `karma/hooks/pre_tool_use.py`, `karma/hooks/subagent_start.py`, `karma/hooks/user_prompt_submit.py`, `karma/hooks/pre_compact.py`, `karma/hooks/session_start.py` (7 hook files, 7 occurrences total)
- `tests/test_violations.py`, `tests/test_sticky.py`, `tests/test_paths.py`, `tests/test_cli.py`, `tests/test_post_tool_use_reinject.py` (5 test files)
- `mock.patch("karma.sticky.load", ...)` patterns in `test_post_tool_use_reinject.py` → `mock.patch("karma.rule.load", ...)` (4 patches) — Python module aliasing means patching the alias namespace doesn't reach the real module if the consumer imports from the real module directly

### Verification

- `pytest`: 410/410 passing
- `pytest -W error::DeprecationWarning`: 410/410 passing — **zero `karma.sticky` deprecation warnings** triggered from karma's own code or tests
- `ruff`: 0 issues
- `grep -rn "from karma.sticky" karma/ tests/` returns only the `karma/sticky.py` shim's own docstring (the shim's purpose is to be a thing to import; it doesn't import itself)

### v0.6.0 readiness status

After this release, deleting `karma/sticky.py` in v0.6.0 will not break any internal callsite. Same for the 4 class/property aliases (`MAX_STICKY`, `Sticky`, `StickyConfigError`, `EXAMPLE_STICKY*`) — they have zero internal users now. The `.sticky_id` @property on `CheckHit` + `Violation` already had zero internal users since v0.5.13. The `karma sticky <subcommand>` CLI alias has zero internal users (it's an entry-point branch in `cli.py:1183`).

In short: v0.6.0 can ship as a pure deletion commit, no refactor required.

## [0.5.14] — 2026-05-15 (docs — `karma-rule` skill teaches the modify recipe with existing commands, no new CLI added)

### Why this release

Live dogfooding turned up a real gap: when an Agent walks through Step 2 of the skill and the decision table says "modify existing rule," the skill stopped there — `karma rule edit` was mentioned but that command launches `$EDITOR` for the user (not Agent-automatable). The Agent had no clear path to "modify" using the CLI surface it has, which led me (the Agent dogfooding right now) to propose adding a new `karma rule replace` command. User pushed back: don't grow surface area; teach the existing commands clearly.

### What changed

Pure skill documentation — **zero new CLI commands, zero new code**. Closes the modify gap entirely through clearer instructions.

- **New "How to modify an existing rule (replace / merge / extend scope)" section** under Step 2, with:
  - The 3-step recipe (draft yaml → preview → `remove && add` swap)
  - A 4-row "common modify shapes" table (Replace / Extend scope / Merge / Genuine purpose change) clarifying when to keep the `id` (almost always — keeps violation history linked) vs. when to use a new one
  - Explicit "why not `karma rule edit`" callout — it's a user escape hatch, not an Agent path
- **Step 6 expanded** with two branches (new rule vs. modify) showing exact commands
- **Honest atomicity caveat** — clarifies that `remove && add` is *not* a true transaction (if `add` fails after `remove` succeeded, the rule is gone); preview-first reduces but doesn't eliminate the risk; `cp rules.yaml rules.yaml.bak` is the cheap belt-and-suspenders. Original draft incorrectly claimed `&&` "ensured" atomicity — caught and corrected in this same commit (sticky #4: be honest about caveats).

### Why no new CLI command

User principle (from this session): "don't give users a pile of rarely-used skills/commands." Modifying = removing + adding; the existing commands compose. Adding `karma rule replace` would have been surface-area bloat with no real capability gain — the Agent reading the skill just needed the recipe documented.

### Verification

- skill: 269 → 302 lines (+33), 7 `### Step N` headings intact, 10 "modify" / "remove + add" / "How to modify" references in the doc
- `pytest`: 410/410 passing (unchanged — pure docs)
- `ruff`: 0 issues

### Also in this release

- `rule 9 lighthearted-vibe` modified in user's `~/.claude/karma/sticky.yaml` (out-of-tree user data, not in this commit): scope expanded from "during /karma rule conversations" to "整体说话方式", with a stronger dual clause "具体问题分析要认真深刻" replacing the milder "该严肃就严肃." This served as the dogfood that exposed the skill gap fixed here.

## [0.5.13] — 2026-05-15 (refactor — audit-driven dedup: shared `is_python_c_command` + sticky_id alias cleanup + doctor skill check)

### What this release closes

An end-of-day code audit surfaced 3 real debts. v0.5.13 pays them off in one clean release.

### F1 — `_LANG_C_HEAD_RE` was copy-pasted across 3 check files

`testset.py` / `bypass_karma.py` / `non_blocking.py` each defined the same regex `r"\b(?:python\d?|node|ruby|perl)\s+-[ce]\b"` independently. v0.5.9 lifted the parallel `_BASH_REDIR_TARGET_RE` into `description_context.py` but missed this one.

**Fix**: Added `is_python_c_command(cmd: str) -> bool` helper in `karma/checks/common.py` (correct home — sits alongside `_SHELL_INTERPRETER_RE`, `_HEREDOC_RE`, and other Bash-parsing utilities). All 3 checks now import and call `is_python_c_command(cmd_raw)` instead of holding their own pattern.

### F2 — `karma doctor` didn't report skill installation status

v0.5.12 added `karma install-skill`, but `cmd_doctor` only reported hook installation, not skill. A user running `karma doctor` after a clean install couldn't see whether `/karma rule <NL>` was actually wired up.

**Fix**: `cmd_doctor` now reports `karma-rule skill` status in three states:
- "存在 ✓ 最新" — installed and content matches the shipped version
- "存在 ⚠ 跟当前 karma 版本不一致" — installed but out of date (suggests `karma install-skill` to upgrade)
- "未装" — missing (suggests `karma install-skill`)

### F3 — 34 `.sticky_id` callsites would have broken at v0.6.0

v0.5.0 announced "sticky → rule renamed across entire codebase" but in practice 34 `.sticky_id` attribute accesses survived in `cli.py` (13), hooks (`pre_tool_use.py`/`stop.py`/`user_prompt_submit.py`: 19), and tests (6). They worked silently via the `@property def sticky_id: return self.rule_id` backward-compat alias on `Violation` and `CheckHit`. When v0.6.0 removes the alias (as documented in the dataclass comments), those call sites would have hard-failed in production code paths far from the test surface.

**Fix**: Batch `s/\b(\w+)\.sticky_id\b/$1.rule_id/g` across the 5 internal files. The `@property` alias stays in `violations.py` and `_types.py` so external user code keeps working until v0.6.0. Pure rename, no behavior change.

### Verification

- 1 new regression test in `tests/test_cli.py` (`test_v0513_doctor_reports_skill_status`) — covers all 3 doctor-skill states
- All 3 fixes coexist with existing tests: 409 → 410 (added one for F2)
- `pytest`: 410/410 passing
- `ruff`: 0 issues

### What the audit verified passed

- Zero TODO/FIXME/HACK residuals in tonight's diff (sticky #1 long-term-fundamental held)
- Zero weak claims ("应该可以"/"大概率") outside `evidence.py`'s detection patterns
- All 5 Bash-aware checks use unified `tool_name == "Bash"` guard
- v0.5.9 refactor cleanup was clean (no stale `_bash_writes_to_description_context` or `_DESC_CTX_PATH_RE` residuals)

## [0.5.12] — 2026-05-15 (feat — `karma init` auto-installs `karma-rule` skill + new `karma install-skill` command)

### feat — `/karma rule <NL>` flow now works out-of-box for new users

v0.5.11 audit surfaced the gap: `skills/karma-rule.md` was in the repo but not auto-installed to `~/.claude/skills/karma-rule.md`, so first-time users typing `/karma rule add a new rule about X` in Claude Code would get nothing — the skill needed manual copy. This release closes the gap.

### Changes

- **`karma init` now auto-installs the skill** at the end of its flow. Path: `~/.claude/skills/karma-rule.md`. First run prints `创建 karma-rule skill: <path>` plus the `/karma rule <NL>` usage tip.
- **New `karma install-skill [--force]` subcommand** for users who installed karma before v0.5.12 (or want to upgrade the skill after a clarity audit like v0.5.11). Without `--force`, conflicts are non-destructive — if the user has a locally-modified `karma-rule.md`, the new version writes to `karma-rule.md.new` and tells the user how to diff/merge. `--force` overwrites.
- **`pyproject.toml` `force-include`** now packages `skills/karma-rule.md` into the wheel so `pip install karma` works.
- **`karma --help`** lists the new `install-skill` subcommand with brief usage.

### Conflict handling (sticky #1: don't overwrite user changes silently)

- File doesn't exist → install, return `(True, "installed")`
- File exists + content identical → skip, return `(False, "up-to-date")`
- File exists + content differs + `force=False` → write `.md.new` sibling, return `(False, "exists-diff")`
- File exists + content differs + `force=True` → overwrite, return `(True, "force-overwritten")`
- Source missing (theoretically impossible in shipped wheel, but possible in dev install edge cases) → return `(False, "source-missing")`, `cmd_install_skill` exits 1, `cmd_init` warns but doesn't block

### Verification

- 5 new regression tests in `tests/test_cli.py`:
  - `test_v0512_init_auto_installs_karma_rule_skill` — first run installs ✓
  - `test_v0512_init_second_run_skill_up_to_date` — idempotent on second run ✓
  - `test_v0512_init_skill_user_modified_writes_new_file` — user changes preserved, `.md.new` written ✓
  - `test_v0512_install_skill_force_overwrites` — `--force` wins ✓
  - `test_v0512_install_skill_handles_missing_source` — graceful `exit 1` when source missing ✓
- `pytest`: 409/409 passing (404 prior + 5 new)
- `ruff`: 0 issues

## [0.5.11] — 2026-05-15 (docs — `skills/karma-rule.md` clarity audit, 5 gaps closed)

### docs — 5 clarity gaps in `/karma rule` skill template closed

Dogfood-driven audit. While walking through the `/karma rule` flow end-to-end (real natural-language input → CLI), 5 places where a first-time Agent could silently make the wrong call surfaced:

1. **Step 1 missed anchor-vs-scope ambiguity** — User phrasing "during scenario X, do Y" usually means "X is an example" not "Y only applies during X," but karma v2 is always-on injection (no scene routing). Skill now requires the Agent to surface this ambiguity verbatim instead of silently guessing scope. Also adds a one-off vs long-term tell list (`"for this PR" → one-off` / `"I always want" → long-term`) so the "is this karma-worthy at all" check is concrete.

2. **Step 2 had no overlap-decision standard** — Skill said "check existing rules" but gave no rule for what counts as overlap (id match? semantic similarity? keyword intersection?). Added a 4-row decision table covering 4 overlap cases with concrete actions (modify existing / two-option ask / mention keyword overlap / add fresh).

3. **Step 3 → Step 5 skipped user inline draft review** — Original flow went straight from "draft to temp file" → preview → user sees finished yaml. Users wanting wording tweaks had to make the Agent restart. Skill now requires showing a draft inline in Step 3 before writing to disk, with explicit "say so now if you want adjustments" callout.

4. **No locale-aware tone guidance** — Post v0.5.2 i18n made karma bilingual, but skill had English-only examples. Added explicit "write `preference` in the language the user is talking to you in; `violation_checks` function names stay English" rule. Points Chinese-locale Agents at `data/rules.dev.example.zh.yaml` as reference pattern source.

5. **Step 7 "when it takes effect" was buried** — Original skill had a standalone `## Restart Claude Code after karma rule add` section at the bottom, easy to miss. Moved the "takes effect on next UserPromptSubmit" notice inline into Step 7 as bullet 4, plus made the "suggest deletions" step concrete (name specific redundant pairs, not vague "review for duplicates"). Removed the standalone section.

3 new entries added to the `## Common mistakes to avoid` list at the bottom mirroring gaps 1, 4, and 3 so a quick scan catches the high-impact failure modes.

### Discovered (but not fixed in v0.5.11)

While auditing, also noticed `skills/karma-rule.md` is **not auto-installed** to `~/.claude/skills/karma-rule.md` by `karma init` — users have to copy it manually. This means today's `/karma rule <NL>` flow only works if the user knows about the manual install step. Not in scope for v0.5.11 (docs-only release), but worth a v0.5.12 `karma install-skill` or `karma init` extension.

### Verification

- skill structure intact: 7 `### Step N` headings present (was 7, still 7)
- Length: 225 → 269 lines (net +44, explicit guidance not bloat)
- No code changes — `pytest 404/404`, `ruff 0` unchanged

## [0.5.10] — 2026-05-15 (docs — `karma --help` now lists `rule add` / `rule preview` subcommands)

### docs — `karma --help` was hiding `karma rule add` / `karma rule preview`

A user-initiated dogfood test (running the v0.5.1 `karma rule` flow end-to-end for the first time) surfaced that `karma --help` still only listed `karma sticky list/edit/remove` — the new `rule add`, `rule preview`, and `rule list/edit/remove` subcommands shipped in v0.5.1 were fully implemented and dispatched correctly, but invisible from top-level help. A first-time user typing `karma --help` would have no idea `karma rule add` exists.

This release fixes the docstring at the top of `karma/cli.py` to:
- List all 4 `rule` subcommands (`list` / `edit` / `remove` / `add` / `preview`) with their flags (`--from-yaml <file>` / `--from-stdin`)
- Mention `karma sticky` as a deprecated alias removed in v0.6.0
- Add a footer pointer to the Claude Code `/karma rule <natural language>` skill workflow

The implementation has been working since v0.5.1; this is a pure documentation fix.

### Verified end-to-end (16 test cases)

- `karma rule preview --from-stdin` with valid yaml → schema check + injection preview render ✓
- `karma rule preview` error paths (missing id / nonexistent yaml file) → `exit 1` with `❌` message ✓
- `karma rule add --from-stdin` with valid yaml → schema validate + id-uniqueness + cap + REGISTRY check + write + report ✓
- `karma rule add --from-yaml <file>` with valid yaml → same flow ✓
- `karma rule add` duplicate id → `exit 1` ✓
- `karma rule add` unknown `violation_checks` function → `exit 1` with available-functions list ✓
- `karma rule add` schema error (missing preference) → `exit 1` ✓
- `karma rule add` invalid yaml → `exit 1` ✓
- `karma rule add` no flag → `exit 1` with usage prompt + `/karma rule` skill hint ✓
- `karma rule` no subcommand → `exit 1` with subcommand list ✓
- `karma rule foobar` unknown subcommand → `exit 1` ✓
- `karma rule list` shows newly-added rule ✓
- `karma rule remove <id>` removes the rule ✓
- `karma rule remove <id>` then `karma rule add` same id → succeeds ✓
- `rules.yaml` is truly persisted (grep verified line count = 7 after 2 adds to 5-minimal base) ✓

Plus `pytest` 404/404 + `ruff` 0 issues.

## [0.5.9] — 2026-05-15 (refactor — Bash heredoc exemption lifted into `description_context.py`, shared by all Bash-aware checks)

### refactor — `is_description_context(tool_name="Bash")` now supported

v0.5.8 promised this. v0.5.9 delivers: the Bash-heredoc-target-path exemption that lived locally in `testset.py` is now in `description_context.py`, and all Bash-aware checks (`long_term`, `testset`, etc.) that already call `is_description_context()` get the same treatment automatically.

- New `_classify_path(file_path) -> (bool, str)` helper in `description_context.py` (extracted from the original Write/Edit branch)
- `is_description_context()` now special-cases `tool_name == "Bash"` — scans the command for `>` / `>>` redirect targets and applies `_classify_path` to each; if any target is a description context, the whole call is exempt
- `testset.py` v0.5.8 local helper removed; behavior preserved by the new shared logic
- `long_term.py` automatically inherits — e.g. `echo "TODO: x" >> docs/CHANGELOG.md` is now exempt (was previously incorrectly blocked as `TODO` marker)

### Verification

- `pytest`: 404/404 passing (v0.5.8 tests still green — same test cases, now flow through the shared helper)
- `ruff`: 0 issues

## [0.5.8] — 2026-05-15 (fix — testset check exempts Bash heredoc writes targeting description-context paths)

### fix — `cat >> tests/test_x.py <<EOF ... case_id="..." ... EOF` false-positive

A v0.5.7 dogfooding session hit it: when appending the new v0.5.7 regression tests via `cat >> tests/test_checks.py <<'PY'`, the heredoc body contained `case_id = "a1b2c3d4..."` — meant as a test fixture literal — and got blocked as "test-set case ID hard-coded." Root cause: v0.5.5 only added the `python -c` exemption; the parallel case of Bash redirect/heredoc writing to a description-context path (tests/ / .md / .yaml) was still missing.

This is the same root-cause family as v0.5.5: when the *target* of a write is a description-context path, the *content* of the write is descriptive, not executable. Today the parity check covers:

- `python -c "..."` content (v0.5.5)
- Bash heredoc / redirect `>` `>>` to a path matching tests/test/__tests__/spec dirs, or `.md/.rst/.txt/.yaml/.yml/.json/.toml/.ini/.csv/.tsv` suffix, or `test_*.py` / `*_test.py` filename pattern (v0.5.8)

`src/runner.py` / production-code paths are still blocked even when written via heredoc.

A future refactor (likely v0.5.9) will lift this into `description_context.py` so all Bash-aware checks share the same exemption surface. For v0.5.8 the helper lives in `testset.py` only.

### Verification

- 3 new regression tests in `tests/test_checks.py`:
  - `test_testset_v058_heredoc_to_tests_path_exempted` — heredoc to `tests/` exempted
  - `test_testset_v058_heredoc_to_md_doc_exempted` — heredoc to `.md` exempted
  - `test_testset_v058_heredoc_to_src_still_blocked` — heredoc to `src/` still blocked
- `pytest`: 404/404 passing (401 prior + 3 new)
- `ruff`: 0 issues

## [0.5.7] — 2026-05-15 (feat — locale-agnostic `trigger_key` field on `CheckHit` + `Violation` for cross-locale audit grouping)

### feat — audit groups by `trigger_key` instead of `trigger` literal

A side-effect of v0.5.4 (i18n'd all trigger strings): `karma audit` was grouping by `trigger` literal, so a user who ran karma in zh locale for a week then switched to en would see "the same behavior" split into two separate counter lines. The audit's "top trigger" analysis would mis-represent reality.

v0.5.7 adds a locale-agnostic `trigger_key` (the i18n key itself, e.g. `"check.evidence.commit.trigger"`) as a stable identifier across locales:

- **`CheckHit.trigger_key: str = ""`** — every check function now passes both `trigger=tr(key)` (display string) and `trigger_key=key` (group identifier)
- **`Violation.trigger_key: str = ""`** — stored in violations.jsonl alongside the locale-specific `trigger` literal
- **`cli.py cmd_audit`** — groups by `trigger_key or trigger` (fallback to literal for legacy rows without the field)
- **Display** — still shows the locale-translated `trigger` literal (whichever was captured first), so users see readable text; only counting is unified

### Backward compatibility

- Legacy `violations.jsonl` rows without `trigger_key` load with `trigger_key=""` and group by `trigger` literal — no data loss.
- `to_json()` omits the field when empty, keeping jsonl file size identical for legacy writes.

### Verification

- 5 new regression tests in `tests/test_checks.py`:
  - `test_v057_check_hits_carry_trigger_key` — every check function returns non-empty `trigger_key` starting with `"check."`
  - `test_v057_violation_roundtrip_trigger_key` — write + read jsonl preserves `trigger_key`
  - `test_v057_violation_backward_compat_no_trigger_key` — legacy rows load with empty `trigger_key`, no crash
  - `test_v057_audit_groups_by_trigger_key_across_locales` — 5 zh + 5 en same key → single counter group of 10
  - `test_v057_audit_legacy_no_key_fallback_to_trigger` — legacy rows fall back to literal grouping
- `pytest`: 401/401 passing
- `ruff`: 0 issues

## [0.5.6] — 2026-05-15 (fix — keep_pushing `_PUSH_SIGNAL_RE` covers "next push point / next step is" planning phrases)

### fix — keep_pushing false-positive on "下一推进点 / 下一步是" tail phrases

This v0.5.4 dogfooding session hit it 7 times in a row: every response ended with a clear "next push point: X" / "next step: Y" planning phrase, but `keep_pushing.check()` still fired the "no push signal, no decision question — real stop" default trigger. Root cause: `_PUSH_SIGNAL_RE` (introduced in v0.4.19 to cover "future-planning push signals") missed the most common form — `下一(推进点 / 步 / 个 / 波 / milestone)` + verb.

This is the same root cause as v0.4.19 ("`_PUSH_SIGNAL_RE` missed future-planning expressions"), but on a different phrase family. Fix: extend `_PUSH_SIGNAL_RE` with 4 new branches:

- `下一(?:推进点|步|个|个推进点|波|个 milestone|个里程碑)` — bare "next push point / next step" phrase
- `下一步\s*(?:是|做|打算|准备|考虑|推进|继续|去|要|想|可以|应该)` — "next step is/plans to" + intent
- `接下来\s*(?:打算|准备|计划|考虑|可以|可选|的方向|的推进点)` — "next planning to / direction" forms
- `后续\s*(?:推进|步骤|计划|打算|准备|是)` — "follow-up steps / plans" forms

False-cousin "下一次再说吧" (deferral, not planning) is correctly *not* covered because the new patterns require `下一` + planning noun, not `下一次` + filler.

### Verification

- 2 new regression tests in `tests/test_keep_pushing.py`:
  - `test_v056_next_push_point_phrasing_exempted` — 6 push phrase variants all exempt
  - `test_v056_partial_stop_still_blocked` — `"下一次再说吧"` deferral still blocks
- `pytest`: 396/396 passing (394 prior + 2 new)
- `ruff`: 0 issues

## [0.5.5] — 2026-05-15 (fix — testset check adds `python -c` exemption, parity with non_blocking / bypass_karma)

### fix — testset.py false-positive on `python -c` string literals

A v0.5.3 dogfooding session hit it: a probe script `python -c "r = check(content='gold_cases.append(x)')"` was blocked by the testset check, treating the in-quote string `gold_cases.append(x)` as a real reverse-feed call. Root cause: `testset.py` was the only one of three `python -c`-affected checks missing the `_LANG_C_HEAD_RE` exemption (`non_blocking.py` got it in v0.4.18, `bypass_karma.py` got it in v0.4.13).

This release adds the same exemption pattern to `testset.py` `check()` — when `tool_name == "Bash"` and command head matches `\b(?:python\d?|node|ruby|perl)\s+-[ce]\b`, the check returns `None`. Real reverse-feed Bash commands (`cp eval/* train/`, `cat detail.json >> pool.jsonl`) without a `-c` wrapper still trigger.

### Verification

- 2 new regression tests in `tests/test_checks.py`:
  - `test_testset_python_c_string_literal_exempted` — confirms exemption applies
  - `test_testset_real_bash_reverse_feed_still_blocked` — confirms direct `cp eval/* train/` still blocks
- `pytest`: 394/394 passing (392 prior + 2 new)
- `ruff`: 0 issues

## [0.5.4] — 2026-05-15 (feat — Phase D wave 3: all 28 `CheckHit.trigger` strings switchable en/zh)

### feat — All `CheckHit.trigger` audit labels now locale-aware

The `trigger` field — written to `~/.claude/karma/violations.jsonl` for audit-log classification — was the last bilingual gap left after v0.5.3. v0.5.4 closes it: 28 trigger strings across 8 check modules are now `tr()`-driven, parallel to the `fix` namespace.

- 14 direct-trigger entries in `chinese_plain` / `non_blocking` / `evidence` / `keep_pushing` / `read_first` / `bypass_karma` (with `{term}` / `{cmd}` / `{word}` / `{tool}` / `{file_path}` / `{target}` interpolations)
- 14 pattern-table entries in `long_term` / `testset` — tuple structure now `(regex, trigger_key, fix_key)`, both translated at hit time

### feat — 28 new `check.*.trigger` keys in `data/locales/en.yaml` + `zh.yaml`

`!r`-style format specifiers carried over from the original `f"..."` so `'value'` quote-wrapping behavior stays identical.

### Verification

- `pytest`: 392/392 passing
- `ruff`: 0 issues
- Manual probe: 28/28 keys resolve in both EN and ZH with correct interpolation (`time.sleep(5)`, `'真' repeats 7 times`, etc.)

### What's left in Chinese (intentional)

`Sticky #N` rule body content in `data/rules.dev.example.zh.yaml` — these are the *user's preferences* (Chinese users get the Chinese template, English users get the English template via `_select_rule_template()`), so per-locale templates are the right model, not runtime translation.

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
