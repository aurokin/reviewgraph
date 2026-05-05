# Harness Engineering

Harnesses prove the product contract without requiring live GitHub or live LLM calls.

## Confidence ladder

Use the lightest harness that proves the change.

1. **Schema harness** — validate config, PR context, findings, verdicts, and payload models.
2. **Routing harness** — fixture PRs select the expected reviewer agents with expected reasons.
3. **Reviewer harness** — deterministic fake LLM responses normalize into findings.
4. **Dedupe/verdict harness** — overlapping findings merge and produce expected verdicts.
5. **Graph harness** — full LangGraph run with fixture GitHub adapter and fake LLM.
6. **Dry-run CLI harness** — command produces markdown + JSON and performs no side effects.
7. **Approval harness** — rejected approval never calls GitHub writer; approved approval calls writer exactly once.
8. **Live read smoke** — fetch a real public PR in read-only mode.
9. **Live post smoke** — only against a disposable test PR, after explicit human approval.

## Fixture PRs

Maintain fixtures under `tests/fixtures/prs/` once implementation starts:

- `frontend-state-change.json`
- `security-sensitive-change.json`
- `docs-only-change.json`
- `mixed-risk-change.json`

Each fixture should include metadata, labels, changed files, and patch snippets.

## Required tests before MVP is complete

- Config validation rejects unknown trigger fields.
- Path triggers select matching reviewers.
- Diff patterns select matching reviewers.
- Always-on reviewers are selected for every PR.
- Failed optional reviewer records an error and continues.
- Failed required reviewer prevents posting.
- Low-confidence finding cannot request changes.
- Duplicate findings merge into one summary item.
- Dry-run mode never invokes GitHub writer.
- Approval rejection never invokes GitHub writer.
- Approval acceptance invokes GitHub writer once with exact payload.

## Live API discipline

Live tests are opt-in. They must never run as part of default test commands.

Recommended future commands:

```bash
pytest
pytest -m live_read
pytest -m live_post --requires-human-approval
```
