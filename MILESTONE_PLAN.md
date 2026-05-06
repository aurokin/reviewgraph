# MILESTONE PLAN: PRD 0005 Review Quality

Active execution artifact for this milestone. Linear remains the durable source for issue status, milestone order, blockers, relationships, and handoff details; if this file conflicts with Linear, Linear wins. Re-fetch current Linear state before starting each issue.

## Linear Scope Snapshot

- Milestone: `PRD 0005: Review Quality`
- Milestone ID: `7c623166-927e-43d7-a14d-41af005a2587`
- Current status at intake: all implementation issues are `Backlog`; no evidence comments yet.
- Implementation issues:
  - `AUR-201` / `RG-012: Normalize Reviewer Output` / `Backlog`
  - `AUR-202` / `RG-013: Classify Review Quality` / `Backlog`
  - `AUR-203` / `RG-014: Classify Testing Feedback Quality` / `Backlog`
  - `AUR-204` / `RG-015: Validate Diff Anchors For Inline Candidates` / `Backlog`
  - `AUR-205` / `RG-016: Stop For Clarification Requests` / `Backlog`
  - `AUR-206` / `RG-017: Resume From Clarification Answers` / `Backlog`
  - `AUR-207` / `RG-018: Compute Local Verdict` / `Backlog`
  - `AUR-226` / `RG-037: Continue After Optional Reviewer Failure` / `Backlog`
  - `AUR-227` / `RG-038: Repair Or Record Malformed Reviewer JSON` / `Backlog`
- Gate issue:
  - `AUR-257` / `Complete PRD 0005: Review Quality` / `Backlog`

## Milestone Intent

PRD 0005 is the trust bar for ReviewGraph output. The milestone turns reviewer output into graph-owned quality decisions before rendering or posting can see it: postable findings, local notes, clarification requests, suggested replies, and suppressed non-findings.

The product point is restraint. ReviewGraph should prefer no finding over a plausible weak finding. Agents may propose issues, questions, notes, and replies, but the graph owns postability, priority, blocking status, fingerprints, local verdicts, and side-effect eligibility.

## Current Code Snapshot

- `src/reviewgraph/models.py` already defines `RawReviewerFinding`, `ClassifiedFinding`, `DiffAnchor`, `LocalNote`, `SuggestedReply`, `SuppressedReviewerOutput`, `ClarificationRequest`, `ReviewVerdict`, and graph-owned-field rejection.
- `src/reviewgraph/reviewers.py` already normalizes deterministic fake reviewer items into typed `ReviewerResult` fields, but the runner still re-parses `raw_output` for policy. `AUR-201` should make typed normalized artifacts the policy input.
- `src/reviewgraph/runner.py` currently contains legacy in-run normalization/classification helpers such as `_classify_reviewer_output`, `_is_postable_finding`, `_local_verdict`, evidence-provenance checks, and optional/required failure wiring. General and testing quality rules are currently interleaved here.
- `src/reviewgraph/posting.py` already keeps suggested replies/local notes/suppressed output local-only, rejects public request-changes wording in candidate payloads, and validates inline candidates when explicitly requested.
- `DiffAnchor` exists in models and posting validation, but runner-created findings do not yet attach anchors and the graph does not yet produce inline candidates.
- Existing CLI/tracer tests cover many quality behaviors in broad integration form. PRD 0005 should add focused harnesses as each issue lands and extract policy into narrow modules without broad behavior drift.

## Execution Order

