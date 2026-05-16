---
name: karma
description: Natural-language karma rule input — refine user's plain description into karma's validated rule structure, preview, confirm, and add to rules.yaml. Use when the user types `/karma <natural language describing a rule preference>`.
---

# karma skill — Natural-language rule input

**Auto-installed by**: `karma init` / `karma install-skill`. Installed across all detected backends:
- Claude Code: `~/.claude/skills/karma/SKILL.md`
- Codex CLI: `~/.agents/skills/karma/SKILL.md`
- Gemini CLI: `~/.gemini/skills/karma/SKILL.md` (auto-trigger) + `~/.gemini/commands/karma.toml` (explicit `/karma` slash command, generated from this Markdown)

**Trigger**:
- **Claude Code**: user types `/karma <natural-language description>` — args available as `$ARGUMENTS`
- **Codex**: user invokes via `/skills` menu or inline `$karma <description>`; auto-trigger on description match
- **Gemini CLI**: explicit `/karma <description>` (commands path) or auto-trigger (skills path)

**No-argument trigger** (v0.9.11+): when the user types `/karma` with **no description** (empty `$ARGUMENTS`), don't try to refine — instead, run `karma audit --by-check` and relay the output to the user. This gives them a quick "dogfood data dashboard": which engine checks fire most, real vs false-positive distribution, keyword-only fallback share. The user can then decide whether to tune any check or skip a rule. See "No-argument flow" section below.

---

## Your job (Agent)

When the user invokes `/karma <description>`, you (the Agent) refine their natural-language description into karma's validated structure, test it, then add to their rules.yaml.

**Critical constraints — do NOT skip any step**:
1. Refine user's natural language into karma's "collaborative agreement" tone (not rule-system tone)
2. Format `violation_keywords` (if any) in "intent-prefix + action" format (e.g., "I'll skip this" not "skip")
3. Decide whether to attach `violation_checks` (engine-layer hook detection) — this is **optional**
4. Test via `karma rule preview` before writing
5. Confirm with user before calling `karma rule add`
6. After adding, report: refined content + test passed + current rule library count + suggest deletions/modifications

## karma rule design principles (apply these when refining)

### Tone: "collaborative agreement" not "rule system"

✅ "The user trusts you to dig into root causes. They want you to pause and think 'what's the cleanest solution?' rather than 'fastest patch'..."

❌ "You must always use long-term solutions. Don't patch."

The first activates cooperation, the second activates fight-or-flight defensive reactions.

### preference text structure

Open with user perspective:
- "The user trusts/hopes/needs..."
- "The user you're collaborating with is..."
- "When [situation], the user..."

Explain **why** (short-term vs. long-term trust):
- "Short-term [behavior] looks fine but [user perspective consequence]"
- "[Honest behavior] beats [evasive behavior] for trust-building"

Provide **exception channel** anchored to concrete scenarios:
- "If [significant disagreement], raise it for alignment"
- "Exception: user explicitly says X → only then..."

### violation_keywords format (if needed)

**Use "intent-prefix + action" format** to distinguish from discussion:

✅ "I'll patch this quickly" / "let me hardcode" / "I'll wait for tests"

❌ "patch" / "hardcode" / "wait" (too broad, false positives in discussions)

Cap at ~5-10 keywords per rule. More keywords ≠ better detection (LLMs tend to pattern-match "keyword list exists" not actually read).

### violation_checks (optional — engine-layer hook detection)

karma has 8 built-in engine-layer check functions. Attach one if the rule fits:

| Function | Detects |
|---|---|
| `long_term_fundamental` | git `--no-verify` / hardcoded long-hash if-branches / TODO comments |
| `non_blocking_parallel` | `sleep N` / long tasks without `run_in_background` |
| `loud_failure_with_evidence` | Completion words + no test pass evidence in session |
| `no_testset_no_future_leakage` | Eval data backfeeding training / cross-split copying |
| `read_before_write` | Edit/Write before Read on same file path |
| `bypass_karma_detection` | Bash commands with karma internal state + write ops |
| `keep_pushing_no_stop` | Agent silent-stop → reflective continuation prompt |
| `chinese_plain_no_jargon` | Chinese ratio < 40% / English jargon (Chinese users only) |

**If no engine check fits**, leave `violation_checks: []` — the rule still injects in headers, just without real-time interception. **Don't fabricate check function names** — only use the 8 above.

### force_block_exempt (optional)

Set `force_block_exempt: true` only for "should keep pushing / non-blocking" type rules where cumulative penalty would be self-contradictory (e.g., `non-blocking-parallel`, `keep-pushing-no-stop`).

## Workflow when user invokes `/karma <description>`

### Step 1: Understand intent

