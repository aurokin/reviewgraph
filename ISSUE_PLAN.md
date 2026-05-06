# ISSUE PLAN: AUR-202 Classify Review Quality

Active issue plan for `AUR-202` / `RG-013: Classify Review Quality`.

## Linear Snapshot

- Issue: `AUR-202`
- Status at plan time: `In Progress`
- Milestone: `PRD 0005: Review Quality`
- Comments at plan time: none
- Linear description: implement a Codex-inspired quality classifier that converts normalized reviewer output into postable findings, local notes, clarification requests, suggested replies, and suppressed non-findings.
- Focused harness requested by Linear: `python -m pytest tests/test_quality.py`
- Relations: blocked by `AUR-201`, which is complete; blocks `AUR-203`, `AUR-204`, `AUR-205`, `AUR-207`, `AUR-226`, `AUR-238`, and milestone gate `AUR-257`.
- Ordering note: `AUR-204` was next in the original local milestone plan, but Linear currently marks `AUR-204` blocked by `AUR-202`; Linear wins.
- Upstream issue now complete: `AUR-227`, commit `871dfe2`, introduced deterministic fake repair and structured repair metadata before quality classification.

## Goal

Extract and harden the general review-quality classifier so normalized reviewer artifacts become graph-owned classified output before rendering or candidate payload construction. The graph, not the reviewer, decides postability, priority, blocking status, fingerprint, and public eligibility.

This slice should move quality policy out of incidental runner helpers into a focused module with a focused harness, while preserving existing broad CLI/tracer behavior. It should prefer suppression/local-only output over weak public findings.

## Acceptance Mapping

- Postable findings require changed-code evidence and actionable scenario:
  - Keep changed-line validation as a prerequisite for postable findings.
  - Require concrete evidence text that names changed code and enough scenario detail to be actionable.
  - Findings referencing omitted context or unsafe memory provenance stay suppressed.
- Postable findings include graph-owned structured fields:
  - Output must include classification, graph-owned priority, severity, confidence, rationale/body, evidence, fingerprint, source reviewer/stage, path, line, and `line_end` when supplied.
  - Diff-anchor population remains out of scope for this issue; `AUR-204` owns validated `DiffAnchor` construction and inline candidates.
- Reviewer self-declared postability or blocking is ignored:
  - Graph-owned fields from raw reviewer findings remain suppressed by normalization.
  - Valid normalized findings should receive graph-owned priority/fingerprint/blocking values only from quality policy.
- Generic, speculative, pre-existing, unsupported findings are suppressed or downgraded:
  - Existing broad CLI behavior for generic coverage, generic refactor advice, speculative language, pre-existing issues, weak evidence, and vague scenarios must remain green.
  - Suppression reason should remain stable enough for current dry-run assertions unless the focused harness justifies a durable contract change.
- Classified findings get priority, blocking status, fingerprint, and classification from the graph:
  - Priority remains distinct from severity.
  - Fingerprints remain deterministic and secret-safe.
  - Blocking remains graph-owned and high-confidence only; this slice should not introduce public request-changes wording or GitHub review events.
- Low-confidence or ambiguous mergeability issues cannot become blocking findings:
  - Low/medium confidence findings should not be postable/blocking.
  - Ambiguous mergeability concerns should become clarification requests only when represented as reviewer clarification artifacts; generating new clarifications from finding prose is out of scope unless the plan review identifies an existing deterministic rule.
- Logic-review findings:
  - Cross-file evidence may support a finding, but the postable location must still be a changed line.
  - Ambiguous product intent should remain clarification output, not an inflated blocking finding.
  - Generic architecture advice stays local-only or suppressed.
- Golden cases:
  - Add focused `tests/test_quality.py` cases for postable finding, local note passthrough, clarification request passthrough, suggested reply passthrough, suppressed non-finding passthrough, generic/speculative/pre-existing/self-declared-blocking suppression, cross-file logic evidence, ambiguous invariant clarification, and generic architecture advice.

## Current Baseline

- `src/reviewgraph/runner.py` currently owns quality classification through `_classify_normalized_reviewer_output`, `_classified_finding`, `_is_postable_finding`, evidence provenance helpers, graph fingerprint/priority helpers, and local verdict helpers.
- `src/reviewgraph/findings.py` now normalizes reviewer outputs into typed `ReviewerResult` artifacts and records graph-owned field rejection as structured normalization errors/suppressed output.
- Existing CLI tests already encode many quality cases, but they are broad fixture-run tests rather than a focused classifier harness.
- `docs/architecture/review-quality.md` and `docs/architecture/findings-contract.md` already describe the intended quality contract; implementation is still mostly embedded in runner helpers.
- `src/reviewgraph/models.py` already has `ClassifiedFinding`, `LocalNote`, `SuggestedReply`, `SuppressedReviewerOutput`, `ClarificationRequest`, and `DiffAnchor`, but this slice should not construct diff anchors.

