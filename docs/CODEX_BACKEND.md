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

## The 6-method contract

Codex backend (`CodexBackend` class in `karma/backends/codex.py`) must implement these methods. Default implementations in `JsonHooksBackend` base class are Claude-shaped; override to match codex protocol.

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

## Known TODO list (codex agenda)

These are gaps karma maintainer identified but **deferred to codex backend owner** because they require codex-side protocol knowledge:

| # | Issue | Suggested approach |
|---|---|---|
| 1 | **shell-as-Read** — `exec_command` running `tail`/`sed`/`cat` should count as Read for `record_read` and lift `read_first` denials | New `karma/utils/shell_read.py` with `extract_read_paths_from_shell(command) -> list[str]`. `codex.normalize_tool_input` writes `read_file_paths` field. `post_tool_use` general handler records each. Codex should test against real codex CLI sessions to avoid false-positives on complex pipelines (xargs, find, ls -la). |
| 2 | **Real hook-level payload capture** — currently inferred from session rollout (`response_item.payload.input` field) but actual hook stdin shape (after codex wrapping) not directly captured. `_extract_codex_patch_text` defensively unwraps several candidate shapes; can be tightened once real payload schema is known. | Add `KARMA_DEBUG_DUMP_PAYLOAD` env to a real interactive codex session (after `/hooks` approval), dump payloads, lock real shape in test fixtures. |
| 3 | **Codex feature-flag detection** — `_is_hooks_feature_enabled` parses `~/.codex/config.toml`. Codex may expose a cleaner API. | If codex CLI has e.g. `codex features list --json` or status file, replace the toml parser. |
| 4 | **Other codex tool names not mapped** — `exec_command` should map to `Bash` (it's the codex equivalent). `update_plan` probably should pass through. | Audit codex tool registry, update `_CODEX_TOOL_MAP`. |
| 5 | **Approval state detection** — `karma doctor` currently prints a manual reminder. If codex exposes approved-hook list (sqlite? file? API?), `doctor` could programmatically verify each wrapper is approved. | Investigate codex internals; if no API exists, file an issue with OpenAI codex team. |

## How to contribute (codex PR flow)

1. **Modify** `karma/backends/codex.py` only (and `tests/test_codex_backend.py` if you create it)
2. **Verify** existing tests still pass: `.venv/bin/python -m pytest tests/test_protocol_adapter.py tests/test_backends.py -q`
3. **Add tests** for any new method behavior — at minimum, lock the new shape with a hardcoded expected output
4. **Capture real codex CLI evidence** (rollout file path / session ID / version) in commit message — this avoids the v0.9.15 "Claude guessed and got it wrong" pattern
5. **Don't break the 6-method contract** — if you need to add a new method, file an issue first so karma maintainer can update `_base.py` Protocol and all backends synchronously
6. **PR description must include**:
   - codex CLI version tested against (e.g., `codex 0.130.0`)
   - real-world test transcript (e.g., user prompt → karma response screenshot)
   - any new tool names / payload shapes captured (file path to session rollout)

## Contract testing (planned, not yet implemented)

karma maintainer will add `tests/test_backend_contract.py` running the same abstract contract test suite against every backend in `REGISTRY` — codex's PR should not break these. Expected coverage:
- All 6 methods callable without crash on minimal payload
- `emit_allow` and `emit_deny` return valid JSON
- `normalize_tool_name` preserves canonical names (idempotent)
- `pre_install_setup` and `post_install_message` return lists

## Communication channels

- **Architectural questions**: file GitHub issue tagged `backend:codex`, mention `@jhaizhou-ops`
- **PR review**: karma maintainer reviews within 1-2 days; aim for narrow, focused PRs (one TODO item per PR)
- **Breaking changes**: must be discussed in issue first; codex backend can request `_base.py` contract changes if real codex protocol needs it
