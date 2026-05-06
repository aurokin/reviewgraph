# ISSUE PLAN: AUR-237 Add Core Redaction Service

Active issue plan for `AUR-237` / `RG-048: Add Core Redaction Service`.

## Linear Snapshot

- Issue: `AUR-237`
- Status at start: `In Progress`
- Milestone: `PRD 0003: Contracts`
- Blocks: `AUR-211`, then milestone gate `AUR-254`
- Blocked by: `AUR-192` (Done)
- Comments at start: none
- Harness from Linear: `python -m pytest tests/test_redaction.py`

## Goal

Promote redaction from an indirectly tested helper into a focused contract that future render, tracing, payload, and live LLM adapter work can safely reuse.

This issue should not add live LLM calls, live GitHub reads, approval UI, writer behavior, or raw-content tracing. It should make the safe default explicit: redacted text is the only normal path for external PR-derived text.

## Current Code

- `src/reviewgraph/redaction.py` already redacts private keys, authorization headers, bearer tokens, GitHub tokens, API-key-like assignments, `.env` assignments, and standalone key shapes.
- `src/reviewgraph/posting.py` redacts candidate issue-comment bodies before hashing.
- `src/reviewgraph/render.py` redacts rendered markdown/JSON fields and absorbs candidate payload redaction status.
- `src/reviewgraph/runner.py` redacts the top-level JSON envelope and CLI-facing errors through fixture error helpers.
- Existing coverage lives in `tests/test_render.py`, `tests/test_posting.py`, `tests/test_cli.py`, and tracer tests. There is no focused `tests/test_redaction.py` harness.

## Implementation Plan

1. Strengthen `src/reviewgraph/redaction.py` as the shared redaction contract:
   - Keep `redact_text` deterministic and preserve existing replacement/category behavior.
   - Add a reusable JSON/data redaction helper for logs, traces, JSON errors, default JSON output, and future provider-bound request stubs.
   - Add a small policy/result wrapper for provider-bound text that records whether raw submission was explicitly enabled; default must redact.
   - Keep raw opt-in as a recorded policy result only, not as live provider behavior.
2. Add `tests/test_redaction.py`:
   - Direct pattern coverage for API keys, bearer tokens, GitHub tokens, private keys, `.env` assignments, and authorization headers.
   - Determinism checks for repeated redaction over the same text and nested JSON-like structures.
   - Surface checks for fixture title/body, labels, patches, comments, reviews, review-thread comments, rendered markdown/JSON, candidate payloads, JSON error payloads, trace/log dictionaries, and provider-bound request stubs.
   - Fail-closed checks proving provider-bound payloads are redacted by default and raw provider submission requires explicit opt-in recorded in the result.
3. Integrate narrowly where useful:
   - Replace or share runner-local JSON redaction with the redaction module helper if it reduces duplication without changing output shape.
   - Preserve existing render/posting behavior and redaction status accounting.
   - Ensure `ReviewState.redaction_status` and `GitHubReviewPayload.redaction_status` remain the state-facing proof points before payload validation/finalization.
4. Update durable docs only if implementation names or policies need alignment:
   - `docs/architecture/llm-data-handling.md`
   - `docs/harnesses/harness-engineering.md`

## Out Of Scope

- No live LLM adapter or provider call.
- No live GitHub read.
- No approval/final-payload UI.
- No writer/finalization implementation.
- No broad context package implementation; provider-bound payloads in this issue are deterministic redaction stubs only.

## Validation

Focused:

```bash
python -m pytest tests/test_redaction.py
```

Regression:

```bash
python -m pytest tests/test_render.py tests/test_posting.py tests/test_cli.py tests/test_tracer_fixture_run.py
python -m pytest
python -m py_compile src/reviewgraph/*.py
python scripts/check_docs.py
git diff --check
```

## Completion Evidence To Comment On Linear

- Files changed.
- Focused redaction harness output.
- Regression/full validation output.
- Explicit confirmation that no live provider, live GitHub, approval, or writer behavior was introduced.
- Subagent plan/code review results.