## Implementation Plan

1. Create `tests/test_quality.py` before implementation changes.
   - Use typed `ReviewerResult` / `RawReviewerFinding` fixtures where possible instead of full CLI fixture files.
   - Include small fixture PR helpers only for changed-line validation and omitted-context checks.
   - Prove graph-owned priority/fingerprint/blocking/classification decisions.
   - Prove passthrough for local notes, clarification requests, suggested replies, and normalized suppressed outputs.
   - Prove suppression for low confidence, generic, speculative, pre-existing, weak evidence, self-declared graph-owned fields, unsafe memory provenance, omitted context, and generic architecture advice.
2. Introduce `src/reviewgraph/quality.py`.
   - Move general quality classification helpers out of `runner.py` into a focused API.
   - Candidate API shape: `classify_review_quality(fixture, reviewer_result, memory_references, omitted_file_paths=()) -> QualityClassificationResult`.
   - Keep the result typed or minimally structured so runner can extend existing `classified` collections without changing render JSON shape.
   - Keep `RunnerError`-style validation either in runner or converted into a small quality error class; avoid widening exception behavior unless tests require it.
3. Wire `runner.py` to the new quality module.
   - Replace `_classify_normalized_reviewer_output` internals with a call into `quality.py`.
   - Leave legacy `_classify_reviewer_output` only if still needed for compatibility; do not use it for the current fake reviewer normalized path.
   - Keep side effects, approval, posting, rendering, local verdict, ranking, and writer behavior unchanged.
4. Preserve current policy behavior while making ownership explicit.
   - Reuse current deterministic priority and fingerprint rules unless plan review finds a contract gap.
   - Keep blocking default `False` unless a high-confidence blocking policy already exists; do not invent public request-changes behavior.
   - Keep existing suppression reason text stable where current tests depend on it.
5. Update durable docs narrowly.
   - `docs/architecture/review-quality.md` if the module boundary or general classifier contract becomes more concrete.
   - `docs/architecture/findings-contract.md` if classified JSON shape or graph-owned field behavior changes.
   - `docs/harnesses/harness-engineering.md` for the new focused `tests/test_quality.py` harness expectations.
   - `docs/plans/implementation-plan.md` only if the phase narrative changes materially.
6. Keep `AUR-204`, `AUR-203`, `AUR-205`, `AUR-206`, `AUR-226`, and `AUR-207` out of scope.

## Out Of Scope

- No diff-anchor validation or inline candidate construction; `AUR-204` owns it.
- No testing-specific stricter classifier beyond preserving existing behavior; `AUR-203` owns it.
- No clarification stop/resume graph changes; `AUR-205` and `AUR-206` own them.
- No optional failure continuation change; `AUR-226` owns focused proof.
- No local verdict extraction; `AUR-207` owns it.
- No ranking rewrite, rendering rewrite, approval, GitHub posting, live GitHub reads, live LLM calls, provider calls, writer behavior, or public request-changes events.
- No semantic deduplication.

## Validation Plan

```bash
python -m pytest tests/test_quality.py
python -m pytest tests/test_findings.py tests/test_reviewer_json_repair.py
python -m pytest tests/test_reviewers_fake.py tests/test_required_reviewer_failure.py tests/test_reviewer_runs.py
python -m pytest tests/test_tracer_fixture_run.py tests/test_cli.py tests/test_render.py
python -m pytest tests/test_reviewer_context.py tests/test_contract_boundaries.py tests/test_context_budget.py tests/test_prompt_injection_memory.py tests/test_redaction.py
python scripts/check_docs.py
python -m py_compile src/reviewgraph/*.py
git diff --check
```

Run `python -m pytest -q` after focused and regression harnesses are green.

## Completion Evidence To Collect

- Focused `tests/test_quality.py` output.
- Existing CLI quality regression output.
- Normalization/repair regression output proving AUR-201/AUR-227 behavior still feeds quality correctly.
- Reviewer/failure, tracer/render, boundary, docs, py-compile, diff, and full-suite checks.
- Subagent plan-review findings and fixes.
- Subagent code-review findings and fixes.
- Linear evidence comment mapping every AUR-202 acceptance criterion to code/tests.
