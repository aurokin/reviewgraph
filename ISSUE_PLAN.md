# ISSUE PLAN: AUR-230 Seed Fixture Corpus Manifest

Active issue plan for `AUR-230` / `RG-041: Seed Fixture Corpus Manifest`.

## Linear Snapshot

- Issue: `AUR-230`
- Status at start: `In Progress`
- Milestone: `PRD 0003: Contracts`
- Blocks: `AUR-192`, `AUR-233`, `AUR-235`, `AUR-237`, `AUR-254`
- Blocked by: `AUR-190` (now Done)
- Comments at start: none
- Harness from Linear: manifest validation for names and consumers only

## Goal

Seed the fixture corpus manifest so downstream harness work uses a shared scenario map before the full fixture schema/files are implemented.

This is manifest-only. It must not require schema-valid PR fixture files for the new scenarios yet, and it must not introduce live GitHub reads, live LLM calls, or runner behavior.

## Implementation Plan

1. Expand `src/reviewgraph/fixtures_data/manifest.json` with a dedicated manifest-only section for the required PRD 0003 corpus scenarios:
   - `frontend-state-change`
   - `security-sensitive-change`
   - `docs-only-change`
   - `mixed-risk-change`
   - `ambiguous-logic-change`
   - `breaking-api-change`
   - `oversized-change`
   - `stale-approval-change`
   - `untrusted-comment-injection`
   - `paginated-github-read`
2. For every scenario, record:
   - behavior proved
   - later issue or harness consumers
   - intended fixture shape fields: comments, review comments, reviews, thread state, labels, changed files, patches, base/head SHA, merge-base SHA, and diff basis
   - no live GitHub/LLM requirement
   - explicit schema-valid fixture deferral to `AUR-192`
3. Add focused manifest tests:
   - Required scenario IDs are present exactly once.
   - Each required scenario has at least one consumer.
   - Each required scenario has behavior text and fixture shape notes for the required fields.
   - Each required scenario declares no live GitHub/LLM requirement.
   - Each required scenario explicitly defers schema-valid fixture files to `AUR-192`.
4. Preserve existing runnable packaged fixtures and reviewer config manifest entries used by current CLI/tracer harnesses.

## Out Of Scope

- No schema-valid files for the ten required corpus scenarios. `AUR-192` owns that.
- No fixture parser expansion beyond reading the manifest as JSON.
- No live GitHub transport, live LLM calls, reviewer execution changes, context budget, or redaction changes.

## Validation

Focused:

```bash
python -m pytest tests/test_fixture_manifest.py tests/test_cli.py::test_manifest_registry_includes_consumed_basic_fixture
```

Regression:

```bash
python -m pytest
python -m py_compile src/reviewgraph/*.py
python scripts/check_docs.py
git diff --check
```

## Completion Evidence To Comment On Linear

- Required scenario IDs and consumer mapping.
- Focused manifest harness output.
- Full regression output.
- Confirmation that schema-valid fixture files are deferred to `AUR-192`.
- Confirmation that no live GitHub or live LLM requirement was introduced.
