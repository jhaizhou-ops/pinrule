---
name: pinrule
description: Natural-language pinrule rule input — handles two paths. (A) Single rule add/modify/remove from user's plain description. (B) Scenario rule pack generation — when user names a domain ("I mainly do research / writing / legal / data analysis"), synthesize 5-7 tailored rules by combining their existing local rule files (CLAUDE.md / AGENTS.md / .cursor/rules), online best practices (WebSearch), Karpathy CLAUDE.md baseline, and your session context with the user. Use when the user types `/pinrule <natural language>` — either a single rule or a scenario description.
---

# pinrule skill — Natural-language rule input

**Auto-installed by**: `pinrule init` / `pinrule install-skill`. Installed across all detected backends:
- Claude Code: `~/.claude/skills/pinrule/SKILL.md`
- Codex CLI: `~/.agents/skills/pinrule/SKILL.md`
- Cursor 1.7+: per-project `.cursor/skills/pinrule/SKILL.md` (Cursor doesn't expose home-global skills — see post-install hint)

**Trigger**:
- **Claude Code**: user types `/pinrule <natural-language description>` — args available as `$ARGUMENTS`
- **Codex**: user invokes via `/skills` menu or inline `$pinrule <description>`; auto-trigger on description match
- **Cursor**: project-scoped skill, invoked from inside an Agent session that has the project's `.cursor/skills/pinrule/` directory available

## 🚨 Fast-path: No-argument `/pinrule` — Bash direct, no synthesis

**If `$ARGUMENTS` is empty, STOP reading this skill right now.** Do the following and exit:

```bash
pinrule audit --by-check
```

**Dump the output verbatim to the user**. Do NOT synthesize / summarize / add commentary / ask follow-up questions. This is pure engineering output — `pinrule audit --by-check` is the user's data dashboard, your job is to be a transparent pipe.

The only exception: if the output is genuinely empty (no violations yet), tell the user "no violations recorded yet, come back after a few sessions". Otherwise — raw output, exit.

This fast-path exists because no-argument `/pinrule` is a pure read operation, not creative work. Agent involvement adds latency + token cost + risk of paraphrasing the data wrong. The user typed `/pinrule` (no args) because they wanted the dashboard, not your interpretation of it.

---

## Your job (Agent) — dispatch first

`/pinrule` is the user's **single command** for all pinrule interactions. They never need to remember `pinrule rule add` / `pinrule audit --by-check` / etc. — they just type `/pinrule <whatever>` and you dispatch.

When the user invokes `/pinrule [args]`, **first decide which path**:

| Path | Triggered by | Outcome |
|---|---|---|
| **0. Empty / no args** (`/pinrule`) | `$ARGUMENTS` is empty | Run `pinrule audit --by-check` and relay output as a "dogfood data dashboard" — see [No-argument flow](#no-argument-flow-v0911--pinrule-with-no-description) section |
| **A. Single rule** (default, ~80% of args calls) | "我希望 X / I want Agent to do X / change rule Y / remove rule Z" — talks about **one** behavior | One rule added / modified / removed via Path A workflow |
| **B. Scenario rule pack** | "我主要做 X / I mainly do X / set up rules for X scenario / switch to X / 切到 X 场景 / replace rule library for X" — names a **domain** | 5-7 new rules synthesized from local rule files + online best practices + Karpathy baseline + your session context |

Dispatch logic:
1. If `$ARGUMENTS` empty → Path 0 (audit dashboard)
2. Vocabulary tells: "scenario / 场景 / switch / 切到 / mainly do / 主要做 / replace rule library / 替换规则库" → Path B
3. Otherwise → Path A

If genuinely ambiguous, ask **once**, then proceed. Don't ping-pong.

**Path A constraints — do NOT skip any step**:
1. Refine user's natural language into pinrule's "collaborative agreement" tone (not rule-system tone)
2. Format `violation_keywords` (if any) in "intent-prefix + action" format (e.g., "I'll skip this" not "skip")
3. Decide whether to attach `violation_checks` (engine-layer hook detection) — this is **optional**
4. Test via `pinrule rule preview` before writing
5. Confirm with user before calling `pinrule rule add`
6. After adding, report: refined content + test passed + current rule library count + suggest deletions/modifications

**Path B**: jump to [Path B: Scenario rule pack generation](#path-b-scenario-rule-pack-generation) — has its own workflow.

---

## Design principle: engineering-first, Agent doesn't reinvent

This skill is a **workflow choreography document**, not a research assignment for the Agent. When pinrule has an engineering primitive that already solves a step (e.g., `pinrule doctor` for backend detection, `pinrule rule preview` for schema validation, `pinrule rule add` for atomic write), **call it directly via Bash** — don't reinvent the logic with `Read` + manual parsing.

Real dogfood lesson (Path B Step 0.5): when SKILL.md said "Use Read tool to scan `~/.cursor/hooks.json`", the Agent missed a clearly-installed Cursor because it scanned the wrong path / made wrong inferences from file existence. The fix wasn't smarter prompting — it was redirecting to `pinrule doctor` which is the authoritative API pinrule already ships.

**Default heuristic**: if the work the Agent needs to do has a corresponding `pinrule <subcommand>` already shipped, the SKILL.md should instruct the Agent to call that subcommand, parse output, and proceed. Reinventing logic is the failure mode.

Agent free-form judgment belongs in:
- Domain knowledge synthesis (Path B Step 3: composing rule content from session context + external sources)
- Tone refinement (Path A Step 3: rephrasing into "collaborative agreement" tone)
- Cross-scenario semantic mapping (Path B Step 7: mapping new rules to existing engine checks)
- Source attribution (deciding which signal contributed what)

Agent reinvention does NOT belong in:
- Backend detection → call `pinrule doctor`
- Schema validation → call `pinrule rule preview`
- Single rule write → call `pinrule rule add --from-json`
- **Atomic batch write (Path B Step 10)** → call `pinrule rule import-pack --from-json <pack> --mode replace --backup` (v0.18.0+ — one command, validates everything first, then atomic swap; no half-replaced state if any step fails)
- Existing rule library inspection → call `pinrule rule list`
- Violation audit → call `pinrule audit --by-check`

## pinrule rule design principles (apply these when refining)

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

pinrule has 8 built-in engine-layer check functions. Attach one if the rule fits:

| Function | Detects |
|---|---|
| `long_term_fundamental` | git `--no-verify` / hardcoded long-hash if-branches / TODO comments |
| `non_blocking_parallel` | `sleep N` / long tasks without `run_in_background` |
| `loud_failure_with_evidence` | Completion words + no test pass evidence in session |
| `no_testset_no_future_leakage` | Eval data backfeeding training / cross-split copying |
| `read_before_write` | Edit/Write before Read on same file path |
| `bypass_pinrule_detection` | Bash commands with pinrule internal state + write ops |
| `keep_pushing_no_stop` | Agent silent-stop → reflective continuation prompt |
| `chinese_plain_no_jargon` | Chinese ratio < 40% / English jargon (Chinese users only) |

**If no engine check fits**, leave `violation_checks: []` — the rule still injects in headers, just without real-time interception. **Don't fabricate check function names** — only use the 8 above.

### force_block_exempt (optional)

Set `force_block_exempt: true` only for "should keep pushing / non-blocking" type rules where cumulative penalty would be self-contradictory (e.g., `non-blocking-parallel`, `keep-pushing-no-stop`).

## Path A: Single-rule workflow (when user describes one behavior)

### Step 1: Understand intent

Ask clarifying questions if needed:
- What scenario triggers this rule?
- What Agent behavior do you want to prevent?
- Is this a one-off request or a long-term direction?

If it's a one-off request, suggest they handle it via in-context prompt instead — pinrule is for **long-term directional preferences**, not single-task instructions.

**Critical: watch for anchor-vs-scope ambiguity.** User language like "when I do X, I want Y" often means "X is an example trigger" not "Y only applies during X." pinrule v2 rules are **always-on injection** (CLAUDE.md line 21: "5-10 rules all always-on, no selection needed") — there's no scene routing. If the user's request sounds scoped to a specific situation, surface the ambiguity:

> "Just to check: do you want this whenever we collaborate, or strictly during [the X scenario you mentioned]? pinrule injects this rule into every turn header — it can't be scoped to one situation. If you only want it for [X], we'd handle that outside pinrule."

Don't silently guess. If you guess wrong, the rule either over-fires (annoying) or under-applies (useless).

**Common one-off vs long-term tells**:
- "for this PR / this task / today" → one-off, suggest in-context prompt
- "I always want / I prefer / generally" → long-term, pinrule fits
- "let's try this approach this time" → one-off
- "in this codebase / for this kind of work" → long-term

### Step 2: Check existing rules

Run `pinrule rule list` to see if existing rules already cover this case. **Compare by semantics, not by id/name** — a rule named `loud-failure-with-evidence` and a new request "I want Agent to attach test logs when claiming done" are semantically the same even though the words don't overlap.

**Overlap decision table**:

| Situation | Action |
|---|---|
| New request's preference text says >50% the same thing as existing rule | **Modify the existing rule** — see "How to modify an existing rule" below. Don't add a duplicate. |
| Existing rule covers a superset but new request adds a specific dimension | Two options: (a) **modify existing** to absorb the dimension (preferred — keeps library tight), or (b) add new as a sibling — ask user which they prefer |
| New request shares 1-2 violation_keywords with existing but different intent | Add as separate rule, but mention the keyword overlap so user can decide |
| No semantic overlap | Add as new rule |

Don't be paranoid — most new rules don't overlap. But if they do, flag it before drafting (saves a Step 3 → Step 5 → "wait, this duplicates X" loop).

#### How to modify an existing rule (replace / merge / extend scope)

pinrule has no atomic `rule replace` command **on purpose** — modifying = `remove` + `add` composed by the Agent, so the steps are explicit and the user sees both halves.

**The 3-step modify recipe** (use this when Step 2 says "modify"):

1. **Draft the new JSON first** — write the full revised rule to `/tmp/pinrule-rule-<id>.json` (keep the original `id` so violation history stays linked, unless the rule's purpose genuinely changed)
2. **Preview** — `pinrule rule preview --from-json /tmp/pinrule-rule-<id>.json` to confirm schema + injection text
3. **Atomic-ish swap** — `pinrule rule remove <id> && pinrule rule add --from-json /tmp/pinrule-rule-<id>.json` (chain with `&&` so an `add` failure doesn't leave the library missing the rule)

**Common modify shapes**:

| Shape | What changes | Keep id? |
|---|---|---|
| **Replace** (same intent, better wording) | `preference` text rewritten | Yes — history stays linked |
| **Extend scope** (anchor → general) | `preference` widens applicability + violation_keywords may grow | Yes |
| **Merge** (fold rule B into rule A) | A absorbs B's intent; B removed | Keep A's id, then `pinrule rule remove <B-id>` |
| **Genuine purpose change** | New rule is a different concern | Use new id (rare — usually means a fresh rule, not a modify) |

**Why not `pinrule rule edit`?** That command launches `$EDITOR` for the user to hand-edit `rules.json` — it's a user-facing escape hatch, not an Agent-automatable path. The Agent should always use the `remove` + `add` recipe so the user sees the diff in conversation.

### Step 3: Refine into JSON

Draft a JSON snippet with:
- `id` — kebab-case slug (e.g., `must-run-tests-before-done`)
- `preference` — multi-line in collaborative-agreement tone (~3-5 lines; use `\n` for line breaks)
- `violation_keywords` — intent-prefix + action format (3-8 entries)
- `violation_checks` — pick 0 or 1 of the 8 built-in functions
- `force_block_exempt` — usually omit (default false)

**Show the draft to the user inline before saving to a temp file.** Don't go straight to `preview` — the user should have a chance to react to wording / structure choices in conversation, not face a finished JSON.

A good flow:

> "Here's a draft based on what you said:
>
> ```json
> {
>   "id": "must-run-tests-before-done",
>   "preference": "...\nmulti-line via \\n escape...",
>   "violation_keywords": ["...", "..."]
> }
> ```
>
> Look right? If yes I'll preview + add. If you want to adjust the wording / keywords / scope, say so now."

If the user is OK or wants minor tweaks, then save to `/tmp/pinrule-new-rule.json` and move to Step 4.

**Locale-aware tone**: write `preference` in the language the user is talking to you in. Chinese user → Chinese preference text (using «协作默契» collaborative-agreement phrasing — see existing `data/rules.dev.example.zh.json` for reference patterns). English user → English text. Mixed-locale users typically prefer their primary language; if unsure, ask. The 8 built-in `violation_checks` function names stay English regardless (they're stable identifiers).

### Step 4: Preview test

Run:
```bash
pinrule rule preview --from-json /tmp/pinrule-new-rule.json
```

Shows: schema validation + how the rule looks in the injection header.

### Step 5: Confirm with user

Show the refined JSON + preview output. Ask:
- "Does this match your intent?"
- "Want to adjust the wording, add keywords, or attach an engine-layer check?"

If user wants changes, iterate (back to Step 3).

**Also surface any of these if true** (don't let the user discover them after `add`):
- "Heads up: this rule will be always-on, not just during [the X scenario]. If you only want X, we'd need a different mechanism."
- "This overlaps semantically with existing rule `[id]` — want me to merge / replace, or keep both?"
- "Current library is at N/10 — adding this puts you at N+1. After ~10, LLM attention to individual rules drops. Consider removing [Y] if it's redundant."

### Step 6: Write to rules.json

Once user confirms:

**For a brand-new rule** (Step 2 said "no overlap"):
```bash
pinrule rule add --from-json /tmp/pinrule-new-rule.json
```

**For modifying an existing rule** (Step 2 said "modify"):
```bash
# Step 1: preview the new version BEFORE removing — catches schema/REGISTRY errors while old rule still exists
pinrule rule preview --from-json /tmp/pinrule-rule-<id>.json
# Step 2: only after preview passes, do the swap
pinrule rule remove <id> && pinrule rule add --from-json /tmp/pinrule-rule-<id>.json
```

Both paths re-validate schema + check id conflicts + verify `violation_checks` exist in REGISTRY before touching `~/.claude/pinrule/rules.json`.

**Honest caveat on atomicity**: `remove && add` is *not* a true transaction — if `add` fails (e.g., disk full, permission error) after `remove` succeeded, the rule is gone. That's why preview-first matters: it surfaces schema errors before the destructive `remove` step. For paranoid scenarios, `cp ~/.claude/pinrule/rules.json ~/.claude/pinrule/rules.json.bak` before the swap is the cheap insurance.

### Step 7: Report results

After `pinrule rule add` succeeds, summarize for the user:

1. **What was added** — show the final JSON (refined from their natural language)
2. **pinrule tests passed** — schema validation + violation_checks existence verified
3. **Current rule library count** — X of soft cap 10 / hard cap 12
4. **When it takes effect** — "Takes effect on the next UserPromptSubmit. Send any new message (or restart Claude Code) to see it injected in the header." Don't make the user hunt for this.
5. **Suggest deletions/modifications**:
   - If close to soft cap (8+), suggest reviewing existing rules for duplicates/merging. Be concrete: name the specific rule pair that looks redundant ("`[X]` and `[Y]` both target evidence-attaching — consider merging") rather than vague "review for duplicates."
   - If any existing rule seems related, suggest adjusting it instead of keeping both
   - Ask: "Do you want to remove or modify any existing rules?"

## Example walkthrough

**User**: `/pinrule When the Agent says "this is done", I want it to actually attach test pass evidence — don't just say done`

**Agent**:

> Got it. Let me check existing rules first.
>
> [Runs `pinrule rule list`]
>
> I see you have `loud-failure-with-evidence` already, which partially covers this. But your new request adds specificity: "must attach actual test pass evidence." Let me refine into JSON:
>
> ```json
> {
>   "id": "must-show-test-evidence-on-done",
>   "preference": "The user trusts your \"done\" signal but needs to see actual evidence.\nWhen you say \"this is done\" for code tasks, attach test-pass output /\nbuild OK / data / screenshots so they can directly verify the result.\nIf you skipped a test or used mocks, honestly state it rather than\nfake completion — this builds more trust than pretending.\nLoud failure beats quiet covering-up.",
>   "violation_keywords": [
>     "this is done",
>     "I'm done with this",
>     "task complete"
>   ],
>   "violation_checks": ["loud_failure_with_evidence"]
> }
> ```
>
> [Runs `pinrule rule preview --from-json /tmp/...`]
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

> [Adds "all set" to violation_keywords, runs `pinrule rule add --from-json /tmp/...`]
>
> ✓ Rule added. Summary:
>
> **Added** `must-show-test-evidence-on-done`:
> - preference: (the refined text above)
> - violation_keywords: ["this is done", "I'm done with this", "task complete", "all set"]
> - violation_checks: ["loud_failure_with_evidence"] (engine-layer detection enabled)
>
> ✓ pinrule schema test passed
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
> 💡 **Suggestion**: You're at 8 of soft cap 10. The new rule overlaps with `loud-failure-with-evidence` in concept (both about evidence). If you find one redundant after a few days of use, consider running `pinrule rule remove <id>`. Want to do that now?

## Path B: Scenario rule pack generation

**Triggered when** the user names a domain rather than describing a single behavior:
- "我主要做科研 / 写作 / 数据分析 / 法律 / 教学 / 客户支持"
- "I mainly do research / writing / data analysis / legal / teaching"
- "Set up rules for X scenario / 给 X 场景定规则"
- "Switch to X / 切到 X 场景"
- "Replace rule library for X / 替换为 X 场景规则集"

The user wants a **coherent rule pack** tailored to their scenario, not one rule. You will synthesize 5-7 rules by combining four signals (no opt-in prompt — all four are on by default; pinrule is opinionated):

### Step 0.5 (Path B): Preflight — detect user's active backends FIRST

**This is Path B's mandatory first action** — before Step 1 scenario interpretation, before Phase 1 content drafting, before anything else. Backend detection shapes Phase 1 content tone (e.g., Cursor CLI主战场用户的 Stop-hook 类规则需要更自包含 preference 文本) **and** Phase 2 mechanism advisory (engine check coverage table).

**Run via Bash tool (NOT Read tool — see "Design principle" section above)**:

```bash
pinrule doctor
```

**Parse output for**:

| Signal | What it means |
|---|---|
| `[claude-code]` section with `✓` marks | Claude Code installed |
| `[codex]` section with `✓` marks | Codex CLI installed |
| `[cursor]` section with `✓` marks | Cursor installed |
| Cursor transcript section reports majority **non-null** `transcript_path` for `stop` / `afterAgentResponse` | **桌面 Agent 路径正常** ✅ |
| Cursor transcript section reports majority **null** `transcript_path` | User mostly on CLI / privacy mode → response-level checks will silent-skip ⚠️ |
| Cursor transcript section absent / no logs found | Cursor installed but no recent session → can't determine 桌面 vs CLI yet |

**Store the results** — you'll use them in Step 3 (Phase 1 content adapt to backend constraints), Step 7 (Phase 2 engine check coverage table), and Step 11 (closing reminder).

**Do NOT skip Step 0.5 to "save time"** — without it, Phase 1 content can't be backend-aware and Phase 2 coverage advisory becomes guesswork. Real dogfood (v4) showed Agent missing Step 0.5 entirely when it sat in Phase 2 region — that's why Step 0.5 is up front.

### Step 1 (Path B): Interpret scenario from session context — don't ping-pong

You're working with the user *right now in this session*. You have context on:
- What files they've opened
- What tasks they've asked you to do
- The vocabulary / frameworks / tools they use
- Their domain language

**Infer the subscenario silently** — don't ask "is your research theoretical or experimental?". The user gave you a scenario *because they want you to figure out the rest from working with them*.

**Exception**: brand new session with zero prior task history *and* the scenario word is genuinely ambiguous (e.g., just "research" with no other context) → **one** clarifying question is OK, then proceed.

### Step 2 (Path B): Gather signal from four sources (all on, no opt-in)

#### Source A — User's existing local rule files (highest signal)

Use the `Read` tool to scan these paths, in order:

```
~/.claude/CLAUDE.md                          # Claude Code home-level (user's global preferences)
~/.codex/AGENTS.md                           # Codex home-level
<cwd>/CLAUDE.md                              # current project, Claude Code
<cwd>/AGENTS.md                              # current project, Codex
<cwd>/.cursor/rules/*.mdc                    # Cursor project rules
<cwd>/.cursorrules                           # Cursor legacy
<cwd>/.github/copilot-instructions.md        # GitHub Copilot
<cwd>/CONTRIBUTING.md                        # Project collaboration norms
<cwd>/README.md                              # Project context / style hints
```

**Skip pinrule-generated files** (self-reference noise):
- `.cursor/rules/pinrule-*.mdc`
- `.cursor/rules/karma-*.mdc` (legacy v1 name)
- `~/.pinrule/rules.json` (current pinrule state, not source material)

If a file exists but is empty / tiny (e.g., just `@RTK.md` import), skip it.

These are highest signal because **the user wrote them** — they reflect real pain points, not theoretical best practice.

#### Source B — Online best practices for the scenario

Use `WebSearch` and `WebFetch` (your client's tools) to find:

```
"awesome-claude-md" / "awesome-cursor-rules" aggregator repos on GitHub
"<scenario> + claude.md" / "<scenario> + AI agent rules" GitHub search
High-star (1k+) GitHub repos in the user's domain with quality CLAUDE.md / AGENTS.md
Anthropic / Cursor / OpenAI official prompt engineering writeups
Academic papers if scenario is research-adjacent
```

**Source quality filter**: prefer GitHub repos with 1k+ stars, recognized company engineering blogs, peer-reviewed papers. Skip SEO listicles, low-effort medium posts.

**🔒 Privacy boundary — non-negotiable**:
- Search queries use **only scenario keywords** the user explicitly typed (e.g., "UX research best practices", "legal contract review rules")
- **Do NOT include** in web queries: local rule file contents, private project names, repository paths, conversation transcripts, file paths under the user's home directory, or any session-specific detail
- If you need to reference user-specific context in the synthesized rule pack, source it from **Source A / Source S** (local, never uploaded), not from web search queries
- If the user explicitly says "search for X in the context of my project Y", you may include `Y` in queries — but flag it back to them: "I'll include `Y` in the search query, OK?"

This isn't about pinrule's runtime (which is 0 network), it's about your Agent's WebSearch behavior — the user's local data must not leak through query strings.

#### Source H — Karpathy CLAUDE.md baseline

Reference Andrej Karpathy's [CLAUDE.md template](https://github.com/forrestchang/andrej-karpathy-skills). Several of his principles transfer across scenarios (test coverage / explicit failure / minimal abstraction). Pull principles that fit the user's scenario; skip ones that don't.

#### Source S — Your session context (the one signal nobody else has)

You've been working with this user. You know:
- What they actually do day-to-day
- What mistakes they've corrected you on
- What tone they prefer
- What they care about (speed vs. correctness vs. clarity)

This is the **synthesis** signal — it's how you decide which Source-A/B/H candidates fit *this* user vs. *anyone* doing this scenario.

Path B runs in **two phases**. Each phase has its own user approval gate. The split lets you focus: Phase 1 is pure content (domain knowledge + signal synthesis), Phase 2 is pure mechanism (keyword + engine check engineering). Mixing them in one shot dilutes Agent attention and stuffs user with too many decisions at once.

---

## Phase 1 — Content draft + approval (Steps 3-5)

### Step 3 (Path B, Phase 1): Synthesize rule **content** — preference + source only

For each candidate rule, generate **only**:
- `id` (kebab-case slug)
- `preference` text (full multi-line collaborative-agreement tone)
- `Source:` attribution line

**Do NOT fill `violation_keywords` or `violation_checks` yet** — Phase 2 handles mechanism. Keeping Phase 1 content-pure means:
- You focus on domain accuracy + source synthesis
- User reviews content only, not schema details
- If user rejects a rule, you didn't waste effort on its keywords/checks

Compose the pack:

- **Preserve cross-scenario universals from current pinrule defaults** (if installed): `loud-failure-with-evidence`, `read-before-write`, `non-blocking-parallel` apply to *any* scenario. Strongly recommend keeping them.
- **Drop dev-specific rules that don't apply**: e.g., `chinese-plain-no-jargon`, `no-testset-no-future-leakage`, `long-term-fundamental` (anti-shortcut for code) — drop if scenario isn't dev.
- **Add 3-5 scenario-specific rules** synthesized from Source A/B/H, filtered through Source S.

**Each rule MUST have source attribution.** Format:

```
[research-no-fabricated-citation]
  preference: <full multi-line text>
  Source: 源自 your ~/.claude/CLAUDE.md L42-45 + ICLR 2024 reviewer guidelines
```

This lets the user audit each rule's provenance before approving the *content*. Mechanism details (keywords, checks) come in Phase 2.

### Step 4 (Path B, Phase 1): Content preview with diff

Show the user the **content** of the full proposed library + diff vs. current. Show no mechanism details yet — keep the review focused.

**Required first line: backend detection summary.** Phase 1 preview MUST start with a one-line backend summary from Step 0.5. If you haven't run `pinrule doctor` yet, run it now and parse before continuing. This isn't decorative — it's the only way to enforce that Step 0.5 actually executed before Phase 2 needs the data. Format:

```
**Backends detected** (via `pinrule doctor`): Claude ✓ / Codex ✓ / Cursor ✓ (桌面 Agent transcripts OK)
```

If a backend isn't installed, show ✗. For Cursor specifically, also note 桌面 / CLI / mixed status based on `transcript_path` health (covered by `pinrule.cursor_transcript_doctor` parsed by `pinrule doctor` output).

```markdown
## Proposed scenario rule pack — research (7 rules) — CONTENT PREVIEW

**Backends detected** (via `pinrule doctor`): Claude ✓ / Codex ✓ / Cursor ✓ (桌面 Agent)

### Carried over from current library (3 cross-scenario universals)
- [loud-failure-with-evidence] — 完成时附证据
- [read-before-write] — 改前先读
- [non-blocking-parallel] — 非阻塞推进

### New (4 scenario-specific)
- [no-fabricated-citation]
  preference: <full text>
  Source: 源自 your ~/.claude/CLAUDE.md L42 + ICLR 2024 reviewer guidelines

- [assumption-vs-conclusion]
  preference: <full text>
  Source: 源自 nature.com/articles/research-integrity-guide-2023 + Karpathy principle 7

- ...

### Removed from current library (4 — dev-specific, don't apply to research)
- [chinese-plain-no-jargon] — language-style preference, not domain rule
- [no-testset-no-future-leakage] — ML-eval specific
- [long-term-fundamental] — anti-shortcut for code refactoring
- [deep-fix-not-bypass] — pinrule-meta rule for dev work

— mechanism details (keywords + engine checks) come in Phase 2 after you confirm content —
```

### Step 5 (Path B, Phase 1): Content approval — one prompt, not per-rule

```
"以上 7 条规则的**内容**替换你现有规则库, 来源已标注. 用一行回复:
   - '应用' / 'apply' → 内容定下来, 进入 Phase 2 配置机制 (keyword + engine check)
   - '应用但保留 [X / Y]' → 我保留你 call out 的现有规则一起加
   - '换 [Z] 为 [...]' → 我替换某条内容
   - '不要 [W]' → 我去掉某条
   - '追加不替换 / append' → 仅加新规则, 现有全保留 (会超软上限)"
```

Don't ping-pong per-rule. User gives one structured reply, you commit the content list and move to Phase 2.

---

## Phase 2 — Mechanism design + approval (Steps 6-9)

Now that the **rule list is locked**, you design the detection mechanism for each rule. This is pure schema engineering — no more domain debate.

**Note**: backend detection happened in **Step 0.5** (Path B Preflight, before Phase 1). The detection results should already be available — use them directly in Step 7 (coverage table) and Step 11 (closing reminder). If you skipped Step 0.5, go back and run `pinrule doctor` now — DO NOT proceed to Step 6/7 without backend data.

### Step 6 (Path B, Phase 2): Generate `violation_keywords` for each approved rule

For each approved rule, generate 3-8 `violation_keywords`:

- **Format**: "intent-prefix + action" (e.g., `"我直接给你方案"` not `"方案"`)
- Match phrases the user/Agent would actually say *when violating the rule*
- Cap at ~5-8 keywords per rule (more ≠ better; noisy pattern-match)
- Mental test: "If Agent says this exact phrase, did they violate?"

Example for `no-fabricated-user-voice`:
```
violation_keywords: [
  "用户应该会说",
  "典型用户会",
  "假设用户觉得",
  "我猜大部分用户",
  "用户大概会反馈"
]
```

These get scanned in PreToolUse (Write/Edit/Bash content) + Stop hook (Agent response text) — **Layer 1.5 keyword detection works for any rule, no engine check required**.

### Step 7 (Path B, Phase 2): Map each rule to an engine check (semantic pattern matching)

Now evaluate whether each rule semantically matches one of the **8 built-in engine checks**. Engine checks add Layer 2 precision (read tool_input + session_state for joint judgment beyond keyword grep).

**Critical**: don't fabricate function names. Schema validation will reject unknown names. Only the 8 below work:

| Rule semantic pattern | Engine check function | What it detects |
|---|---|---|
| "X before Y" / 「先理解再行动」 | `read_before_write` | Edit/Write tool before Read on same target |
| "claim with evidence" / 「证据 + 老实失败」 | `loud_failure_with_evidence` | Completion words without test_pass / data evidence in session |
| "non-blocking / 长任务期间不 idle" | `non_blocking_parallel` | Sleep / long task without `run_in_background` |
| "keep pushing / no silent stop" | `keep_pushing_no_stop` | Agent silent-stop with pending TODOs |
| "no shortcut / 不糊弄" | `long_term_fundamental` | git `--no-verify` / hardcoded long-hash if-branch / TODO scaffolding |
| "no testset leak / 评测干净" | `no_testset_no_future_leakage` | Eval data backfeeding training / cross-split copying |
| "deep fix not bypass" | `bypass_pinrule_detection` | Bash command writing pinrule internal state |
| "plain language" / 「直白沟通」 | `chinese_plain_no_jargon` | Chinese ratio < 40% / jargon terms |

**Cross-scenario reuse examples** (8 engine checks **partially map** to generic behavior patterns — they don't semantically understand UX research / legal citations / writing outlines, they detect specific operational signals):

- UX scenario 的 `understand-context-before-design` → `read_before_write` (设计前没读已有研究 partially maps to「Edit/Write tool 前没 Read 同 file」—— engine 真检测的是 tool-level 读写顺序，跨场景对应是部分映射不是语义等价)
- Legal scenario 的 `evidence-with-citation` → `loud_failure_with_evidence` (法律意见没附判决引用 partially maps to 「完成 claim + session 缺测试通过 evidence」—— engine 不真验证判决书 citation，只检测 completion-language + missing-evidence 这一层)
- Writing scenario 的 `outline-before-prose` → `read_before_write` (写正文前没列大纲 partially maps —— engine 不懂「大纲」概念，只检测 file 读写顺序)
- Research scenario 的 `validate-before-claim` → `loud_failure_with_evidence` (结论没附实验数据 partially maps to claim-without-evidence operational signal)
- Marketing scenario 的 `data-driven-not-vibes` → `loud_failure_with_evidence` (策略主张没附数据 partially maps)

**Be honest about engine check limits**: `read_before_write` is file-IO-order detection, `loud_failure_with_evidence` is completion-language + session-evidence detection. They don't understand UX research methodology / legal citation standards / writing craft. Most cross-scenario rules end up as `preference-only` (Layer 1 header injection + Layer 1.5 keyword) — that's expected, not a failure.

**If no engine check semantically fits** → leave `violation_checks: []`. The rule still gets header injection (Layer 1) + keyword detection (Layer 1.5), just no Layer 2 precision check. Many cross-scenario rules are fine as `preference-only`.

#### Backend coverage for each engine check

Each engine check fires at different hook event points. Coverage by backend (based on which hook events each backend actually delivers):

| Engine check | Hook event | Claude | Codex | Cursor 桌面 Agent | Cursor CLI |
|---|---|---|---|---|---|
| `read_before_write` | PreToolUse | ✅ | ✅ | ✅ | ✅ |
| `loud_failure_with_evidence` | Stop / afterAgentResponse | ✅ | ✅ | ✅ | ⚠️ silent if transcript_path null |
| `non_blocking_parallel` | PreToolUse (Bash) | ✅ | ✅ | ✅ | ✅ |
| `keep_pushing_no_stop` | Stop | ✅ | ✅ | ✅ | ⚠️ |
| `chinese_plain_no_jargon` | Stop | ✅ | ✅ | ✅ | ⚠️ |
| `long_term_fundamental` | Stop + PreToolUse | ✅ | ✅ | ✅ Bash 路径; Stop 路径 ✅ | Bash ✅ / Stop ⚠️ |
| `no_testset_no_future_leakage` | PreToolUse | ✅ | ✅ | ✅ | ✅ |
| `bypass_pinrule_detection` | PreToolUse | ✅ | ✅ | ✅ | ✅ |

**Read this carefully**:
- **Cursor 桌面 Agent (IDE Composer) = 默认整列 ✅** —— transcript 自动写, 不需要用户开开关. **不要给桌面用户发任何 transcript advisory**, 那是 over-warning.
- **Cursor CLI (`cursor agent` 终端) = 边缘场景, 部分 Stop-hook 类 check ⚠️** —— 这是 future feature, pinrule 当前不补齐 CLI null `transcript_path`. 检测到 CLI 主战场用户时再给警告.
- **Claude / Codex = 整列 ✅** —— 不需要任何 backend-specific advisory.

When assigning engine checks in Step 7, **based on Step 0.5 detected backend**, decide whether each rule's engine check is reliable:
- 桌面 Agent 用户: 8 个 check 全可靠 → 直接 attach 适用的 check
- Cursor CLI 主战场用户 (rare): Stop-hook 类 4 个 check 不稳 → 仍然 attach 但 Step 8 preview 标 ⚠️ + Step 11 末尾建议「主用桌面 Agent」

### Step 8 (Path B, Phase 2): Mechanism preview — full rules with keywords + checks

Show user the *complete* rule pack with mechanism details:

```markdown
## 机制配置 (Phase 2) — 完整规则集

[loud-failure-with-evidence] ✓ engine: loud_failure_with_evidence (保留)
  preference: <text>
  violation_keywords: ["这事搞定了", "已经完成", ...] (保留现有)
  violation_checks: ["loud_failure_with_evidence"]

[no-fabricated-user-voice] preference-only (keyword-detect only)
  preference: <text>
  violation_keywords: ["用户应该会说", "典型用户会", "假设用户觉得", "我猜大部分用户", "用户大概会反馈"]
  violation_checks: []
  Why no engine: 「编造 user voice」是字面违反, keyword 已覆盖, 没有 8 个内建 check 语义匹配

[understand-context-before-design] ✓ engine: read_before_write
  preference: <text>
  violation_keywords: ["看起来是个新需求", "应该不影响别的", "我直接设计就好"]
  violation_checks: ["read_before_write"]
  Why this engine: 「设计前没读已有研究」≡「Edit 前没 Read」同行为 pattern
  Backend coverage: ✅ Claude / ✅ Codex / ✅ Cursor 桌面 (PreToolUse 通用)

[loud-failure-research-claim] ✓ engine: loud_failure_with_evidence
  preference: <text>
  violation_keywords: ["这个研究表明", "数据显示", "结论是"]
  violation_checks: ["loud_failure_with_evidence"]
  Why this engine: 「研究 claim 没附数据」≡「completion 没附 test_pass evidence」
  Backend coverage: ✅ Claude / ✅ Codex / ✅ Cursor 桌面 Agent
  ⚠️ 如果你主要用 Cursor CLI (非桌面 Agent), Stop hook 路径 silent — 建议主用桌面 Agent

...
```

For each rule explicitly state:
- Whether it has engine check
- Which one + why (cross-scenario reuse rationale)
- Or why no engine check (preference-only + keyword 已经够 / 没匹配的 pattern)
- **Backend coverage line** showing which backends this engine check works on (based on Step 0.5 detection — only flag Cursor CLI advisory if user is detected as Cursor CLI主战场, otherwise just show Cursor 桌面 ✅)

### Step 9 (Path B, Phase 2): Mechanism approval

```
"机制配置 ready. 用一行回复:
  - '应用' → batch write
  - '调 [<id>] keyword: 加 X / 删 Y' → 调某条 keyword
  - '调 [<id>] engine: 用 X 不要 Y' → 调某条 engine check 映射
  - '退回 Phase 1' → 回去改内容"
```

Don't re-debate content here — content was locked in Step 5. If user wants content change, explicitly retreat to Phase 1.

---

## Step 10 (Path B): Atomic batch write — `pinrule rule import-pack`

After both phases approved, write the final rule pack as **one atomic command** (v0.18.0+):

```bash
# 1. Compose the final pack as a single JSON file (Phase 2 approved keywords + checks)
cat > /tmp/pinrule-scenario-pack.json <<'EOF'
[
  {"id": "loud-failure-with-evidence", "preference": "...", "violation_keywords": [...], "violation_checks": ["loud_failure_with_evidence"]},
  {"id": "read-before-write", "preference": "...", "violation_keywords": [...], "violation_checks": ["read_before_write"]},
  {"id": "no-fabricated-user-voice", "preference": "...", "violation_keywords": [...], "violation_checks": []},
  ...
]
EOF

# 2. Atomic import — replaces rule library in one shot, with backup
pinrule rule import-pack --from-json /tmp/pinrule-scenario-pack.json --mode replace --backup
```

**Why a single command** (engineering-first principle): pinrule's `import-pack` does **all validation before any write**:
1. Reads existing `rules.json`
2. Parses + schema-validates the entire pack
3. Verifies id uniqueness, soft/hard caps, `violation_checks` function existence
4. Creates a backup (if `--backup`)
5. Writes to `rules.json.tmp` + `os.rename` swap (atomic on POSIX + Windows)

**If anything in steps 1-4 fails**, `rules.json` is **byte-for-byte unchanged**. This is real atomic, not the old `remove + add` shell chain which could leave the library half-replaced.

**Modes**:
- `--mode replace`: Default for Path B scenario switch. Entire rule library = new pack.
- `--mode append`: Add new pack to existing rules. Only use if user explicitly said "追加 / append" in Phase 1.

**Always pass `--backup`** for scenario switches — creates `~/.pinrule/rules.json.before-scenario-<YYYYMMDD-HHMMSS>` so the user can revert if they don't like the new pack after a few sessions.

If `pinrule rule import-pack` fails (e.g., schema reject), tell the user the exact reason from stderr — `rules.json` is intact, just retry after fixing the rejected rule.

### Step 11 (Path B): Tell user this is v1 — iterate from real data

After writing:

> ✓ 已切到「<scenario>」规则集 (X 条). 这是基于以下信号综合起草的初稿:
>   - 你本机已有规则文件 (扫了 ~/.claude/CLAUDE.md + 项目 CLAUDE.md)
>   - 业界 best practice (从 [X / Y repos] 拉了 N 条参考)
>   - Karpathy CLAUDE.md baseline (用了 N 条 principle)
>   - 我跟你协作的 session 上下文
>
> 建议跑 1-2 周后:
>   - `pinrule audit --by-check` 看哪些规则真触发 / 哪些没触发
>   - 真触发但你觉得是假阳 → `pinrule rule remove <id>` 删
>   - 真有用的方向但当前规则措辞不够 → `/pinrule <自然语言>` 加调整规则
>
> 备份: ~/.pinrule/rules.json.before-scenario-<timestamp>

**Backend-aware reminder** (conditional on Step 0.5 detection):

- If user is **Cursor 桌面 Agent 主战场**: no extra warning needed — coverage is full (don't over-warn).
- If user is **Cursor CLI 主战场** (rare, detected via `pinrule doctor` showing mostly null `transcript_path`): append:
  > ⚠️ 检测到你主要用 Cursor CLI (非桌面 Agent), 你这套规则里 N 条 Stop-hook 类 engine check (loud_failure / keep_pushing / chinese_plain / long_term) 在 CLI 上可能 silent. 建议主用 Cursor **桌面 Agent (IDE Composer)** —— 默认 transcript 自动写, 这些 check 真生效. 跑 `pinrule doctor` 看 transcript 状态.
- If user is **Claude / Codex 主战场**: no Cursor-specific warning needed.

### Path B example walkthrough — research scenario (two-phase flow)

**User**: `/pinrule 我主要做 ML 论文 + 数据分析, 切到这个场景规则集`

#### Phase 1 — Content

**Agent** (you):

> 收到. 我帮你综合 4 个信号源生成研究场景规则集 — 先扫信号源.
>
> [Read ~/.claude/CLAUDE.md] → 你写了 8 条偏好, 跟 ML 相关的有: ...
> [Read 当前项目 CLAUDE.md] → 项目协作约定有: ...
> [WebSearch "ICLR research integrity AI agent"] → 找到: arxiv.org/abs/... + github.com/...
> [WebFetch github.com/awesome-claude-md/research/CLAUDE.md] → 借鉴 3 条原则
> [Karpathy CLAUDE.md] → 适用 ML 场景: 原则 3 (explicit failure) / 原则 7 (single-source-of-truth)
> [Session context] → 我看你这个 session 做的是 transformer model 训练 + ablation 实验, 偏 experimental ML
>
> ## 📋 Phase 1: 内容预览 — ML research (7 条)
>
> ### 保留现有 (3 条普适)
> - [loud-failure-with-evidence]
> - [read-before-write]
> - [non-blocking-parallel]
>
> ### 新加 (4 条 ML research 特化)
>
> - [no-fabricated-citation]
>   preference: 用户做 ML 研究, 引用论文 / dataset / 结果时必须真存在 ...
>   Source: 源自 ICLR 2024 reviewer guidelines + your ~/.claude/CLAUDE.md L23
>
> - [ablation-completeness]
>   preference: 报实验结果时必须含 ablation / baseline 对比, 不能只报主结果 ...
>   Source: 源自 github.com/google/papers-with-code best practice + your project CLAUDE.md L8
>
> - [eval-data-isolation]
>   preference: 模型 eval / hyperparam search 严格分离 train/val/test ...
>   Source: 源自 your previous `no-testset-no-future-leakage` 规则 (保留改名) + Karpathy 原则 5
>
> - [assumption-explicit]
>   preference: 写论文 claim 时区分「数据支持的结论 vs 还在假设阶段的推测」 ...
>   Source: 源自 Karpathy 原则 7 + arxiv.org/abs/2306.research-integrity
>
> ### 删掉 (4 条 dev-specific)
> - [chinese-plain-no-jargon] — 语言风格偏好
> - [no-testset-no-future-leakage] → 被 [eval-data-isolation] 替换
> - [long-term-fundamental] — ML 实验代码迭代快不适用
> - [deep-fix-not-bypass] — pinrule-meta 规则
>
> — 机制配置 (keywords + engine checks) 会在 Phase 2 配, 先确认内容 —
>
> 一行回复:
>   - '应用' → 内容定下, 进入 Phase 2 配机制
>   - '应用但保留 [...]' → 保留你指定的现有规则一起加
>   - '不要 [Y]' → 去掉某条
>   - '追加不替换' → 仅加新的, 不删现有

**User**: 应用, 但保留 chinese-plain-no-jargon

#### Phase 2 — Mechanism

**Agent**:

> 内容定下来了 — 8 条规则 (3 保留 + 1 用户 call out + 4 新). 进入 Phase 2 配机制.
>
> ## ⚙️ Phase 2: 机制预览
>
> ### 保留现有 (4 条 — keyword + engine check 不动)
> - [loud-failure-with-evidence] ✓ engine: loud_failure_with_evidence
> - [read-before-write] ✓ engine: read_before_write
> - [non-blocking-parallel] ✓ engine: non_blocking_parallel (force_block_exempt)
> - [chinese-plain-no-jargon] preference-only (按你要求保留, 现有 keyword 不动)
>
> ### 新规则机制配置 (4 条)
>
> - [no-fabricated-citation] preference-only (keyword-detect only)
>   violation_keywords: ["该论文表明", "据某研究", "有研究指出", "文献支持", "已有工作显示"]
>   violation_checks: []
>   Why no engine: 「编造引用」是字面违反, keyword 已覆盖; 没有 8 个内建 check 语义匹配 (loud_failure 偏 "claim with data 证据", 不是 "citation 真假")
>
> - [ablation-completeness] ✓ engine: loud_failure_with_evidence
>   violation_keywords: ["主结果是 X", "整体准确率", "我们的方法效果"]
>   violation_checks: ["loud_failure_with_evidence"]
>   Why this engine: 「报实验结果没附 ablation/baseline」≡ 「claim 没附数据」同 pattern — loud_failure 检测 completion words + 缺测试通过 evidence, 同样适用「ML claim + 缺 ablation 数据」
>
> - [eval-data-isolation] ✓ engine: no_testset_no_future_leakage
>   violation_keywords: ["复用 test set", "拿测试集调", "在 eval 上 search"]
>   violation_checks: ["no_testset_no_future_leakage"]
>   Why this engine: 直接复用现有 check, 同语义模式 (eval data 反喂主流程)
>
> - [assumption-explicit] preference-only (keyword-detect only)
>   violation_keywords: ["显示", "证明", "表明" (在缺数据的 claim 后面)]
>   violation_checks: []
>   Why no engine: 「假设当结论」需要 semantic 判断, 不是字面 trigger. 现有 8 个 check 没匹配的 — preference 注入 + keyword 兜底就够
>
> 一行回复:
>   - '应用' → batch write
>   - '调 [<id>] keyword: 加 X / 删 Y' → 调某条 keyword
>   - '调 [<id>] engine: 用 X 不要 Y' → 调某条 engine check 映射
>   - '退回 Phase 1' → 回去改内容

**User**: 应用

**Agent**:

> [组合 Phase 2 approved 8 条规则 → /tmp/pinrule-ml-research-pack.json]
> [pinrule rule import-pack --from-json /tmp/pinrule-ml-research-pack.json --mode replace --backup]
>
> ✓ Import pack 成功 (replace 模式) — 当前规则库 8 条
> 备份: ~/.pinrule/rules.json.before-scenario-20260518-153022
>
> ✓ 已切到 ML research 场景规则集 (8 条):
>   - 4 条保留 (3 普适 + chinese-plain 按你要求)
>   - 4 条新加 (2 条 engine: ablation-completeness + eval-data-isolation, 2 条 preference-only: no-fabricated-citation + assumption-explicit)
>
> 备份: ~/.pinrule/rules.json.before-scenario-20260518-153022
>
> 跑 1-2 周后 `pinrule audit --by-check` 看真触发分布, 据此调整.

## Common mistakes to avoid

- ❌ Don't write rules in "rule-system" tone ("you must always...")
- ❌ Don't use noun-only violation_keywords ("hardcoding" — too broad)
- ❌ Don't fabricate `violation_checks` function names — only use the 8 built-in ones
- ❌ Don't skip the preview step — always preview before `add`
- ❌ Don't add a new rule without checking for overlap with existing ones
- ❌ Don't exceed the soft cap 10 / hard cap 12 — too many rules backfire (LLMs pattern-match rule existence instead of truly reading)
- ❌ Don't silently treat scoped-sounding requests ("during X, do Y") as scoped — pinrule is always-on. Surface the ambiguity in Step 1.
- ❌ Don't write English `preference` text when the user is talking to you in Chinese (or vice versa) — match the user's language. Only `violation_checks` function names stay English (stable identifiers).
- ❌ Don't go straight from Step 1 → Step 4 preview without showing the user a draft inline in Step 3 — they should react to wording before it's written to disk.

### Path B specific mistakes

- ❌ Don't ping-pong with subscenario questions when session context already tells you (Step 1)
- ❌ Don't ask user to opt into each signal source (A/B/H/S) — all four are default-on, pinrule is opinionated
- ❌ Don't skip the **Source attribution** line in each rule preview — provenance is non-negotiable for user audit
- ❌ Don't default to append for scenario rule pack (Path A default is append; Path B default is replace)
- ❌ Don't skip the backup step before batch write — `cp ~/.pinrule/rules.json ~/.pinrule/rules.json.before-scenario-*` is the rollback path if anything fails
- ❌ Don't claim "I researched online" without actually running WebSearch / WebFetch — fabricating sources is worse than just synthesizing from training knowledge honestly
- ❌ Don't include `pinrule rule add --from-json` for rules sourced from `~/.pinrule/rules.json` itself (self-reference loop — read user's *non-pinrule* files for signal)
- ❌ Don't propose >10 rules in the pack (pinrule soft cap is 10; aim for 5-7 to leave room for user's later /pinrule additions)

### Path B two-phase mistakes (specific to the Phase 1/Phase 2 split)

- ❌ Don't put `violation_keywords` or `violation_checks` in Phase 1 content preview — Phase 1 is content-only. Mixing mechanism into content review dilutes user attention and wastes effort on rules that may get rejected.
- ❌ Don't re-debate rule **content** in Phase 2 — content was locked in Step 5. If user wants content change, explicitly retreat to Phase 1.
- ❌ Don't fabricate engine check function names — only the 8 in the mapping table work. Schema validation rejects unknown names.
- ❌ Don't force every rule to have an engine check — if no built-in check semantically fits, `violation_checks: []` (preference-only) is fine. Layer 1 (header injection) + Layer 1.5 (keyword detection) still work.
- ❌ Don't skip the "Why this engine / Why no engine" rationale line per rule in Phase 2 preview — user needs to see your mapping reasoning to trust it.

---

## No-argument flow — see fast-path at top of skill

This is fully handled by the **Fast-path** block at the very top of this skill (right after frontmatter). When `$ARGUMENTS` is empty:

1. Run `pinrule audit --by-check` via Bash
2. Dump output verbatim, no synthesis
3. Exit — don't ask follow-ups

No business logic, no Agent interpretation, no second-guessing. Pure pass-through. This is the simplest possible flow on purpose — the user typed `/pinrule` with no args because they want the data, not your commentary.

**Edge cases** (rare):
- User typed `/pinrule help` or similar literal help-request → show brief summary of `/pinrule` ({rule add | scenario switch | no-args → audit dashboard})
- `pinrule audit --by-check` returns empty (no violations yet) → tell user "no violations recorded yet, come back after a few sessions"
