---
name: Feature / Improvement Suggestion (English)
about: Suggest new features / new rule scenarios / new AI client backend
title: '[Feature] '
labels: enhancement
assignees: ''
---

## Your real pain point

Describe the scenario concretely. pinrule's design principle is "user-real-pain-driven" — we don't accept "I think this might be useful" type preventive suggestions.

## Proposed solution

If you have a specific idea, write it out. Include:
- Is it at the rule layer (can users solve this by writing their own `rules.yaml`)?
- Or at the check layer (needs new engine-layer violation_check function)?
- Or at the hook layer (needs new hook event or changes to existing hook behavior)?

## Have you considered alternatives

pinrule explicitly **doesn't do** these things — see README's "What pinrule doesn't do" section. If your need falls outside those boundaries, explain why an exception is necessary.

## Real user scenario (not speculation)

One of pinrule v1's failure lessons was "preventive design." New features must be driven by real user scenarios; we don't accept "might be useful" type needs.
