# ISSUE PLAN: AUR-215 Apply GitHub Trust Rules To Memory

Active issue plan for `AUR-215` / `RG-026: Apply GitHub Trust Rules To Memory`.

Linear remains the durable source of current issue status and relationships. This file is the committed execution plan for the issue.

## Linear Snapshot

- Project: `ReviewGraph`
- Team: `Aurokin`
- Milestone: `PRD 0006: GitHub Read And Memory`
- Issue: `AUR-215`
- Title: `RG-026: Apply GitHub Trust Rules To Memory`
- Status when planned: `In Progress`
- Priority: `Medium`
- Linear comments fetched on 2026-05-07: none

## Acceptance Mapping

1. Trusted humans are owner/member/collaborator plus authenticated operator.
   - Prove with GitHub-derived issue comments and review-thread comments from owner/member/collaborator/operator authors.
   - Preserve existing fixture behavior where explicit fixture `trust_label="trusted"` plus trusted association becomes trusted memory.
   - In this issue, authenticated operator means configured `trusted_operator_authors`; deriving it from a live actor/permission snapshot is PRD 0007 side-effect policy.
   - Operator and bot allowlists match canonical GitHub logins exactly; mismatches fail closed.
2. Trusted review bots are default-deny allowlisted.
   - Prove a bot with owner/member association remains passive unless present in `trusted_bot_authors`.
3. Unlisted bot comments remain passive memory.
   - Prove both top-level issue comments and review-thread comments from unlisted bots produce `trust_label="untrusted"`, `actionable=False`, and `passive_reason="untrusted author"`.
4. Untrusted comments cannot trigger conversation-pattern routing.
   - Use the existing routing selector with GitHub-derived passive memory whose body matches a `conversation_patterns` selector and assert no reviewer is selected.
5. Untrusted comments cannot influence reviewer prompts as instructions, local verdicts, approval input, or public payload text.
   - Prompt input: assert passive GitHub memory bodies are omitted from instructions and prompt data.
   - Quality/local verdict: add a GitHub-derived passive-memory case where reviewer output cites passive memory by ID without copying the body; prove it is suppressed or local-only and cannot change the local verdict.
   - Public payload: add a GitHub-derived passive-memory case with a unique phrase and prove the phrase is absent from prompt data, rendered memory body, candidate payload preview, and public posting-plan items.
   - Approval/writer code remains out of scope and unreachable for this issue.
6. Resolved threads are non-actionable unless new unresolved follow-up appears.
   - Prove trusted GitHub review-thread comments in `resolved` and `unknown` thread states are passive.
   - Prove the same trusted author in an `unresolved` thread becomes actionable, representing the new-unresolved-follow-up case available in the current model.
   - Current data has thread-level resolved state, not per-comment transition timestamps. AUR-215 will preserve thread IDs as seen-state but will not infer which older comment reopened a thread; finer-grained follow-up detection is deferred until the model has per-comment event/state history.
7. Seen-state is preserved.
   - Preserve raw source comment/review/review-comment IDs as `source_id`.
   - Use collision-safe namespaced `MemoryReference.id` values for GitHub-derived memory so issue comments, reviews, and review comments with the same raw ID cannot collide.
   - Preserve review-thread IDs as `thread_id` on review-thread memory entries and rendered/reviewer-context JSON.
   - Do not introduce durable deduplication or semantic duplicate detection in this issue.

## Design

AUR-214 forced paginated GitHub conversation items to `trust_label="untrusted"` as a temporary safe default. AUR-215 replaces that temporary default with explicit provenance plus memory-side GitHub trust classification.

Planned contract:

- Add explicit source provenance fields to model data, likely `source_provider` on `PullRequestComment`, `PullRequestReview`, and `MemoryReference`, plus `thread_id` on `MemoryReference`.
- The GitHub fake read adapter sets `source_provider="github"` on comments, review comments, and reviews.
- `source_provider` allowed values are `fixture` and `github`. Existing fixtures/default constructors use `fixture`; unknown values are allowed only as non-trusted provenance and fail closed for trust.
- The adapter ignores any inbound `trust_label` and `source_provider` fields from fake page payloads. Transport data must not be able to self-declare trusted memory or trusted provenance.
- `build_conversation_memory()` treats `trust_label="trusted"` as explicit fixture/test trust eligibility and `source_provider="github"` as GitHub-derived trust eligibility.
- `source_provider` is provenance, not trust. It may appear in diagnostic/rendered memory metadata; it must never appear as `MemoryReference.trust_label`.
- Final `MemoryReference.trust_label` remains only `trusted` or `untrusted`.
- `_is_trusted()` remains the central policy:
  - user + `OWNER`, `MEMBER`, or `COLLABORATOR` -> trusted
  - user + configured `trusted_operator_authors` -> trusted
  - bot + configured `trusted_bot_authors` -> trusted
  - unlisted bot, unknown actor type, contributor, unknown trust label -> untrusted