1. `AUR-201` first: extract reviewer-output normalization into a focused contract. Valid reviewer output should become typed raw findings, local notes, clarification requests, suggested replies, and suppressible non-findings. Malformed raw strings or malformed mappings must flow to the explicit repair/error policy rather than being silently coerced. Graph-owned fields must not be stripped silently; they should be preserved as rejection/suppression evidence for policy.
2. `AUR-227` second: add the deterministic fake repair/error path for malformed reviewer JSON. This should happen before broader quality classification so malformed inputs have one clear lifecycle: repair once, normalize on success, record required/optional failure on exhaustion.
3. `AUR-204` third: validate changed-line locations and diff anchors before the quality classifier can mark output postable. Keep inline posting out of scope. Findings without precise changed-line locations remain local-only unless a future top-level exception is explicitly designed.
4. `AUR-202` fourth: extract and harden the general quality classifier. It should ignore reviewer self-declared postability/blocking, require changed-code evidence, safe evidence provenance, a validated changed-code location when available, an actionable scenario, concise/matter-of-fact comment shape, redaction-safe rendering/posting behavior, graph-owned priority/fingerprint/blocking decisions, and logic-review rules. Generic/speculative/pre-existing/locationless output should be suppressed or downgraded.
5. `AUR-203` fifth: layer testing-reviewer quality rules on the extracted classifier. Testing output is postable only with changed behavior, a concrete regression scenario, and identifiable missing coverage; generic "add tests" remains local-only or suppressed.
6. `AUR-205` sixth: make clarification-stop behavior a focused graph contract. Pending blocking clarification requests set `post_enabled=false`, render the question and why it matters, and prevent the ambiguous issue from producing a local blocking verdict.
7. `AUR-206` seventh: implement answered clarification resume. `ingest_clarification_answer` records answers without mutating cursor fields; `advance_or_finish_stage` activates transient `clarification_review`; only affected reviewers rerun.
8. `AUR-226` eighth: confirm optional reviewer failures continue through later stages with partial-review metadata. Earlier PRD 0004 work already covers much of this behavior; this issue should add focused quality-era proof and avoid changing required-failure semantics.
9. `AUR-207` ninth: extract local verdict policy from classified outputs and failure/clarification state. Local verdict remains private/dry-run state and does not imply GitHub review events or public request-changes wording.
10. `AUR-257` last: close the milestone only after all implementation issues are `Done`, focused/full validation passes, durable docs capture the final review-quality contracts, Linear evidence is complete, and fresh subagent review reports no material gaps.

## Issue Workflow

For each issue:

1. Re-fetch the issue, comments, blockers, and current milestone state from Linear.
2. Move the issue to `In Progress`.
3. Replace `ISSUE_PLAN.md` with a narrow plan for that issue and commit it before implementation.
4. Use fresh subagents to review the issue plan before code changes.
5. Implement the smallest contract/harness slice that satisfies the issue and does not implement later milestone scope.
6. Run the issue harness named by Linear plus regression tests covering touched shared behavior.
7. Use fresh subagents for code/docs review until no material findings remain.
8. Commit the completed issue, and commit separately after every review-fix batch.
9. Move the issue to `In Review`, add a Linear evidence comment with commands and artifact coverage, then move it to `Done` only when acceptance criteria are mapped to concrete evidence.

## Harness Strategy

- `AUR-201` focused harness: `python -m pytest tests/test_findings.py`
- `AUR-227` focused harness: `python -m pytest tests/test_reviewer_json_repair.py`
- `AUR-204` focused harness: `python -m pytest tests/test_diff_anchor.py`
- `AUR-202` focused harness: `python -m pytest tests/test_quality.py`
- `AUR-203` focused harness: `python -m pytest tests/test_quality_testing.py`
- `AUR-205` focused harness: `python -m pytest tests/test_clarification.py`
- `AUR-206` focused harness: `python -m pytest tests/test_clarification_resume.py`
- `AUR-226` focused harness: `python -m pytest tests/test_optional_reviewer_failure.py`
- `AUR-207` focused harness: `python -m pytest tests/test_verdict.py`
- Focused harness note: several `tests/test_*.py` files named above do not exist at milestone intake. Each issue should create or extract its focused harness before implementation and keep existing broad CLI/tracer coverage green.
- Tracer/CLI regression harness:
  - `python -m pytest tests/test_tracer_fixture_run.py tests/test_cli.py tests/test_render.py`
- Reviewer/failure regression harness:
  - `python -m pytest tests/test_reviewers_fake.py tests/test_required_reviewer_failure.py tests/test_reviewer_runs.py`
- Boundary regression harness:
  - `python -m pytest tests/test_reviewer_context.py tests/test_contract_boundaries.py tests/test_context_budget.py tests/test_prompt_injection_memory.py tests/test_redaction.py`
- Full validation after shared policy changes:
  - `python -m pytest -q`
  - `python -m py_compile src/reviewgraph/*.py`
  - `python scripts/check_docs.py`
  - `git diff --check`

## Contract Guardrails

