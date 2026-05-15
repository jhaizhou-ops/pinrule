# karma Product Requirements Document

**[🇨🇳 中文](./PRD.md) · [🇬🇧 English (current)](./PRD.en.md)**

## User pain points (empirical)

karma v2's design starts from a **real long-term pain point**, user's own words:

> The rules I keep stressing but the Agent keeps violating: the Agent's approach is always short-sighted, cheating, opportunistic, and patch-oriented; while I'm always pursuing fundamental, long-term, universal, and correct. I have to keep repeating and emphasizing, but the Agent still hardcodes, cheats, pursues short-term goal achievement while forgetting long-term goals.

> Another example: I'm very insistent on not blocking the frontend for development and tests. But after a few turns, the Agent starts ignoring whether there are more tasks ahead and defaults to blocking the frontend with meaningless waits.

> Another example: I'm very efficiency-oriented and repeatedly ask for parallel multi-agent development/testing and constantly exploring more efficient workflows. But the Agent quickly forgets.

> Another example: I only care about Chinese and non-technical background. But after compact, the Agent starts defaulting to English output, and the content becomes increasingly technical until I completely don't understand.

## Nature of the pain points

These examples share the same pattern:

| Characteristic | Description |
|---|---|
| Type | "**Long-term directional preference**" — not factual memory (not "my dog is named X") |
| User behavior | Repeatedly emphasized (5+ times), not Agent missing it |
| Agent immediate behavior | Cooperates when hearing it, remembers for a few turns |
| Agent mid-term behavior | After a few turns, attention drifts, starts violating |
| Cross-session/compact | Completely lost after context compression |

**Core problem**: Not that the Agent **doesn't know** the user's preferences, but **"attention drift in long contexts + compression into vague words after compact."**

## Why existing solutions are insufficient

| Solution | Insufficient because |
|---|---|
| **CLAUDE.md** | Written but drowned by task details; Agent attention disperses; compressed into vague words after compact; project-level doesn't cross projects |
| **Claude Code auto-memory** | Leans toward "factual memory" (I use Mac / I like X), doesn't specialize in "behavioral-direction preferences"; recall timing is wrong |
| **karma v1** | Tried auto-distillation + retrieval — but the real pain point is "persistence" not "recall," directionally misaligned |

## karma v2 design philosophy

### 1. Core directions "pinned" rather than "retrieved"

User's highest-priority directions (cap 10 (close to but not exceeding 14 attention inflection point)) **always-on**, injected before every user_prompt.

No cosine / scene needed to pick which one — because these are all **user-publicly-declared highest priority**, should be seen every time.

### 2. User-controlled (no auto-distillation)

karma doesn't learn new rules. The user manually lists "core directions," karma only ensures they're **always at the position of highest Agent attention**.

This avoids:
- LLM-distillation noise / misalignment / overfitting specific users
- "Facts about the user" vs. "Agent behavior preferences" track confusion

### 3. Violation detection → feedback loop

Retrieval's limitation: put rules in context for the Agent to "take a look" — but seeing isn't equivalent to high priority.

karma uses **"behavioral-violation detection"** as feedback:
- After Agent response, hook scans trigger words / regex / simple classification
- Detected violation → notify user + next injection marks the rule with **explicit RECENT_VIOLATION**
- Agent seeing RECENT_VIOLATION marker is more attentive than pure description (empirically unvalidated, this is the core hypothesis)

### 4. Doesn't compete with any existing track

- Factual memory / preference retrieval → Claude Code auto-memory / mem0 etc.
- Project-level rules → CLAUDE.md
- Workflow automation → Claude Code hooks directly

karma does only **"core direction persistence + violation detection"** — one thing.

## Functional requirements (v0 MVP — delivered)

### F1. Core direction configuration ✅

- User defines 5-10 entries in `~/.claude/karma/rules.yaml` (cap 10, over 12 refuses to load)
- Fields: `id` / `preference` / `violation_keywords` / `violation_checks` (engine-layer check function name list)
- karma CLI: `karma rule list / edit / remove`, `karma init`

### F2. user_prompt_submit hook ✅

