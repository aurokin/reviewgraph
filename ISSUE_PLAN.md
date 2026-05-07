# ISSUE PLAN: AUR-220 Fail Closed On Stale Review Target

Active issue plan for `AUR-220` / `RG-031: Fail Closed On Stale Review Target`.

Linear is the durable source for status, blockers, and handoff. Durable behavior comes from `docs/architecture/side-effects.md`, `docs/architecture/state-graph.md`, `docs/architecture/github-integration.md`, and `docs/harnesses/harness-engineering.md`.

## Linear Snapshot

- Project: `ReviewGraph`
- Team: `Aurokin`
- Milestone: `PRD 0007: Side Effects`
- Issue: `AUR-220`
- Title: `RG-031: Fail Closed On Stale Review Target`
- Status when planned: `In Progress`
- Linear comments fetched on 2026-05-07: none
- Upstream blockers complete: `AUR-244`, `AUR-218`, `AUR-217`, `AUR-219`, and `AUR-243`.

## Objective

Add a target-freshness finalization gate so ReviewGraph can prove the PR target has not changed since approval before any final payload construction or writer reachability.

This is still a harness-first side-effect slice. It does not implement live GitHub refetch, marker reconciliation, graph post-mode routing, fake writer, real writer, or any GitHub mutation. It must, however, add a minimal `finalize_github_payload` orchestration surface that consumes actor/permission and target freshness preflights, fails closed with dry-run/finalization evidence, and proves no writer input can be released before the full finalization contract exists.

## Contracts To Preserve

- Dry-run remains the default behavior and must not invoke a writer.
- The freshness check is bound to the approved `ReviewTarget`, not merely a head SHA string.
- Current target proof must include owner/repo, PR number, base SHA, head SHA, merge-base SHA, diff basis, checked-at time, endpoint kind, check method, and redacted transport summary.
- Changed head SHA blocks writer reachability.
- Changed base SHA, merge-base SHA, or diff basis blocks writer reachability.
- Owner/repo or PR-number mismatch blocks writer reachability.
- Timeout, rate limit, forbidden, not found, unavailable service, malformed response, stale cached target proof, missing checked-at, or unknown freshness fails closed with stable machine reason, retryability, and request ID when available.
- Cached success cannot substitute for a current target check. The helper must accept a raw fake target probe plus explicit `evaluated_at`, then evaluate freshness itself.
- Target freshness must be checked after approval. The helper must accept `ApprovalDecision` or an explicit approved-at timestamp, validate that timestamp, and reject target proofs whose `checked_at` predates approval even if the proof is otherwise fresh by max-age.
- Unknown freshness fails before final payload construction and before writer reachability.
- A passing target-freshness preflight does not by itself mean the final payload is finalized. `finalize_github_payload` must still validate approval shape, approved IDs, non-empty approved findings, duplicate approved fingerprints, actor/permission preflight, final payload hash, redaction, and later marker reconciliation before writer input can be released.
- Marker reconciliation remains deferred, so AUR-220 must not set `FinalizationState.FINALIZED`, `final_github_payload`, `final_payload_hash`, or a writer-input release object on the fresh-target path.
- The writer adapter, once it exists, receives only already-finalized payloads. AUR-220 proves this with a fake writer-input sentinel: stale/unknown target freshness calls the final payload builder zero times and releases no writer input; fresh matching target can advance to a `preflight_passed_marker_reconciliation_deferred` state but still releases no writer input.

## Implementation Shape

1. Add target-freshness model contracts in `src/reviewgraph/models.py`:
   - `TargetFreshnessReasonCode`
   - `TargetFreshnessTransportSummary`
   - `TargetFreshnessCheckResult`
