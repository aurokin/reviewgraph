# ISSUE PLAN: AUR-243 Bind Approval To Actor And Permission Snapshot

Active issue plan for `AUR-243` / `RG-054: Bind Approval To Actor And Permission Snapshot`.

Linear is the durable source for status, blockers, and handoff. Durable behavior comes from `docs/architecture/side-effects.md`, `docs/architecture/state-graph.md`, `docs/architecture/github-integration.md`, and `docs/harnesses/harness-engineering.md`.

## Linear Snapshot

- Project: `ReviewGraph`
- Team: `Aurokin`
- Milestone: `PRD 0007: Side Effects`
- Issue: `AUR-243`
- Title: `RG-054: Bind Approval To Actor And Permission Snapshot`
- Status when planned: `In Progress`
- Linear comments fetched on 2026-05-07: none
- Upstream blockers complete: `AUR-244`, `AUR-218`, `AUR-217`, and `AUR-219`.

## Objective

Bind item-level human approval to the exact actor/permission gate snapshot shown before approval, then add a pure finalization preflight that re-evaluates the current actor/permission proof immediately before final payload construction can happen.

This issue is still a harness-first pre-writer slice. It does not implement live GitHub permission calls, live target freshness refetch, marker reconciliation, post-mode CLI prompting, graph post-mode routing, fake writer, real writer, or any GitHub mutation. It creates the approval binding and final actor/permission re-check contracts that later target freshness, marker, and writer slices must consume.

## Contracts To Preserve

- Dry-run remains the default behavior and must not invoke a writer.
- Approval can pass only when the pre-approval `ActorPermissionGateResult` has `status=pass`.
- Approval stores the approved actor, credential principal, credential source, compatibility permission, repo/installation/endpoint permission fields, issue-comment write proof, checked-at time, checked target, checked target hash, endpoint, endpoint kind, check method, and review target.
- Unknown actor, unknown credential source, unknown permission, insufficient endpoint permission, missing checked-at time, stale cached proof, or any AUR-219 transport failure blocks approval/posting.
- Finalization re-checks actor/permission from a current probe and fails closed if the current proof is absent, failed, stale, or does not exactly match the approved snapshot.
- If current actor changes after approval, finalization fails closed even when the new actor has permission.
- If current credential source, credential principal, compatibility permission, repo/installation/endpoint permission, endpoint write ability, checked target, endpoint, endpoint kind, endpoint method, or check method changes after approval, finalization fails closed.
- Cached success cannot substitute for an unknown or failed current check. The finalization API must accept a raw current `ActorPermissionProbeResult`, expected target, `evaluated_at`, and max-age policy, then call `evaluate_actor_permission_gate` itself. It must not accept a caller-supplied passing `ActorPermissionGateResult` as enough proof of current permission.
- Current proof `checked_at` must be greater than or equal to the approved snapshot `approved_permission_checked_at`. A current proof that is otherwise fresh by max-age but older than the approved proof fails closed.
- Final re-check failures reuse AUR-219 `ActorPermissionReasonCode` taxonomy and redacted `ActorPermissionTransportSummary` semantics.
- A failed finalization must not build a final payload, set a final payload hash, reconcile markers, or make a writer reachable.
- Target freshness is intentionally deferred to `AUR-220`; this issue only verifies that actor/permission proof is bound to the approved `ReviewTarget`.

## Implementation Shape

1. Expand `ApprovalDecision` in `src/reviewgraph/models.py` to carry the endpoint-specific actor/permission snapshot from AUR-219:
   - `approved_credential_principal`
   - `approved_credential_source`
   - `approved_repo_permission`
   - `approved_installation_permission`
   - `approved_endpoint_permission`
   - `approved_issue_comment_write`
   - `approved_permission_check_method`
   - `approved_permission_endpoint_method`
   - `approved_permission_checked_target`
   - `approved_permission_checked_target_hash`
   - `approved_permission_endpoint`
   - `approved_permission_endpoint_kind`
   - `approved_permission_transport_summary`
