# Codex Backend — Handoff Guide

**[🇬🇧 English (current)](./CODEX_BACKEND.md) · [🇨🇳 中文](./CODEX_BACKEND.zh.md)**

This document is the **interface contract + ownership boundary** for the karma `codex` backend. Starting from v0.10.0, the codex backend is owned and maintained by the **Codex CLI itself** (via PRs from Codex sessions); karma main repo only provides the contract layer and merges PRs after review.

## Why this split

karma v0.9.15 cross-model audit and v0.9.16 codex envelope parser both hit a recurring failure pattern: **when Claude tries to guess Codex protocol details, it gets them wrong**. Documented incidents:

- **v0.9.15** assumed Codex accepts `hookSpecificOutput.permissionDecision:"allow"` shape — real-world testing on 2026-05-16 with codex 0.130 CLI produced the error `unsupported permissionDecision:allow`. The correct shape is bare `{}` per [codex hooks docs](https://developers.openai.com/codex/hooks). karma had this wrong for 1 release.
- **shell-as-Read gap** — codex CLI has no separate `Read` tool; it reads files via `exec_command` running `tail` / `sed` / `cat` etc. karma's `record_read` only matches `tool_name == "Read"`, so codex's shell reads are invisible to karma's `read_first` check, causing false-positive denials on edits where the agent had legitimately read the file via shell. The fix requires recognizing shell-read patterns inside the codex backend, which Claude is not best positioned to design.
- Codex feature flag churn — `codex_hooks` deprecated in favor of `hooks` (~2026-04), `features.hooks=true` now required, `/hooks` TUI approval required per wrapper (v0.130+). karma main repo is always 1-2 weeks behind on these.

**Conclusion**: codex protocol detail ownership belongs to whoever has fastest signal on codex platform changes. That's Codex CLI itself, running PR sessions through this very repo.

## Ownership boundary

| File | Owner | Codex can modify? |
|---|---|---|
| `karma/backends/codex.py` | **Codex** | ✅ yes, primary file |
| `tests/test_codex_backend.py` (new, optional) | **Codex** | ✅ yes, codex private tests |
| `karma/backends/_base.py` Protocol | karma maintainer | ❌ contract layer, file an issue to change |
| `karma/backends/_json_hooks.py` base class | karma maintainer | ❌ default Claude-shape behaviors |
| `karma/backends/protocol_adapter.py` dispatch | karma maintainer | ❌ pure routing |
| `karma/hooks/*.py` main logic | karma maintainer | ❌ backend-neutral |
| `karma/checks/*.py` engine checks | karma maintainer | ❌ backend-neutral |
| `tests/test_protocol_adapter.py` cross-backend tests | karma maintainer | ❌ contract testing |

## The 8-method contract

Codex backend (`CodexBackend` class in `karma/backends/codex.py`) must implement these methods. Default implementations in `JsonHooksBackend` base class are Claude-shaped; override to match codex protocol.

Methods 1-6 came with v0.10.0 split; methods 7-8 added in v0.10.6 to remove silent Claude-shape assumptions across ContextInjection + Stop hooks (4 ContextInjection-firing hooks + Stop's 2 block paths used to direct-print Claude shape — same drift pattern as v0.9.15).

### 1. `pre_install_setup(self) -> list[str]`

Called before karma writes hooks.json. Currently runs `codex features enable hooks` to flip the feature flag. Return value is per-line user-visible log.

**Current**: ✅ implemented. Reviews codex CLI for the feature command.

### 2. `post_install_message(self) -> list[str]`

Called after karma writes hooks.json. Returns loud reminder lines printed to stdout. Used to tell user about `/hooks` TUI approval requirement.

**Current**: ✅ implemented (placeholder text). Codex can tune the wording / add tutorial links / detect approval state if codex exposes an API.

### 3. `normalize_tool_name(self, raw_tool_name: str, payload: dict) -> str`

Map codex-native tool names to karma canonical (Claude-style: `Bash` / `Read` / `Edit` / `Write` / `NotebookEdit`).

**Current**: `apply_patch → Edit`. **Likely incomplete** — codex may have other tool names (`exec_command`, `update_plan`, plugin tools) that karma should canonicalize.

**Why this matters**: karma's engine checks compare `tool_name in ("Edit", "Write")` etc. Anything unmapped early-returns `None` from checks → no enforcement.

### 4. `normalize_tool_input(self, raw_tool_name, raw_tool_input, payload) -> Any`

Convert codex tool_input to karma canonical dict. For `apply_patch`, parse the envelope string into `{file_path, new_string, multi_file_targets}`.

**Current state** — **placeholder, codex should improve**:
- `parse_apply_patch_envelope()` regex-parses `*** Begin Patch / *** Update File: / @@ / *** End Patch` blocks. Locked against one real captured envelope from 2026-05-16 13:51:47 session rollout. May miss edge cases (escaped paths, binary patches, etc.).
- `_extract_codex_patch_text()` defensively handles bare-string and dict-wrap input forms. Real hook-level payload schema was never captured (codex `exec` mode doesn't fire hooks; interactive `codex` hook payload not dumped yet). **Codex should capture and lock the real hook payload shape**.
- **shell-as-Read gap not implemented** — when `raw_tool_name == "exec_command"` and command matches read-only patterns (`tail`, `sed -n`, `cat`, `head`, `less`, `more`, `wc`, `file`, `grep -l`), this method should output something like `{"read_file_paths": [...]}` and `post_tool_use` will need a corresponding handler. Codex owns the design here because shell-read pattern detection has high false-positive risk and codex has fastest signal on real-world `exec_command` patterns.

### 5. `emit_deny(self, reason: str, payload: dict) -> str`

Return JSON string for "deny this tool call". Codex accepts Claude's `hookSpecificOutput.permissionDecision:"deny"` shape (verified by real testing 2026-05-16 case 1).

**Current**: ✅ correct shape (overridden from base).

### 6. `emit_allow(self, payload: dict) -> str`

Return JSON string for "allow this tool call". **Codex does NOT accept `hookSpecificOutput.permissionDecision:"allow"`** — official [codex hooks docs](https://developers.openai.com/codex/hooks) state:

> "permissionDecision: 'ask', legacy 'decision: 'approve', 'updatedInput', 'continue: false', 'stopReason', and 'suppressOutput' are parsed but not supported yet, so they fail open."
> "To permit a tool call, either return an empty JSON object (`{}`) or exit with code `0` and no output."

**Current**: ✅ returns `"{}"`. There's a locked regression test (`test_codex_emit_allow_returns_empty_dict_not_claude_shape`) preventing future PRs from accidentally reverting to Claude shape.

### 7. `emit_context_injection(self, event_name: str, additional_context: str, payload: dict) -> str`

Return JSON string for "inject additional context into the Agent's view" (SessionStart / UserPromptSubmit / PostToolUse / SubagentStart). Claude shape is `{hookSpecificOutput: {hookEventName: event_name, additionalContext: additional_context}}`.

**Current**: inherits Claude-shape default from `JsonHooksBackend`. **Real codex acceptance unverified** — see Remaining TODO #8. If codex returns error or silently drops the injection, override to match codex's real shape.

### 8. `emit_stop_block(self, reason: str, payload: dict) -> str`

Return JSON string for "block the Agent's stop" (Stop hook force_block / keep_pushing_block paths). Claude shape is `{decision: "block", reason: reason}`. Gemini overrides to `{}` because AfterAgent has no block semantics — returning empty fails open instead of silently rejecting.

**Current**: inherits Claude-shape default. **Real codex acceptance unverified** — see Remaining TODO #8.

## Completed TODOs (v0.10.x)

These TODOs were defined in v0.10.0's first cut of this doc and completed in subsequent codex-owned PRs:

| # | Issue | Status | Shipped in |
|---|---|---|---|
| 1 | **shell-as-Read** — `exec_command` running `tail`/`sed`/`cat` should count as Read | ✅ Done | v0.10.1 [PR #3](https://github.com/jhaizhou-ops/karma/pull/3) `extract_read_paths_from_exec_command()` |
| 1.5 | **Simple pipe reads** — `head N | tail M` / `cat | head/tail` chains | ✅ Done | v0.10.3 [PR #5](https://github.com/jhaizhou-ops/karma/pull/5) extending shell-as-Read |
| 2 | **Real hook-level payload capture** for SessionStart | ✅ Done | v0.10.2 [PR #4](https://github.com/jhaizhou-ops/karma/pull/4) — codex SessionStart payload captured and locked in test fixture |
| 4 | **Other codex tool names** — `exec_command → Bash`, etc | ✅ Done | v0.10.2 [PR #4](https://github.com/jhaizhou-ops/karma/pull/4) `_CODEX_TOOL_MAP` extended |
| 5a | **Approval state UX** — manual `/hooks` approval bottleneck | ✅ Done | v0.10.2 [PR #4](https://github.com/jhaizhou-ops/karma/pull/4) `trust_karma_hooks()` auto-writes `trusted_hash` |
| 7 | **`write_file_paths` canonical write field** — `sed -i` / `tee` / `producer \| tee file` write commands emit `write_file_paths` along with `is_write=True`. Generic layer `karma/hooks/post_tool_use.py:124-155` consumes the list (v0.10.5 karma-side ready) calling `state.record_edit(p)` for each path. Evidence check now sees codex `sed -i` etc as real code edits. | ✅ Done | post-v0.11.2 [PR #6](https://github.com/jhaizhou-ops/karma/pull/6) `extract_read_write_paths_from_exec_command` (function renamed from `extract_read_paths_from_exec_command`) returns `(read_paths, write_paths, is_write)` tuple |

## Remaining TODO list (codex agenda)

| # | Issue | Suggested approach |
|---|---|---|
| 2-followup | **Real hook-level payload capture for PreToolUse / PostToolUse / Stop / UserPromptSubmit** — only SessionStart shape captured so far. `_extract_codex_patch_text` still defensively unwraps multiple candidate shapes for apply_patch hook payloads — can be tightened once real PreToolUse hook payload captured. | Add `KARMA_DEBUG_DUMP_PAYLOAD` env to real interactive codex session (post-`/hooks` approval), dump payloads, lock real shape in fixture, tighten `_extract_codex_patch_text` to verified key only. |
| 3 | **Codex feature-flag detection cleanup** — `_is_hooks_feature_enabled` parses `~/.codex/config.toml`. Codex may expose a cleaner API in 0.131+. | If codex CLI ships `codex features list --json` or status file, replace the toml parser. Low priority — toml parser works. |
| 5b | **Programmatic approval verification** — `trust_karma_hooks()` writes `trusted_hash`; `karma doctor` could programmatically verify each wrapper is currently approved (vs. relying on user to check TUI). | Investigate whether `~/.codex/config.toml` `[hooks.state]` entries can be read back and validated against current wrapper hashes. If yes, `karma doctor` adds a green/red check per wrapper. |
| 6 | **Pipe read additional patterns** — `xargs cat` / recursive `grep -r` / `find` deliberately not recognized (PR #5 conservative scope). If real codex usage shows high false-negative rate on these, design combo-pattern engine. | Mine `~/.codex/sessions/*/` rollouts for actual frequency of these patterns; if high, design extension. |
| 8 | **`emit_context_injection` / `emit_stop_block` codex shape verification** — v0.10.6 added 8-method Backend Protocol; codex.py currently inherits Claude-shape defaults but real codex acceptance of `{hookSpecificOutput, additionalContext}` shape (SessionStart / UserPromptSubmit / PostToolUse / SubagentStart) and `{decision: "block", reason}` shape (Stop) unverified. PR #6 explicitly punted: "not override, Claude shape default" with locked test. | Capture real codex payloads when these hooks fire in interactive sessions. If codex accepts Claude shape silently, lock test stays. If codex returns error / silently drops, override `emit_context_injection` / `emit_stop_block` for codex backend. |

## How to contribute (codex PR flow)

1. **Modify** `karma/backends/codex.py` only (and `tests/test_codex_backend.py` if you create it)
2. **Verify** existing tests still pass: `.venv/bin/python -m pytest tests/test_protocol_adapter.py tests/test_backends.py -q`
3. **Add tests** for any new method behavior — at minimum, lock the new shape with a hardcoded expected output
4. **Capture real codex CLI evidence** (rollout file path / session ID / version) in commit message — this avoids the v0.9.15 "Claude guessed and got it wrong" pattern
5. **Don't break the 8-method contract** — if you need to add a new method, file an issue first so karma maintainer can update `_base.py` Protocol and all backends synchronously
6. **PR description must include**:
   - codex CLI version tested against (e.g., `codex 0.130.0`)
   - real-world test transcript (e.g., user prompt → karma response screenshot)
   - any new tool names / payload shapes captured (file path to session rollout)

## Contract testing (implemented v0.10.1)

`tests/contract/test_backend_contract.py` runs 14 abstract contract tests via `pytest.parametrize` against every backend in `REGISTRY`. Coverage:
- All 6 methods callable without crash on minimal payload
- `emit_allow` and `emit_deny` return valid JSON string
- `normalize_tool_name` returns str + passthrough unknowns + idempotent on canonical names
- `hook_events()` non-empty dict + snake_case basenames
- `settings_path()` under dotted config dir
- `build_event_entry()` returns dict with `hooks` key
- `is_karma_entry()` recognizes own entry + rejects foreign entry
- `name` / `display_name` non-empty
- `skill_install_targets()` returns list with valid format strings

Any codex PR breaking these auto-fails CI. Adding a new backend automatically picks up all 14 contract tests via REGISTRY registration — no per-backend boilerplate.

## Communication channels

- **Architectural questions**: file GitHub issue tagged `backend:codex`, mention `@jhaizhou-ops`
- **PR review**: karma maintainer reviews within 1-2 days; aim for narrow, focused PRs (one TODO item per PR)
- **Breaking changes**: must be discussed in issue first; codex backend can request `_base.py` contract changes if real codex protocol needs it