2. Add a dedicated `ReviewState` field such as `target_freshness_check: TargetFreshnessCheckResult | None`.
3. Add `TargetFreshnessProbeResult` and `validate_target_freshness_for_finalization(...)` in `src/reviewgraph/finalization.py` or a small pure module if that keeps boundaries clearer.
4. The helper owns fake-probe evaluation:
   - accepts raw `TargetFreshnessProbeResult`
   - accepts `ApprovalDecision` or approved target plus explicit approved-at timestamp
   - accepts explicit `evaluated_at`
   - accepts deterministic max proof age policy
   - does not accept an already-passing freshness result as enough proof
5. Target freshness pass requires:
   - probe status/evidence is current and well-formed
   - current `ReviewTarget` exactly equals the approved target across owner/repo, PR number, base SHA, head SHA, merge-base SHA, and diff basis
   - approved and current merge-base SHA are known in post/finalization mode; `None` merge-base freshness is unknown and fails closed in AUR-220
   - checked-at is UTC RFC3339 with trailing `Z`
   - checked-at is fresh relative to `evaluated_at`
   - checked-at is greater than or equal to the approval timestamp
   - transport summary is redacted and present
6. Target freshness failure result:
   - uses stable reason code
   - includes retryability classification
   - includes redacted transport summary and request ID when available
   - includes allowlisted mismatched fields for target drift
   - carries no final payload, final payload hash, marker reconciliation, or writer result
7. `GateStatus.UNKNOWN` is invalid for target freshness results and must be rejected or normalized to fail before state.
8. Raw unknown or missing-current-proof input must return a structured fail-closed `TargetFreshnessCheckResult(status=fail, reason_code=unknown_freshness, retryable=...)`; it must not crash or rely on an uncaught model constructor error.
9. `TargetFreshnessTransportSummary` must have model-level allowlisting comparable to actor/permission summaries: endpoint-kind constants, pass/fail reason consistency, retryability consistency, request-ID character and secret filtering, and no fields for raw stderr, raw bodies, request headers, or tokens.
10. Add or expand `FinalizationStatus` with stable finalization reason codes so target freshness failures have structured finalization evidence:
   - `target_freshness_failed`
   - `actor_permission_failed` if the composed actor/permission preflight fails
   - `approval_preflight_failed` for invalid approved IDs, empty approvals, unknown approved IDs, or duplicate approved fingerprints before any current reads
   - `payload_validation_failed` for final payload/hash/redaction validation failures in this minimal orchestrator
   - `marker_reconciliation_deferred` or `preflight_passed_marker_reconciliation_deferred` for the fresh target path that cannot become fully finalized yet
11. Add `finalize_github_payload(...)` in `src/reviewgraph/finalization.py`:
   - validates approved decision shape, approved IDs, non-empty approved findings, unknown approved IDs, and duplicate approved fingerprints before any current actor/permission or target freshness reads
   - runs actor/permission finalization preflight from AUR-243
   - runs target freshness preflight from AUR-220
   - fails closed before final payload construction when either preflight fails
   - records `target_freshness_check`, `actor_permission_finalization_check`, `finalization_status`, and a dry-run/error evidence shape for stale target
   - may call a deterministic final payload preview/builder only after approval shape, approved ID preflight, actor/permission, and target freshness pass
   - validates the preview hash against `approval.approved_final_payload_hash` if it constructs a preview
   - returns a non-finalized `marker_reconciliation_deferred` result on the fresh path; no writer input is released until AUR-221/AUR-245 marker reconciliation exists
12. The dry-run/failure evidence shape must expose stale target reason code, retryability, endpoint kind, request ID when available, and mismatched fields without raw response bodies, headers, tokens, stderr, or unredacted payloads.
13. Keep `src/reviewgraph/finalization.py` pure: no live GitHub client, shell, subprocess, writer, graph post mode, marker reconciliation, or environment reads.
14. Update narrow durable docs with the target-freshness result shape, the minimal finalization gate, and its position after actor/permission preflight and before final payload construction.

## Reason Codes

Target freshness failures should include at least:

- `target_mismatch`
- `missing_merge_base`
- `missing_checked_at`
- `stale_cached_target`
- `future_checked_at`
- `checked_at_before_approval`
- `unknown_freshness`
- `timeout`
- `rate_limited`
- `forbidden`
- `not_found`
- `unavailable`
- `malformed_response`

