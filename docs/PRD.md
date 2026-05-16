# karma Product Requirements Document

**[🇬🇧 English (current)](./PRD.md) · [🇨🇳 中文](./PRD.zh.md)**

## User pain points (empirical)

karma's design starts from a **long-term pain point**, in the user's own words:

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

## karma design philosophy

### 1. Core directions "pinned," not "retrieved"

User's highest-priority directions (soft cap 10, hard cap 12 — the attention cliff point per Mnilax's empirical study) **always-on**, injected before every user_prompt.

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

- Every user_prompt_submit, hook reads `rules.yaml`
- Uses `additionalContext` injection into Claude Code context (doesn't modify user_text itself)
- **v0.9.0**: per-turn injection is compact anchor (`format_anchor_only`: id + first-line preference + drift marker, ~490 tokens), NOT the full preference text
- Full baseline (with every preference's complete multi-line body, ~1817 tokens) is injected once at SessionStart and persists in conversation history — see F2.5 below
- Rules triggered within recent N turns get `〔Last response showed drift — let's realign〕` marker on the anchor

### F2.5. Injection architecture (v0.9.0)

5-hook coordinated injection lifecycle:

| Hook | Format | Frequency |
|---|---|---|
| SessionStart | full baseline (~1817 tok) | once per session, covers startup/resume/clear/compact sources |
| UserPromptSubmit | compact anchor (~490 tok) + drift markers + violation fallback | every turn |
| PostToolUse | full reinject (~1817 tok) | session-global byte_seq accumulation hits model decay threshold (Opus 60K / Sonnet 40K / Haiku 30K) |
| Stop strong reminder | violation hits + suggested_fix | when violations detected |
| SubagentStart | compact rule list | per subagent spawn |

Per-turn injection ~490 tokens (compact anchor); 100-turn session across 1M Opus context cumulatively about 8%.
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
- `karma doctor` — Check environment (rule validity + all hook install status + skill install status, Claude Code 8 events)
- `karma audit` — Per-rule top trigger frequency + locale-agnostic grouping (v0.5.7+)
- `karma install-hooks / uninstall-hooks` — Auto-write/clean settings.json (idempotent + backup + preserve other hooks)
- `karma install-skill [--force]` — Install / upgrade the `karma-rule` Claude Code skill (`karma init` runs this automatically; standalone command for upgrades)

### F5. Natural-language rule input via `/karma` skill ✅ (v0.5.16+ — first release where the skill actually triggers)

**Triggering**: user types `/karma <natural language>` in any of Claude Code / Codex CLI / Gemini CLI. Skill walks a 7-step workflow: intent → existing-rule overlap check → draft yaml inline → `karma rule preview` schema check → confirm with user → `karma rule add` write → report.

**What the skill handles**:
- Tone refinement (collaborative-agreement phrasing — LLMs respond with alignment instead of defensive argument)
- `violation_keywords` reformatting to "intent-prefix + action" form (`"I'll hardcode"` not `"hardcode"`)
- Overlap detection (4-shape decision table: full duplicate / superset / keyword-overlap / no overlap)
- Anchor-vs-scope ambiguity surfacing (always-on injection has no scene routing)
- Locale-aware preference drafting (matches user's chat language; `violation_checks` function names stay English as stable identifiers)
- Modify recipe (`remove + add` composition — no separate "replace" CLI needed)

**Backing CLI** (callable independently from skill or scripts):
- `karma rule add --from-yaml <file>` / `karma rule add --from-stdin` — Programmatic write with schema + id-conflict + REGISTRY validation
- `karma rule preview --from-yaml/--from-stdin` — Dry-run validation + header-injection preview

**Multi-backend installation** (v0.5.16+):
- Claude Code: `~/.claude/skills/karma/SKILL.md` (Markdown + YAML frontmatter)
- Codex CLI: `~/.agents/skills/karma/SKILL.md` (note: `~/.agents/`, not `~/.codex/` — shared namespace with Anthropic per OpenAI design)
- Gemini CLI: `~/.gemini/skills/karma/SKILL.md` (auto-trigger) **plus** `~/.gemini/commands/karma.toml` (explicit `/karma` slash, generated via `karma/skill_packaging.py` Markdown → TOML conversion with `$ARGUMENTS` ↔ `{{args}}` syntax translation)
- `karma init` auto-installs to all three; `karma install-skill [--force] [--backend <name>]` for upgrades; `karma doctor` reports per-backend skill status


### F6. Internationalization (v0.5.2+ injection text; v0.8.0+ detection signals) ✅

karma has **two-way i18n**: speaking-side (what karma injects into the Agent prompt) and listening-side (what regex phrases karma uses to detect signals in user / Agent dialogue).

**Speaking side — injection text** (v0.5.2+):
- `karma/i18n.py` with `tr(key, **fmt)` lookup, `{placeholder}` interpolation, fail-open on missing keys
- Locale resolution chain: `KARMA_LOCALE` env > `config.yaml` `locale` field > auto-detect via `karma.locale_detect.is_chinese_user()` > `en` fallback
- All hook injection text (header / drift marker / mid-injection / strong reminder / Stop reason / SessionStart variants / SubagentStart) + all 28 check `suggested_fix` strings + all 28 `CheckHit.trigger` audit labels switchable en/zh via `data/locales/{en,zh}.yaml`
- `Violation.trigger_key` + `CheckHit.trigger_key` (v0.5.7+) — locale-agnostic stable identifier for `karma audit` cross-locale grouping (users switching locale mid-week still see correct aggregation)
- `karma init` selects rule template by detected locale (`rules.dev.example.zh.yaml` for Chinese users, English default otherwise)

**Listening side — detection signals** (v0.8.0 → v0.8.2):
- `karma/signals.py` with `load_phrases()` (`.txt` flat phrases) + `load_patterns()` (`.yaml` Cartesian templates) + `compile_alternation()` union compile (long-phrase priority, `re.escape` literals vs raw regex templates)
- All 7 detection signals externalized to `data/signals/<name>/{zh,en}.{txt,yaml}`:
  - `.txt` flat: `user_stop_hints` / `agent_saturation` / `stop_hints` / `explicit_handoff` / `weak_claims` / `completion_words`
  - `.yaml` Cartesian DSL (`templates` + `subjects`/`verbs` vocab + `phrases`): `push_signals`
- Cross-language character sets don't overlap (Chinese vs Latin vs kana vs hangul) → no false matches
- **Adding a new language = ~7 small files per signal directory, zero Python code, zero LLM in the loop**

### F7. `keep_pushing` user-stop exemption (v0.4.41 + v0.7.4) ✅

User explicit stop signals exempt the reflection nudge for the whole turn (rule #8 exception). Two semantic categories covered:

- **Tired / dismissive** (v0.4.41): "不用了 / 休息吧 / 算了 / 明天再说" — user wants to pause
- **Satisfied / confirmation** (v0.7.4): "不错不错 / 挺稳定 / LGTM / looks good" — user reached a satisfaction point

Both categories live in `data/signals/user_stop_hints/{zh,en}.txt` (v0.8.0 externalization). Combined with `_AGENT_SATURATION_RE` (Agent declares own saturation) and `_EXPLICIT_USER_HANDOFF_RE` (Agent explicitly asks for user decision), the reflection nudge has three orthogonal exemption paths.

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

- **No LLM dependency, ever** — karma is firmly pure-engineering (regex / keywords / counting). Not just for v0 — this is a permanent boundary
- **Hook performance** — `user_prompt_submit` hook must stay under 60ms (can't slow the Agent's response)

## v0 scope explicitly excludes

- ❌ Auto-distilling new rules
- ❌ retrieval / cosine / scene routing
- ❌ Multi-user collaboration / sync
- ❌ Web UI / graphical config (CLI yaml editing is enough)
- ❌ Evaluation system / accuracy metrics (self-use observation is enough)

Cross-IDE / cross-AI client support already shipped: Claude Code / Codex CLI / Gemini CLI all three universal; base-class abstraction makes adding Cursor / Factory / Qoder / Copilot / CodeBuddy / Kimi etc. a "fill-in-form" task. See [`karma/backends/HOWTO.md`](../karma/backends/HOWTO.md).

## Future possibilities (v1+)

Once v0 has validated the core hypothesis:

- **More backends**: Cursor / Windsurf / Factory / Qoder / Copilot / etc.
- **Team-level rules**: Teams sharing one set of core directions (e.g. an SWE team's code-style baseline)
- **Rule template marketplace**: Cross-user sharing of useful rule sets — opt-in reference, not auto-use

What v1+ **won't** add: an LLM dependency, even a local one. Pure engineering is a permanent boundary, not a v0 stopgap.
