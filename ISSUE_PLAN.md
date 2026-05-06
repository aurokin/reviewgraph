# ISSUE PLAN: AUR-191 Validate Example Reviewer Config

Active issue plan for `AUR-191` / `RG-002: Validate Example Reviewer Config`.

## Linear Snapshot

- Issue: `AUR-191`
- Status at start: `In Progress`
- Milestone: `PRD 0003: Contracts`
- Direct blocker context: this stale blocker must be closed before `AUR-254` can complete.
- Comments at start: none.
- Harness from Linear: `python -m pytest tests/test_config.py`

## Goal

Verify and, if needed, complete reviewer config validation for the shipped example config, stage eligibility, trigger fields, verdict power, and MVP capability rules.

This appears already implemented by the AUR-312 contract/config work. Treat this as a verification-only closeout unless the harness exposes a missing acceptance criterion.

## Acceptance Mapping

- `examples/review_agents.example.yaml` parses successfully:
  - Covered by `tests/test_config.py::test_packaged_and_example_reviewer_configs_validate`.
- Unknown trigger fields are rejected:
  - Covered by `tests/test_config.py::test_invalid_reviewer_config_fails_clearly`.
- `triggers.stages` is rejected and top-level `stages` is accepted:
  - Rejection covered by `tests/test_config.py::test_invalid_reviewer_config_fails_clearly`.
  - Acceptance covered by `tests/test_config.py::test_packaged_and_example_reviewer_configs_validate` and `_valid_config`.
- `verdict_power: approve` is rejected for MVP:
  - Covered by `tests/test_config.py::test_invalid_reviewer_config_fails_clearly`.
- Unsupported capabilities such as `read_repo` are rejected for MVP:
  - Covered by `tests/test_config.py::test_invalid_reviewer_config_fails_clearly`.

## Implementation Plan

1. Run the focused harness:
   - `python -m pytest tests/test_config.py`
2. Run the relevant regression/static checks:
   - `python -m pytest tests/test_models.py tests/test_contract_boundaries.py tests/test_config.py`
   - `python -m py_compile src/reviewgraph/*.py`
   - `python scripts/check_docs.py`
   - `git diff --check`
3. Use a fresh subagent review to verify the acceptance mapping is complete and this is safe to close without code changes.
4. If no material findings remain, commit this issue plan, comment evidence on Linear, and mark `AUR-191` Done.

## Out Of Scope

- No reviewer execution.
- No GitHub access.
- No prompt execution.
- No live LLM behavior.
- No config features beyond the MVP contract already documented.
