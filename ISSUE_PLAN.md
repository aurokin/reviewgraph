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

Add a pure pre-approval actor/permission gate contract and fake transport harness so write mode can show the authenticated GitHub identity and endpoint-specific issue-comment permission before any human approval can proceed.

This issue does not implement final approval snapshot binding, pre-finalization re-checks, target freshness, writer adapters, live GitHub permission calls, post-mode CLI prompting, or graph writer reachability. It defines and tests the gate result and fake-transport discovery behavior that later approval/finalization slices must consume.

## Contracts To Preserve

- The gate is endpoint-specific for MVP top-level issue-comment posting: `POST /repos/{owner}/{repo}/issues/{pr_number}/comments`.
- A passing gate records authenticated actor, credential principal/source, repo or installation permission, issue-comment endpoint write ability, check method, checked target, checked-at time, and redacted transport summary.
- Unknown actor blocks approval/posting.
- Unknown credential source blocks approval/posting.
- Unknown permission blocks approval/posting.
- Repo-level write/admin role is insufficient when the token/app lacks issue-comment write ability.
- Timeout, rate limit, forbidden, not found, unavailable service, malformed response, or stale cached proof blocks approval/posting with stable reason code and retryability.
- Transport summaries record endpoint kind, retryability, stable failure code, and request ID when available.
- Transport summaries must not log tokens, raw stderr, or unredacted response bodies.
- The gate result is included in dry-run/read output when present.
- Final approval snapshot persistence and finalization re-checks are deferred to `AUR-243`.
- No GitHub write, approval prompt, final payload construction, marker reconciliation, or writer module becomes reachable in this issue.

## Stable Permission Reason Codes

The initial failure code set is:

- `unknown_actor`
- `unknown_credential_source`
- `unknown_permission`
- `insufficient_endpoint_permission`
- `timeout`
- `rate_limited`
- `forbidden`
- `not_found`
- `unavailable`
- `malformed_response`
- `stale_cached_proof`

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
   - repo or installation permission,
   - `issue_comment_write=true`,
   - check method,
   - checked target matching the expected target,
   - checked-at time.
6. Failing gate returns `GateStatus.FAIL`, stable reason code, no approval-pass proof, and a redacted transport summary.
7. Include a dry-run/read serialization update so `GitHubReadResult.to_dict()` includes the richer actor/permission gate when present.
8. Add `tests/test_permissions.py` for:
   - passing endpoint-specific gate,
   - unknown actor,
   - unknown credential source,
   - unknown permission,
   - repo-role-write but missing issue-comment write ability,
   - timeout, rate limit, forbidden, not found, unavailable, malformed response, and stale cached proof,
   - redacted summaries exclude tokens/raw stderr/response bodies while preserving request ID/retryability,
   - checked target mismatch fails closed,
   - module import-boundary proof.
9. Update existing `tests/test_github_fake_read.py` serialization expectations as needed.
10. Update narrow durable docs only if implementation clarifies the actor/permission result shape beyond current docs.

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
- Target freshness (`AUR-220`).
- Non-interactive post-mode gate (`AUR-246`).
- Fake writer, real writer, live post smoke, or any GitHub mutation.
