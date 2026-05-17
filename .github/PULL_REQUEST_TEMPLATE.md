## What this PR does

Brief description of the change. If it's a new feature, explain whether it's at the rule layer / check layer / hook layer.

## Real driving scenario

pinrule's validation criterion is "the author / user can describe 3 concrete cases" — what real scenarios does this PR solve?

## Verification evidence

- [ ] All tests pass: `pytest tests/ -q`
- [ ] Static checks clean: `ruff check pinrule/ tests/ && mypy pinrule/ tests/ && vulture pinrule/ --min-confidence 80`
- [ ] Manual run verifies hook behavior (if hooks changed)
- [ ] If adding new rule templates / check functions, add corresponding tests

## Boundary check

- [ ] No LLM dependency introduced
- [ ] No retrieval / cosine / scoring system introduced
- [ ] No backward-incompatible breakage of existing rule configs
- [ ] Small and reviewable by default; larger batches OK when the maintainer has explicitly asked for "one PR, don't fragment it"

## Related

- Related issue: #
- Related version: (see `pinrule --version`)
