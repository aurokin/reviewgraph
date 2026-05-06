# ISSUE PLAN: AUR-192 Parse Fixture PR With Review Target

Active issue plan for `AUR-192` / `RG-003: Parse Fixture PR With Review Target`.

## Linear Snapshot

- Issue: `AUR-192`
- Status at start: `In Progress`
- Milestone: `PRD 0003: Contracts`
- Blocks: `AUR-193`, `AUR-194`, `AUR-213`, `AUR-234`, `AUR-237`, `AUR-254`
- Blocked by: `AUR-312`, `AUR-230`, `AUR-190` (all now Done)
- Comments at start: none
- Harness from Linear: `python -m pytest tests/test_fixtures.py`

## Goal

Define the fixture PR schema and parse packaged fixture files into typed `ReviewTarget` and `PullRequestContext` contracts.

This issue should make fixture PRs durable enough for later memory, budget, redaction, fake GitHub transport, and empty graph slices. It should not add live GitHub transport, reviewer execution behavior, context budgeting, or redaction behavior.

## Implementation Plan

1. Strengthen fixture parsing in `src/reviewgraph/fixtures.py`:
   - Parse `target` into `ReviewTarget` during fixture load.
   - Parse PR metadata into `PullRequestContext`: title, body, labels, changed files, comments, reviews, and review threads.
   - Keep the current dry-run runner compatible by preserving `FixturePR` access to `labels`, `changed_files`, `memory`, `truncation`, and raw reviewer outputs.
   - Keep fixture errors clear and field-specific.
2. Strengthen PR context contracts where needed in `src/reviewgraph/models.py`:
   - Validate PR comments, reviews, review threads, changed files, and `PullRequestContext` enough that parser tests catch malformed fixture state.
   - Keep these contracts schema-only and stdlib-only.
3. Expand fixture schema fields:
   - Required target fields: owner/repo, PR number, base SHA, head SHA, merge-base SHA or null, and diff basis.
   - Required PR metadata: title, body or null, labels, changed files, comments, reviews, and review threads.
   - Changed files include path, patch, changed ranges, additions, and deletions.
   - Review threads include `resolved`, `unresolved`, or `unknown` thread state and nested comments.
4. Add schema-valid fixture files for every `AUR-230` corpus scenario:
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
   These fixtures can be intentionally small, deterministic, and synthetic; they only need to validate and represent the scenario shape.
5. Update the packaged manifest:
   - Add a schema-valid `path` to each `corpus_scenarios` entry.
   - Register corpus fixtures in the runnable `fixtures` registry only if they satisfy the same base parser requirements as existing fixtures.
   - Ensure every required scenario is consumed by at least one later issue or harness.
6. Add `tests/test_fixtures.py`:
   - All corpus scenarios from the manifest have exactly one schema-valid fixture file.
   - Every manifest fixture/corpus scenario has consumers.
   - Parsed fixtures expose a stable `ReviewTarget`.
   - Review target hashes change when base SHA, head SHA, or diff basis changes.
   - Invalid fixture shapes fail with clear errors for target, labels, changed files, comments, reviews, review threads, and missing corpus fixture files.
   - Existing packaged fixtures still parse and support the current dry-run harness.

## Out Of Scope

- No live GitHub transport or pagination implementation. `AUR-213` owns fake transport reads.
- No conversation-memory builder. `AUR-193` owns trusted memory behavior.
- No empty LangGraph runtime. `AUR-194` owns graph execution.
- No context budget enforcement. `AUR-234` owns budget behavior.
- No redaction service change. `AUR-237` owns redaction behavior.
- No live LLM calls or writer behavior.

## Validation

Focused:

```bash
python -m pytest tests/test_fixtures.py
```

Regression:

```bash
python -m pytest tests/test_fixture_manifest.py tests/test_cli.py tests/test_tracer_fixture_run.py
python -m pytest
python -m py_compile src/reviewgraph/*.py
python scripts/check_docs.py
git diff --check
```

## Completion Evidence To Comment On Linear

- Files changed and fixture IDs added.
- Focused fixture harness output.
- Full regression output.
- Confirmation that all `AUR-230` corpus entries have schema-valid fixture files.
- Confirmation that no live GitHub, live LLM, graph runtime, or writer behavior was introduced.