- Every user_prompt_submit, hook reads rules.yaml
- Uses `additionalContext` injection into Claude context (doesn't modify user_text itself)
- Format: `[karma — Your long-term agreement with the user]` plus 1-10 numbered rules
- Rules triggered within 24h marked with `〔Last response showed drift — let's realign〕`
- Performance: < 60ms

### F3. Violation detection / feedback loop ✅

Two-layer detection:
- **Keyword layer**: scan Bash command + Write/Edit comment lines + Stop hook checks Agent response for violation terms
- **Engine layer (M2+ reinforced)**: 8 violation_check functions doing precise regex detection for each rule
  - long_term_fundamental: long-hash if branches / blacklist-whitelist literals / TODO actual comments / intent literal comments / all-caps constant lists
  - non_blocking_parallel: sleep / wait / long tasks without background / indirect shell execution
  - chinese_plain_no_jargon: Chinese ratio + jargon detection (strips code blocks + inline code)
  - loud_failure_with_evidence: completion words / weak claims in code-task context + no test evidence
  - no_testset_no_future_leakage: long-hash literals / backfeeding pools etc.
  - read_before_write: Edit/Write without Read on same file → block
  - keep_pushing_no_stop: response-end push signal / question mark / pause word detection
  - bypass_karma_detection: Bash commands with karma internal sensitive literals + write operations

Three hook feedback points:
- **PreToolUse**: Real-time intercept before Agent calls tool (deny + show reason)
- **PostToolUse**: Track session state (Read/Edit/Write history + Bash PASS/FAIL)
- **Stop**: Scan Agent response for literal violations

### F4. Self-use observation tools ✅

- `karma stats` — Each rule's violation count + last trigger time
- `karma violations recent [N]` — Last N violation details
- `karma doctor` — Check environment (rule validity + all hook install status, Claude Code 8 events)
- `karma install-hooks / uninstall-hooks` — Auto-write/clean settings.json (idempotent + backup + preserve other hooks)

### M3 completeness supplements (engineering refinement above v0 MVP)

- **Unified description-context exemption** (`karma/checks/description_context.py`) — `.md` / `.yaml` / `.json` / tests/ / `/tmp/` / probe-sample naming files: "description trigger patterns" don't count as execution intent
- **Shell quote literal + heredoc smart stripping** — `git commit -m "..."` quote literals are descriptions; `bash <<EOF` heredoc inside is shell command (keep scanning); `python <<EOF` heredoc inside is data (strip)
- **Background task evidence auto-integration** — After `pytest > log.txt &`, next hook trigger catchup_pending_bg reads log into last_test_pass_ts
- **`has_recent_test_pass` new semantics** — "Tests run and passed since most recent code change"
- **post_tool_use skips failed tools** — Read failure doesn't record_read, preventing read_first bypass
- **Cross-language comment + docstring scanning** — `# / // / -- / """ / ''' / /* */` all covered by keyword-layer Write/Edit scan

### Feedback mechanism + config system

- **Desktop notification** (`karma/notify.py`) — Cross-platform (macOS osascript / Linux notify-send / Windows msg), stop hook supplementary stderr-outside-view alerts when detecting violations
- **Cumulative alerts on turn dimension** — Recent N turns with same rule violation ≥ M times → 🚨 severe notification (window / threshold configurable). By turn not human time — Agent attention drift accumulates by turn; user leaving for meetings vs. continuous operations is completely different Agent state
- **Config system** (`karma/config.py` + `~/.claude/karma/config.yaml`) — All thresholds centrally adjustable (notify toggle / rotation / purge / escalate); fail open (file missing / field null uses DEFAULTS)
- **`karma doctor` shows current effective config** — Lets user see all current thresholds clearly

## Validation criteria (v0)

karma v0 doesn't pursue accuracy numbers — pursues **whether the author self-using actually feels "Agent makes fewer directional errors in long tasks"**.

Observation metrics:
1. **Violation trigger frequency in long tasks** — comparison before vs. after karma install
2. **User repeating same rule emphasis count** — decreasing
3. **Whether Agent still remembers core directions after compact** — verified through several long-session tests

If after a week of self-use there's no obvious improvement → karma's hypothesis is wrong, needs redesign.

### Validation criteria's working framework (updated post-M3)

User's own words: "We keep pushing — that IS the observation period" — **"development" and "self-use observation" aren't binary choices**.

karma's development process itself is its most rigorous self-use observation period: every development push has Claude running with karma installed, every commit goes through hook interception. M3's six waves accumulated 30+ real violation data points, all 6 rules triggered, false-positive / false-negative boundaries continuously exposed + fixed in dogfooding.

This is denser / more real / faster feedback than "install and observe for a week."

## Scenario positioning (clarified after M3)

karma = **universal hook framework** + **scenario rule sets**.

Current `data/rules.dev.example.yaml` is the "**software development scenario**" preset — 7 rules all targeting attention drift while writing code (long-term solutions / non-blocking / plain Chinese / completion evidence / no testset feedback / no bypass detection / read before write). The 8 engine-layer violation_check functions (pytest / Edit / Write / Bash / bypass_karma / keep_pushing etc.) are also dev-scenario oriented.

Other scenarios (writing / research / product / design / legal etc.) need different rule sets — users can customize rules.yaml, or community contributes presets. karma framework layer is cross-scenario universal.

This positioning emerged as insight from M3 dogfooding — previously assumed "universal across users," actually "universal across users within same scenario."

## Non-functional requirements

- **Cannot use sonnet** — strictly inherits v1 LLM authorization rules
- **Local ≤4 concurrent small tasks can use mlx Qwen3.6** — but karma v0 design doesn't need LLM
- **Hook performance** — user_prompt_submit hook must be < 60ms (can't slow Agent response)

## v0 scope explicitly excludes

- ❌ Auto-distilling new rules
- ❌ retrieval / cosine / scene routing
- ❌ Multi-user collaboration / sync
- ❌ Web UI / graphical config (CLI yaml editing is enough)
- ~~❌ Cross-IDE / cross-AI platform support (Claude Code only)~~ — **Supported in v0.4+**:
  Claude Code / Codex CLI / Gemini CLI all three universal, base-class abstraction makes adding Cursor / Factory / Qoder / Copilot / CodeBuddy / Kimi etc. a "fill-in-form" task. See
  [`karma/backends/HOWTO.md`](../karma/backends/HOWTO.md).
- ❌ Evaluation system / accuracy metrics (self-use observation is enough)

## Future possibilities (v1+)

If v0 validates karma is useful:

- **Cross-IDE/platform**: Cursor / Windsurf / Codex support
- **Team-level rules**: Team shares one set of core directions (e.g. SWE team's code style)
- **Behavioral violation detection enhancement**: Upgrade from "keyword" to "LLM-judged" (but local small model, zero external)
- **Core direction template marketplace**: Cross-user sharing of useful rule sets (not karma auto-using, just reference)

But **v0 doesn't do these**. First validate minimum hypothesis.
