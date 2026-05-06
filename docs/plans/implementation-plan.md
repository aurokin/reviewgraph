# ReviewGraph MVP Implementation Plan

**Goal:** Build a CLI LangGraph PR review orchestrator that reads a PR, builds shared conversation memory from PR comments, introduces reviewer agents at explicit graph stages, runs deterministic/fake or live reviewer contexts, classifies review output for quality, renders findings/notes/clarification requests, and dry-runs GitHub posting behind item-level approval.

**Architecture:** Keep GitHub access, PR conversation memory, LLM calls, LangGraph state, reviewer prompts, and side effects behind separate adapters. Prove behavior with fixtures before live APIs.

**Tech Stack:** Python, LangGraph, LangChain model integrations, Pydantic, PyYAML, Typer or argparse, pytest.

---

## Implementation posture

Start with tracer bullets, not a complete policy engine. The first useful implementation should run a fixture PR through the graph, select reviewers with staged reasons, emit markdown/JSON, classify output into postable and non-postable items, and prove no GitHub writer is called. Reviewer context boundaries and clarification state are part of the early graph shape, not late integration polish. Answered clarification resume belongs to the fixture graph contract; live reads, live LLM calls, and approval-gated posting come after the fixture graph proves those contracts.

The executable backlog lives in Linear. Treat this plan as the durable sequencing narrative, not the complete ticket list. Every implementation issue should identify the narrowest contract doc, the deterministic fixture or fake, the harness command, the expected artifact, and the explicit out-of-scope boundary before code lands.

## Implemented orchestration checkpoint

The PRD 0004 graph-orchestration slice now proves these contracts in fixtures and harnesses:

- empty LangGraph dry-run initialization with no-writer proof;
- normal stage cursor state and transition traces;
- active-stage reviewer selection for always/path/diff/label/risk/size triggers;
- deterministic risk and size state before risk-gated selection;
- reviewer run keys, run status, completion/skipped suppression, retry selection, and retry exhaustion;
- deterministic fake reviewer execution behind `ReviewerContextPackage`;
- required fake reviewer failure as graph-owned fail-closed state with dry-run output preserved;
- optional fake reviewer failure as non-terminal reviewer-result error plus local note.

## Implemented review-quality checkpoint

The PRD 0005 review-quality slice now proves these contracts in fixtures and harnesses:

- reviewer output normalizes into typed raw artifacts before quality policy runs;
- malformed selected-reviewer output gets one deterministic fake repair attempt before required/optional failure policy;
- quality classification separates postable findings, local notes, clarification requests, suggested replies, and suppressed non-findings;
- postable findings require changed-code evidence, actionable scenarios, safe provenance, concise public shape, graph-owned priority/fingerprint/blocking decisions, and changed-code locations when available;
- testing feedback uses the stricter changed-behavior, concrete-regression-scenario, and missing-coverage-target bar;
- diff anchors are derived and validated for dry-run inline candidates without enabling inline posting;
- blocking clarification requests stop posting and answered clarifications resume only affected reviewers through transient `clarification_review`;
- optional reviewer failures produce partial-review metadata without blocking post eligibility, while required failures remain fail-closed;
- local verdict policy is private state and does not imply GitHub review events or public request-changes wording.

Remaining graph work is intentionally staged in later PRDs: live GitHub reads, live LLM reviewer execution, approval/finalization, and writer behavior.

## MVP constraints

- Dry-run is the default behavior.
- Reviewer output becomes structured findings, local notes, clarification requests, suggested replies, or suppressed non-findings before rendering.
- The local verdict is separate from public GitHub text.
- Side effects are last, behind rendering, item-level approval, final payload validation, target freshness, actor/permission proof, redaction, and marker reconciliation.
- MVP writes only an approved top-level PR comment.
- Formal GitHub review submission, inline comments, approvals, and request-changes writes are out of scope for MVP.
- Fixture PRs, fake GitHub adapters, and fake reviewer adapters prove behavior before live integrations.
- Live read, live LLM, and live post behavior are opt-in.
- Linear is the executable backlog; repository docs are the durable product, architecture, harness, and decision contracts.

## Phase 1 — Contracts and fixtures

### Task 1: Create Python project skeleton

**Objective:** Add package layout and tooling config.

**Files:**
- Create: `pyproject.toml`
- Create: `src/reviewgraph/__init__.py`
- Create: `tests/`

**Verification:** `python -m pytest` discovers an empty test suite or placeholder passing test.

### Task 2: Define state and schema models

**Objective:** Add typed models for run mode, review targets, posting targets, PR context, conversation memory, config, selected reviewers, reviewer run keys, risk assessment, findings, local notes, suggested replies, suppressed outputs, clarification requests, posting plans, verdicts, approvals, and writer results.

