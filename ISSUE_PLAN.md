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

This issue validates the MVP GitHub artifact contract without making the graph writer-ready. It does not implement approval, final payload construction, finalization, marker reconciliation, fake writer, real writer, or live posting.

## Contracts To Preserve

- MVP GitHub write artifact is only a top-level `issue_comment`.
- MVP endpoint is only `POST /repos/{owner}/{repo}/issues/{pr_number}/comments`.
- Formal PR review payloads, `/pulls/{pr}/reviews`, `event: COMMENT`, `APPROVE`, and `REQUEST_CHANGES` are rejected or deferred.
- Candidate payloads carry candidate visible body hash and findings hash inputs only.
- Candidate payloads do not contain a final marker line and do not expose candidate-owned final hash semantics.
- Candidate dataclass and dry-run JSON/markdown must remove `full_body_hash`; a candidate preview hash, if needed later, must be a separate explicitly named field and is not part of this issue.
- Remove `candidate_payload_hash` from `ReviewState`, `docs/architecture/state-graph.md`, and model contract tests. Candidate visible body hash stays on the candidate payload object only.
- Candidate payloads are never accepted as writer or final-payload input.
- Final issue-comment payload contract models carry final body, exact marker line/components, visible body hash, final payload hash, findings hash, review target, item fingerprints, and redaction status. They are inert contracts in this issue, not graph-produced writer inputs.
- Final payload self-consistency validation checks the exact invariants: marker is the final line, marker fields match payload fields, marker `payload` equals visible-body hash excluding marker, final payload hash includes marker, target hash matches payload review target, and findings hash matches sorted unique payload fingerprints.
- Writer-readiness validation is deferred. This issue may define a pure request contract validator, but it must not connect it to the graph or writer adapters. If present, that validator must accept independent expected inputs (`ReviewTarget`, selected unique fingerprints, and final payload) so later approval/finalization cannot self-validate payload-owned fields.
- Candidate and final payload validation require passing redaction status; failed or unknown redaction status fails validation with a stable reason code.
- Pure request-shape validation, if included, includes `method=POST`, exact issue-comment endpoint `/repos/{owner}/{repo}/issues/{pr_number}/comments`, endpoint owner/repo/PR number matching the independently supplied expected `ReviewTarget`, and a body shape exactly equal to `{"body": final_payload.body}` with no formal-review fields.
- Payload validation runs before any writer adapter can receive a payload.
- `ReviewState` and `docs/architecture/state-graph.md` use distinct candidate/final payload type names.
- `docs/architecture/side-effects.md`, `docs/architecture/github-integration.md`, `docs/plans/implementation-plan.md`, `docs/prds/0003-contracts.md`, and `docs/prds/0007-side-effects.md` must be updated to stop describing candidate payloads as having generic/final payload hashes. They should distinguish candidate visible-body/findings hash inputs from final payload hash.
- Validation failures return stable machine-readable reason codes so later finalization/writer slices can fail closed without parsing prose exceptions.
- Candidate tamper validation is bound by independent expected inputs: current `ReviewTarget`, posting plan/current classified findings or rebuilt expected candidate payload, expected sorted unique fingerprints, `body`, `visible_body_hash`, `findings_hash`, sorted unique `item_fingerprints`, and passing `redaction_status`. Removing candidate `full_body_hash` must not weaken the existing render-time proof that the supplied candidate equals the payload rebuilt from the current posting plan and findings.
- `PayloadValidationResult` must expose a typed/validated `reason_code` machine contract. A free-form display `reason` may remain, but tests must reject unknown reason codes and no downstream code may need to parse prose.

## Stable Reason Codes

The initial stable code set is:

- `wrong_artifact_kind`
- `redaction_not_passed`
- `candidate_contains_marker`
- `candidate_binding_mismatch`
- `not_final_payload`
- `body_hash_mismatch`
- `findings_hash_mismatch`
- `duplicate_fingerprints`
- `target_hash_mismatch`
- `marker_not_final_line`
- `marker_field_mismatch`
- `final_payload_hash_mismatch`
- `wrong_method`
- `wrong_endpoint`
- `request_target_mismatch`
- `wrong_request_body`
- `formal_review_payload_rejected`

## Implementation Shape

1. Replace the current `CandidateIssueCommentPayload = GitHubReviewPayload` alias with distinct dataclasses in `src/reviewgraph/models.py`.
2. Remove `full_body_hash` from candidate payload model and candidate dry-run JSON/markdown. Candidate preview should expose body, visible body hash, findings hash, item fingerprints, review target, artifact kind, and redaction status only.
3. Remove `candidate_payload_hash` state from code/docs/tests.
4. Add inert final payload model fields for marker components and exact marker line, reusing `AUR-244` hash helpers, without constructing final payloads in the graph.
5. Add a small pure request contract model or validator input for method/endpoint/body-shape validation without implementing a writer transport.
6. Extend `PayloadValidationResult` with a typed/validated `reason_code` field and keep `reason` as optional display text only.
7. Add a payload validation module, likely `src/reviewgraph/payload_validation.py`, with explicit validators for:
   - candidate payload preview against independent expected inputs or a rebuilt expected candidate payload,
   - finalized issue-comment payload self-consistency,
   - optional writer request shape accepts only finalized issue comments and independently supplied expected target/fingerprint inputs,
   - request endpoint target matches the independently supplied expected review target,
   - request body is exactly `{"body": final_payload.body}`,
   - rejected formal review payload dictionaries/endpoints.
8. Add `tests/test_payload_validation.py` covering every acceptance criterion, including stable failure reason codes, candidate-as-final/request rejection, unknown reason-code rejection, and the import boundary proving `payload_validation.py` does not import GitHub transport, writer, approval, finalization, or live adapter modules.
9. Preserve the existing render binding check that rejects a supplied candidate payload unless it matches the independently rebuilt candidate from the current `posting_plan` and classified findings. It may stay a `RenderError` or move into `payload_validation.py` as `candidate_binding_mismatch`, but the current tampered-body-with-recomputed-hashes regression must keep failing.
10. Update `docs/architecture/state-graph.md`, `docs/architecture/side-effects.md`, `docs/architecture/github-integration.md`, `docs/plans/implementation-plan.md`, `docs/prds/0003-contracts.md`, `docs/prds/0007-side-effects.md`, and model contract tests so candidate/final payload fields and hash semantics are distinct.
11. Update existing tests/render serialization only where required by the candidate/final split.

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
