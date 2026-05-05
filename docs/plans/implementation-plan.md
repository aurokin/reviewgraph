# ReviewGraph MVP Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Build a CLI LangGraph PR review orchestrator that reads a PR, selects configured reviewer agents, runs deterministic/fake or live LLM reviewers, renders findings, and dry-runs GitHub posting behind approval.

**Architecture:** Keep GitHub access, LLM calls, LangGraph state, reviewer prompts, and side effects behind separate adapters. Prove behavior with fixtures before live APIs.

**Tech Stack:** Python, LangGraph, LangChain model integrations, Pydantic, PyYAML, Typer or argparse, pytest.

---

## Phase 1 — Contracts and fixtures

### Task 1: Create Python project skeleton

**Objective:** Add package layout and tooling config.

**Files:**
- Create: `pyproject.toml`
- Create: `src/reviewgraph/__init__.py`
- Create: `tests/`

**Verification:** `python -m pytest` discovers an empty test suite or placeholder passing test.

### Task 2: Define state and schema models

**Objective:** Add typed models for PR context, config, selected reviewers, findings, verdicts, and approval decisions.

**Files:**
- Create: `src/reviewgraph/models.py`
- Test: `tests/test_models.py`

**Verification:** model tests validate happy path and invalid severity/confidence values.

### Task 3: Add reviewer config loader

**Objective:** Load YAML config and validate triggers.

**Files:**
- Create: `src/reviewgraph/config.py`
- Create: `review_agents.example.yaml`
- Test: `tests/test_config.py`

**Verification:** invalid trigger fields fail with clear errors.

### Task 4: Add PR fixture format

**Objective:** Create fixture PR contexts for routing tests.

**Files:**
- Create: `tests/fixtures/prs/security-sensitive-change.json`
- Create: `tests/fixtures/prs/frontend-state-change.json`
- Create: `tests/fixtures/prs/docs-only-change.json`

**Verification:** fixtures parse into `PullRequestContext`.

## Phase 2 — Routing and policy

### Task 5: Implement reviewer selection

**Objective:** Select reviewers based on always/path/label/diff/risk triggers.

**Files:**
- Create: `src/reviewgraph/routing.py`
- Test: `tests/test_routing.py`

**Verification:** each fixture selects expected reviewers and records reasons.

### Task 6: Implement finding normalization

**Objective:** Convert reviewer JSON into validated finding objects.

**Files:**
- Create: `src/reviewgraph/findings.py`
- Test: `tests/test_findings.py`

**Verification:** malformed findings are rejected or repaired according to policy.

### Task 7: Implement dedupe and verdict policy

**Objective:** Merge duplicate findings and recommend comment/request-changes/dry-run verdict.

**Files:**
- Create: `src/reviewgraph/policy.py`
- Test: `tests/test_policy.py`

**Verification:** low-confidence findings cannot request changes.

## Phase 3 — Graph and adapters

### Task 8: Add fake GitHub adapter

**Objective:** Let graph runs use fixture PRs as GitHub context.

**Files:**
- Create: `src/reviewgraph/github.py`
- Test: `tests/test_github_fixture_adapter.py`

**Verification:** adapter returns fixture context by PR ref.

### Task 9: Add fake LLM reviewer adapter

**Objective:** Run reviewers deterministically for tests.

**Files:**
- Create: `src/reviewgraph/reviewers.py`
- Test: `tests/test_reviewers_fake.py`

**Verification:** fake reviewer results normalize into expected findings.

### Task 10: Build LangGraph workflow

**Objective:** Wire fetch, route, review, normalize, dedupe, render, approve, and emit nodes.

**Files:**
- Create: `src/reviewgraph/graph.py`
- Test: `tests/test_graph.py`

**Verification:** full fixture run reaches dry-run output with no side effects.

## Phase 4 — CLI and live-read

### Task 11: Add dry-run CLI

**Objective:** Review a PR fixture or live PR and emit markdown/JSON.

**Files:**
- Create: `src/reviewgraph/cli.py`
- Test: `tests/test_cli.py`

**Verification:** CLI dry run writes expected outputs and never calls writer.

### Task 12: Add live GitHub read adapter

**Objective:** Fetch PR metadata/files/diff via GitHub API or `gh`.

**Files:**
- Modify: `src/reviewgraph/github.py`
- Test: `tests/test_github_live_read_contract.py`

**Verification:** live tests are opt-in and skipped by default.

### Task 13: Add live LLM adapter

**Objective:** Use configured API provider for real reviewer calls.

**Files:**
- Create: `src/reviewgraph/llm.py`
- Modify: `src/reviewgraph/reviewers.py`

**Verification:** fake adapter remains default for tests; live adapter is opt-in.

## Phase 5 — Approval-gated posting

### Task 14: Add approval gate

**Objective:** Require explicit approval before side effects.

**Files:**
- Create: `src/reviewgraph/approval.py`
- Test: `tests/test_approval.py`

**Verification:** rejection never calls writer; approval passes exact payload.

### Task 15: Add GitHub comment writer

**Objective:** Post a top-level review comment only after approval.

**Files:**
- Modify: `src/reviewgraph/github.py`
- Test: `tests/test_github_writer.py`

**Verification:** writer tests use a fake transport; live post smoke is manual only.
