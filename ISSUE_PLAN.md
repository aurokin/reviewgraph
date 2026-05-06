# ISSUE PLAN: AUR-204 Validate Diff Anchors For Inline Candidates

Active issue plan for `AUR-204` / `RG-015: Validate Diff Anchors For Inline Candidates`.

Linear remains the source of truth for issue state and relationships.

## Linear Snapshot

- Issue: `AUR-204`
- Status at plan time: `In Progress`
- Milestone: `PRD 0005: Review Quality`
- Title: `RG-015: Validate Diff Anchors For Inline Candidates`
- Harness: `python -m pytest tests/test_diff_anchor.py`
- Out of scope from Linear: live inline GitHub comments.

## Intent

Give ReviewGraph a deterministic dry-run inline-candidate path without making inline posting reachable.

The user-facing finding location remains `path`, `line`, and optional `line_end`. `DiffAnchor` is a separate machine location used to prove that a finding can be represented as an inline candidate against the current target commit. If an anchor is missing or invalid, the finding must not become an inline candidate. The MVP fallback remains a local or top-level dry-run artifact; no live GitHub inline comment is created.

## Current Baseline

- `src/reviewgraph/models.py` already defines `DiffAnchor` with path, line, target commit SHA, hunk bounds, side/start side, file status, hunk ID, start line, and old path.
- `src/reviewgraph/posting.py` already validates explicitly supplied `inline_candidate_ids`, requires a `DiffAnchor`, requires a `ReviewTarget`, and marks inline candidates as non-public payload items.
- `src/reviewgraph/quality.py` currently classifies only findings whose `path:line` overlaps changed fixture lines. It does not attach `DiffAnchor`.
- `src/reviewgraph/render.py` does not render `diff_anchor` metadata in JSON.
- No focused `tests/test_diff_anchor.py` exists yet.

## Decisions

1. Create a focused diff-anchor helper module rather than expanding posting or quality with hunk construction logic.
2. The helper input is a narrow protocol, not a fixture import: `path`, `changed_ranges`, `status`, `previous_path`, `patch_status`, and `contains_line()`. Current fixture `ChangedFile` satisfies it; live `PullRequestChangedFile` does not yet, so live-read anchoring remains future work.
3. Anchor validation should be deterministic and target-bound. `target_commit_sha` must be the current review target head SHA.
4. AUR-204 supports single-hunk `RIGHT` anchors from fixture changed ranges. A multi-line finding is anchorable only when `line_end` stays inside the same changed range; otherwise it remains non-inline.
5. `file_status` and `old_path` are source-validated when the helper derives the anchor from the changed file. Posting validation still validates target/finding binding and treats these fields as descriptive metadata because it does not receive the source changed file.
6. Dry-run inline candidates must be visible in machine output and posting plan state, but remain non-public-payload items.
7. Findings with missing or invalid anchors should not raise during dry-run rendering. They should remain non-inline output unless the caller explicitly asked to force them as inline candidates.
8. Keep current AUR-202 quality eligibility intact. Do not rewrite general postability heuristics, evidence provenance, testing-specific policy, ranking, approval, or GitHub posting.

## Implementation Plan

1. Add `src/reviewgraph/diff_anchor.py`.
   - Provide a small API that accepts changed-file context implementing the anchor protocol, a `ReviewTarget`, and a `ClassifiedFinding`.
   - Return a valid `DiffAnchor` when the finding overlaps a changed range and target metadata is available.
   - Return `None` for missing/invalid/non-overlapping anchor cases that should stay non-inline, including unavailable patches, deleted/unsupported statuses, and `line_end` outside the selected range.
   - Keep hunk IDs stable and fixture-derived, likely `"{path}:{start}-{end}"`.

2. Add focused harness `tests/test_diff_anchor.py`.
   - Valid anchor includes all required fields and validates against the finding and target head SHA.
   - Multi-line findings anchor only when the full range stays inside one changed range.
   - Renamed file carries `old_path` and file status from source changed-file metadata.
   - Missing/non-overlapping changed range returns no anchor rather than creating an invalid inline candidate.
   - Unavailable patch or unsupported deleted-file status returns no anchor.
   - Stale target SHA or mismatched path remains rejected by existing posting validation.
   - Inline candidate posting-plan items are `inline_candidate` and `public_payload_eligible=false`.

3. Wire dry-run inline candidates narrowly.
   - Attach a `DiffAnchor` to classified findings after quality classification when a fixture-safe anchor can be derived.
   - Feed the anchored finding IDs into `build_posting_plan(..., inline_candidate_ids=...)`.
   - Keep candidate issue-comment payload top-level only; inline candidates must not enter the public payload body.

4. Render machine-visible anchor metadata.
   - Add `diff_anchor` JSON for findings when present.
   - Ensure markdown stays concise and does not imply live inline posting.
   - Preserve existing `line_end` rendering.

5. Update durable docs only where behavior changes.
   - `docs/architecture/findings-contract.md` if rendered `diff_anchor` shape changes.
   - `docs/architecture/review-quality.md` if local-only fallback wording needs tightening.
   - `docs/harnesses/harness-engineering.md` if new harness expectations need naming.

## Verification

- Focused: `python -m pytest tests/test_diff_anchor.py`
- Regression: `python -m pytest tests/test_quality.py tests/test_posting.py tests/test_render.py tests/test_cli.py`
- Full: `python -m pytest -q`
- Hygiene: `git diff --check`

## Out Of Scope

- Live inline GitHub comments.
- GitHub patch position APIs.
- Approval, finalization, writer reachability, or public PR review events.
- Ranking/local verdict extraction.
- General quality classifier rewrites.
- Semantic dedupe.
