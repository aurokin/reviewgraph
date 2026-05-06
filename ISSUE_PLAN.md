# ISSUE PLAN: AUR-233 Add Prompt Injection Memory Harness

Active issue plan for `AUR-233` / `RG-044: Add Prompt Injection Memory Harness`.

## Linear Snapshot

- Issue: `AUR-233`
- Status: `In Progress`
- Milestone: `PRD 0010: Agent Context And Adapter Boundaries`
- Milestone ID: `0dea2cdd-6433-41d8-b1a4-b91b07d3acc9`
- Relationship: `AUR-233` depends on completed context package issue `AUR-231`; `AUR-255` gate depends on this issue.
- Existing fixture: `src/reviewgraph/fixtures_data/prs/untrusted-comment-injection.json`
- Existing related coverage:
  - `tests/test_memory.py` covers trust/passive memory construction.
  - `tests/test_cli.py` covers conversation-pattern routing for trusted/untrusted memory.
  - `tests/test_reviewer_context.py` covers prompt instruction/data separation and passive memory public-payload suppression.

## Goal

Add a focused malicious-comment harness proving PR conversation memory is shared labeled data, not an instruction stream.

This issue should consolidate PRD 0010 injection-memory proof into a named harness without adding live LLM calls, live GitHub reads/writes, approval, finalization, writer behavior, or broad web-security scanning.

## Acceptance Mapping

- Untrusted comments cannot select reviewers through `conversation_patterns`.
- Untrusted comments cannot override prompts or reviewer capabilities.
- Untrusted comments cannot appear as reviewer instructions or satisfy reviewer evidence requirements.
- Later verdict, approval, payload-destination, and public-payload assertions remain delegated to `AUR-209`, `AUR-217`, `AUR-218`, and `AUR-243`; this harness must not implement or assert those flows beyond existing regressions.
- Trusted comments can remain available as cited memory without bypassing quality classification.
- Harness output shows which memory IDs were included in reviewer-visible context, their trust labels, their passive/actionable state, and their prompt data role.

## Implementation Plan

1. Re-read `untrusted-comment-injection` fixture, `tests/test_memory.py`, `tests/test_cli.py`, `tests/test_reviewer_context.py`, `src/reviewgraph/runner.py`, `src/reviewgraph/reviewer_context.py`, and the classifier evidence guards.
2. Add `tests/test_prompt_injection_memory.py` as the focused AUR-233 harness.
3. Prefer composing existing helpers over creating new product code. Add implementation only if the harness exposes a real contract gap.
4. Add tests proving untrusted top-level comments and review bodies remain passive and cannot satisfy `conversation_patterns` reviewer selection.
5. Add tests building `ReviewerPromptInput` from `ReviewerContextPackage` and asserting prompt-like untrusted memory bodies appear only in labeled `passive_data`, never in system/developer/task instruction fields.
6. Add tests asserting reviewer capability policy is not changed by untrusted memory and remains no GitHub writes, no repository access, no live provider calls, and only explicit config capabilities.
7. Add tests proving untrusted/passive memory cannot satisfy reviewer evidence requirements at the quality/classification boundary. Keep this as suppressed or localized fake-reviewer evidence, not candidate payload eligibility, approval, finalization, or posting behavior.
8. Add tests proving a trusted actionable comment can be included as cited memory data and can select a reviewer through `conversation_patterns`, while still going through the normal fake-reviewer quality/rendering path.
9. Add harness-output assertions against `ReviewerContextPackage.trace` and `ReviewerPromptInput.data` for included memory IDs, trust labels, passive/actionable state, prompt data roles, and truncation status. Do not require omitted-memory assertions unless the focused fixture actually omits memory.
10. Update durable docs only if the new harness clarifies a durable rule not already represented in PRD 0010, reviewer config, state graph, or harness engineering docs.
11. Validate focused and regression coverage, then use fresh subagents to review tests/docs/code until no material findings remain.
12. Commit implementation and evidence, comment on `AUR-233`, move it to `Done`, then return to `AUR-255` gate planning.

## Out Of Scope

- No live GitHub reads or writes.
- No live LLM calls.
- No reviewer tool execution.
- No approval UI, finalization, writer, payload-destination, or public-posting implementation.
- No general web-security scanner.
- No `.ws/` recreation.

## Validation Plan

Focused issue harness:

```bash
python -m pytest tests/test_prompt_injection_memory.py tests/test_reviewer_context.py tests/test_memory.py tests/test_cli.py -q
```

Boundary and regression checks:

```bash
python -m pytest tests/test_contract_boundaries.py tests/test_render.py tests/test_redaction.py -q
```

Full validation before Linear completion:

```bash
python -m pytest -q
python -m py_compile src/reviewgraph/*.py
python scripts/check_docs.py
git diff --check
```

## Completion Evidence To Collect

- Focused harness output.
- Boundary/regression output.
- Full validation output.
- Subagent review result with no material findings.
- Mapping from each `AUR-233` acceptance criterion to tests/code/docs.
- Confirmation `.ws/` is absent.
