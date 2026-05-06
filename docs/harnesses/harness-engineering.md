# Harness Engineering

Harnesses are the product contract in executable form. They prove ReviewGraph's graph state, reviewer boundaries, quality policy, and side-effect gates before live GitHub or live LLM behavior is trusted.

This document is not the implementation backlog. The detailed issue sequence lives in Linear. Use this guide to decide what proof a slice needs, what fixtures or fakes should exist, and which validation command an implementation agent should run before handing off work.

## Progressive Disclosure

Read only as deep as the task requires:

1. Product behavior: `docs/product/rules.md`
2. Graph shape and state: `docs/architecture/state-graph.md`
3. Reviewer context and prompts: `docs/prds/0010-agent-context-and-adapter-boundaries.md`
4. Quality policy: `docs/architecture/review-quality.md`
5. Side effects and approval: `docs/architecture/side-effects.md`
6. Harness proof: this document
7. Concrete task order: Linear issues in the ReviewGraph project

If a slice changes behavior, update the narrowest durable doc before or alongside the harness. Do not copy the Linear issue list into docs.

## Slice Proof Contract

Every implementation slice should be able to answer:

- Contract: which product, architecture, PRD, or decision doc defines the behavior?
- Fixture or fake: what deterministic input proves the behavior without live credentials?
- Harness: what command proves the slice?
- Expected artifact: what model, output file, trace, or fake transport result should exist?
- Side-effect proof: why no GitHub write, live LLM call, or secret-bearing trace can happen by default?
- Out of scope: what tempting adjacent behavior is explicitly deferred?

Use this shape for issue handoff comments, PR descriptions, and implementation notes. Keep it short enough that another agent can execute it without rereading the whole repository.

## Confidence Ladder

Use the lightest harness that proves the change. Move down the ladder only when the lower proof depends on the higher one.

1. Schema harness: config, PR context, graph state, findings, verdicts, approvals, payloads, gate results.
2. Fixture harness: static PR contexts with changed files, patches, comments, reviews, thread state, labels, and target SHAs.
3. Memory harness: fixture conversation becomes trusted/passive memory with resolved, unresolved, or unknown thread state.
4. Routing harness: reviewer selection records stage, trigger, risk, budget, and memory reasons.
5. Reviewer harness: fake reviewer outputs cover success, local notes, clarification, suggested replies, non-findings, malformed JSON, and failures.
6. Quality harness: reviewer output becomes postable findings, local notes, clarification requests, suggested replies, or suppressed output.
7. Graph harness: full LangGraph fixture run proves stage cursor, reviewer status, clarification resume, dry-run branch, and fail-closed branches.
8. Render harness: markdown and JSON output are redacted, stable enough for golden checks, and do not include public write pressure by default.
9. Approval/finalization harness: approval binds item selection, final payload hash, actor/permission snapshot, target freshness, marker reconciliation, and non-empty approved findings.
10. Fake writer harness: approved finalized top-level issue-comment payload creates at most one fake comment.
11. Live read smoke: opt-in read-only GitHub fetch with pagination and read-gap reporting.
12. Live LLM smoke: opt-in provider call after redaction, minimization, budget, and fake reviewer proof.
13. Live post smoke: manual-only disposable PR proof after dry-run, approval, freshness, actor, permission, hash, marker, and fake writer proof.

## Fixture Corpus

Maintain a manifest under `tests/fixtures/prs/` once implementation starts. The manifest is required before individual schema-valid fixture files are complete.

Required scenarios:

- `frontend-state-change`
- `security-sensitive-change`
- `docs-only-change`
- `mixed-risk-change`
- `ambiguous-logic-change`
- `breaking-api-change`
- `oversized-change`
- `stale-approval-change`
- `untrusted-comment-injection`
- `paginated-github-read`

Each manifest entry should name:

