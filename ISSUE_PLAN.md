# ISSUE PLAN: AUR-201 Normalize Reviewer Output

Active issue plan for `AUR-201` / `RG-012: Normalize Reviewer Output`.

## Linear Snapshot

- Issue: `AUR-201`
- Status at plan time: `In Progress`
- Milestone: `PRD 0005: Review Quality`
- Comments at plan time: none
- Linear description: normalize valid fake reviewer outputs into typed raw reviewer findings, local notes, clarification requests, suggested replies, non-findings, or recorded errors. Malformed JSON repair is handled by `AUR-227`.

## Goal

Extract reviewer-output normalization into a focused module and harness so the graph can consume typed reviewer artifacts before quality classification. This issue should preserve current broad dry-run behavior while making the policy input explicit and safe for later `AUR-227`, `AUR-204`, and `AUR-202` work.

## Acceptance Mapping

- Valid raw findings parse into raw finding models:
  - Add `src/reviewgraph/findings.py` with a normalization function that returns typed `RawReviewerFinding` values for valid findings.
  - Add focused tests proving required fields, severity/confidence enums, evidence provenance fields, and line metadata are preserved.
- Valid local notes normalize into local-note models:
  - Preserve ID, title, body, evidence, and `local_note` classification without making them public-payload eligible.
- Clarification requests include source stage, source run key, status, and resume target:
  - Preserve existing `ClarificationRequest` constructor compatibility, but add normalized metadata that captures source stage, stable run key, pending status, and reviewer resume target for graph use.
  - Derive source stage, source run key, status, and resume target from `ReviewerRunKey` and graph-owned reviewer state. Reviewer-supplied `source_stage`, `source_run_key`, `status`, or `resume_target` must be ignored or rejected as graph-owned control data.
  - Do not implement answer ingestion or resume execution in this issue.
- Suggested replies remain local-only:
  - Normalize suggested replies into `SuggestedReply` and ensure posting/payload destinations remain out of the normalizer.
- Non-finding outputs are preserved as suppressible reviewer output:
  - Normalize `suppressed` and `non_finding` items into `SuppressedReviewerOutput` with stable IDs and reasons.
- Malformed reviewer JSON is passed to repair/error policy instead of silently coerced:
  - Define a focused `NormalizationError` or equivalent parse-error artifact with stable code/message, source run key, and `repairable` metadata for `AUR-227`.
  - Mapping/list/schema errors become failed normalization results or reviewer-result errors. They do not become postable findings, local notes, or general quality suppressions.
  - Preserve existing raw-string and missing-output failure behavior until `AUR-227`; this issue establishes the error contract that repair will consume, not the repair attempt itself.
  - Do not implement the one-repair attempt; that belongs to `AUR-227`.
- Reviewer graph-owned fields are not stripped silently:
  - If a finding attempts `priority`, `fingerprint`, `blocking`, `classification`, `destination`, `verdict`, or other graph-owned fields, preserve the attempted field names as an explicit rejected artifact or parse error. Prefer a rejected normalization artifact over immediate quality suppression so `AUR-202` still owns postability/classification policy.

## Current Baseline

- `src/reviewgraph/reviewers.py` currently builds typed `ReviewerResult` artifacts, but `_finding()` strips `GRAPH_OWNED_REVIEWER_FIELDS` before `RawReviewerFinding.from_mapping`.
- `src/reviewgraph/runner.py` currently re-parses `reviewer_result.raw_output` in `_classify_reviewer_output`, which is why graph-owned field attempts are still suppressible in current broad tests.
- `RawReviewerFinding.from_mapping` already rejects graph-owned fields when they reach the model.
- Existing broad tests in `tests/test_reviewers_fake.py`, `tests/test_cli.py`, and `tests/test_tracer_fixture_run.py` should remain green while focused `tests/test_findings.py` is added.

## Implementation Plan

1. Create `src/reviewgraph/findings.py` with a small, pure normalization API, shaped like `normalize_reviewer_output(raw_output, run_key) -> NormalizationResult`. Keep it independent of GitHub transports, posting, rendering, approval, live LLM, and side-effect modules.
2. Define a result shape for successful normalized artifacts plus parse/rejection artifacts. Prefer existing models where possible; add the minimum additional typed metadata needed for source stage/run-key/status/resume-target without broad model churn.
3. Move item parsing logic from `reviewers.py` into `findings.py`, but change graph-owned field handling so it is explicit and testable instead of silently stripped.
4. Update `reviewers.py` to call the new normalizer for valid mapping outputs and to preserve existing behavior for raw strings/missing output until `AUR-227`.
5. Update `runner.py` so valid normalized artifacts are the source of truth, but feed them through the existing safety and quality policy checks instead of appending them directly to classified output. Preserve omitted-context checks, changed-line assertions, evidence-provenance checks, current postability policy, graph-owned priority/fingerprint generation, and existing broad CLI behavior.
6. Add `tests/test_findings.py` covering valid findings, local notes, clarification requests with graph-derived source metadata, spoofed reviewer-owned clarification control fields, suggested replies, non-findings, malformed items, and graph-owned field attempts.
7. Add a regression proving runner output is driven by normalized valid artifacts rather than a second raw-output parse, without bypassing the legacy safety/quality checks.
8. Run the focused harness and broad regressions that exercise fake reviewer and dry-run output paths.

## Out Of Scope

- No quality/postability classification extraction.
- No malformed JSON repair attempt; `AUR-227` owns repair.
- No conversion of parse errors into postable/suppressed quality decisions beyond what is needed to preserve current failed-reviewer behavior.
- No diff-anchor validation; `AUR-204` owns anchors and changed-line location validation.
- No clarification answer ingestion or resume; `AUR-206` owns resume.
- No verdict policy extraction; `AUR-207` owns verdict.
- No live GitHub, live LLM, approval, finalization, or writer behavior.

## Validation Plan

```bash
python -m pytest tests/test_findings.py
python -m pytest tests/test_reviewers_fake.py tests/test_required_reviewer_failure.py tests/test_reviewer_runs.py
python -m pytest tests/test_tracer_fixture_run.py tests/test_cli.py tests/test_render.py
python -m pytest tests/test_reviewer_context.py tests/test_contract_boundaries.py tests/test_context_budget.py tests/test_prompt_injection_memory.py
python scripts/check_docs.py
git diff --check
```

## Completion Evidence To Collect

- Focused `tests/test_findings.py` output.
- Reviewer/failure regression output.
- Tracer/CLI/render regression output.
- Boundary regression output for reviewer context and memory safety.
- Docs and diff checks.
- Code review/subagent findings and fixes.
- Linear evidence comment mapping every acceptance criterion to code/tests.
