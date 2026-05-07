# ISSUE PLAN: AUR-219 Gate Posting On Actor And Permission

Active issue plan for `AUR-219` / `RG-030: Gate Posting On Actor And Permission`.

Linear is the durable source for status, blockers, and handoff. Durable behavior comes from `docs/architecture/side-effects.md`, `docs/architecture/state-graph.md`, `docs/architecture/github-integration.md`, and `docs/harnesses/harness-engineering.md`.

## Linear Snapshot

- Project: `ReviewGraph`
- Team: `Aurokin`
- Milestone: `PRD 0007: Side Effects`
- Issue: `AUR-219`
- Title: `RG-030: Gate Posting On Actor And Permission`
- Status when planned: `In Progress`
- Linear comments fetched on 2026-05-07: none
- Upstream blockers complete: `AUR-244`, `AUR-218`, and `AUR-217`.

## Objective

Add a pure actor/permission gate contract and fake transport harness so later write-mode approval can show the authenticated GitHub identity and endpoint-specific issue-comment permission before human approval proceeds.

This issue does not implement final approval snapshot binding, pre-finalization re-checks, live target freshness refetch, writer adapters, live GitHub permission calls, post-mode CLI prompting, or graph writer reachability. It defines and tests the gate result and fake-transport discovery behavior that later approval/finalization slices must consume.

## Contracts To Preserve

- The gate is endpoint-specific for MVP top-level issue-comment posting: `POST /repos/{owner}/{repo}/issues/{pr_number}/comments`.
- A passing gate records authenticated actor, credential principal/source, broad repo permission or endpoint-specific permission, issue-comment endpoint write ability, check method, checked target, checked-at time, and redacted transport summary.
- Unknown actor blocks approval/posting.
- Unknown credential source blocks approval/posting.
- Unknown permission blocks approval/posting.
- Repo-level write/admin role is insufficient when the token/app lacks issue-comment write ability.
- Timeout, rate limit, forbidden, not found, unavailable service, malformed response, or stale cached proof blocks approval/posting with stable reason code and retryability.
- Transport summaries record endpoint kind, retryability, stable failure code, and request ID when available.
- Transport summaries must not log tokens, raw stderr, or unredacted response bodies.
- The gate result is included in dry-run/read output when present.
- Final approval snapshot persistence and finalization re-checks are deferred to `AUR-243`.
- Live target refetch/freshness proof is deferred to `AUR-220`; AUR-219 only verifies that the fake permission proof is bound to the same canonical `ReviewTarget` object supplied to the gate.
- No GitHub write, approval prompt, final payload construction, marker reconciliation, graph post-mode routing, or writer module becomes reachable in this issue.

## Stable Permission Reason Codes

The machine failure code set for this issue is:

- `unknown_actor`
- `unknown_credential_source`
- `unknown_permission`
- `insufficient_endpoint_permission`
- `missing_credential_principal`
- `missing_check_method`
- `missing_checked_target`
- `missing_checked_at`
- `target_mismatch`
- `timeout`
- `rate_limited`
- `forbidden`
- `not_found`
- `unavailable`
- `malformed_response`
- `stale_cached_proof`

`reason` remains a human-readable explanation. `reason_code` is the only machine-readable failure reason. A passing gate has `reason_code=None`.

Transport retryability is part of the fake transport result, not inferred from the human message. The canonical retryable failure codes in this issue are `timeout`, `rate_limited`, and `unavailable`. `forbidden`, `not_found`, `malformed_response`, stale proof, missing proof fields, target mismatch, unknown actor, unknown credential source, unknown permission, and insufficient endpoint permission are not retryable in the gate result unless a later live transport issue explicitly broadens that behavior.

Proof freshness is deterministic. Gate evaluation accepts an explicit `evaluated_at` timestamp and `max_proof_age_seconds` value, with `300` seconds as the default fake-harness policy. `checked_at` must be UTC RFC3339 with a trailing `Z`. Missing `checked_at` returns `missing_checked_at`; an unparsable or non-UTC timestamp returns `malformed_response`; `checked_at` older than the max age or more than 60 seconds in the future returns `stale_cached_proof`. The implementation must not call the wall clock directly.

Allowed proof vocabulary for this issue:

