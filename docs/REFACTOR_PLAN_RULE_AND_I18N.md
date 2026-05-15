# karma Refactor Plan — sticky → rule rename + `/karma rule` natural-language input + multi-language support

**[🇬🇧 English (current)](./REFACTOR_PLAN_RULE_AND_I18N.md) · [🇨🇳 中文](./REFACTOR_PLAN_RULE_AND_I18N.zh.md)**

> ✅ **Status: shipped.** Direction 1 (sticky → rule rename + `/karma` skill) landed across v0.5.0 / v0.5.1 / v0.5.16; the backward-compat scaffolding was removed in v0.6.0. Direction 2 (i18n) landed in v0.5.2–v0.5.4. Kept as the original plan + design rationale, not current operating state — see [ARCHITECTURE.md](./ARCHITECTURE.md) for current state.

## Two user-authorized refactor directions

### Direction 1 — `/karma rule XXX` natural-language rule input + sticky → rule rename

User asked: make personalized rule input frictionless via a single `/karma rule` command. The Agent should automatically refine the user's natural language into karma's validated tone, content, and structure, then write to the rule file after testing passes. Additionally, rename all `sticky` references in code and files to `rule`.

### Direction 2 — Multi-language support

User asked: support major languages beyond Chinese for all user-facing content (CLI output / hook injection text / suggested_fix / rules templates / documentation).

## 4-phase release plan

| Phase | Release | Scope |
|---|---|---|
| **A** | **v0.5.0 ✅ shipped** | sticky → rule rename across entire codebase + backward-compat migration |
| **B** | v0.5.1 (pending) | `karma rule add` CLI + Claude Code skill template for natural-language rule creation |
| **C** | v0.5.2 (pending) | i18n infrastructure (`karma/i18n.py` + locale detection + `data/locales/*.yaml`) |
| **D** | v0.5.3 (pending) | English `rules.en.example.yaml` templates + English hook injection text + English `suggested_fix` for all 8 check functions |

## Phase A details (shipped v0.5.0)

### Implemented changes

- **Core classes**: `class Sticky` → `class Rule`, `StickyConfigError` → `RuleConfigError`, `MAX_STICKY` → `MAX_RULES` (all preserved as aliases until v0.6.0)
- **Module**: `karma/sticky.py` → `karma/rule.py` (git mv preserved history), legacy `karma/sticky.py` became a compat shim with `DeprecationWarning`
- **Fields**: `Violation.sticky_id` → `Violation.rule_id` (property `sticky_id` alias preserved), `CheckHit.sticky_id` → `CheckHit.rule_id`
- **CLI**: `karma sticky list/edit/remove` → `karma rule list/edit/remove`, legacy `karma sticky` as deprecated alias
- **Config**: `~/.claude/karma/sticky.yaml` → `~/.claude/karma/rules.yaml`, legacy users running `karma init` auto-migrates + backups to `sticky.yaml.bak`
- **Data templates**: `data/sticky.dev.example.yaml` → `data/rules.dev.example.yaml`, pyproject.toml force-include updated

### Backward compatibility (v0.5.x kept, removed in v0.6.0)

Legacy users seamlessly upgrade — all old APIs / old imports / old configs still work:

- `from karma.sticky import Sticky / StickyConfigError / MAX_STICKY` still works (with `DeprecationWarning`)
- `karma sticky list` still runs (with `DeprecationWarning`)
- `~/.claude/karma/sticky.yaml` still readable (fallback in `karma.rule.DEFAULT_PATH`)
- `violations.jsonl` legacy `sticky_id` field reading compatible (new writes use `rule_id`)

## Phase B design — `/karma rule` natural-language input

### User-side experience

```
User: /karma rule When the Agent says "this is done", I want it to actually
      attach test pass evidence — don't just say done
```

### Skill behavior (Claude Code skill template)

The Agent receives the user's natural-language description and should:

1. **Analyze against karma rule design principles**:
   - Distinguish "long-term directional preference" from one-off requests
   - Check whether existing rules already cover this case
   - Identify the rule category (engine-layer check vs. preference-only)

