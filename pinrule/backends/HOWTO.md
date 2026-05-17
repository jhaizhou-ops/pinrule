# How to Add a New AI Coding Client Backend

**[🇬🇧 English (current)](./HOWTO.md) · [🇨🇳 中文](./HOWTO.zh.md)**

pinrule currently supports 3 clients out-of-the-box (Claude / Codex / Cursor). This doc explains how to add a 4th — empirically-verified vibe-island bridge supports 9 clients: claude / codex / cursor / factory / qoder / copilot / codebuddy / kimi.

## 5 steps to add a new backend

### Step 1: Research the client's hook protocol

Per pinrule's `long-term-fundamental` rule — **actually run, don't assume.** Research:

1. **Hook config file path** — usually `~/.<client>/settings.json` or `~/.<client>/hooks.json`
2. **Hook event names** — the event names written in config (e.g., Claude's `UserPromptSubmit` vs. Cursor's `preToolUse`)
3. **stdin payload fields** — case style (snake_case or camelCase?) + which fields pinrule cares about (`prompt` / `tool_name` / `tool_input` / `tool_response` / equivalent stop fields like `last_assistant_message` / `prompt_response` / `transcript_path`)
4. **stdout JSON fields** — consistent with Claude → use directly; inconsistent → adapt in hook entry module
5. **Whether enablement step needed** — like Codex requires `[features] hooks = true`
6. **Whether each hook entry needs matcher / timeout fields** — varies per client

Research source priority: ① Official docs ② Actually run client + trace hook stdin fields ③ Look at existing bridge tools (vibe-island) implementation ④ GitHub issues

### Step 2: Create a new backend file in `pinrule/backends/`

**Step 1 research item → Step 2 class attribute mapping** (fill-in-the-form loop):

| Research item | Class attribute | Example (Codex) |
|---|---|---|
| Hook config file path | `_CONFIG_DIR_NAME` + `_SETTINGS_FILENAME` | `".codex"` + `"hooks.json"` (auto-concatenated to `~/.codex/hooks.json`) |
| Client command name (PATH detection) | `_CLIENT_CMD` | `"codex"` (detects via `command -v codex`) |
| Backend registration name | `name` | `"codex"` |
| User-visible name | `display_name` | `"Codex"` |
| Hook event name mapping | `_HOOK_EVENTS` | `{"UserPromptSubmit": "user_prompt_submit", ...}` |
| Whether matcher / timeout fields needed | override `build_event_entry` (optional) | Codex adds `timeout: 30` |
| Whether enablement step needed | override `pre_install_setup` (optional) | Codex runs `codex features enable hooks` |
| stdin payload field differences | modify `pinrule/hooks/stop.py` fallback chain (optional) | Codex uses `last_assistant_message` instead of `transcript_path` |

Reference `pinrule/backends/claude_code.py` for the cleanest template (inherits `JsonHooksBackend`, only fills class attributes):

```python
from pinrule.backends._json_hooks import JsonHooksBackend

class CursorBackend(JsonHooksBackend):
    name = "cursor"                          # backend registration name
    display_name = "Cursor"                  # user-visible name
    _CONFIG_DIR_NAME = ".cursor"             # ~/ subdirectory name
    _SETTINGS_FILENAME = "hooks.json"        # config filename
    _CLIENT_CMD = "cursor"                   # PATH command name (for install detection)

    # backend native event name → pinrule internal wrapper basename
    # pinrule internal 4 wrappers: user_prompt_submit / pre_tool_use /
    # post_tool_use / stop (reused across backends, don't modify)
    _HOOK_EVENTS = {
        "UserPromptSubmit": "user_prompt_submit",
        "PreToolUse": "pre_tool_use",
        "PostToolUse": "post_tool_use",
        "Stop": "stop",
    }

    # ✓ Minimal stub stops here — default doesn't need override of
    # build_event_entry / pre_install_setup. Base class _json_hooks.py provides
    # reasonable defaults.
```

### Claude-specific optional extensions (v0.4.28+)

pinrule v0.4.28+ added 2 Claude protocol-specific hook events for "rule mid-injection + compact amnesia two-pronged defense":

```python
# Claude backend additional 2 events (other backends without these don't require)
"SessionStart": "session_start",  # v0.4.28 — inject rule baseline at session start
                                   # source field distinguishes startup/resume/clear/compact
"PreCompact": "pre_compact",       # v0.4.29 — dump full rule state before compact
                                   # combined with SessionStart(source=compact) two-pronged defense
```

New backend implementer assessment:

- If backend protocol **has** similar session lifecycle / context compact events →
  add mapping in `_HOOK_EVENTS` + write corresponding wrapper to enable pinrule's mid-conversation injection + compact-time dump double-bracket coverage