- `credential_source`: `pat`, `fine_grained_pat`, `github_app_installation`, or `github_app_user`. Missing or any other value returns `unknown_credential_source`.
- `repo_permission`: `read`, `triage`, `write`, `maintain`, or `admin` when known; `null` is allowed for fine-grained credentials that expose endpoint-specific repository permissions instead of a broad role.
- `installation_permission`: `issues:read`, `issues:write`, `pull_requests:read`, or `pull_requests:write` when `credential_source="github_app_installation"`; `null` is allowed for PAT and GitHub App user-token checks.
- `endpoint_permission`: normalized endpoint permission, either `issues:read`, `issues:write`, `pull_requests:read`, or `pull_requests:write` when known. For GitHub App installation tokens, this may mirror `installation_permission`, but `installation_permission` remains the source of truth. `null` is allowed only when a broad repo permission or GitHub App installation permission proves write access.
- `permission`: output-only compatibility summary derived by the gate as `repo_permission` when present, otherwise `installation_permission` when present, otherwise `endpoint_permission`. Fake transport input must not provide `permission`; this avoids accepting contradictory precomputed summaries.
- `endpoint_kind`: `issue_comment`.
- `endpoint_method`: `POST`.
- `check_method`: `fake_issue_comment_permission_probe`.

Passing gates require a known credential source, non-empty credential principal, derived compatibility permission, `issue_comment_write=true`, `endpoint_method="POST"`, `endpoint_kind="issue_comment"`, the expected endpoint path, canonical target equality, and a fresh checked-at timestamp. Endpoint authorization follows GitHub's current `Create an issue comment` permission rule: a broad repo `write`/`maintain`/`admin` role, `installation_permission="issues:write"`, `installation_permission="pull_requests:write"`, `endpoint_permission="issues:write"`, or `endpoint_permission="pull_requests:write"` can satisfy the display permission requirement, but broad permission is still insufficient without `issue_comment_write=true`. GitHub App installation pass goldens may use `installation_permission` as the compatibility source without duplicating it into `endpoint_permission`; GitHub App user-token and endpoint-only fine-grained PAT pass goldens use `installation_permission=null` and `endpoint_permission` as the compatibility source. Read-only endpoint permissions and missing derivable permission summaries fail closed with `unknown_permission` or `insufficient_endpoint_permission` as appropriate.

Actor-permission evaluation never returns or serializes `GateStatus.UNKNOWN`. Passing gates require `reason_code=None`; every failing gate requires one of the AUR-219 reason codes above.

## Serialized Gate Shape

`GitHubReadResult.to_dict()` must serialize the actor/permission gate with this exact top-level shape when present:

```json
{
  "status": "pass",
  "actor": "reviewgraph-bot",
  "permission": "write",
  "checked_at": "2026-05-07T00:00:00Z",
  "reason": null,
  "reason_code": null,
  "credential_principal": "gh-user:reviewgraph-bot",
  "credential_source": "pat",
  "repo_permission": "write",
  "installation_permission": null,
  "endpoint_permission": null,
  "issue_comment_write": true,
  "check_method": "fake_issue_comment_permission_probe",
  "endpoint_method": "POST",
  "checked_target": {
    "owner_repo": "example/repo",
    "pr_number": 42,
    "base_sha": "base",
    "head_sha": "head",
    "merge_base_sha": "merge-base",
    "diff_basis": "merge_base"
  },
  "checked_target_hash": "<sha256>",
  "endpoint": "/repos/example/repo/issues/42/comments",
  "endpoint_kind": "issue_comment",
  "transport_summary": {
    "endpoint_kind": "issue_comment_permission",
    "retryable": false,
    "reason_code": null,
    "request_id": "REQ-123"
  }
}
```

Failing gates use the same object shape. They set `status="fail"`, set `reason_code` to one of the stable codes above, preserve any safe known fields, and set unsafe or unknown proof fields to `null`. `transport_summary.reason_code` matches the transport failure code for transport failures and is `null` for local proof-validation failures such as missing actor, missing checked target, or endpoint permission insufficiency. This issue records one already-redacted transport summary per gate result.

Compatibility fields keep their current meaning:

- `actor` is the authenticated GitHub actor shown to the human.
- `permission` is the legacy display summary derived as `repo_permission`, otherwise `installation_permission`, otherwise `endpoint_permission`.
- `checked_at` is the proof timestamp shown to the human.

Endpoint-specific proof lives in the explicit fields:

- `credential_principal`
- `credential_source`
- `repo_permission`
- `installation_permission`
- `endpoint_permission`
- `issue_comment_write`
- `check_method`
- `endpoint_method`
- `checked_target`
- `checked_target_hash`
- `endpoint`
- `endpoint_kind`

`checked_target` serializes the full `ReviewTarget.to_ordered_dict()` value verbatim, and `checked_target_hash` is exactly `ReviewTarget.target_hash()`. AUR-219 requires the permission proof target to equal the expected `ReviewTarget` across owner/repo, PR number, base SHA, head SHA, merge-base SHA, and diff basis. This is target binding, not live freshness: the gate does not refetch GitHub refs or prove the expected target is current. Live ref freshness remains deferred to `AUR-220`.

