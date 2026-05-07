# ISSUE PLAN: AUR-218 Validate Top-Level Issue Comment Payloads

Active issue plan for `AUR-218` / `RG-029: Validate Top-Level Issue Comment Payloads`.

Linear is the durable source for status, blockers, and issue handoff. Durable behavior comes from `docs/architecture/github-integration.md`, `docs/architecture/side-effects.md`, `docs/architecture/state-graph.md`, and `docs/harnesses/harness-engineering.md`.

## Linear Snapshot

- Project: `ReviewGraph`
- Team: `Aurokin`
- Milestone: `PRD 0007: Side Effects`
- Issue: `AUR-218`
- Title: `RG-029: Validate Top-Level Issue Comment Payloads`
- Status when planned: `In Progress`
- Linear comments fetched on 2026-05-07: none
- Upstream blocker: `AUR-244` complete with canonical hash primitives and golden tests.

## Objective

Split candidate and finalized payload contracts enough that later approval, finalization, and writer slices cannot treat a candidate payload as a writer input.

This issue validates the MVP GitHub artifact shape. It does not implement approval, finalization, marker reconciliation, fake writer, real writer, or live posting.

## Contracts To Preserve

- MVP GitHub write artifact is only a top-level `issue_comment`.
- MVP endpoint is only `POST /repos/{owner}/{repo}/issues/{pr_number}/comments`.
- Formal PR review payloads, `/pulls/{pr}/reviews`, `event: COMMENT`, `APPROVE`, and `REQUEST_CHANGES` are rejected or deferred.
- Candidate payloads carry candidate visible body hash and findings hash inputs only.
- Candidate payloads do not contain a final marker line and do not expose candidate-owned final hash semantics.
- Candidate payloads are never accepted as writer input.
- Final issue-comment payloads carry final body, exact marker line/components, visible body hash, final payload hash, findings hash, review target, and redaction status.
- Payload validation runs before any writer adapter can receive a payload.

## Implementation Shape

1. Replace the current `CandidateIssueCommentPayload = GitHubReviewPayload` alias with distinct dataclasses in `src/reviewgraph/models.py`.
2. Keep dry-run candidate preview behavior compatible for render/CLI JSON, but rename or reshape fields so candidate payloads no longer own final hash semantics.
3. Add final payload model fields for marker components and exact marker line, reusing `AUR-244` hash helpers.
4. Add a payload validation module, likely `src/reviewgraph/payload_validation.py`, with explicit validators for:
   - candidate payload preview,
   - finalized issue-comment payload,
   - writer input accepts only finalized issue comments,
   - rejected formal review payload dictionaries/endpoints.
5. Add `tests/test_payload_validation.py` covering every acceptance criterion.
6. Update existing tests/render serialization only where required by the candidate/final split.

## Validation

Focused:

```bash
python -m pytest tests/test_payload_validation.py -q
```

Regression:

```bash
python -m pytest tests/test_payload_hashes.py tests/test_posting.py tests/test_models.py tests/test_render.py tests/test_cli.py -q
python scripts/check_docs.py
git diff --check
```

Run the full suite if model/render/CLI changes touch shared contracts broadly.

## Out Of Scope

- Approval decision model or item-level approval (`AUR-217`).
- Actor/permission gates, target freshness, non-interactive post mode, marker reconciliation, fake writer, real writer, or live post smoke.
- Posting formal PR reviews, inline comments, replies, labels, statuses, approvals, or request-changes.
