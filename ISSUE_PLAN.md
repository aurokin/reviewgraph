# ISSUE PLAN: AUR-223 Suppress Writes With No Approved Findings

Active issue plan for `AUR-223` / `RG-034: Suppress Writes With No Approved Findings`.

Linear is the durable source for status, blockers, and handoff. Durable behavior comes from `docs/architecture/side-effects.md`, `docs/architecture/state-graph.md`, `docs/architecture/github-integration.md`, `docs/harnesses/harness-engineering.md`, and `docs/prds/0007-side-effects.md`.

## Linear Snapshot

- Project: `ReviewGraph`
- Team: `Aurokin`
- Milestone: `PRD 0007: Side Effects`
- Issue: `AUR-223`
- Title: `RG-034: Suppress Writes With No Approved Findings`
- Status when planned: `In Progress`
- Linear comments fetched on 2026-05-07: none
- Upstream blockers complete: `AUR-244`, `AUR-218`, `AUR-217`, `AUR-219`, `AUR-243`, `AUR-220`, `AUR-221`, `AUR-245`, and `AUR-246`.
- Downstream issues: `AUR-222` owns the fake writer graph/CLI route; `AUR-241` owns the real writer adapter; `AUR-224` owns manual live post smoke.

## Objective

Prove that ReviewGraph never releases writer input when there is no approved public finding to post.

The current code already has approval proof and finalization preflight primitives, but there is no writer route yet. This issue should therefore harden the no-approved-finding contract at the approval/finalization boundary and in dry-run harness output, without adding fake writer, real writer, public post mode, or live GitHub writes.

Linear's handoff names `src/reviewgraph/finalize.py`; the repository module is `src/reviewgraph/finalization.py`.

## Contracts To Preserve

- Dry-run remains the default behavior.
- Candidate payloads are not final payloads and are never writer input.
- Approval is item-level and only public `postable_finding` items may be approved.
- Missing approval, empty `approved_item_ids`, rejected approval, unknown approved IDs, local notes, suggested replies, suppressed findings, and clarification requests cannot release writer input.
- Suggested replies remain local-only even when the same run has approved findings.
- Writer reachability in later issues must require `post_enabled=true`, an `ApprovalDecision` with `approved=true`, and approved IDs that are public `review_body_item` postable finding items from the current posting plan.
- Final payload construction stays after approval preflight, actor/permission re-check, and target freshness re-check.
- No writer module should be imported or reachable in this issue.
- Default dry-run output should say no GitHub write is attempted in dry-run, and separately explain why no public payload was prepared when everything is local-only.

## Implementation Shape

1. Add a focused no-approved-findings harness in `tests/test_no_approved_findings.py`:
   - empty `approved_item_ids` fails at the approval-proof/model layer or finalization preflight before payload builder and before writer reachability; do not introduce a parallel `approved_finding_ids` field.
   - missing approval is represented by a narrow pre-finalization guard or post-route preflight helper that accepts `approval=None` and fails before `finalize_github_payload(...)`; if no route consumes it yet, this helper is still the AUR-222 handoff contract.
   - rejected approval fails finalization preflight before current reads, payload builder, and writer reachability.
   - finalization preflight rejects approved IDs whose current object is not a `ClassifiedFinding` or whose current posting-plan item is not a public `review_body_item` `postable_finding`, even if the object happens to carry a `fingerprint` attribute.
   - direct negative cases should include approved IDs for a local note, suggested reply, suppressed output, clarification request, inline candidate, summary item, and malformed fingerprint-bearing object.
   - local-notes-only dry-run has `post_enabled=false`, no candidate payload preview, zero writer calls, and markdown explains no public payload was prepared.
   - suggested-reply-only dry-run has the same no-write proof and keeps the reply in local-only output.
   - suppressed-findings-only dry-run has no candidate payload preview, no writer call, and local-only posting-plan evidence.
   - clarification-only dry-run has no candidate payload preview, no writer call, and local-only posting-plan evidence.
   - mixed run with approved findings plus suggested reply keeps candidate payload/final approval proof restricted to the finding; suggested reply text must not enter candidate or final public payloads.
