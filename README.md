# karma

**[🇬🇧 English (current)](./README.md) · [🇨🇳 中文](./README.zh.md)**

[![CI](https://github.com/jhaizhou-ops/karma/actions/workflows/ci.yml/badge.svg)](https://github.com/jhaizhou-ops/karma/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen)](https://github.com/jhaizhou-ops/karma/actions)
[![Latest Release](https://img.shields.io/github/v/release/jhaizhou-ops/karma?label=release)](https://github.com/jhaizhou-ops/karma/releases)
[![Last Commit](https://img.shields.io/github/last-commit/jhaizhou-ops/karma)](https://github.com/jhaizhou-ops/karma/commits/main)

> **Andrej Karpathy's 60k-stars [CLAUDE.md](https://github.com/forrestchang/andrej-karpathy-skills) teaches AI how to write good code. karma solves the other half — how to make AI never violate your rules in long tasks, and most importantly, how to auto-correct violations before they frustrate you.**
>
> **Two sides of the same loop**:
>
> 🛡️ **Pin your rules → Agent complies.** 5-10 core directions injected into every prompt header; real-time hook detection; cross-compact + cross-locale + cross-backend. Measured violation rate in long-running tasks: **≈ 0%.**
>
> ✨ **Tell karma in plain words → Agent writes the rule.** Type `/karma <natural language>` — Claude Code / Codex / Gemini CLI launches the karma skill that refines your phrasing into karma's validated "collaborative agreement" tone, previews the injection text, confirms with you, then adds to your rules.yaml. Auto-installed across all three backends on `karma init`.
>
> Works with Claude Code / Codex CLI / Gemini CLI. Pure engineering, zero LLM dependency, violation monitoring response < 60ms.

---

**Table of contents**: [Real problems](#real-problems-you-face) · [Quick install](#zero-dependency-pure-engineering-10-second-install) · [How it works](#why-it-works) · [`/karma` natural-language rule input](#karma-natural-language--agent-writes-the-rule-for-you) · [Usage effects](#usage-effects) · [Performance](#performance-quantified) · [8 hook monitoring](#8-hook-positions-full-monitoring) · [Customize rules](#customize-your-own-rules) · [What karma doesn't do](#tried-and-rejected-what-karma-doesnt-do) · [FAQ](#faq) · [Docs](#documentation)

---

## Real problems you face

| Real pain | Failure scene | How karma solves |
|---|---|---|
| **"I said use long-term solutions, not patches" — after 30 turns the Agent patches again** | Turn 1: you say "use the cleanest solution," Agent answers "got it." Turn 50: "let me patch this quickly." Your preference got diluted by new content. | Pin 5-10 core directions at the most prominent position of every prompt — Agent can't miss them |
| **"I said don't block the frontend — keep working while tests run" — Agent runs `sleep` anyway** | Agent runs `sleep 30`, UI blocks for 30s, you watch the progress bar — Agent never realized this is "stuck waiting" | Real-time block of `sleep` / `wait` / long tasks without background mode, hit → deny before tool runs |
| **After compact the Agent compressed my preferences into vague words** | At 80K context, compact triggers; after SessionStart, Agent compresses "no patches" into "write clean code," intent lost | Auto-dump full rule state pre-compact; auto-reload + strong-inject post-compact restart |
| **Long context accumulation → attention decay → Agent drifts** | At 60-80K accumulated context, headers get diluted — Agent isn't ignorant, attention decayed | Per-model adaptive threshold (different decay points per model), auto-reinject mid-conversation when accumulation hits threshold |
| **Agent sees reminders → triggers defense reactions / rationalization** | LLMs trained to please users — when faced with violation reminders, the first reaction is defensive self-justification or shortest-path patching, not genuine correction | Translate "rule" tone into "collaborative agreement" tone. Long-term real-world testing shows: LLMs facing "collaborative agreement" language switch first reaction to "align and comply" rather than "find workaround" |
| **Agent finishes one small feature, then stops to ask "what's next?" (the author is fully-delegating)** | User gives clear direction → Agent finishes step 1 → "What should I do next?" → user comes back from other work and finds Agent stopped for 30 minutes | Stop hook detects silent stops, injects reflective prompt with up to 2 nudges encouraging continued execution until progress truly saturates |
| **"I want to add a rule but writing yaml is too heavy / my phrasing doesn't make the Agent comply"** | You know what behavior you want but writing the rule itself is a chore — wrong `violation_keywords` format triggers false positives, wrong tone makes Agents defensive | Type `/karma <natural language>` in any of Claude Code / Codex / Gemini CLI — karma's skill refines tone, formats keywords, detects overlap with existing rules, previews the injection, confirms with you, then writes — 30 seconds end-to-end |

---

## Zero-dependency pure engineering, 10-second install

```bash
git clone https://github.com/jhaizhou-ops/karma.git ~/karma
cd ~/karma && python -m venv .venv && .venv/bin/python -m pip install -e .
.venv/bin/karma init && .venv/bin/karma install-hooks
```

> Restart Claude Code / Codex CLI / Gemini CLI — takes effect immediately.
>
> `karma init` auto-installs the `/karma` natural-language skill across all three backends (`~/.claude/skills/karma/`, `~/.agents/skills/karma/`, `~/.gemini/skills/karma/` + `~/.gemini/commands/karma.toml`). No extra step.

### Or ask your AI client to install it

Paste this to Claude Code / Codex / Gemini CLI:

```
Install karma (github.com/jhaizhou-ops/karma) — a lightweight hook system
that keeps my core direction preferences from being lost in long tasks.
Steps:
1. git clone to ~/karma
2. Create .venv and pip install -e .
3. Run `karma init` to initialize the default rule template
4. Run `karma install-hooks` to install for my current client
5. Run `karma doctor` to verify installation
```

### Per-client install commands

| Client | Install command | Note |
|---|---|---|
| Claude Code | `karma install-hooks` (default) | Takes effect immediately |
| Codex CLI | `karma install-hooks --backend codex` | **codex 0.130+ requires manual approval** of karma's 4 wrappers via TUI `/hooks` command |
| Gemini CLI | `karma install-hooks --backend gemini-cli` | Takes effect immediately |

### Uninstall

```bash
.venv/bin/karma uninstall-hooks                                # Remove hooks
cp ~/.claude/settings.json.before-karma ~/.claude/settings.json # Restore original
```

---

## Usage effects

After installing karma and restarting your AI client, you'll see these automatic interventions in typical scenarios:

### 1. Every conversation auto-injects rule full text + past violation highlights

Every user prompt submission, your AI client auto-prepends your 5-10 core directions + reminders about which rules drifted in your last response. The Agent sees them first:

```
[karma — Your long-term agreement with the user]
You're collaborating with a real human user who listed several
long-term priorities. This isn't rules and isn't a judgment — these
are the collaborative agreements they hope to build with you.

1. The user trusts you to dig into root causes...
   〔Last response had drift on this one — let's realign this turn〕
2. When sleep / wait / long tasks are running, the user is waiting...
3. Your user is non-technical — they want comprehensible reports...
```

### 2. Long-context accumulation triggers mid-conversation reminders (anti-drift)

LLMs' attention decays in long contexts — headers get diluted by new content. karma tracks accumulation per tool call, and once the current model's decay threshold is hit (per-model adaptive), auto-injects a concise reminder at the point where the Agent is about to drift, re-anchoring at the precise context length:

```
[karma — After long context, recall the agreement with the user]
Context has accumulated for a while. Reminding you of the
long-term priorities (no need to respond, just refresh in mind
to avoid future drift):
  ▸ long-term-fundamental: The user trusts you to dig into root causes...
  ▸ non-blocking-parallel: When sleep / wait / long tasks are running...
  ▸ chinese-plain-no-jargon: Your user is non-technical...
```

### 3. Real-time violation check before tool calls + targeted reminders

Before Agent runs Bash / Edit / Write tools, karma scans the command content + keywords. Hits → deny tool with improvement suggestion:

```
$ Bash sleep 30
karma ⚠️: 'non-blocking-parallel' violation — sleep periods make the user
        feel "stuck." Use run_in_background=True; the task completion
        will notify you, freeing you to do the next thing.
[permission deny]
```

### 4. Subagent monitoring with full coverage

When the main Agent spawns subagents via the Task tool, karma auto-injects the full rule set to the subagent + maintains independent monitoring state. Subagents are monitored at the same intensity as the main Agent; state auto-destroys on completion without polluting the main session.

### 5. Context-compression auto-injection (anti-compact-amnesia)

When the AI client auto-triggers compact for long sessions, karma dumps the full rule state to a local file before compression. After compression restart, immediately re-reads and strong-injects — rules survive compact without loss.

### 6. Silent-stop reflective injection

When Agent finishes a wave and tries to stop and ask "what's next?", karma detects this silent-stop behavior and injects a reflective prompt encouraging continued progress:

```
[karma — Your last response showed no next-step signal]
The user is fully-delegating — they expect you to immediately
continue after finishing a wave. If you need their judgment, ask
clearly; if you're truly saturated, say where you're stuck — don't
silently wait.
(Reminder 1/2)
```

Up to 2 consecutive reflective prompts — if truly saturated, the Agent can say where it's stuck, and karma won't force-push.

---

## `/karma <natural language>` — Agent writes the rule for you

This is karma's other half — the **partner** side, not the **monitor** side.

```
You (in Claude Code):   /karma When I say "done" I want test pass evidence attached
                        Don't accept vague "should work" claims.

Agent (karma skill walks 7 steps automatically):
  ① Understand intent — flags anchor-vs-scope ambiguity if any
  ② Check existing rules — semantic overlap detection (modify vs add)
  ③ Draft yaml inline — collaborative-agreement tone, locale-aware
  ④ karma rule preview — schema + REGISTRY validation
  ⑤ Confirm with you — adjust wording / keywords / engine-check
  ⑥ karma rule add — atomic write to rules.yaml
  ⑦ Report — count, takes-effect timing, redundancy suggestions

→ 30 seconds end-to-end, rule live on next UserPromptSubmit.
```

### What the skill handles for you

| Hard part of writing a rule | What the skill does |
|---|---|
| **Tone — "you must always X" backfires on LLMs** | Rewrites in karma's "collaborative agreement" phrasing. Long-term testing shows LLMs respond with "let me align" rather than "let me argue" |
| **Format — bare keywords trigger false positives** | Converts to "intent-prefix + action" format (e.g. `"I'll hardcode"` not `"hardcode"`) so discussion vs. action is distinguishable |
| **Overlap — accidentally adding a duplicate rule wastes a slot** | 4-row decision table on overlap shape (full duplicate / superset / keyword-overlap / no overlap); offers modify-existing path instead of bloating to 11 rules |
| **Scope ambiguity — "during X, do Y" is often anchor not scope** | Surfaces the ambiguity verbatim ("just to check: whenever we collaborate, or strictly during X?") instead of silently guessing |
| **Locale — mixing English skill body for Chinese user** | Detects user's chat language; writes Chinese `preference` for Chinese users, English for English users. Built-in `violation_checks` function names stay English (stable identifiers) |
| **Modify vs add — no separate `rule replace` command** | Knows the `remove + add` recipe atomically; preserves `id` so violation history stays linked |

### Three backends, one command

| Backend | Path (auto-installed) | Trigger in client |
|---|---|---|
| Claude Code | `~/.claude/skills/karma/SKILL.md` | `/karma <natural language>` |
| Codex CLI | `~/.agents/skills/karma/SKILL.md` (note: `~/.agents/` shared with Anthropic) | `/skills` menu, `$karma <description>` inline, or auto-trigger |
| Gemini CLI | `~/.gemini/skills/karma/SKILL.md` (auto) + `~/.gemini/commands/karma.toml` (explicit) | `/karma <natural language>` (explicit) or auto-trigger (skill path) |

The repository ships one Markdown source of truth at [`skills/karma/SKILL.md`](./skills/karma/SKILL.md); the `karma install-skill` command handles the Markdown → TOML conversion for the Gemini commands path automatically (`$ARGUMENTS` ↔ `{{args}}` syntax translation included).

### Updating the skill after a karma upgrade

```bash
karma install-skill --force          # overwrite all backends' skills with current version
karma install-skill --backend codex  # update one backend only
```

Without `--force`, the new version is written to a `.new` sibling file so you can `diff` your local edits against upstream before deciding.

`karma doctor` reports per-backend skill status so you can see at a glance which is up-to-date.

---

## Why it works

karma isn't a linter, isn't a scoring system, isn't a retrieval system. It addresses 3 real but overlooked LLM collaboration problems:

### 1. Long-context attention decay is real

Modern LLMs' attention decay isn't as early as early models — but it still has decay points. Rules at the conversation top get diluted by new content after dozens of turns. karma per-model adaptively re-injects a reminder at the exact context-length point where decay begins.

### 2. Each conversation "re-forgets" everything

Every AI client conversation works by "send all context to the model again" — the model doesn't persistently remember anything. Your stated preferences need to be re-sent each time. karma does this automatically so you don't have to repeat yourself.

### 3. "Collaborative agreement" tone activates different reactions than "rule system" tone

When LLMs see warnings like "you must always follow X" / "⚠️ violation," the first reaction is defensive self-justification or finding a workaround — because that activates the "I'm being scolded" psychology.

karma uses "the human user you're collaborating with hopes..." style collaborative agreement tone instead of rule-system tone — LLMs facing this style switch first reaction to "adjust to align with collaboration" instead of "find workaround." This is karma's core finding from long-term real-world testing and the key to driving violation rates to ≈ 0%.

### 4. Monitoring covers all hook positions, no blind spots

After installation, karma monitors at 8 hook positions in your AI client (detailed below) — not just "inject once at conversation start." Before/after every tool call / subagent start/stop / pre/post compact / silent Agent stop — all have targeted injections or interceptions, covering every drift opportunity.

---

## Performance (quantified)

| Dimension | Number | Note |
|---|---|---|
| **Runtime dependencies** | **Zero** | Uses only Python ecosystem standard YAML parser (PyYAML is a 15+ year mature core component). No LLM API key / no network calls / no ML framework. |
| **Source code total** | 5481 lines | All Python, readable and modifiable |
| **Test coverage** | Full 4-check green + 5610 test lines + 500+ hours real-world development tuning | lint / type check / dead code scan / unit tests |
| **Violation monitoring latency** | **< 60ms** (measured user_prompt_submit hook ~49ms) | AI client protocol requirement < 200ms |
| **Token injection cost** | ~400 tokens/turn at header + ~60 tokens/mid-conversation refresh | 1 turn 60K context total injection < 1% |
| **Disk usage** | < 10MB | Config + violation history + session state |
| **Supported models** | Per-model adaptive thresholds | Each major model auto-fits its real decay point |
| **Supported clients** | 3 mainstream | Claude Code / Codex CLI / Gemini CLI |

---

## 8 hook positions: full monitoring

| Hook position | Function + scenario | Pain point solved |
|---|---|---|
| **Every user prompt** (UserPromptSubmit) | Header injects full rules + drift markers | Agent forgets your preferences after long session |
| **Before every tool call** (PreToolUse) | Keyword + engine-layer double-check; hit → deny | Agent wants to run sleep / commit --no-verify / bypass rules |
| **After every tool call** (PostToolUse) | Track file read/edit/bash state + auto mid-conversation refresh when accumulation hits threshold | Long context accumulation → attention decay → Agent drifts |
| **Agent stops generating** (Stop) | Terminal stderr ⚠️ + desktop notify + silent-stop reflective intervention | Agent finishes one wave and stops to ask, user gets interrupted repeatedly |
| **Every session start** (SessionStart) | Inject rule baseline at session start; on compact-restart, read snapshot for strong-inject | Rules don't get lost across sessions / across compacts |
| **Before AI client compresses history** (PreCompact) | Dump full rule state to disk for SessionStart to re-read | After compact, Agent compresses rules into vague words |
| **Subagent starts** (SubagentStart) | Subagent auto-inherits full rule set + writes independent monitoring state | Subagents running independent tasks leave monitoring gaps |
| **Subagent ends** (SubagentStop) | Subagent temporary state auto-destroys, doesn't pollute main session | Multiple subagent spawns cause state accumulation, main session data gets confused |

All hook outputs strictly comply with the AI client's official protocol schema — no UI error messages.

---

## Customize your own rules

> 👉 **For most users, use `/karma <natural language>`** ([see above](#karma-natural-language--agent-writes-the-rule-for-you)) — the skill handles tone / overlap / locale / schema validation for you. This section is for **advanced users** who want direct yaml control or are running karma in an environment without the skill loaded.

### Manual `rules.yaml` editing

`~/.claude/karma/rules.yaml` (`karma init` copies the default template):

```yaml
- id: long-term-fundamental
  preference: |
    The user trusts you to dig into root causes. When facing hard problems
    they want you to pause and think "what's the cleanest solution?"
    rather than "what's the fastest patch?"
  violation_keywords:
    - "I'll patch this quickly"   # "Intent prefix + action" format
    - "let me workaround"          # distinguishes discussion from real action
    - "I'll hardcode"
  violation_checks:
    - long_term_fundamental    # 8 built-in engine-layer checks selectable

- id: non-blocking-parallel
  preference: |
    During sleep / wait / long tasks, the user waits for your output.
    Staring at a progress bar isn't collaboration — it's "stuck."
    After kicking off a background task, immediately push the next thing
    that can be done — you'll be notified when the task completes.
  violation_keywords:
    - "let me wait for tests"
    - "let me wait for the subagent"
  violation_checks:
    - non_blocking_parallel
  force_block_exempt: true  # "Non-blocking" conflicts with cumulative-penalty semantics, exempt
```

**Key design points**:
- **`violation_keywords` use "intent-prefix + action" format** ("I'll hardcode" instead of "hardcode") — distinguishes discussion concepts vs. real action statements, avoiding false positives like "don't hardcode" type natural-language discussions
- **Soft cap 10, hard cap 12** — too many rules backfire; LLMs tend to pattern-match "rule exists" rather than truly read; compliance rate drops. Keep rule count within 10 is empirically optimal
- **`force_block_exempt`** for "should keep pushing" type rules — otherwise cumulative penalties contradict the rule semantics itself

### 8 built-in engine-layer check functions

| Function | What it detects |
|---|---|
| `long_term_fundamental` | git `--no-verify` / long-hash if branches / TODO comments |
| `non_blocking_parallel` | `sleep N` / long tasks without `run_in_background` |
| `loud_failure_with_evidence` | Code task claimed done but no test-pass evidence in session |
| `no_testset_no_future_leakage` | Eval data backfeeding training / cross-split copying |
| `read_before_write` | Edit / Write without prior Read of the file_path |
| `bypass_karma_detection` | Bash command containing karma internal state strings + write operations |
| `keep_pushing_no_stop` | Agent silent-stop → reflective continuation prompt |
| `chinese_plain_no_jargon` | Chinese ratio < 40% / English jargon without Chinese explanation (Chinese-user rule, see customization for other languages) |

---

## Tried and rejected (what karma doesn't do)

The author iterated for 2+ months with 3 major refactors and long-term self-use validation:

| Tried | Reason rejected (user perspective) |
|---|---|
| **LLM auto-distilling new rules** | Not just cost — response time drops significantly hurting UX, and auto-distilled rules often produce noise / misalignment (hearing a user say something once doesn't mean it's a core direction). Chose "user manually maintains 5-10 rules" approach, giving users full control |
| **Retrieval / cosine recall** | Real pain point is "persistence," not "recall" — 5-10 rules can all be always-on, no need to select; retrieval introduces extra latency and matching errors |
| **More than 12 rules** | Too many rules backfire — LLMs tend to pattern-match "rule exists" rather than truly read, compliance drops from 76% to 52%. Keeping rule count within 10 is empirically optimal |
| **Competing with memory systems** | "Facts / preferences about the user" are better handled by AI clients' built-in memory systems. karma only does "pin down things you've already repeatedly said" — that one thing |
| **Introducing LLM dependency** | Not just cost — response time drops significantly hurting UX. So we chose pure engineering, zero dependency, < 60ms ultra-low latency approach |
| **Reward / RL scoring system** | Behavior reminders aren't reward functions — scoring rules makes LLMs focus on "score" rather than "behavior," degrading performance |
| **Blocking compact** | Compact is the AI client's protection mechanism — karma shouldn't interfere. We use PreCompact dump + SessionStart re-read to span across, rather than forcibly preventing |
| **"Must follow X / Fix immediately / Don't repeat" warning words** | LLMs facing warning words first react defensively or find workarounds — not genuine correction. Switching to collaborative-agreement tone, LLMs' first reaction becomes "align" not "workaround," and violation rates drop significantly |
| **Precise numeric thresholds in suggested_fix text** | LLMs seeing "34% < 40%" optimize the number (pad Chinese chars) rather than the underlying UX. Changed to goal descriptions like "let users read without needing to look up words" for better effects |

---

## Honest tool boundaries

karma is a **regex literal matching + counting** engineering tool, not LLM semantic understanding:

- **False positives exist** (legitimate operations may get blocked): table cell term references / `python -c` string literals / commit message descriptions of violation terms — all can cause false hits. Use `karma audit` to see "⚠️ possible false positive" markers and report back
- **False negatives exist** (real violations missed): users intentionally disguising violations — regex can't distinguish. karma trusts users won't deliberately cheat
- **`karma audit` 0 triggers after fix ≠ fix is correct**: the pattern might just be too wide swallowing real violations. Historical audit data is suspicion hints, not ground truth

Treat karma as **"a tool between git and lint"** — provides signals, doesn't replace decisions.

---

## FAQ

<details>
<summary><b>Nothing happens after install?</b></summary>

Run `karma doctor` to check:
- Are all hook events ✓? (Claude Code 8 / Codex 4 / Gemini 4)
- Did rules load successfully?
- Did session state directory generate new files?

Codex CLI 0.130+ requires manual `/hooks` approval of karma's 4 wrappers in TUI.
</details>

<details>
<summary><b>Too many false positives, what to do?</b></summary>

`karma audit` shows triggers marked "⚠️ possible false positive" — report to the author (GitHub Issue). Temporarily disable a rule: `karma rule remove <id>` or edit `~/.claude/karma/rules.yaml` and remove `violation_keywords` / `violation_checks` fields while keeping `preference`.
</details>

<details>
<summary><b>Does this overlap with Andrej Karpathy's CLAUDE.md?</b></summary>

**Completely complementary, no overlap**:
- Karpathy's 12 rules ([complete version](https://github.com/forrestchang/andrej-karpathy-skills)) are **universal coding principles** (cross-user, cross-project): "Think before coding," "Simplicity first," etc.
- karma's rules are **per-user personal preferences** (each user differs): "I prefer Chinese over jargon," "I want full-delegation," etc.

**Recommended setup**: install Karpathy's 12 rules in CLAUDE.md (project-shared) + install your personal rules via karma (user-level). They run on the same AI client without conflict.
</details>

<details>
<summary><b>Custom rule sets for non-development scenarios (writing / research / legal)?</b></summary>

`karma init` defaults to "software development" scenario. For other scenarios, write `~/.claude/karma/rules.yaml` manually — the framework (hook injection / real-time interception) is cross-scenario universal, but the 8 built-in violation_checks are dev-oriented. Other scenarios may need preference text reminders + custom keywords (without check functions).
</details>

---

## Mental model

> **A rules file isn't a wishlist. It's a behavioral contract that closes out specific failure modes you've observed. Each rule should answer: what error is this rule preventing?**

karma works the same way:

> **6 rules targeting failures you've actually hit > 12 rules including 6 you'll never use.**

karma's `data/rules.dev.example.yaml` 7 default rules are real pain points the author accumulated from self-use — **not for you to copy verbatim**. After installation, run `karma rule list` to see the defaults, keep those matching your real failure scenes, delete the rest and replace with your own real pain points.

---

## Documentation

- [docs/PRD.md](./docs/PRD.md) — Product requirements + validation criteria + scenario positioning (Chinese)
- [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) — Technical architecture + hook protocol details + 8 check implementations (Chinese)
- [CHANGELOG.md](./CHANGELOG.md) — Version change history (Chinese)
- [docs/HANDOFF.md](./docs/HANDOFF.md) — Internal development handoff doc (Chinese)
- [docs/RULES_REDESIGN_PROPOSAL.md](./docs/RULES_REDESIGN_PROPOSAL.md) — "Collaborative agreement" tone design proposal (core design philosophy) (Chinese)
- [docs/REFACTOR_PLAN_RULE_AND_I18N.md](./docs/REFACTOR_PLAN_RULE_AND_I18N.md) — sticky → rule rename + i18n implementation plan (Chinese)
- [CLAUDE.md](./CLAUDE.md) — Project charter for Claude Code collaboration (Chinese)

Full English translation of all auxiliary docs lands in v0.5.3 (Phase D of the refactor plan).

## Related projects and acknowledgments

- [Andrej Karpathy's CLAUDE.md coding-principles template](https://github.com/forrestchang/andrej-karpathy-skills) (60k stars / universal coding principles) — complementary to karma, not competing. Karpathy teaches AI how to write good code; karma helps AI never drift from your preferences in long tasks
- [Mnilax's 30-codebase 6-week CLAUDE.md rule-count empirical study](https://x.com/Mnilax/status/2053116311132155938) — karma's "soft cap 10 / hard cap 12" design directly borrows from this study's findings

## Contributing

- Bug reports / suggestions: [GitHub Issues](https://github.com/jhaizhou-ops/karma/issues)
- Add new AI client backend: [karma/backends/HOWTO.md](./karma/backends/HOWTO.md)
- Add new scenario rule templates (writing / research / legal etc.): PR to `data/`

karma is in early **real-user phase** — new-user first-install pain points will continuously trigger improvements.

## License

MIT
