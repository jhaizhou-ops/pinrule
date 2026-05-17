# pinrule Hook Configuration Guide

**[🇬🇧 English (current)](./HOOK_CONFIGURATION_GUIDE.md) · [🇨🇳 中文](./HOOK_CONFIGURATION_GUIDE.zh.md)**

`pinrule install-hooks` writes hooks into your AI client's settings file. This guide uses Claude as the running example (8 hooks — most complete coverage); Codex / Cursor use the same command with `--backend`, the hook business logic is shared, only the native-event count and write path differ.

| Backend | Install command | Write location | Native event count |
|---|---|---|---|
| Claude (default) | `pinrule install-hooks` | `~/.claude/settings.json` | 8 |
| Codex CLI | `pinrule install-hooks --backend codex` | `~/.codex/config.toml` | 6 |
| Cursor 1.7+ | `pinrule install-hooks --backend cursor` | `~/.cursor/hooks.json` | 12 |

## Quick start

```bash
pinrule init                                       # Create ~/.pinrule/ + copy rule template
pinrule install-hooks                              # Defaults to Claude (also accepts --backend codex/cursor or all)
pinrule doctor                                     # Verify install (auto-scans every installed backend)
```

Restart your AI client after install — hooks take effect immediately. Rules live in `~/.pinrule/rules.yaml` (shared across backends) — edit with `pinrule rule edit`, or invoke `/pinrule <natural language>` and let the skill write the rule for you.

---

## 8-hook cheat sheet

| Hook | When it fires | What it does | User visibility |
|---|---|---|---|
| **UserPromptSubmit** | Before you submit a prompt | Injects compact anchor (id + first line + drift markers, ~490 tok) — v0.9.0 design | Background, no notification |
| **PreToolUse** | Before Agent calls a tool | Intercepts tool calls that violate core directions | ❌ Permission denied (with reason) on hit |
| **PostToolUse** | After tool call succeeds | Tracks session state; on hitting per-model decay threshold (Opus 60K / Sonnet 40K / Haiku 30K) full-reinjects rules to fight dilution | Background tracking, no notification |
| **Stop** | Before Agent stops generating | Detects violations + nudges continuation on silent stop | ⚠️ stderr reminder + desktop notify |
| **PreCompact** | Before client auto-compacts | Snapshots full rule state to disk | Background snapshot, no notification |
| **SessionStart** | Session start / compact restart | **Full** baseline rule injection (the v0.9.0 one-and-only ~1817 tok inject into history); on compact-restart, reads the snapshot and force-injects | Background inject, no notification |
| **SubagentStart** | When spawning a subagent | Subagent auto-inherits the full rule set + maintains independent monitoring state | Subagent sees rules in its header |
| **SubagentStop** | When a subagent finishes | Subagent's temp state auto-destroys, doesn't pollute the main session | Background cleanup, no notification |

All hook outputs strictly follow each client's official protocol schema — no client-side UI error popups.

---

## File paths

**Shared across backends** (user-level data):

```bash
~/.pinrule/rules.yaml           # Your core directions (manual edit or /pinrule skill)
~/.pinrule/config.yaml          # Threshold config (DEFAULTS apply if missing)
~/.pinrule/violations.jsonl     # Violation history (auto-rotate at 5000 lines)
~/.pinrule/session-state/       # One JSON per session (30-day auto-cleanup)
~/.pinrule/pre_compact_snapshot.md  # Pre-compact rule dump (SessionStart re-reads it)
```

**Per-backend hook wrapper + settings**:

```bash
# Claude
~/.claude/hooks/pinrule_*.py          # 8 hook wrappers (install-hooks auto-generates)
~/.claude/settings.json               # Claude config (pinrule writes hooks section)

# Codex CLI
~/.codex/hooks/pinrule_*.py           # 6 hook wrappers
~/.codex/config.toml                  # Codex config (pinrule writes [hooks.*] sections + trusted_hash)

# Cursor 1.7+
~/.cursor/hooks/pinrule_*.py          # 12 hook wrappers (including 4 dedicated gates)
~/.cursor/hooks.json                  # Cursor config (pinrule writes hooks section)
```

