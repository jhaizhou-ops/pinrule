---
name: Bug Report (English)
about: Report a pinrule bug / false positive / install issue / hook malfunction
title: '[Bug] '
labels: bug
assignees: ''
---

## What did you encounter

Brief description of the problem. For **false positives** (pinrule blocks legitimate operations), paste `pinrule audit` output with the `⚠️ possible false positive` markers.

## Reproduction steps

1. Install via `pinrule install-hooks ...`
2. ...
3. Observed error / unexpected behavior

## Real state (output of `pinrule doctor`)

```
(paste complete `pinrule doctor` output)
```

## Environment

- pinrule version: (`pinrule --version`)
- AI client: Claude Code / Codex CLI / Gemini CLI (with version)
- OS: macOS / Linux / WSL
- Python: (`python --version`)
- Shell: zsh / bash / fish

## Key logs (if any)

If hook output schema errors or installation failures occur, paste the stderr / Claude Code UI error section.
