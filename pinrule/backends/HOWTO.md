# How to Add a New AI Coding Client Backend

**[🇬🇧 English (current)](./HOWTO.md) · [🇨🇳 中文](./HOWTO.zh.md)**

pinrule currently supports 4 clients out-of-the-box (Claude / Codex / Cursor / Hermes). This doc explains how to add a 5th — in principle **any AI coding client that exposes a hook interface** (registers external commands at event triggers + passes payload via stdin) can be added as a backend.

## 5 steps to add a new backend

### Step 1: Research the client's hook protocol

Per pinrule's `long-term-fundamental` rule — **actually run, don't assume.** Research:

1. **Hook config file path** — usually `~/.<client>/settings.json` or `~/.<client>/hooks.json`
2. **Hook event names** — the event names written in config (e.g., Claude's `UserPromptSubmit` vs. Cursor's `preToolUse`)
3. **stdin payload fields** — case style (snake_case or camelCase?) + which fields pinrule cares about (`prompt` / `tool_name` / `tool_input` / `tool_response` / equivalent stop fields like `last_assistant_message` / `prompt_response` / `transcript_path`)
4. **stdout JSON fields** — consistent with Claude → use directly; inconsistent → adapt in hook entry module
5. **Whether enablement step needed** — like Codex requires `[features] hooks = true`
6. **Whether each hook entry needs matcher / timeout fields** — varies per client

Research source priority: ① Official docs ② Actually run client + trace hook stdin fields ③ GitHub issues / community

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

Stop fields differ across backends (pinrule stop.py has fallback chain):
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
- ❌ **Don't break coexistence with other hooks** (rtk and similar tools' same-event multiple entries must be preserved)
- ❌ **Atomic config file writes** (base class already implements tmp + os.replace, no need to touch)
- ❌ **Don't hardcode backend id names into core logic** — adding a backend shouldn't require modifying cli.py or other core code

## Currently supported backends

| Client | Config path | Status |
|---|---|---|
| Claude | `~/.claude/settings.json` | ✓ Since v0.1.0 |
| Codex | `~/.codex/hooks.json` | ✓ Since v0.3.0 |
| Cursor | `~/.cursor/hooks.json` | ✓ Since v0.12.0 (Cursor 1.7+ required; `/pinrule` skill is project-scoped only — no global skills dir on Cursor) |
| Hermes | `~/.hermes/config.yaml` | ✓ Since v0.19.0 (NousResearch Hermes Agent v0.14.0+ — persistent server agent with plugin hooks; source-grounded against `agent/shell_hooks.py`. Line-based surgical operator only touches the top-level `hooks:` section — Hermes's other sections preserved verbatim, install is fully automatic.) |

## Candidate backends — no pre-built list

In principle **any AI coding client that exposes a hook interface** can be added as a backend. The client's protocol needs to provide:

- A hook config file (JSON / TOML / YAML — all fine)
- Ability to execute external commands at events like user prompt / tool call / stop
- stdin payload delivery (with fields like `prompt` / `tool_input` / `transcript_path`)

**There's no pre-built shopping list** — client protocols evolve fast and secondary intel goes stale (field names change, event names change, enablement flags change). **Empirically verifying protocol fields beats reading any list.**

Process to add a new backend: install that client → trace hook protocol to see real fields → follow the 5 steps above → add tests → PR.

**When adding a new backend, update the "Currently supported backends" table above** so later contributors see what's actually supported.
