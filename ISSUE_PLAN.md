# ISSUE PLAN: AUR-190 Project Skeleton And Empty Test Harness

Active issue plan for `AUR-190` / `RG-001: Project Skeleton And Empty Test Harness`.

## Linear Snapshot

- Issue: `AUR-190`
- Status at start: `Backlog`
- Milestone: `PRD 0003: Contracts`
- Blocks: `AUR-230`, `AUR-192`, `AUR-191`, `AUR-254`
- Blocked by: `AUR-253` (already Done)
- Comments at start: none checked in this pass
- Harness from Linear: `python -m pytest`

## Goal

Verify that the repo has the minimal Python package skeleton and runnable test harness required by downstream PRD 0003 contract work.

This issue is already satisfied by the current repository state. No product behavior, live GitHub integration, live LLM integration, graph runtime, or fixture parsing changes are needed for this issue.

## Acceptance Mapping

- Python package skeleton exists under `src/reviewgraph`: `__init__.py`, CLI/runtime modules, fixture/config/model modules.
- Default test command discovers and runs tests: `python -m pytest` currently collects and passes the full suite.
- Package metadata exists in `pyproject.toml`, with package discovery, console script, package data, pytest config, and the runtime/test dependencies needed by the current fixture-based slices.
- No live GitHub or live LLM dependency is required for tests.

## Validation

```bash
python -m pytest
python -m py_compile src/reviewgraph/*.py
python scripts/check_docs.py
git diff --check
```

## Completion Evidence To Comment On Linear

- `pyproject.toml` package metadata and pytest config are present.
- `src/reviewgraph/__init__.py` and package modules are present.
- Full suite passes.
- Compile/docs/diff checks pass.
- No live GitHub or live LLM dependency is required.