- If **no** corresponding events (like Codex / Cursor's current situation) →
  skip; 4 universal wrappers already cover pinrule core functionality (violation detection + rule injection into user prompt)

If backend needs matcher / timeout field in hook entry: override `build_event_entry`:

```python
def build_event_entry(self, hook_name_lower: str, event_name: str) -> dict:
    wrapper = self.hooks_dir() / f"pinrule_{hook_name_lower}.py"
    return {
        "hooks": [{"type": "command", "command": str(wrapper), "timeout": 30}]
    }
```

If backend needs an enablement step (Codex-like): override `pre_install_setup`:

```python
def pre_install_setup(self) -> list[str]:
    # Returns user-visible step log
    ...
```

### Step 3: Register in `pinrule/backends/__init__.py`

```python
from pinrule.backends.cursor import CursorBackend

REGISTRY: dict[str, Backend] = {
    "claude-code": ClaudeCodeBackend(),
    "codex": CodexBackend(),
    "cursor": CursorBackend(),              # add this line
}
```

### Step 4: Check stdin payload field differences

pinrule hook entries (`pinrule/hooks/*.py`) use the following fields, typically same-named across backends:

- `session_id` — all backends use `session_id` (snake_case)
- `prompt` — UserPromptSubmit / BeforeAgent both use `prompt`
- `tool_name` / `tool_input` / `tool_response` — Pre/PostToolUse all use same names

Stop fields differ across 3 backends (pinrule stop.py already three-way fallback):
- Claude: `transcript_path` (reverse-read transcript)
- Codex: `last_assistant_message`

If a new backend uses a 4th field name, modify `pinrule/hooks/stop.py:_read_last_assistant_response` fallback chain to add `or payload.get("<new_field>", "")`.

### Step 5: Add guard tests

Reference `tests/test_backends.py`:

- backend paths correct
- event entry construction correct (including timeout / matcher fields if any)
- load_settings / save_settings roundtrip
- `is_pinrule_entry` recognizes `pinrule_` prefix

If stop.py adapter field added: reference `tests/test_hooks.py::test_stop_hook_uses_codex_last_assistant_message_field` for a field-fallback test.

## Real-world verification (actually run, don't assume)

After adding, **must actually run** to verify:

```bash
pinrule install-hooks --backend <new-name>
cat ~/.<client>/settings.json | python -m json.tool  # See pinrule's 4 entries added + others' hooks preserved
pinrule uninstall-hooks --backend <new-name>
cat ~/.<client>/settings.json | python -m json.tool  # See pinrule cleaned + others' hooks preserved
```

Simulate stdin payload to test pinrule stop hook catching violations:

```bash
echo '{"session_id":"t","prompt_response":"I'll patch this quickly","<other fields>":"..."}' | \
    ~/.<client>/hooks/pinrule_stop.py
# Expected: ⚠️ pinrule: Agent triggered keyword ... + JSON decision=block output
```

## Non-skippable steps (per pinrule project principles)

- ❌ **Don't ship based on docs alone — actually run the new backend end-to-end** (pinrule's `long-term-fundamental` + `loud-failure-with-evidence` rules)
- ❌ **Don't break coexistence with other hooks** (vibe-island / rtk etc. same-event multiple entries must be preserved)
- ❌ **Atomic config file writes** (base class already implements tmp + os.replace, no need to touch)
- ❌ **Don't hardcode backend id names into core logic** — adding a backend shouldn't require modifying cli.py or other core code

## Candidate backend list (vibe-island empirical intel, pending real install + test)

From `~/.vibe-island/bin/vibe-island-bridge` zsh script line 28, vibe-island's empirically-supported clients with config paths. **This is secondary intel needing real client install + protocol field verification** before backend can be added — left here for future contributors to pick from:

| Client | Suspected config path | Status |
|---|---|---|
| Claude | `~/.claude/settings.json` | ✓ Since v0.1.0 |
| Codex | `~/.codex/hooks.json` | ✓ Since v0.3.0 |
| Cursor | `~/.cursor/hooks.json` | ✓ Since v0.12.0 (Cursor 1.7+ required; `/pinrule` skill is project-scoped only — no global skills dir on Cursor) |
| Factory | `~/.factory/settings.json` | Pending install + test |
| Qoder | `~/.qoder/settings.json` | Pending install + test |
| GitHub Copilot | `~/.copilot/config.json` | Pending install + test (may not have hook protocol) |
| CodeBuddy | `~/.codebuddy/settings.json` | Pending install + test |
| Kimi CLI | `~/.kimi/config.toml` (TOML not JSON!) | Pending install + test — TOML format may not inherit JsonHooksBackend directly |

**Before testing each**, check that client's hook protocol docs (if any) + which event names vibe-island uses for that client + client version (vibe-island intel may be outdated — we empirically found Codex's real feature name is `hooks` not vibe-island config.toml's `codex_hooks`).

**When adding new backend, update this table in this file** to ensure later contributors see what's currently supported vs. pending.