- Dry-run remains the default. No PRD 0005 work should introduce live GitHub reads, live LLM calls, approval prompts, or writer reachability.
- Reviewer output cannot self-declare postability, final priority, blocking status, fingerprint, destination, approval, public verdict, or GitHub review event.
- Findings must be structured before markdown rendering. Markdown is output, not policy state.
- Postable findings require changed-code evidence, an actionable scenario, safe evidence provenance, and a precise changed-code location when available. Critical, blocking, or request-changes-driving findings require high confidence; medium-confidence findings may be postable only when non-blocking and still concrete enough for the author to act on. Low-confidence or ambiguous issues cannot drive public findings or blocking verdicts.
- Logic-review findings may cite cross-file evidence, but public locations anchor to changed code that introduced or exposed the risk. Unclear product intent becomes clarification, not a blocking finding.
- Testing findings are postable only with changed behavior, a concrete regression scenario, and identifiable missing coverage. Generic "add tests" output is local-only or suppressed.
- Postable comment bodies should be concise, matter-of-fact, one issue per item, and free of public verdict pressure unless a later approval policy explicitly permits it.
- Secret-like evidence must be redacted before rendering, JSON output, candidate payloads, final payloads, traces, logs, or provider-bound requests.
- Suggested replies are local-only in MVP and never become automatic GitHub replies.
- Inline candidates remain dry-run only. Inline GitHub posting is outside PRD 0005.
- Passive or untrusted memory cannot support postable findings, verdict-blocking clarifications, routing pressure, approval input, or public payload text.
- Optional reviewer failures may produce partial-review metadata and local notes without blocking post eligibility by themselves. Required reviewer failures remain fail-closed.
- The local verdict is private ReviewGraph output. Public request-changes wording is excluded from candidate GitHub payloads by default.

## Documentation Work

Update the narrowest durable docs alongside behavior:

- Quality classification, output classes, and finding eligibility belong in `docs/architecture/review-quality.md`.
- Raw and classified schemas, diff anchors, clarification requests, and provenance rules belong in `docs/architecture/findings-contract.md`.
- Clarification stop/resume graph behavior belongs in `docs/architecture/state-graph.md`.
- Quality harness families and golden-case expectations belong in `docs/harnesses/harness-engineering.md`.
- Sequencing narrative belongs in `docs/plans/implementation-plan.md` only if the project phase narrative changes materially.
- Add an ADR only for a durable tradeoff that future implementers would otherwise reopen.
- Keep Linear as the executable backlog. Do not copy the issue tree into durable product docs beyond this active execution plan.

## PRD 0005 Acceptance Surface

The milestone is complete when ReviewGraph proves:

- Valid reviewer output normalizes into typed raw artifacts before quality policy runs.
- Malformed reviewer JSON gets one deterministic fake repair attempt and then either normalizes or records required/optional failure state.
- Diff anchors and changed-line locations are validated before postable classification depends on them.
- General quality classification separates postable findings, local notes, clarification requests, suggested replies, and suppressed non-findings.
- Generic, speculative, self-declared-blocking, pre-existing, unsupported, unsafe-memory, unsafe-secret-bearing, and locationless output cannot become postable findings.
- Postable findings have graph-owned priority `0..3`, severity/confidence preserved from typed evidence, graph-owned blocking status, and fingerprints. Tests must prove priority is not accepted from reviewer output and does not have to equal severity.
- Postable comments are concise and matter-of-fact enough for public review text, while local verdict wording remains private by default.
- Testing-reviewer output follows the stricter changed-behavior/regression-scenario/missing-coverage bar.
- Diff anchors are modeled and validated for dry-run inline candidates without enabling inline posting.
- Blocking clarification requests stop post eligibility and avoid fake certainty.
- Answered clarifications can resume only affected reviewers through transient `clarification_review`.
- Optional reviewer failure continuation is proven in the quality-era graph, while required failure remains fail-closed.
- Local verdict computation is extracted from public GitHub behavior and excludes public request-changes pressure by default.

## Deferred Scope

- Semantic deduplication remains deferred.
- Inline GitHub comments remain deferred.
- Automatic replies to human PR comments remain deferred.
- Live GitHub reads, live LLM reviewers, approval finalization, marker reconciliation, and writer behavior remain later PRDs.

## Milestone Completion Criteria

`AUR-257` can close only when:

- Every implementation issue listed in this plan is `Done` in Linear with an evidence comment.
- A fresh Linear milestone inventory proves every active PRD 0005 blocker is complete or has an explicit stale/canceled/not-applicable rationale in Linear.
- Focused validation for all PRD 0005 harness families passes.
- Tracer, reviewer/failure, boundary, full validation, docs check, py-compile, and diff check pass.
- Durable docs explain the final review-quality contracts an implementation agent needs when dropping into the repo.
- Fresh subagent review of code, tests, docs, Linear evidence, and the milestone gate reports no material issues.
- No unapproved live API, live LLM, approval, inline-posting, or GitHub writer behavior has been introduced.
- No `.ws/` or temporary export artifacts remain.
