# Security Policy

**[🇬🇧 English (current)](./SECURITY.md) · [🇨🇳 中文](./SECURITY.zh.md)**

## Reporting vulnerabilities

If you find a security issue in karma, **don't open a public issue**. Use [GitHub's private Security Advisory](https://github.com/jhaizhou-ops/karma/security/advisories/new) — that's the fastest channel.

## karma's real threat model

karma is a **local hook tool** — runs on your machine, reads your local config, writes local files. It doesn't connect to external services (no LLM API / no telemetry / no network calls). The attack surface is limited but **not zero**:

### Realistic threat scenarios

| Scenario | Risk | Mitigation |
|---|---|---|
| **`rules.yaml` contains malicious regex** | User copies untrusted rule template containing ReDoS patterns that hang the hook | karma fails loud on `re.compile` errors during rule loading; users should only copy templates from trusted sources |
| **Hook wrapper tampered with** | Attacker replaces `~/.claude/hooks/karma_*.py` to inject malicious code | karma doesn't actively verify wrapper integrity — `karma install-hooks` reinstall can restore; protect hooks directory with OS file permissions |
| **`violations.jsonl` contains sensitive strings** | Bash command containing secrets triggers karma detection → secret enters `~/.claude/karma/violations.jsonl` snippet field | Don't put plaintext secrets in Bash commands; karma doesn't perform secret detection on disk (not its responsibility) |
| **`pre_compact_snapshot.md` contains sensitive content** | Pre-compact rule state dumped to `~/.claude/karma/pre_compact_snapshot.md` containing your `rules.yaml` preference content | Don't put secrets in `rules.yaml` `preference` field; file is 600 permissions + home directory protected by default |
| **Cross-session state contamination** | Multiple session JSON files in `~/.claude/karma/session-state/` containing read_files / edit_files / recent_bash summaries | Auto-cleaned after 30 days (configurable via `session_state_max_age_days`); doesn't sync cross-user / cross-machine |

### **Not** karma's security responsibility

- **Claude / Codex / Cursor model security issues** → contact upstream
- **Agent behavior after rule injection** → model behavior is outside karma's control (karma only injects rule text, doesn't adjudicate how the Agent executes)
- **Security of other tools in your `~/.claude/`** → contact those tools' maintainers
- **Network-layer / system-layer threats** → outside karma's threat model

## Known limitations

karma is a **regex matching + counting** engineering tool, not LLM semantic understanding:

- **Can't detect Agent implicitly bypassing rules** — users modifying `violation_keywords` keyword list is trust-based; karma doesn't validate keyword reasonableness
- **Can't detect actual legitimacy of `rules.yaml` content** — if a user writes "encourage Agent to write insecure code" type preferences, karma will still inject as-is. **Users are responsible for `rules.yaml` content**
- **`bypass_karma_detection` check blocks "Bash commands containing karma internal state strings + write operations"** — can't prevent users from using other tools (vim / cat / Python scripts) to modify karma internal state without going through AI client hooks

## Response timelines

- **Vulnerability confirmation**: response within 3 business days
- **Fix release**: high severity 7 days / medium severity 30 days / low severity bundled with next release

karma is an individually-maintained project with no dedicated security team. Please understand response times may be affected by maintainer availability.

## Acknowledgments

Responsible disclosure researchers are welcome to be acknowledged in fix release notes / project contributors (if you accept public credit).