Ask clarifying questions if needed:
- What scenario triggers this rule?
- What Agent behavior do you want to prevent?
- Is this a one-off request or a long-term direction?

If it's a one-off request, suggest they handle it via in-context prompt instead — karma is for **long-term directional preferences**, not single-task instructions.

**Critical: watch for anchor-vs-scope ambiguity.** User language like "when I do X, I want Y" often means "X is an example trigger" not "Y only applies during X." karma v2 rules are **always-on injection** (CLAUDE.md line 21: "5-10 rules all always-on, no selection needed") — there's no scene routing. If the user's request sounds scoped to a specific situation, surface the ambiguity:

> "Just to check: do you want this whenever we collaborate, or strictly during [the X scenario you mentioned]? karma injects this rule into every turn header — it can't be scoped to one situation. If you only want it for [X], we'd handle that outside karma."

Don't silently guess. If you guess wrong, the rule either over-fires (annoying) or under-applies (useless).

**Common one-off vs long-term tells**:
- "for this PR / this task / today" → one-off, suggest in-context prompt
- "I always want / I prefer / generally" → long-term, karma fits
- "let's try this approach this time" → one-off
- "in this codebase / for this kind of work" → long-term

### Step 2: Check existing rules

Run `karma rule list` to see if existing rules already cover this case. **Compare by semantics, not by id/name** — a rule named `loud-failure-with-evidence` and a new request "I want Agent to attach test logs when claiming done" are semantically the same even though the words don't overlap.

**Overlap decision table**:

| Situation | Action |
|---|---|
| New request's preference text says >50% the same thing as existing rule | **Modify the existing rule** — see "How to modify an existing rule" below. Don't add a duplicate. |
| Existing rule covers a superset but new request adds a specific dimension | Two options: (a) **modify existing** to absorb the dimension (preferred — keeps library tight), or (b) add new as a sibling — ask user which they prefer |
| New request shares 1-2 violation_keywords with existing but different intent | Add as separate rule, but mention the keyword overlap so user can decide |
| No semantic overlap | Add as new rule |

Don't be paranoid — most new rules don't overlap. But if they do, flag it before drafting (saves a Step 3 → Step 5 → "wait, this duplicates X" loop).

#### How to modify an existing rule (replace / merge / extend scope)

karma has no atomic `rule replace` command **on purpose** — modifying = `remove` + `add` composed by the Agent, so the steps are explicit and the user sees both halves.

**The 3-step modify recipe** (use this when Step 2 says "modify"):