**Files:**
- Create: `src/reviewgraph/models.py`
- Test: `tests/test_models.py`

**Verification:** model tests validate happy path and invalid severity/confidence/priority values.

### Task 3: Add reviewer config loader

**Objective:** Load YAML config and validate triggers.

**Files:**
- Create: `src/reviewgraph/config.py`
- Create: `examples/review_agents.example.yaml`
- Test: `tests/test_config.py`

**Verification:** invalid trigger fields, `triggers.stages`, `verdict_power: approve`, and unsupported reviewer capabilities fail with clear errors; `examples/review_agents.example.yaml` validates.

### Task 4: Add PR fixture and conversation format

**Objective:** Create fixture PR contexts for routing, memory, and graph tests.

**Files:**
- Create: `tests/fixtures/prs/security-sensitive-change.json`
- Create: `tests/fixtures/prs/frontend-state-change.json`
- Create: `tests/fixtures/prs/docs-only-change.json`
- Create: `tests/fixtures/prs/mixed-risk-change.json`
- Create: `tests/fixtures/prs/ambiguous-logic-change.json`
- Create: `tests/fixtures/prs/breaking-api-change.json`
- Create: `tests/fixtures/prs/oversized-change.json`
- Create: `tests/fixtures/prs/stale-approval-change.json`
- Create: `tests/fixtures/prs/untrusted-comment-injection.json`
- Create: `tests/fixtures/prs/paginated-github-read.json`

**Verification:** fixtures parse into `PullRequestContext` with comments, review threads, base/head SHAs, merge-base SHAs, diff basis, trust metadata, and stable review target metadata.

### Task 5: Build PR conversation memory

**Objective:** Convert fixture comments and review threads into structured graph memory with trusted author metadata, seen/resolved status, and passive untrusted-memory handling.

**Files:**
- Create: `src/reviewgraph/memory.py`
- Test: `tests/test_memory.py`

**Verification:** resolved and unresolved threads are preserved, trusted/untrusted authors are distinguished, reviewer-visible memory is deterministic, and untrusted comments cannot become instructions, routing triggers, verdict evidence, approval input, or public payload text.

### Task 6: Add review target and context budget contracts

**Objective:** Bind every run to immutable base/head/diff target metadata and bounded reviewer context.

**Files:**
- Create: `src/reviewgraph/targets.py`
- Create: `src/reviewgraph/context_budget.py`
- Test: `tests/test_targets.py`
- Test: `tests/test_context_budget.py`

**Verification:** oversized fixtures receive truncation markers and stale target metadata prevents post eligibility.

### Task 7: Define reviewer context package and adapter boundary

**Objective:** Define the scoped package that every reviewer receives before any reviewer adapter is implemented.

**Files:**
- Create: `src/reviewgraph/reviewer_context.py`
- Create: `src/reviewgraph/prompts/`
- Test: `tests/test_reviewer_context.py`
- Test: `tests/test_adapter_boundaries.py`

**Verification:** context packages include target metadata, active stage, selected reviewer metadata, bounded diff context, trusted memory references, passive untrusted-memory metadata, truncation notes, capability policy, model/tool config, and redaction status. Boundary tests fail if reviewer or prompt modules import GitHub write transports, approval code, payload builders, or global GitHub clients.

## Phase 2 — Routing and policy

### Task 8: Implement staged reviewer selection

**Objective:** Select reviewers based on stage, always/path/label/diff/conversation/risk triggers.

**Files:**
- Create: `src/reviewgraph/routing.py`
- Test: `tests/test_routing.py`

**Verification:** each fixture selects expected reviewers and records stage plus reasons. `conversation_patterns` match only trusted actionable memory and untrusted comments cannot select reviewers.

### Task 9: Implement reviewer output normalization

**Objective:** Convert reviewer JSON into validated finding objects or clarification requests.

**Files:**
- Create: `src/reviewgraph/findings.py`
- Test: `tests/test_findings.py`

**Verification:** malformed findings are rejected or repaired according to policy.

### Task 10: Implement review quality classification

**Objective:** Classify normalized reviewer output into postable findings, local notes, clarification requests, suggested replies, or suppressed non-findings.

**Files:**
- Create: `src/reviewgraph/quality.py`
- Test: `tests/test_quality.py`

**Verification:** Codex-inspired eligibility rules suppress generic, speculative, pre-existing, self-declared blocking, and locationless postable findings. Logic-review golden cases cover cross-file invariant evidence, changed-line anchoring, ambiguity-to-clarification, and suppression of generic architecture advice.

### Task 11: Implement ranking and verdict policy

**Objective:** Rank quality-classified findings and recommend local comment/request-changes/dry-run verdict.

**Files:**
- Create: `src/reviewgraph/verdict.py`
- Test: `tests/test_verdict.py`