- Behavior proved by the fixture.
- Later harnesses or issue IDs that consume it.
- Required fields: metadata, labels, changed files, patches, base SHA, head SHA, merge-base SHA, diff basis, comments, review comments, reviews, and resolved/unresolved/unknown thread state when relevant.
- Whether it must include trusted memory, untrusted memory, secret-like content, pagination, target drift, or oversized context.

Default validation should prove every required scenario is named and every schema-valid fixture is consumed by at least one harness.

## Golden Output Rules

Golden tests should protect product behavior without freezing incidental wording.

- Prefer whole-object equality for typed models and machine JSON.
- Compare selected markdown sections, not full prompt-shaped prose.
- Never compare raw live LLM output in default tests.
- Redaction tests should assert secrets are absent from logs, traces, JSON errors, markdown, candidate payloads, final payloads, and provider-bound requests.
- Quality golden cases should include postable finding, local note, clarification request, suggested reply, suppressed non-finding, generic missing-test feedback, cross-file logic evidence, ambiguous logic intent, and generic architecture advice.
- Logic-review findings may cite cross-file evidence, but public locations must anchor to changed code that introduced or exposed the risk.

## Required Harness Families

### Contracts

- Config rejects unknown trigger fields, `triggers.stages`, unsupported MVP capabilities, and `verdict_power: approve`.
- `ReviewState` includes explicit gate state for read gaps, redaction, actor/permission, payload validation, marker reconciliation, finalization, approval, and writer result.
- Reviewer output cannot self-declare postability, blocking, final priority, or GitHub destination.

### Graph Cursor

- Initial cursor is `active_stage=None`, `stage_queue=["initial_triage","specialized_review","logic_review"]`, and `completed_stages=[]`.
- `advance_or_finish_stage` is the only node that mutates cursor fields.
- `clarification_review` is transient and never lives in the normal queue.
- Resume from clarification reruns only affected reviewers and does not pop unrelated stages.

### Memory And Trust

- PR comments and review threads become structured memory before reviewer fanout.
- Trusted humans, trusted bots, untrusted humans, unlisted bots, resolved threads, unresolved threads, and unknown thread state are distinct.
- Fixture and adapter memory inputs must include explicit actor type; missing or unknown actor type fails closed for trust.
- Untrusted comments are passive data. They cannot route reviewers, override prompts, satisfy evidence requirements, influence verdicts, approve posting, or enter public payload text in MVP.
- Prompt-injection memory harnesses must prove passive memory is labeled as data, not instructions, and that reviewer findings citing PR memory use explicit trusted-memory IDs rather than copied passive comment text.
- Unknown required thread state fails closed for actionability until a later policy proves otherwise.

### Reviewer Boundaries

- Reviewer adapters receive only `ReviewerContextPackage` and return structured `ReviewerResult`.
- Reviewer adapters do not receive GitHub transports, approval state, finalization code, payload builders, or writer clients.
- Fake and live reviewers share the same input/output contract.
- Capabilities default to `none` or `diff_context`; tool-using reviewers are future work. Any `tools` config accepted before that policy exists is inert metadata only and must not become callable handles, provider tool schemas, live-call budget, repository access, GitHub access, or write access.
- Prompt-input harnesses must prove instructions are separate from context data. Untrusted or passive memory is exposed only as labeled metadata in MVP; bodies must not enter prompt instructions or prompt data.
- Context-package traces must include selected reviewer config metadata, memory IDs, trust labels, resolved status, passive/actionable state, truncation status, omitted-context IDs, and capability policy.
- Provider-bound preview harnesses are non-live. They must prove minimized/redacted request text, redaction status, provider identity absent unless explicitly supplied by a future live caller, and separate `raw_provider_submission_enabled=false` and `raw_trace_persistence_enabled=false` defaults.
- Context-budget harnesses must prove changed-file, patch-byte, memory-byte, reviewer-count, and live-call caps before reviewer execution. Deferred reviewers are selected-then-skipped, become local notes, and their raw fixture output is not consumed.

### Review Quality