2. Add a named pure writer-release preflight helper for AUR-222 to consume before finalization:
   - Prefer a small surface such as `evaluate_writer_release_preflight(post_enabled, approval_result, posting_plan, current_items_by_id)`, where `approval_result` is the single canonical input: an `ApprovalDecisionBuildResult`, an `ApprovalDecision`, or `None`.
   - `current_items_by_id` is a body-free resolver map keyed by posting-plan item ID. It may contain current typed source objects (`ClassifiedFinding`, `LocalNote`, `SuggestedReply`, `ClarificationRequest`, or suppressed-output records) or a small typed descriptor, but the posting plan is authoritative for unknown IDs, destination, source classification, and public eligibility.
   - It returns a typed `WriterReleasePreflightResult` recorded on `ReviewState.writer_release_preflight`.
   - Result shape: `status`, `reason_code`, `approved_item_ids`, `approved_finding_ids` absent, `nested_reason_code`, `nested_actor_permission_reason_code`, `item_diagnostics`, `eligible_for_finalization`, `writer_input_released`, `final_payload_hash=None`, `writer_result=None`, and no body text.
   - Pass shape: `status=pass`, `eligible_for_finalization=true`, `writer_input_released=false` in AUR-223, no `reason_code`, `approved_item_ids` contains only approved public `review_body_item` postable finding IDs, `item_diagnostics` is empty, and local-only suggested replies remain excluded.
   - Failure shape: `status=fail`, `approved_item_ids=()`, no final payload/hash/writer result, and stable no-release reason.
   - Reason precedence: `post_disabled` first; then `approval_build_failed` for failed `ApprovalDecisionBuildResult` while preserving its nested reason; then `missing_approval`; then `rejected_approval`; then `empty_approval`; then duplicate approved IDs/fingerprints; then `unknown_approved_id`; then `non_public_approved_item`; then `no_public_approved_findings`.
   - It returns stable no-release evidence with explicit reason codes: `post_disabled`, `approval_build_failed`, `missing_approval`, `rejected_approval`, `empty_approval`, `duplicate_approved_item`, `duplicate_approved_fingerprint`, `unknown_approved_id`, `non_public_approved_item`, and `no_public_approved_findings`.
   - Item diagnostics are body-free and may include only item ID, destination, source classification, `public_payload_eligible`, and reason.
   - It does not call `finalize_github_payload(...)`, current actor/permission probes, target freshness probes, final payload builders, marker reconciliation, or writer code when it fails.
3. Tighten finalization preflight evidence if needed:
   - Preserve approval preflight as the first check inside `finalize_github_payload(...)`.
   - Mandatory: pass the current `PostingPlan` or a smaller typed approved-item resolver into finalization preflight so approved IDs are checked against current posting-plan public eligibility, not only object presence and `fingerprint`.
   - Return stable dry-run/preflight evidence for missing, empty, rejected, failed-proof, unknown, or non-public approval.
   - Keep `final_payload_builder_calls=0`, `writer_input_released=false`, `final_payload=None`, no final payload hash, no writer result, and a structured reason code for all preflight failures.
   - Do not import writer, GitHub transport, CLI, graph post-mode, marker scanning, or ambient process state.
4. Improve render/dry-run explanation:
   - When `candidate_payload_preview` is absent because all items are local-only or no public findings are eligible, markdown should say dry-run never attempts a GitHub write and no public GitHub payload was prepared because no public postable finding items are eligible.
   - Do not label other fail-closed states as "no public findings" when postable findings exist but are blocked by clarification, required reviewer failure, read gaps, or another graph error.
   - Make the explanation cause-aware from posting-plan public eligibility plus graph errors/clarification/read-gap state, not merely `candidate_payload is None`.
   - Expose the machine-readable reason under top-level `writer_release_preflight` in dry-run/post-attempt JSON when the helper is evaluated; render metadata can mirror it, but AUR-222 should consume the top-level key.
   - Normal dry-run runs with public candidate findings do not evaluate `writer_release_preflight`; local-only dry-run runs expose a separate top-level `public_payload_preparation` reason, such as `no_public_postable_items`, so no-public-payload evidence is not collapsed into `missing_approval` or `post_disabled`.
   - Direct writer-release preflight tests use `post_enabled=true` when exercising no-public-approved-item reasons; `post_enabled=false` tests assert the separate `post_disabled` precedence.
