# ISSUE PLAN: AUR-208 Build Posting Plan For Dry Run

Historical execution artifact for this issue. Linear remains the durable source for issue status, blockers, and handoff details; if this file conflicts with Linear, Linear wins. Fetch current state from Linear before acting on this plan.

## Linear issue snapshot

- Issue: `AUR-208` / `RG-019: Build Posting Plan For Dry Run`
- Milestone: `PRD 0002: MVP Tracer Bullet`
- Status at planning: `In Progress`

## Acceptance criteria mapping

1. Posting plan supports local only, top-level summary item, review body item, inline candidate, and suggested reply.
   - Evidence target: typed destination enum/model and tests that assign each supported destination.
2. MVP artifact kind is `issue_comment`.
   - Evidence target: candidate payload model stores `artifact_kind="issue_comment"` and top-level PR comment target metadata.
3. Formal PR review payloads are rejected.
   - Evidence target: construction/validation rejects `pull_request_review`, `inline_comment`, `approve`, `request_changes`, or `COMMENT` review-event style payload kinds.
4. Local notes and suggested replies are excluded from postable payload items.
   - Evidence target: posting plan tests include findings, local notes, and suggested replies; only postable findings enter candidate public payload items.
5. Candidate payload includes review target metadata and idempotency fingerprints.
   - Evidence target: candidate payload includes owner/repo, PR number, base SHA, head SHA, merge-base SHA, diff basis, item fingerprints, visible-body hash, final-body hash placeholder/primitives, and sorted finding fingerprint hash primitives.

## Minimal foundation ownership

This issue is the first runtime issue in a scaffold-only repo. It may add only the foundation needed by posting-plan tests:

- `pyproject.toml` with package/test tooling and a runnable `python -m pytest` path.
- `src/reviewgraph/__init__.py` and minimal modules for models, posting, redaction, and side-effect sentinel types.
- `tests/` with focused posting tests and a placeholder/default test path if needed.
- Minimal shared dataclasses/enums for review targets, diff anchors, classified findings, local notes, suggested replies, suppressed outputs, clarification requests, local verdict, redaction status, posting destinations, posting plan items, and candidate issue-comment payload.
- A small redaction primitive used by candidate payload body construction so token-like text is not introduced into payload previews before `AUR-209`. Tests must cover the redaction classes this issue claims to support.
- Pure posting-plan and payload builders. `src/reviewgraph/posting.py` must not import writer, transport, GitHub client, approval, finalization, or marker-reconciliation modules, and builders must not accept writer/client arguments.

Do not implement the graph shell, CLI, reviewer config loader, fake reviewer adapter, rich quality classifier, approval storage, marker reconciliation, live reads, live LLM, writer port, or real writer behavior in this issue.

## Implementation plan

1. Add the Python project skeleton with conservative dependencies. Prefer stdlib dataclasses/enums unless a dependency is already justified by tests.
2. Define minimal model contracts in `src/reviewgraph/models.py`:
   - `ReviewTarget`
   - `ClassifiedFinding`
   - `DiffAnchor`
   - `LocalNote`
   - `SuggestedReply`
   - `SuppressedOutput`
   - `ClarificationRequest`
   - `ReviewVerdict`
   - `RedactionStatus`
   - strict literal/enum values for severity, confidence, priority, classification, and artifact kind
3. Add `src/reviewgraph/redaction.py` with deterministic token-like redaction for API keys, bearer/GitHub tokens, authorization headers, `.env` assignments, and private key blocks. Keep it small; broader live-LLM redaction coverage remains later scope, but this slice must test every redaction class it claims.
4. Add `src/reviewgraph/posting.py`:
   - `PostingDestination`
   - `PostingPlanItem`
   - `PostingPlan`
   - `CandidateIssueCommentPayload`
   - `build_posting_plan(...)`
   - `build_candidate_issue_comment_payload(...)`
   - `validate_mvp_artifact_kind(...)`
   - stable hash/fingerprint helpers with explicit canonicalization
5. Keep writer reachability out of this slice by design. Do not add `side_effects.py` unless it contains only a non-writer marker such as a deliberately unimported test sentinel. Prefer tests that inspect `posting.py` imports/signatures and prove builders are pure.
6. Add `tests/test_posting.py` covering:
   - every destination enum value;
   - candidate payload kind is `issue_comment`;
   - invalid formal PR review/inline/request-changes/approve artifact kinds fail;
   - inline candidates require a `DiffAnchor` that overlaps changed target code, while MVP still renders/posts only top-level issue-comment payloads;
   - local notes, suggested replies, clarification requests, suppressed outputs, and non-findings are excluded from public payload items;
   - local `request_changes` verdict wording is excluded from candidate public payload text unless a later approval policy explicitly allows it;
   - review target metadata and fingerprints are present;
   - hashes are deterministic and canonical: UTF-8 bytes, LF line endings, one trailing newline for visible bodies, stable target field order, sorted finding fingerprints, duplicate fingerprint rejection, visible-body hash excluding future marker lines, and final-body hash primitive including the exact full body bytes supplied to it;
   - API keys, bearer tokens, GitHub tokens, authorization headers, `.env` assignments, and private key blocks are redacted before candidate body/hash creation;
   - `src/reviewgraph/posting.py` does not import writer, transport, GitHub client, approval, finalization, or marker-reconciliation modules;
   - posting-plan and candidate-payload builders do not accept writer/client arguments.
7. Run:
   - `python -m pytest tests/test_posting.py`
   - `python -m pytest`
   - `python scripts/check_docs.py`
   - `git diff --check`

## Out of scope

- No real GitHub writer adapter.
- No writer port/interface in posting-plan code.
- No approval model beyond payload/hash primitives needed by posting-plan metadata.
- No full PR fixture schema, graph shell, CLI, reviewer config validation, fake reviewer adapter, or live integrations.
- No formal PR review, inline comment, approval, or request-changes GitHub payload construction.
- No semantic deduplication.

## Review approach

- Get fresh subagent plan review before implementation.
- After implementation, move `AUR-208` to `In Review`, run fresh code review subagents, fix material issues, and commit after each review cycle.
