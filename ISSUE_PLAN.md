# ISSUE PLAN: AUR-217 Model Item-Level Approval And Final Hash

Active issue plan for `AUR-217` / `RG-028: Model Item-Level Approval And Final Hash`.

Linear is the durable source for status, blockers, and handoff. Durable behavior comes from `docs/architecture/side-effects.md`, `docs/architecture/state-graph.md`, `docs/architecture/github-integration.md`, and `docs/prds/0007-side-effects.md`.

## Linear Snapshot

- Project: `ReviewGraph`
- Team: `Aurokin`
- Milestone: `PRD 0007: Side Effects`
- Issue: `AUR-217`
- Title: `RG-028: Model Item-Level Approval And Final Hash`
- Status when planned: `In Progress`
- Linear comments fetched on 2026-05-07: none
- Upstream blockers complete: `AUR-244` hash domains and `AUR-218` candidate/final payload validation.

## Objective

Add the pure approval-proof slice that binds item-level approved findings to the deterministic final issue-comment body hash before any writer, actor/permission gate, target freshness gate, marker reconciliation scan, or graph post mode exists.

This issue models approval and final hash binding only. It may add deterministic final payload preview/build helpers needed to compute the approved final hash, but it must not introduce a writer adapter, live GitHub calls, post-mode routing, actor/permission discovery, current-target refetch, marker reconciliation against existing comments, or approval prompts.

## Contracts To Preserve

- Dry-run remains default; no code path posts to GitHub.
- Approval is item-level and stores approved finding IDs.
- Approval is target-bound and stores the full `ReviewTarget` plus `approved_review_target_hash`.
- Approval stores `approved_final_payload_hash` for the post-selection final issue-comment body.
- Approved final hash uses AUR-244 hash domains: marker `payload` equals visible-body hash excluding the marker, and `approved_final_payload_hash` equals the full final body hash including the exact marker line.
- Approval binding uses AUR-218 candidate/final split. Candidate payloads have no final marker, no final payload hash, and are never writer/final input.
- Approving a subset changes the final body and final hash when the selected item set changes.
- Stale candidate-visible hash inputs are rejected: approval/final-hash proof must rebuild the final body from current posting plan, current findings, current candidate payload binding, selected approved IDs, target, and run ID.
- Empty approved finding sets are rejected when `approved=True`. A rejected approval may carry no approved IDs, but it must not carry a writer-reachable final payload proof.
- Duplicate approved finding fingerprints fail closed before final marker/hash construction.
- Suggested replies, local notes, suppressed outputs, clarification requests, and inline candidates remain local-only and cannot enter the final issue-comment payload.
- Public request-changes wording remains excluded unless a later issue explicitly supports it; this issue does not submit GitHub `REQUEST_CHANGES` or approvals.
- Actor/permission snapshot storage is deferred to `AUR-219`/`AUR-243`. Existing placeholder fields may remain on `ApprovalDecision` for compatibility, but this issue must not make them live proof.
- `ApprovalDecision` should not be sufficient by itself to reach a writer. Later finalization must still validate actor/permission, target freshness, redaction, marker reconciliation, payload validation, and writer request shape.

## Implementation Shape

1. Add `src/reviewgraph/approval.py` as a pure module with no GitHub transport, writer, graph post-mode, or live IO imports.
2. Define approval helper/result contracts as needed, likely:
   - approved item selection validation,
   - deterministic final issue-comment payload preview/build from current posting inputs,
   - approval decision construction that stores approved IDs, target hash, target, final payload hash, public-verdict choice, approver, and timestamp.
3. Reuse `build_candidate_issue_comment_payload` or AUR-218 validation to prove the supplied candidate matches current posting inputs before computing final payload proof.
4. Build final issue-comment payloads from approved top-level review-body items only. Include exact ReviewGraph v1 marker line/components and return a `FinalIssueCommentPayload`.
5. Use AUR-244 helpers for visible body hash, marker payload hash, findings hash, review target hash, and final payload hash.
6. Require a run ID for marker generation and keep it within the AUR-244 marker grammar.
7. Keep actor/permission fields inert placeholders or compatibility inputs only; do not claim endpoint permission proof in this issue.
8. Add `tests/test_approval.py` for:
   - approving all findings stores approved IDs, target hash/target, and final payload hash,
   - approving a subset changes final body/hash and findings hash,
   - stale/tampered candidate payload with recomputed candidate hashes is rejected,
   - candidate payload cannot be used as final/writer input,
   - empty approved finding set is rejected for `approved=True`,
   - duplicate approved fingerprints fail closed,
   - local-only destinations are excluded from final payload,
   - final payload marker fields and final hash match AUR-244 helpers,
   - approval module import-boundary proof.
9. Update narrow durable docs only if implementation clarifies behavior beyond existing side-effect docs.

## Validation

Focused:

```bash
python -m pytest tests/test_approval.py -q
```

Regression:

```bash
python -m pytest tests/test_approval.py tests/test_payload_validation.py tests/test_payload_hashes.py tests/test_posting.py tests/test_models.py tests/test_render.py tests/test_cli.py -q
python scripts/check_docs.py
git diff --check
```

Run the full suite because approval contracts touch shared models and side-effect guardrails.

## Out Of Scope

- Actor/permission discovery or binding (`AUR-219`, `AUR-243`).
- Target freshness refetch/finalization gate (`AUR-220`).
- Marker reconciliation against existing GitHub comments (`AUR-221`, `AUR-245`).
- Non-interactive post-mode gate (`AUR-246`).
- Suppressing writer calls for no approved findings in graph/fake-writer paths (`AUR-223`).
- Fake writer, real writer, live post smoke, or GitHub write adapters.
