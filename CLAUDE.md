# pinrule — Project collaboration charter

**[🇬🇧 English (current)](./CLAUDE.md) · [🇨🇳 中文](./CLAUDE.zh.md)**

## One-line positioning

pinrule keeps the user's most-valued directions from being lost in long Agent tasks.

## Strict boundaries (non-negotiable)

These boundaries come from v1's lessons (see [karma-v1/ARCHIVE.md](https://github.com/jhaizhou-ops/karma-v1/blob/main/ARCHIVE.md)). Each one closes off a path that proved costly:

### Things we don't do

- ❌ **No auto-distilling new rules** — User manually maintains directions; LLM distillation produces noise and misalignment
- ❌ **No retrieval / cosine / scene routing** — 5-10 rules are all always-on; selection layer not needed
- ❌ **Don't compete with memory systems** — "Facts about the user" belong in the client's built-in memory
- ❌ **No LLM dependency** — pure engineering (keywords / regex / counting); decision is firm, not just for v0
- ❌ **No reward / RL / scoring** — behavioral reminders aren't reward functions; scoring rules makes the model optimize the score, not the behavior

## Working principles

### 1. Don't cheat the current user

pinrule is validated by author self-use. To keep that signal honest, **never** do these for short-term comfort:
- Hardcode author-specific rules into default templates
- Hardcode author's empirically-found violation phrases into hooks
- Train anything on author's session data

pinrule's defaults have to be **cross-user reasonable** — at CLAUDE.md / Anthropic best-practice level of universality.

### 2. Always design from "I am the user" perspective

For every change, ask:
- Can a first-time pinrule user get started in 5 minutes?
- Is the yaml config self-explanatory, or do they need to read docs to understand it?
- Does the first violation detection make them say "ah, I see"?

If a feature only works for the author → cut it.

### 3. Validation beats accuracy numbers

pinrule v1 fixated on accuracy numbers (67% precision, etc.) and that fixation pulled optimization off-target.

pinrule's validation criterion is **whether the author can describe 3 concrete cases after a week of self-use**:
- "During a long task, I didn't say anything and the Agent reminded itself of X"
- "After a compact, the Agent still remembered Y"
- "When the Agent was about to do Z, I saw the ⚠ prompt and corrected it"

If a week passes with no such cases → pinrule's hypothesis is wrong, redesign.

## Commit conventions

Commit messages explain what was done and why. Brief and direct:

```
feat: rules.yaml parser + schema validation

Supports single-line / multi-line preference, violation_keywords array
Schema validates 5-10 rule cap + id uniqueness
```

No complex templates needed. But every commit must:
- Pass lint and tests
- Not introduce LLM dependencies
- Stay small and reviewable by default; a larger batch is fine when the user explicitly asks for "one commit, don't fragment it"

## Reporting style

Completion reports in 1-3 sentences: **what was done + test results + push status**.
Don't:
- List long todos
- Expand the diff
- Explain tool mechanics
- Write "next possible things" over 3 lines

## Autonomous execution authorization

Default to autonomous on these:
- ✅ After completing tasks, directly git add + commit + push
- ✅ Run tests / install dependencies / fix lint
- ✅ Create comments / issues / PRs
- ✅ Delete merged temporary branches

Still need pre-approval:
- `git push --force` / `git reset --hard` of published commits
- gh repo archive / settings modifications
- Data destruction (`~/.pinrule/` clearing)
- Cross-repo changes

## Failure handling

pinrule's first principle is **honesty**:

- If a hook doesn't take effect, say so plainly — don't fake it
- If a check missed a real violation, record it — don't cover it up
- If a week of self-use produces no felt value, say redesign — don't preserve sunk cost

## Relationship with v1

v1 is archived at [jhaizhou-ops/karma-v1](https://github.com/jhaizhou-ops/karma-v1). Reusable v1 assets (SEED 20 rules, qwen3.5 helper, etc.) can be referenced but aren't required to reuse.

v2 is a cognitive reboot, not a v1 refactor. If a component's design changed, dropping the v1 solution is fine.