2. **Refine into karma's validated structure**:
   - `preference` text in "collaborative agreement" tone (user-perspective, not rule-system)
   - `violation_keywords` in "intent-prefix + action" format (e.g. "I'll skip this test" not "skip")
   - Choose appropriate `violation_checks` from 8 built-in functions (optional)

3. **Test before adding**:
   - Preview rendering of the new rule in the inject header context
   - Test violation_keywords against sample sentences (no false positives)
   - Confirm no conflicts with existing rules

4. **Feedback to user**:
   - Show the refined rule yaml
   - Confirm "passed karma tests"
   - Show current rule count in the library (X of soft cap 10)
   - Ask whether any existing rules need deletion or modification

### Key design constraints

- **karma doesn't introduce LLM API** — Agent refinement is Claude Code's own capability; karma only provides prompt template + CLI commands
- **karma provides "karma-validated tone/content/structure"** as prompt context (so Agent knows karma's collaborative-agreement tone, 8 built-in check functions, field formats, etc.)
- **Preview + confirmation mechanism** protects users (avoids Agent writing incorrect rules)

## Phase C design — i18n infrastructure

- `karma/i18n.py` — load + switch locale interface
- `data/locales/zh.yaml` + `data/locales/en.yaml` — all user-visible text translations
- Install-time `karma/locale_detect.py` (existing) detects system language → writes config.yaml `locale: zh|en`
- All `print(...)` / `notify(...)` / rule baseline header wrapping / suggested_fix text → `_(key)` lookup

## Phase D design — English content

- `data/rules.dev.example.yaml` — English version 5/7 core directions (preference translated + violation_keywords in English idioms)
- Validation: English-native user installation → header injection / interception / reflection all-English experience

## Locked design decisions

1. **rules.yaml plural** (collection semantics)
2. **One-shot v0.5.0 big bang** (karma early-stage, breaking change risk controllable)
3. **`/karma rule` = Claude Code skill + karma CLI combo** (skill template guides Agent to use karma-validated tone)
4. **i18n yaml dict** (simpler than gettext for early-stage)
5. **zh + en starter** (other languages via community contributions)

## Status

- ✅ **Phase A complete** (v0.5.0 released 2026-05-15) — `sticky` → `rule` rename across entire codebase, backward-compat aliases preserved
- ✅ **i18n doc translation complete** — README / SECURITY / CODE_OF_CONDUCT / docs/PRD / docs/ARCHITECTURE / docs/REFACTOR_PLAN / docs/RULES_REDESIGN / HOWTO / CLAUDE.md / .github templates all swapped English default + Chinese alternative; `rules.dev.example.yaml` English default + `.zh.yaml` backup; `karma init` locale-aware template selection via `_select_rule_template()`
- ✅ **Phase B complete** (v0.5.1 released 2026-05-15) — `karma rule add` / `karma rule preview` CLI subcommands with schema validation + id uniqueness + cap enforcement + `violation_checks` REGISTRY validation; Claude Code skill template at `skills/karma-rule.md` with 7-step natural-language workflow
- ✅ **Phase C complete** (v0.5.2 released 2026-05-15) — `karma/i18n.py` module with `tr(key, **fmt)` lookup, `{placeholder}` interpolation, locale resolution chain (`KARMA_LOCALE` env > `config.yaml` `locale` field > `is_chinese_user()` auto-detect > `en` fallback), fail-open on missing keys; 5 hook injection paths (`rule.py format_for_injection` / `post_tool_use` / `stop` / `user_prompt_submit` / `subagent_start`) all switched from hard-coded Chinese to `tr()` lookup
- ✅ **Phase D complete** (v0.5.3 + v0.5.4 released 2026-05-15) — all 28 check `suggested_fix` strings switchable en/zh (v0.5.3); all 28 `CheckHit.trigger` audit-log labels also switchable en/zh (v0.5.4); v0.5.7 adds locale-agnostic `trigger_key` field on `CheckHit` + `Violation` so `karma audit` groups by stable identifier across locale switches

For detailed Chinese version with code samples, file lists, and decision-point discussion, see [REFACTOR_PLAN_RULE_AND_I18N.zh.md](./REFACTOR_PLAN_RULE_AND_I18N.zh.md).