- Postable findings require changed-code evidence, an actionable scenario, graph-owned classification, and a precise changed-code location when available.
- Findings that cite `trusted_memory` must cite concrete actionable memory IDs; findings that cite unknown, passive, or untrusted memory are suppressed before rendering.
- Low-confidence or intent-dependent mergeability concerns become clarification requests.
- Generic, speculative, pre-existing, duplicate-without-new-analysis, or locationless issues are local notes or suppressed output.
- Suggested replies are local-only in MVP.
- Testing feedback is postable only with changed behavior, a concrete regression scenario, and identifiable missing coverage.

### Rendering And Redaction

- Dry-run output includes selected reviewer reasons, memory IDs, trust labels, resolved status, truncation status, local verdict, classified output, posting plan, and suppressed counts.
- Output distinguishes postable findings, local notes, clarification requests, suggested replies, and non-findings.
- Secret-like content is redacted before rendering, tracing, payload validation, live LLM requests, or posting.
- Candidate and final public payloads cannot contain untrusted comment bodies in MVP.
- Harnesses that model provider-bound payloads or trace/log persistence must record redaction status plus separate raw-provider and raw-trace opt-in flags.

### Side Effects

- Dry-run mode never invokes the writer.
- Rejected approval, missing approval, no approved findings, local-note-only, suggested-reply-only, suppressed-only, and clarification-only runs never invoke the writer.
- MVP payload kind is top-level `issue_comment`; formal PR reviews, inline comments, labels, statuses, `APPROVE`, and `REQUEST_CHANGES` are rejected.
- Approval binds approved item IDs, review target, final full comment hash, actor, permission, and checked-at time.
- Finalization re-checks target freshness, actor, permission, redaction, payload hash, marker reconciliation, and duplicate fingerprints before writer reachability.
- Marker reconciliation paginates existing comments, trusts only the approved actor or configured ReviewGraph bot, and fails closed on trusted malformed or conflicting markers for the same target.

## Tracer Bullets

Build these early vertical slices before expanding every policy:

1. Fixture dry run: fixture PR -> conversation memory -> always-on reviewer -> markdown/JSON -> no writer call.
2. Specialized reviewer: path, label, diff, or risk trigger introduces a focused reviewer with recorded stage and reason.
3. Logic ambiguity: logic reviewer returns a clarification request; graph stops before verdict/posting.
4. Clarification resume: supplied human answer is recorded and only affected reviewers rerun.
5. Quality gate: fake reviewer output splits into postable finding, local note, suggested reply, and suppressed non-finding.
6. Allowed post proof: item-approved top-level issue-comment payload calls the fake writer once; rejected or empty approval calls it zero times.
7. GitHub read proof: fake paginated GitHub read feeds the same graph path as fixtures.
8. Fail-closed proof: stale target, read gap, unknown actor, unknown permission, or marker conflict prevents writer reachability.

## Live API Discipline

Default commands must never require credentials or mutate external systems.

Recommended future commands:

```bash
pytest
pytest -m live_read
pytest -m live_llm
pytest -m live_post --requires-human-approval
```

Live read may run only after fake pagination and read-gap harnesses exist. Live LLM may run only after context package, redaction, minimization, budget, and fake reviewer harnesses exist. Live post may run only against a disposable allowlisted PR after fake writer, approval, freshness, actor/permission, final hash, and marker reconciliation harnesses exist.

## Documentation Contract Check

For documentation and planning slices, run:

```bash
python scripts/check_docs.py
```

This verifies the docs index points at required architecture, PRD, decision, harness, and implementation-plan entry points, and that the implementation plan and agent instructions preserve core MVP constraints.

When validating a Linear issue queue, export the ordered Linear issues into the canonical JSON shape described in `docs/implementation/README.md`, then run:

```bash
python scripts/check_docs.py --backlog-export path/to/linear-backlog-export.json
```

The backlog check is intentionally export-based and read-only. It does not make repository docs the backlog; it proves that a Linear-derived queue has no duplicate active IDs, missing blocker references, cycles, or blocker-after-dependent inversions.