> Set `PINRULE_HOME` → all paths above anchor under `$PINRULE_HOME/` (true sandbox isolation, v0.16.11+). Use this for trial / CI / multi-profile.

---

## Typical scenarios

### A. Long session crossing compact

**What you're doing**: multi-hour development task, Agent accumulates 60K+ context.

**What happens**:
1. Claude auto-triggers compact
2. **PreCompact hook**: full `rules.yaml` state snapshots to `pre_compact_snapshot.md`
3. Compact runs (Claude's own compression)
4. **SessionStart hook** (fires on compact-restart): reads snapshot, force-injects full rules

**Result**: rules survive compact, Agent doesn't compress your core directions into vague words.

---

### B. Subagent parallel execution

**What you're doing**: spawn 2 subagents to parallel-search code + fix a bug.

**What happens**:
1. **SubagentStart hook**: full rules inject into subagent context
2. Subagent operates in its own session with constraints visible + independent monitoring state
3. Subagent finishes
4. **SubagentStop hook**: subagent's temp session-state auto-destroys

**Result**: subagents get the same supervisory weight as the main Agent; spawning multiple subagents doesn't corrupt the main session's data.

---

### C. Silent stop → continuation nudge

**What you're doing**: gave the Agent a clear multi-step direction, expecting autonomous progress.

**What happens**:
1. Agent finishes step 1, response ends with a pure statement / no next-step signal
2. **Stop hook** detects silent stop → outputs `decision=block` + continuation prompt
3. Agent sees the prompt and continues with the next step
4. Safeguard: after ≥ 2 cumulative blocks in a single turn (`stop_block_max_per_turn` is tunable), the Agent is allowed to stop to prevent infinite loop
5. If the Agent is genuinely saturated, it explicitly states where it's stuck → pinrule stops pushing

**Result**: Agent finishes one wave and immediately finds the next push point; doesn't keep asking "what's next?".

---

## FAQ

### Q: A hook denied my operation, what now?

Read the rejection reason (stderr / notification both have it) — usually it means your rules consider this a violation. Two paths:
- Edit `rules.yaml` (adjust wording / keyword / engine check)
- Tell the Agent explicitly "skip this one, run it" (user-authorized exception)

If you think this is a pinrule false positive, run `pinrule audit` and look for the "⚠️ likely false positive" tag — please file an issue.

### Q: Can I turn off specific hooks?

Yes. Two ways:
- `pinrule uninstall-hooks` (also accepts `--backend` to remove from a specific backend, or `all`)
- Manually edit the backend's settings file (`~/.claude/settings.json` / `~/.codex/config.toml` / `~/.cursor/hooks.json`) and remove / comment out the event from the hooks section

But try it for a week first.

### Q: Can subagents bypass the rules?

No. `SubagentStart` injects full rules into the subagent's header, and the subagent's own hooks run the same checks. But the **subagent's state is isolated** — keyword detection counts independently per subagent session. This is a privacy / performance tradeoff by design.

### Q: How do I tune thresholds?

Edit `~/.pinrule/config.yaml` (falls back to `pinrule/config.py:DEFAULTS` if missing):

```yaml
recent_violation_turns: 5         # Drift-marker window
stop_block_max_per_turn: 2        # Stop hook nudge cap per turn
force_block_threshold: 5          # Cumulative force-rootcause threshold
session_state_max_age_days: 30    # Session-state auto-cleanup period
```

`pinrule doctor` shows the currently-effective thresholds.

---

## Design principles

1. **Fail open** — config error / load failure → hook doesn't block the Agent, silently continues
2. **Zero LLM** — pure engineering (regex / keywords / counting), no external dependencies
3. **Visible** — interceptions / nudges all surface to stderr + desktop notify, not a black box
4. **Tunable** — edit `rules.yaml`, next turn picks it up immediately

---

**Official protocol references**:
- Claude: https://code.claude.com/docs/en/hooks
- Codex: https://developers.openai.com/codex/hooks
- Cursor: https://cursor.com/docs/agent/hooks