1. **Draft the new yaml first** — write the full revised rule to `/tmp/karma-rule-<id>.yaml` (keep the original `id` so violation history stays linked, unless the rule's purpose genuinely changed)
2. **Preview** — `karma rule preview --from-yaml /tmp/karma-rule-<id>.yaml` to confirm schema + injection text
3. **Atomic-ish swap** — `karma rule remove <id> && karma rule add --from-yaml /tmp/karma-rule-<id>.yaml` (chain with `&&` so an `add` failure doesn't leave the library missing the rule)

**Common modify shapes**:

| Shape | What changes | Keep id? |
|---|---|---|
| **Replace** (same intent, better wording) | `preference` text rewritten | Yes — history stays linked |
| **Extend scope** (anchor → general) | `preference` widens applicability + violation_keywords may grow | Yes |
| **Merge** (fold rule B into rule A) | A absorbs B's intent; B removed | Keep A's id, then `karma rule remove <B-id>` |
| **Genuine purpose change** | New rule is a different concern | Use new id (rare — usually means a fresh rule, not a modify) |

**Why not `karma rule edit`?** That command launches `$EDITOR` for the user to hand-edit `rules.yaml` — it's a user-facing escape hatch, not an Agent-automatable path. The Agent should always use the `remove` + `add` recipe so the user sees the diff in conversation.

### Step 3: Refine into yaml

Draft a yaml snippet with:
- `id` — kebab-case slug (e.g., `must-run-tests-before-done`)
- `preference` — multi-line in collaborative-agreement tone (~3-5 lines)
- `violation_keywords` — intent-prefix + action format (3-8 entries)
- `violation_checks` — pick 0 or 1 of the 8 built-in functions
- `force_block_exempt` — usually omit (default false)

**Show the draft to the user inline before saving to a temp file.** Don't go straight to `preview` — the user should have a chance to react to wording / structure choices in conversation, not face a finished yaml.

A good flow:

> "Here's a draft based on what you said:
>
> ```yaml
> id: must-run-tests-before-done
> preference: |
>   ...
> violation_keywords: [...]
> ```
>
> Look right? If yes I'll preview + add. If you want to adjust the wording / keywords / scope, say so now."

If the user is OK or wants minor tweaks, then save to `/tmp/karma-new-rule.yaml` and move to Step 4.

**Locale-aware tone**: write `preference` in the language the user is talking to you in. Chinese user → Chinese preference text (using «协作默契» collaborative-agreement phrasing — see existing `data/rules.dev.example.zh.yaml` for reference patterns). English user → English text. Mixed-locale users typically prefer their primary language; if unsure, ask. The 8 built-in `violation_checks` function names stay English regardless (they're stable identifiers).

### Step 4: Preview test

Run:
```bash
karma rule preview --from-yaml /tmp/karma-new-rule.yaml
```

Shows: schema validation + how the rule looks in the injection header.

### Step 5: Confirm with user

Show the refined yaml + preview output. Ask:
- "Does this match your intent?"
- "Want to adjust the wording, add keywords, or attach an engine-layer check?"

If user wants changes, iterate (back to Step 3).

**Also surface any of these if true** (don't let the user discover them after `add`):
- "Heads up: this rule will be always-on, not just during [the X scenario]. If you only want X, we'd need a different mechanism."
- "This overlaps semantically with existing rule `[id]` — want me to merge / replace, or keep both?"
- "Current library is at N/10 — adding this puts you at N+1. After ~10, LLM attention to individual rules drops. Consider removing [Y] if it's redundant."

### Step 6: Write to rules.yaml

Once user confirms:

**For a brand-new rule** (Step 2 said "no overlap"):
```bash
karma rule add --from-yaml /tmp/karma-new-rule.yaml
```

**For modifying an existing rule** (Step 2 said "modify"):
```bash
# Step 1: preview the new version BEFORE removing — catches schema/REGISTRY errors while old rule still exists
karma rule preview --from-yaml /tmp/karma-rule-<id>.yaml
# Step 2: only after preview passes, do the swap
karma rule remove <id> && karma rule add --from-yaml /tmp/karma-rule-<id>.yaml
```

Both paths re-validate schema + check id conflicts + verify `violation_checks` exist in REGISTRY before touching `~/.claude/karma/rules.yaml`.

**Honest caveat on atomicity**: `remove && add` is *not* a true transaction — if `add` fails (e.g., disk full, permission error) after `remove` succeeded, the rule is gone. That's why preview-first matters: it surfaces schema errors before the destructive `remove` step. For paranoid scenarios, `cp ~/.claude/karma/rules.yaml ~/.claude/karma/rules.yaml.bak` before the swap is the cheap insurance.

### Step 7: Report results

After `karma rule add` succeeds, summarize for the user:

1. **What was added** — show the final yaml (refined from their natural language)
2. **karma tests passed** — schema validation + violation_checks existence verified
3. **Current rule library count** — X of soft cap 10 / hard cap 12
4. **When it takes effect** — "Takes effect on the next UserPromptSubmit. Send any new message (or restart Claude Code) to see it injected in the header." Don't make the user hunt for this.
5. **Suggest deletions/modifications**:
   - If close to soft cap (8+), suggest reviewing existing rules for duplicates/merging. Be concrete: name the specific rule pair that looks redundant ("`[X]` and `[Y]` both target evidence-attaching — consider merging") rather than vague "review for duplicates."
   - If any existing rule seems related, suggest adjusting it instead of keeping both
   - Ask: "Do you want to remove or modify any existing rules?"

## Example walkthrough

**User**: `/karma When the Agent says "this is done", I want it to actually attach test pass evidence — don't just say done`

**Agent**:

> Got it. Let me check existing rules first.
>
> [Runs `karma rule list`]
>
> I see you have `loud-failure-with-evidence` already, which partially covers this. But your new request adds specificity: "must attach actual test pass evidence." Let me refine into a yaml:
>
> ```yaml
> - id: must-show-test-evidence-on-done
>   preference: |
>     The user trusts your "done" signal but needs to see actual evidence.
>     When you say "this is done" for code tasks, attach test-pass output /
>     build OK / data / screenshots so they can directly verify the result.
>     If you skipped a test or used mocks, honestly state it rather than
>     fake completion — this builds more trust than pretending.
>     Loud failure beats quiet covering-up.
>   violation_keywords:
>     - "this is done"
>     - "I'm done with this"
>     - "task complete"
>   violation_checks:
>     - loud_failure_with_evidence
> ```
>
> [Runs `karma rule preview --from-yaml /tmp/...`]
>
> ✓ Schema validation passed. Here's the injection preview:
>
> ```
> 4. must-show-test-evidence-on-done
>    The user trusts your "done" signal but needs to see actual evidence.
>    ...
> ```
>
> Does this match your intent? Two questions before I write it:
> 1. Should the keyword list also include "all set" or "all good"?
> 2. The existing `loud-failure-with-evidence` rule overlaps — want me to modify that one instead, or add this as a separate, more specific rule?

**User**: Add it. Also include "all set".

**Agent**:

> [Adds "all set" to violation_keywords, runs `karma rule add --from-yaml /tmp/...`]
>
> ✓ Rule added. Summary:
>
> **Added** `must-show-test-evidence-on-done`:
> - preference: (the refined text above)
> - violation_keywords: ["this is done", "I'm done with this", "task complete", "all set"]
> - violation_checks: ["loud_failure_with_evidence"] (engine-layer detection enabled)
>
> ✓ karma schema test passed
>
> 📊 **Current rule library**: 8 of soft cap 10 / hard cap 12
>
> 📋 **Existing rules**:
> - [long-term-fundamental] ✓ engine
> - [non-blocking-parallel] ✓ engine
> - [chinese-plain-no-jargon] preference-only
> - [loud-failure-with-evidence] ✓ engine
> - [no-testset-no-future-leakage] ✓ engine
> - [read-before-write] ✓ engine
> - [deep-fix-not-bypass] ✓ engine
> - [must-show-test-evidence-on-done] ✓ engine ← new
>
> 💡 **Suggestion**: You're at 8 of soft cap 10. The new rule overlaps with `loud-failure-with-evidence` in concept (both about evidence). If you find one redundant after a few days of use, consider running `karma rule remove <id>`. Want to do that now?

## Common mistakes to avoid

- ❌ Don't write rules in "rule-system" tone ("you must always...")
- ❌ Don't use noun-only violation_keywords ("hardcoding" — too broad)
- ❌ Don't fabricate `violation_checks` function names — only use the 8 built-in ones
- ❌ Don't skip the preview step — always preview before `add`
- ❌ Don't add a new rule without checking for overlap with existing ones
- ❌ Don't exceed the soft cap 10 / hard cap 12 — too many rules backfire (LLMs pattern-match rule existence instead of truly reading)
- ❌ Don't silently treat scoped-sounding requests ("during X, do Y") as scoped — karma is always-on. Surface the ambiguity in Step 1.
- ❌ Don't write English `preference` text when the user is talking to you in Chinese (or vice versa) — match the user's language. Only `violation_checks` function names stay English (stable identifiers).
- ❌ Don't go straight from Step 1 → Step 4 preview without showing the user a draft inline in Step 3 — they should react to wording before it's written to disk.

---

## No-argument flow (v0.9.11+) — `/karma` with no description

When the user types `/karma` with empty `$ARGUMENTS`, treat it as a request for the dogfood-data dashboard, not as an "add a rule" intent.

**What to do**:

1. Run `karma audit --by-check`. Capture stdout.
2. Relay the output to the user as-is, then add a one-line interpretation:
   - **High-firing checks** (top 1-2 rows of "按 check 函数聚合"): "Check X fires N% — this rule is the most-violated direction in your sessions."
   - **High keyword-only ratio** (`keyword-only 兜底命中` > 70%): "Most violations are caught by the keyword fallback layer, not engine checks — the engine checks may need more sub-variants, or your specific rules don't have `violation_checks` attached."
   - **High false-positive suspicion** (a sub-variant dominates a check): mention by name, suggest user observe whether it's matching real intent or just literal patterns.
3. Ask: "Want to tune any check, drop a rule, or add a new one based on this data?"

**Example response** (the user typed just `/karma`):

> 这是你本机最近 187 条违反的分布：
>
> ```
> [paste karma audit --by-check output]
> ```
>
> 几个观察：
> - `keep_pushing.default` 占 engine 命中的 69%（18/26）— 这是你 session 里最常被拦的方向，说明 keep-pushing 规则在你的工作流里很活跃
> - 86% 违反走的是 keyword-only 兜底（没 engine check），说明大部分规则没附 `violation_checks` — 这是合理的（不是所有规则都需要 engine 检测）
>
> 想根据这些数据调整哪条规则，还是加一条新规则？

**Why this is the no-arg default** (not "show help"):
- The user has already installed karma and seen the `karma init` summary (which already lists default rules).
- The next most-useful thing isn't documentation — it's **observation data**: "is karma actually doing useful work for me?"
- This closes the dogfood feedback loop: violations.jsonl → audit → user sees pattern → decides to tune.

**Don't run `karma audit --by-check` in these cases**:
- User typed `/karma <some description>` → take it as a rule-add intent, follow Steps 1-7 above
- User typed `/karma help` or similar literal help-request → show a brief summary of what `/karma` does (refine new rule + show data when no-arg)
