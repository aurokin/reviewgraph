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
- Candidate dataclass and dry-run JSON/markdown must remove `full_body_hash`; a candidate preview hash, if needed later, must be a separate explicitly named field and is not part of this issue.
- Remove `candidate_payload_hash` from `ReviewState`, `docs/architecture/state-graph.md`, and model contract tests. Candidate visible body hash stays on the candidate payload object only.
- Candidate payloads are never accepted as writer input.
- Final issue-comment payloads carry final body, exact marker line/components, visible body hash, final payload hash, findings hash, review target, item fingerprints, and redaction status.
- Final payload validation checks the exact invariants: marker is the final line, marker fields match payload fields, marker `payload` equals visible-body hash excluding marker, final payload hash includes marker, target hash matches review target, and findings hash matches sorted unique selected fingerprints.
- Candidate and final payload validation require passing redaction status; failed or unknown redaction status fails validation with a stable reason code.
- Writer-bound request validation includes `method=POST` and exact issue-comment endpoint `/repos/{owner}/{repo}/issues/{pr_number}/comments`, and the endpoint owner/repo/PR number must match the finalized payload `review_target`.
- Payload validation runs before any writer adapter can receive a payload.
- `ReviewState` and `docs/architecture/state-graph.md` use distinct candidate/final payload type names.
- `docs/architecture/side-effects.md` and `docs/architecture/github-integration.md` must be updated to stop describing candidate payloads as having generic/final payload hashes. They should distinguish candidate visible-body/findings hash inputs from final payload hash.
- Validation failures return stable machine-readable reason codes so later finalization/writer slices can fail closed without parsing prose exceptions.

## Implementation Shape

1. Replace the current `CandidateIssueCommentPayload = GitHubReviewPayload` alias with distinct dataclasses in `src/reviewgraph/models.py`.
2. Remove `full_body_hash` from candidate payload model and candidate dry-run JSON/markdown. Candidate preview should expose body, visible body hash, findings hash, item fingerprints, review target, artifact kind, and redaction status only.
3. Remove `candidate_payload_hash` state from code/docs/tests.
4. Add final payload model fields for marker components and exact marker line, reusing `AUR-244` hash helpers.
5. Add a small writer-request model or validator input for method/endpoint validation without implementing a writer transport.
6. Add a payload validation module, likely `src/reviewgraph/payload_validation.py`, with explicit validators for:
   - candidate payload preview,
   - finalized issue-comment payload,
   - writer input accepts only finalized issue comments,
   - writer-bound endpoint target matches final payload review target,
   - rejected formal review payload dictionaries/endpoints.
7. Add `tests/test_payload_validation.py` covering every acceptance criterion, including stable failure reason codes.
8. Update `docs/architecture/state-graph.md`, `docs/architecture/side-effects.md`, `docs/architecture/github-integration.md`, and model contract tests so candidate/final payload fields and hash semantics are distinct.
9. Update existing tests/render serialization only where required by the candidate/final split.

## Validation

Focused:

```bash
python -m pytest tests/test_payload_validation.py -q
```

Regression:

```bash
python -m pytest tests/test_payload_hashes.py tests/test_posting.py tests/test_models.py tests/test_render.py tests/test_cli.py tests/test_tracer_fixture_run.py tests/test_redaction.py tests/test_github_read_gaps.py -q
python scripts/check_docs.py
git diff --check
```

Run the full suite because model/render/CLI payload previews touch shared contracts broadly.

## Out Of Scope

- Approval decision model or item-level approval (`AUR-217`).
- Actor/permission gates, target freshness, non-interactive post mode, marker reconciliation, fake writer, real writer, or live post smoke.
- Posting formal PR reviews, inline comments, replies, labels, statuses, approvals, or request-changes.