2. Keep existing `ApprovalDecision` fields source-compatible where practical. If the model must become stricter, update all call sites and model tests in the same commit.
3. Keep `build_approval_proof(...)` payload/hash-only. It must continue to return `ApprovalProofResult` for approved item IDs, final body hash, marker hash, findings hash, redaction proof, approver, and timestamp. Do not make `ApprovalProofResult` carry side-effect actor/permission state.
4. Add a small pure helper such as `build_approval_decision(proof, actor_permission_gate, ...)` in `src/reviewgraph/approval.py`. This is the only approval-time binding point for `ApprovalDecision`; it consumes a passing `ApprovalProofResult` and a passing actor/permission gate and copies the immutable approval snapshot.
5. Add `ApprovalDecisionBuildResult` and `ApprovalDecisionBuildReasonCode` or equivalent so approval-time actor/permission failures have a stable machine reason without mixing side-effect authorization failures into `ApprovalProofResult` / `ApprovalProofReasonCode`. Minimum reason codes:
   - `approval_proof_failed`
   - `actor_permission_gate_failed`
   - `actor_permission_target_mismatch`
6. Propagate the failing gate's redacted transport summary through the approval-decision build result only as diagnostics if the model shape supports it; do not copy secret-bearing text into reasons. `build_approval_proof` must never emit actor/permission failure codes.
7. Add `ActorPermissionFinalizationCheckResult` and `ActorPermissionFinalizationReasonCode` or equivalent in `src/reviewgraph/models.py`. This is an actor/permission preflight result, not full payload finalization. Minimum fields:
   - `status: GateStatus`
   - `reason_code`
   - `actor_permission_reason_code` when the current gate itself failed with an AUR-219 code
   - `actor_permission_transport_summary`
   - `current_actor_permission_checked_at`
   - allowlisted `mismatched_fields`
   - no final payload, final payload hash, marker reconciliation, or writer result fields
   - `GateStatus.UNKNOWN` is invalid and must be rejected at construction or normalized to a failed-closed result before it reaches state.
8. Add the new result to `ReviewState` as an explicit field such as `actor_permission_finalization_check`. Do not overload `finalization_status` for this preflight pass. Later AUR-220/finalization work may compose this check into full `FinalizationStatus`.
9. Add `ActorPermissionFinalizationReasonCode` values for at least:
   - `actor_permission_gate_failed`
   - `actor_permission_snapshot_mismatch`
   - `actor_permission_checked_at_regressed`
10. Add `src/reviewgraph/finalization.py` as a pure pre-writer module:
   - `validate_actor_permission_snapshot_for_finalization(approval, current_probe, expected_target, evaluated_at, max_proof_age_seconds=...)` or equivalent.
   - the helper owns the call to `evaluate_actor_permission_gate` so tests cannot satisfy finalization with a cached passing gate.
   - the helper returns `ActorPermissionFinalizationCheckResult`.
   - a passing actor/permission check means only that the actor/permission preflight passed; it must not set `FinalizationState.FINALIZED`, `final_github_payload`, `final_payload_hash`, marker reconciliation, or writer reachability.
   - no imports of live GitHub clients, shell, subprocess, writer, graph post mode, or marker reconciliation.
11. Prefer an immutable `ActorPermissionSnapshot` value object if it reduces duplicated field lists. The canonical comparison tuple is actor, credential principal, credential source, compatibility permission, repo permission, installation permission, endpoint permission, issue-comment write, check method, endpoint method, checked target, checked target hash, endpoint, and endpoint kind. `transport_summary` is diagnostic-only and must not participate in pass equality because request IDs can legitimately change across re-checks.
12. Approval building must reject a passing `ActorPermissionGateResult` if `checked_target`, `checked_target_hash`, endpoint path, or endpoint kind does not match the `review_target` being approved. `ApprovalDecision` direct construction should also reject internally inconsistent actor/permission snapshots where the fields are present in the model contract.
13. Actor/permission finalization check comparison must require exact equality for the canonical tuple above and require `current_gate.checked_at >= approval.approved_permission_checked_at`.
14. Failed actor/permission finalization checks should preserve a redacted transport summary from the current evaluated gate when available and expose a stable machine reason:
   - direct AUR-219 reason code for current gate failures,
   - actor/permission finalization-specific mismatch code for approved/current snapshot drift,
   - allowlisted `mismatched_fields` for actor, credential principal, credential source, permission, repo permission, installation permission, endpoint permission, issue-comment write, check method, endpoint method, checked target, checked target hash, endpoint, endpoint kind, or checked-at regression,
   - no secret-bearing fields in reasons or summaries.
15. Update `GitHubReadResult.to_dict()` or dry-run JSON only if needed to prove dry-run output still records the enriched actor/permission gate from AUR-219. Do not add a writer path.
16. Update narrow durable docs with the new approval snapshot shape and final actor/permission re-check semantics.