Retryable target freshness failures are `timeout`, `rate_limited`, `unavailable`, and raw `unknown_freshness` only when the fake probe explicitly marks the unknown proof as retryable. Permission/visibility failures, malformed responses, missing timestamps, future timestamps, checked-at regression before approval, stale cache, missing merge-base, and target mismatch are fail-closed non-retryable by default.

## Focused Harness

Create `tests/test_target_freshness.py` covering:

- Fresh matching target passes with redacted transport summary.
- Changed head SHA fails closed.
- Changed base SHA fails closed.
- Changed merge-base SHA fails closed.
- Missing or unknown approved/current merge-base freshness fails closed.
- Changed diff basis fails closed.
- Changed owner/repo fails closed.
- Changed PR number fails closed.
- Missing checked-at fails closed.
- Malformed checked-at fails closed.
- Stale cached target proof fails closed.
- Future checked-at outside allowed skew fails closed.
- Checked-at before approval timestamp fails closed even when otherwise fresh by max-age.
- Raw unknown/no-current-proof input returns structured fail-closed output with `unknown_freshness`.
- Timeout, rate limit, forbidden, not found, unavailable, and malformed response fail closed with stable reason code, retryability, endpoint kind, and request ID when available.
- `GateStatus.UNKNOWN` is rejected for target freshness result construction, while raw unknown probe input is normalized into structured fail-closed output.
- Transport summary model tests prove endpoint kind, reason-code/retryability consistency, request ID allowlisting, and secret-like request ID rejection.
- Current raw probe evaluation is owned by the helper; there is no API path that accepts a cached passing freshness result as sufficient.
- Stale/unknown target freshness prevents the final payload builder from being called.
- Stale/unknown target freshness records `target_freshness_check`, `finalization_status`, and dry-run/error evidence with stable code, retryability, endpoint kind, request ID, and mismatched fields.
- Passing target freshness alone does not create marker reconciliation or writer state.
- Invalid approved IDs, empty approvals, unknown approved IDs, and duplicate approved fingerprints fail before current actor/permission or target freshness probes are evaluated.
- Fresh matching target plus passing actor/permission preflight produces a non-finalized `marker_reconciliation_deferred` / `preflight_passed_marker_reconciliation_deferred` result, not `FinalizationState.FINALIZED`.
- The fake writer-input sentinel proves writer input is not released by AUR-220 even on the fresh target path because marker reconciliation is not implemented yet; no writer adapter or GitHub mutation is introduced.
- Failing target freshness serializes enough diagnostic context for dry-run/state consumers without raw response bodies, request headers, tokens, raw stderr, or unredacted payloads.
- `src/reviewgraph/finalization.py` import-boundary proof: no live GitHub, shell/subprocess, graph post mode, writer, marker reconciliation, or live transport imports.

Update existing tests as needed:

- `tests/test_models.py` for target freshness model invariants and `ReviewState` field parity with `docs/architecture/state-graph.md`.
- `tests/test_actor_permission_binding.py` only if shared finalization module contracts move.
- `tests/test_github_fake_read.py` only if serialized dry-run/read target evidence changes.

## Validation

Focused:

```bash
python -m pytest tests/test_target_freshness.py -q
```

Regression:

```bash
python -m pytest tests/test_target_freshness.py tests/test_actor_permission_binding.py tests/test_approval.py tests/test_models.py tests/test_permissions.py tests/test_github_fake_read.py tests/test_redaction.py tests/test_cli.py -q
python scripts/check_docs.py
git diff --check
python -m py_compile src/reviewgraph/*.py
```

Run the full suite because this issue touches shared side-effect models and finalization preflight state:

```bash
python -m pytest -q
```

## Out Of Scope

- Live GitHub target re-fetch implementation.
- Marker generation/parsing/reconciliation.
- Non-interactive post-mode gate.
- Fake writer, real writer, manual live post smoke, or any GitHub mutation.