- Review summaries remain passive even when trusted, because later nodes interpret them.
- All passive memory bodies are hidden from prompt data and rendered memory JSON, including trusted review summaries and trusted resolved/unknown review-thread comments. Trusted actionable memory is the only memory body class that can be included.
- Review threads use thread-level `resolved_status`: `resolved` and `unknown` force passive; `unresolved` can be actionable if the author is trusted.
- AUR-215 must prevent trusted GitHub actionable memory from satisfying positive `conversation_patterns` routing until `AUR-236` adds matched-memory IDs and trust status to selection reasons. Fixture memory can keep existing routing behavior.
- URL absence alone does not make GitHub-derived memory untrusted in this slice. The fake adapter is the provenance boundary, source IDs/thread IDs are the seen-state handle, and URL is optional metadata.

## Files

Likely implementation files:

- `src/reviewgraph/github.py`
- `src/reviewgraph/memory.py`
- `src/reviewgraph/models.py`
- `src/reviewgraph/render.py`
- `src/reviewgraph/reviewer_context.py`

Likely test files:

- `tests/test_github_memory_trust.py`
- `tests/test_github_pagination.py`
- `tests/test_memory.py`
- `tests/test_reviewer_context.py`
- `tests/test_routing.py`

Likely docs:

- `docs/architecture/github-integration.md`
- `docs/architecture/state-graph.md`
- `docs/harnesses/harness-engineering.md`

## Implementation Steps

1. Add focused failing tests in `tests/test_github_memory_trust.py`.
2. Add explicit provenance/seen-state fields with backwards-compatible defaults.
3. Update the paginated fake GitHub adapter to mark GitHub-derived comments, review comments, and reviews with non-payload-controlled provenance.
4. Update memory trust eligibility so only explicit fixture-trusted or GitHub-derived items can be classified by author policy.
5. Preserve review-thread IDs in memory, reviewer context trace/prompt metadata, and rendered JSON.
6. Use namespaced GitHub memory IDs and raw `source_id` so seen-state is preserved without collisions.
7. Add candidate-payload/public-boundary proof for GitHub-derived passive memory, including trusted-but-passive review summaries and resolved/unknown threads.
8. Add quality/local-verdict proof for a reviewer output that cites passive GitHub memory by ID.
9. Gate positive GitHub `conversation_patterns` routing until `AUR-236`, while preserving negative routing proof for untrusted/passive GitHub memory.
10. Keep unknown labels and unknown provenance default-denied.
11. Update AUR-214 pagination expectations from temporary untrusted memory defaults to provenance plus memory-classified trust where applicable.
12. Add or adjust docs for the new boundary: source provenance is not trust; memory emits final trusted/untrusted classification.

## Validation Plan

Focused harness:

```bash
python -m pytest tests/test_github_memory_trust.py -q
```

Regression harness:

```bash
python -m pytest tests/test_github_pagination.py tests/test_memory.py tests/test_routing.py tests/test_reviewer_context.py tests/test_prompt_injection_memory.py tests/test_quality.py tests/test_render.py -q
```

Full validation before completion:

```bash
python -m pytest -q
python -m py_compile src/reviewgraph/*.py
python scripts/check_docs.py
git diff --check
```

## Out Of Scope

- Changing `conversation_patterns` selection reason format or adding matched memory IDs. That is `AUR-236`.
- GitHub PR dry-run CLI wiring. That is `AUR-239`.
- Live read. That is `AUR-216`.
- Approval prompts, finalization, writer behavior, or public posting.
- Requiring comment URLs for trust. URL is useful metadata, but source IDs plus adapter provenance are the planned trust boundary for this slice.