## Focused Harness

Create `tests/test_actor_permission_binding.py` covering:

- Approval decision stores approved actor, credential principal/source, compatibility permission, repo/installation/endpoint permission, issue-comment write ability, checked-at time, full checked target, endpoint, endpoint kind, method, check method, transport summary, and review target.
- `build_approval_proof` remains payload/hash-only; `build_approval_decision` owns actor/permission binding.
- Approval decision builder returns a typed failure result when `proof.status != pass` or `actor_permission_gate.status != pass`; permission failures do not use `ApprovalProofReasonCode`.
- Approval builder rejects a passing actor/permission gate whose checked target, checked target hash, endpoint, or endpoint kind does not match the approval review target.
- Direct `ApprovalDecision` construction rejects internally inconsistent actor/permission snapshot fields where practical, including mismatched target hash/target object, incompatible endpoint/target, invalid endpoint kind/method, missing write proof, invalid status-like values, and unsafe identity fields.
- `ActorPermissionFinalizationCheckResult` rejects `GateStatus.UNKNOWN` and requires pass/fail-only semantics.
- Positive actor/permission finalization check: exact current snapshot with `checked_at >= approved_permission_checked_at` returns pass evidence and no mismatched fields.
- Positive actor/permission finalization check with a different current transport request ID proves transport metadata is diagnostic-only and not part of snapshot equality.
- Unknown actor, unknown credential source, unknown permission, insufficient endpoint permission, missing checked-at time, malformed response, stale cached proof, timeout, rate limit, forbidden, not found, and unavailable current gates block approval/finalization.
- Finalization helper owns current proof evaluation from `ActorPermissionProbeResult`, `expected_target`, and `evaluated_at`; tests must prove passing an old approved gate object is not an available API path.
- Current actor mismatch fails closed even if the current gate has write permission.
- Current credential principal mismatch fails closed.
- Current credential source mismatch fails closed.
- Current derived compatibility permission (`approved_permission`) mismatch fails closed, even if one of the lower-level permission fields still appears write-capable.
- Current repo/installation/endpoint permission mismatch fails closed.
- Current `issue_comment_write=false` or failed gate blocks finalization.
- Current checked target, target hash, endpoint, endpoint kind, endpoint method, or check method mismatch fails closed.
- Current checked-at older than the approved checked-at fails closed even when the current proof is otherwise fresh by max-age.
- Cached approved success cannot be reused when current gate is missing, failed, or unknown.
- Actor/permission finalization check failures never return or imply a final payload hash, marker reconciliation, or writer reachability.
- Actor/permission finalization mismatch failures expose stable reason code plus allowlisted mismatched fields rather than overloading `target_mismatch` for actor or credential changes.
- Redacted transport summary preserves endpoint kind, retryability, reason code, and request ID while excluding tokens, raw stderr, and unredacted bodies.
- Failed actor/permission finalization checks serialize enough diagnostic context for dry-run/state consumers while excluding raw probe bodies, request headers, tokens, raw stderr, and unredacted response bodies.
- `src/reviewgraph/finalization.py` import-boundary proof: no live GitHub, shell/subprocess, graph post mode, writer, marker reconciliation, or live transport imports.

Update existing tests as needed:

- `tests/test_approval.py` for the new approval decision builder and failure cases.
- `tests/test_models.py` for stricter `ApprovalDecision` invariants and finalization result invariants.
- `tests/test_github_fake_read.py` only if dry-run/read actor-permission serialization changes.

## Validation

Focused:

```bash
python -m pytest tests/test_actor_permission_binding.py -q
```

Regression:

```bash
python -m pytest tests/test_actor_permission_binding.py tests/test_approval.py tests/test_models.py tests/test_permissions.py tests/test_github_fake_read.py tests/test_redaction.py tests/test_cli.py -q
python scripts/check_docs.py
git diff --check
python -m py_compile src/reviewgraph/*.py
```

Run the full suite because this issue touches shared side-effect models and approval contracts:

```bash
python -m pytest -q
```

## Out Of Scope

- Live GitHub actor/permission discovery.
- Target freshness re-fetch and target drift blocking (`AUR-220`).
- Marker generation/parsing/reconciliation beyond preserving existing approval marker hash behavior.
- Non-interactive post-mode gate (`AUR-246`).
- No-approved-finding writer suppression (`AUR-223`).
- Fake writer, real writer, manual live post smoke, or any GitHub mutation.