**Verification:** low-confidence and ambiguous findings cannot request changes; local request-changes does not imply GitHub `REQUEST_CHANGES`.

### Task 12: Add posting plan and approval proof models

**Objective:** Build item-level posting plans, candidate payload hashes, approved payload hashes, and public/private verdict separation before any live adapter exists.

**Files:**
- Create: `src/reviewgraph/posting.py`
- Create: `src/reviewgraph/approval.py`
- Test: `tests/test_posting.py`
- Test: `tests/test_approval.py`

**Verification:** dry-run output renders candidate payloads; rejected approval calls no writer; request-changes wording is excluded from public markdown unless explicitly approved.

## Phase 3 — Graph and adapters

### Task 13: Add fake GitHub adapter

**Objective:** Let graph runs use fixture PRs as GitHub context.

**Files:**
- Create: `src/reviewgraph/github.py`
- Test: `tests/test_github_fixture_adapter.py`

**Verification:** adapter returns fixture context by PR ref.

### Task 14: Add fake reviewer adapter

**Objective:** Run reviewers deterministically for tests.

**Files:**
- Create: `src/reviewgraph/reviewers.py`
- Test: `tests/test_reviewers_fake.py`

**Verification:** fake reviewer results normalize and classify into expected postable findings, local notes, suppressed outputs, suggested replies, non-findings, malformed JSON, optional failures, required failures, or clarification requests. Reviewer adapters receive only scoped reviewer context packages and no GitHub transports.

### Task 15: Add clarification resume gate

**Objective:** Stop for human clarification when needed and resume only affected reviewers after answers are supplied.

**Files:**
- Create: `src/reviewgraph/clarification.py`
- Test: `tests/test_clarification.py`

**Verification:** clarification request prevents posting; answered clarification resumes the recorded reviewer/stage; unanswered ambiguity cannot produce a blocking verdict; the graph does not pop unrelated queued stages or rerun unrelated completed reviewers.

### Task 16: Build LangGraph workflow

**Objective:** Wire fetch, memory, target resolution, context budgeting, staged routing, review, normalization, quality classification, clarification, ranking, posting plan, render, approve, and emit nodes.

**Files:**
- Create: `src/reviewgraph/graph.py`
- Test: `tests/test_graph.py`

**Verification:** full fixture run reaches dry-run output with no side effects; dry-run mode cannot reach writer branch; ambiguous fixture stops with a clarification request; stale target fixture prevents posting.

## Phase 4 — CLI and live-read

### Task 17: Add dry-run CLI

**Objective:** Review a PR fixture or live PR and emit markdown/JSON postable findings, local notes, suppressed counts, selected reviewers, conversation memory summary, and clarification requests.

**Files:**
- Create: `src/reviewgraph/cli.py`
- Test: `tests/test_cli.py`

**Verification:** CLI dry run writes expected outputs and never calls writer.

### Task 18: Add live GitHub read adapter

**Objective:** Fetch PR metadata/files/diff/comments/review threads via GitHub API or `gh`, including pagination, trusted author, resolved-thread, authenticated actor, and required permission data.

**Files:**
- Modify: `src/reviewgraph/github.py`
- Test: `tests/test_github_live_read_contract.py`

**Verification:** live tests are opt-in and skipped by default; fake transport tests prove all pages are fetched for files, issue comments, review comments, reviews, and thread state before truncation is applied; unknown thread state is modeled distinctly and is non-actionable by default; unknown actor or insufficient/unknown permissions fail closed.

### Task 19: Add live LLM adapter

**Objective:** Use configured API provider for real reviewer calls.

**Files:**
- Create: `src/reviewgraph/llm.py`
- Modify: `src/reviewgraph/reviewers.py`

**Verification:** fake adapter remains default for tests; live adapter is opt-in; provider/model are recorded; provider-bound payloads are minimized/redacted by default; redaction tests cover live LLM request payloads, logs, traces, JSON errors, and default output.

## Phase 5 — Approval-gated posting

### Task 20: Add idempotent GitHub comment writer

**Objective:** Post a top-level PR comment only after fresh-target, actor/permission, redaction, marker-reconciliation, and final-payload-hash approval checks.

**Files:**
- Modify: `src/reviewgraph/github.py`
- Test: `tests/test_github_writer.py`

**Verification:** writer tests use a fake transport; live post smoke is manual only; `COMMENT` reviews, `REQUEST_CHANGES`, and `APPROVE` remain unsupported; approval fails if the GitHub actor changes before write; target freshness includes merge-base SHA when available; marker reconciliation trusts only approved actor/configured bot comments; retry after timeout or process restart discovers the embedded ReviewGraph marker and creates at most one top-level comment for the approved payload.