`ActorPermissionGateResult` must remain source-compatible for existing positional construction of the legacy fields. New fields should be keyword-only/defaulted or all existing call sites must be explicitly migrated in the implementation commit.

`ActorPermissionTransportSummary` is an allowlisted, already-redacted data structure. It must not accept or carry raw request headers, tokens, raw stderr, or unredacted response bodies. Tests must prove it preserves endpoint kind, retryability, reason code, and request ID while rejecting or omitting raw secret-bearing surfaces. The gate-level `endpoint_kind` describes the target artifact (`issue_comment`); `transport_summary.endpoint_kind` describes the permission probe transport (`issue_comment_permission`).

## Implementation Shape

1. Add or expand typed model contracts in `src/reviewgraph/models.py` while keeping it a leaf module:
   - `ActorPermissionReasonCode`
   - `GitHubCredentialSource` or string-constrained source field
   - `ActorPermissionTransportSummary`
   - richer `ActorPermissionGateResult`
2. Preserve existing serialized fields (`status`, `actor`, `permission`, `checked_at`, `reason`) for compatibility, and add endpoint-specific fields without breaking current read serialization tests.
3. Add `src/reviewgraph/permissions.py` as a pure/fake-discovery module. It may define protocol-like fake input/result dataclasses but must not import live GitHub clients, shell, subprocess, writer, finalization, approval, or graph post mode.
4. Gate evaluation should accept explicit fake transport result data and expected `ReviewTarget`; it should not call network or inspect environment.
5. Passing gate requires:
   - actor,
   - credential principal,
   - credential source,
   - broad repo permission, GitHub App installation permission, or endpoint permission,
   - `issue_comment_write=true`,
   - check method,
   - `endpoint_method="POST"`,
   - checked target matching the full expected `ReviewTarget`,
   - checked-at time.
6. Failing gate returns `GateStatus.FAIL`, stable reason code, no approval-pass proof, and a redacted transport summary.
7. Include a dry-run/read serialization update so `GitHubReadResult.to_dict()` includes the richer actor/permission gate when present.
8. Add `tests/test_permissions.py` for:
   - passing endpoint-specific gate,
   - unknown actor,
   - unknown credential source,
   - unknown permission,
   - `GateStatus.UNKNOWN` rejected or normalized to fail before serialization,
   - missing credential principal,
   - missing check method,
   - missing checked target,
   - missing checked-at time,
   - repo-role-write but missing issue-comment write ability,
   - PAT broad `read`/`triage` failures and `maintain`/`admin` passes,
   - fine-grained PAT, GitHub App installation-token, and GitHub App user-token `issues:write` and `pull_requests:write` passes,
   - fine-grained PAT, GitHub App installation-token, and GitHub App user-token `issues:read` and `pull_requests:read` failures,
   - output-only compatibility `permission` derivation from repo, installation, and endpoint permissions,
   - timeout, rate limit, forbidden, not found, unavailable, malformed response, and stale cached proof,
   - invalid checked-at timestamp and future checked-at timestamp,
   - redacted summaries exclude tokens/raw stderr/response bodies while preserving endpoint kind, reason code, request ID, and retryability,
   - checked target owner/repo, PR number, SHA, merge-base, or diff-basis mismatch fails closed with `target_mismatch`,
   - endpoint method/path/kind mismatch fails closed with `target_mismatch`,
   - post-mode graph/CLI routing remains untouched and writer modules remain unreachable,
   - module import-boundary proof.
9. Update existing `tests/test_github_fake_read.py` serialization expectations with whole-object pass/fail goldens for the enriched gate shape.
10. Update narrow durable docs with the actor/permission result shape, failure taxonomy, proof freshness policy, and fake-harness scope introduced by this issue.

## Validation

Focused:

```bash
python -m pytest tests/test_permissions.py -q
```

Regression:

```bash
python -m pytest tests/test_permissions.py tests/test_models.py tests/test_github_fake_read.py tests/test_redaction.py tests/test_cli.py -q
python scripts/check_docs.py
git diff --check
python -m py_compile src/reviewgraph/*.py
```

Run the full suite because the gate result touches shared models and GitHub read serialization.

## Out Of Scope

- Approval snapshot persistence or actor/permission binding into `ApprovalProofResult` (`AUR-243`).
- Pre-finalization actor/permission re-checks (`AUR-243`).
- Live target refetch/freshness (`AUR-220`).
- Non-interactive post-mode gate (`AUR-246`).
- Fake writer, real writer, live post smoke, or any GitHub mutation.