5. Update narrow durable docs:
   - `docs/architecture/side-effects.md` for no-approved/local-only writer suppression.
   - Correct stale durable approval terminology from `approved_finding_ids` to the implemented item-level `approved_item_ids`; do not add an alias or compatibility field.
   - `docs/architecture/state-graph.md` is mandatory because `ReviewState.writer_release_preflight` is a state-shape change.
   - `docs/harnesses/harness-engineering.md` for the focused no-approved-findings harness.

## Focused Harness

Create `tests/test_no_approved_findings.py` covering:

- Empty approval cannot invoke payload builder or release writer input.
- Missing approval cannot enter finalization or release writer input.
- Rejected approval cannot invoke payload builder or release writer input.
- Failed approval proof cannot enter finalization or release writer input.
- `post_enabled=false` cannot enter finalization or release writer input.
- A positive writer-release preflight case passes only approved public finding IDs and excludes local-only suggested replies.
- The named writer-release preflight helper returns specific machine reasons for `post_disabled`, `approval_build_failed`, `missing_approval`, `rejected_approval`, `empty_approval`, `duplicate_approved_item`, `duplicate_approved_fingerprint`, `unknown_approved_id`, `non_public_approved_item`, and `no_public_approved_findings`.
- Failed approval-build preflight preserves nested reason metadata without reinterpreting it.
- Non-public approved IDs for local notes, suggested replies, suppressed outputs, clarification requests, inline candidates, summary items, and malformed fingerprint-bearing objects fail finalization preflight before current reads, payload builder, or writer release.
- Preflight-failed cases expose stable structured no-release evidence: no final payload, no final payload hash, no writer result, `writer_input_released=false`, and a no-public-approved-findings or approval-preflight reason code.
- Passing writer-release preflight in AUR-223 means eligible for finalization only; it still has `writer_input_released=false`.
- Local-notes-only dry-run calls no writer and produces no candidate payload.
- Suggested-reply-only dry-run calls no writer, produces no candidate payload, and keeps the reply local-only.
- Suppressed-findings-only dry-run calls no writer and produces no candidate payload.
- Clarification-only dry-run calls no writer and produces no candidate payload.
- Mixed finding plus suggested reply run keeps suggested reply text out of candidate payload body and approval final body.
- Dry-run markdown explains why no public payload was prepared for local-only/no-post runs.
- Dry-run JSON exposes top-level `public_payload_preparation` for local-only/no-public-payload explanations. `writer_release_preflight` is absent for normal dry-run candidate runs and present only when explicitly evaluated by the harness/post-route preflight.
- Dry-run markdown does not mislabel postable findings blocked by clarification or graph errors as "no public findings."
- Import-boundary proof: any touched no-approved/finalization code does not import writer, GitHub transport, live network clients, `os`, `subprocess`, or ambient stdin.

Update existing tests only when they already own the exact behavior:

- `tests/test_target_freshness.py` if finalization preflight evidence changes.
- `tests/test_cli.py` if dry-run markdown additions affect existing expectations.

## Validation

Focused:

```bash
python -m pytest tests/test_no_approved_findings.py -q
```

Regression:

```bash
python -m pytest tests/test_no_approved_findings.py tests/test_approval.py tests/test_target_freshness.py tests/test_cli.py tests/test_clarification.py tests/test_quality_testing.py tests/test_render.py tests/test_posting.py tests/test_payload_validation.py tests/test_models.py tests/test_contract_boundaries.py tests/test_non_interactive_posting.py -q
python scripts/check_docs.py
git diff --check
python -m py_compile src/reviewgraph/*.py
```

Run the full suite because this issue touches render/finalization side-effect safety contracts:

```bash
python -m pytest -q
```

## Out Of Scope

- Fake top-level comment writer.
- Real writer adapter.
- Live GitHub writes.
- Adding `reviewgraph.writer`, `writer_fake`, GitHub writer transport, or a fake-writer graph route.
- Public CLI `--post`.
- Posting non-finding, local note, suggested reply, suppressed, or clarification content.
- Approval UI or human prompt flow.
- Marker scan/reconciliation changes beyond preserving existing no-writer state.
