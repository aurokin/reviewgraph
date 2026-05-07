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
- Quality golden cases should include postable finding, medium-confidence non-blocking finding, low-confidence suppression, local note, clarification request, unsafe clarification provenance suppression, suggested reply, suppressed non-finding, generic missing-test feedback, cross-file logic evidence, ambiguous logic intent, generic architecture advice, unsafe memory provenance suppression, omitted-context suppression, and multi-line finding preservation.
- Logic-review findings may cite cross-file evidence, but public locations must anchor to changed code that introduced or exposed the risk.

## Required Harness Families

### Contracts

- Config rejects unknown trigger fields, `triggers.stages`, unsupported MVP capabilities, and `verdict_power: approve`.
- `ReviewState` includes explicit gate state for read gaps, redaction, actor/permission, payload validation, marker reconciliation, finalization, approval, and writer result.
- Reviewer output cannot self-declare postability, blocking, final priority, or GitHub destination.
- Actor/permission gate harnesses must prove endpoint-specific issue-comment write ability with fake permission probes, canonical `ReviewTarget` binding, deterministic checked-at freshness, stable fail-closed reason codes, output-only compatibility permission derivation, and redacted transport summaries. They must also prove the permission module does not import live GitHub, approval, finalization, graph post-mode, posting, or writer boundaries.

### Graph Cursor

- Initial cursor is `active_stage=None`, `stage_queue=["initial_triage","specialized_review","logic_review"]`, and `completed_stages=[]`.
- `advance_or_finish_stage` is the only node that mutates cursor fields.
- `clarification_review` is transient and never lives in the normal queue.
- Resume from clarification reruns only affected reviewers and does not pop unrelated stages.
- PRD 0004 implemented normal-stage cursor traces. PRD 0005 adds clarification stop and resume primitives: `tests/test_clarification.py` is the focused stop-state harness for pending IDs, status, blocking IDs, local-only posting-plan conversion, non-blocking clarification behavior, and unsafe clarification suppression. `tests/test_clarification_resume.py` is the focused resume harness for answer ingestion, one-shot ready IDs, transient `clarification_review`, clarification-bound run keys, and stale pending IDs that no longer block posting.

### Memory And Trust

- PR comments and review threads become structured memory before reviewer fanout.
- Trusted humans, trusted bots, untrusted humans, unlisted bots, resolved threads, unresolved threads, and unknown thread state are distinct.
- Fixture and adapter memory inputs must include explicit actor type; missing or unknown actor type fails closed for trust.
- Untrusted comments are passive memory. They cannot route reviewers, override prompts, satisfy evidence requirements, influence verdicts, approve posting, or enter public payload text in MVP.
- GitHub transport payloads cannot self-declare trust or provenance. `tests/test_github_memory_trust.py` proves owner/member/collaborator and configured-operator trust, default-deny bot trust, exact bot matching, source-provider provenance, collision-safe seen-state IDs, resolved/unknown thread passivity, passive-body suppression, and local-verdict suppression. `tests/test_conversation_routing.py` proves trusted actionable memory can route reviewers through `conversation_patterns` only with matched-memory reason metadata, while untrusted, unlisted bot, resolved, and unknown-thread memory cannot route.
- Prompt-injection memory harnesses must prove passive memory is labeled metadata, not instructions or prompt body text, and that reviewer findings citing PR memory use explicit trusted-memory IDs rather than copied passive comment text.
- Unknown required thread state fails closed for actionability until a later policy proves otherwise.

### GitHub Read

- Fake GitHub read is the first adapter proof. `tests/test_github_fake_read.py` covers `owner/repo#number` and GitHub PR URL parsing, metadata/files reads, `ReviewTarget` parity, metadata extras, resource coverage, required read gaps for out-of-scope resources, changed-line metadata, anchor-unavailable metadata, redacted result serialization, and read-only transport calls.
- `tests/test_github_read_gaps.py` covers required and optional GitHub read gaps, stable failure classification, targetless pre-metadata fetch failure rendering, graph error generation, read-gap versus truncation separation, descriptor-only later-page gap fixtures, and redacted dry-run output.
- `tests/test_github_pagination.py` covers fake pagination for files, issue comments, review comments, reviews, and thread state. It must assert exact resource call order, cursor propagation, complete coverage, page-failure fail-closed state, page diagnostics, orphan review-comment thread-state gaps, adapter rejection of inbound trust labels, GitHub actor-policy trust after memory construction, and that pagination completes before truncation.
- The metadata/files-only result is not graph-complete context. Comments, reviews, review comments, and thread state must be fetched and paginated by later PRD 0006 harnesses before GitHub PR dry-run can be treated as complete.
- Changed-line metadata from GitHub reads must satisfy the same structural protocol used by quality and diff-anchor code. Parseable modified, added, and renamed patches expose target hunk ranges when the hunk has target-side additions; unsupported or unavailable patches degrade explicitly instead of producing false ranges.
- GitHub-read boundary tests must prove the fake read adapter does not directly or transitively import live network clients, approval/finalization code, posting payload builders, or writer modules.
- Read-gap policy tests must stay descriptor-only until pagination is implemented. AUR-247 may prove that omitted page-2 content would have affected routing, trust, or redaction, but it must not implement real page traversal.
- `tests/test_live_read_smoke.py` owns the PRD 0006 live-read smoke contract. Default collection skips `@pytest.mark.live_read` unless `REVIEWGRAPH_LIVE_READ=1`; unmarked tests prove prerequisite blockers, read-only `gh api` REST command construction, redacted artifact shape, and writer-boundary imports without network or credentials.
- Live smoke execution requires `REVIEWGRAPH_LIVE_READ=1`, `REVIEWGRAPH_LIVE_READ_PR`, `gh`, and a token from `GITHUB_TOKEN`, `GH_TOKEN`, or `gh auth token`. `REVIEWGRAPH_LIVE_READ_OUT` may point at a local JSON artifact path. Missing prerequisites are blocked/skipped results, not default-test failures.
- PRD 0006 live smoke is REST-only. If review-comment thread state cannot be fetched in the contract shape, the result must fail closed with a read gap instead of marking memory actionable. GraphQL thread-state completion is future work and needs its own read-only policy and harness.

### Reviewer Boundaries

- Reviewer adapters receive only `ReviewerContextPackage` and return structured `ReviewerResult`.
- Reviewer adapters do not receive GitHub transports, approval state, finalization code, payload builders, or writer clients.
- Fake and live reviewers share the same input/output contract.
- Fake reviewer harnesses must cover completed output, explicit required failure, explicit optional failure, valid and malformed raw strings, malformed mappings, deterministic repair success, deterministic repair failure, non-mapping repair-envelope audit capture, and missing, mismatched, or extra repair-envelope fields. Repair success and failure use the strict fake repair envelope; direct legacy mapping output is not repaired. Required explicit failures and required unrepaired selected-output failures are graph errors; optional failures are reviewer-result errors plus local notes.
- Capabilities default to `none` or `diff_context`; tool-using reviewers are future work. Any `tools` config accepted before that policy exists is inert metadata only and must not become callable handles, provider tool schemas, live-call budget, repository access, GitHub access, or write access.
- Prompt-input harnesses must prove instructions are separate from context data. Untrusted or passive memory is exposed only as labeled metadata in MVP; bodies must not enter prompt instructions or prompt data.
- Context-package traces must include selected reviewer config metadata, memory IDs, trust labels, resolved status, passive/actionable state, truncation status, omitted-context IDs, and capability policy.
- Provider-bound preview harnesses are non-live. They must prove minimized/redacted request text, redaction status, provider identity absent unless explicitly supplied by a future live caller, and separate `raw_provider_submission_enabled=false` and `raw_trace_persistence_enabled=false` defaults.
- Context-budget harnesses must prove changed-file, patch-byte, memory-byte, reviewer-count, and live-call caps before reviewer execution. Deferred reviewers are selected-then-skipped, become local notes, and their raw fixture output is not consumed.

### Review Quality

Focused PRD 0005 harness bundle:

```bash
python -m pytest tests/test_findings.py tests/test_reviewer_json_repair.py tests/test_quality.py tests/test_diff_anchor.py tests/test_quality_testing.py tests/test_clarification.py tests/test_clarification_resume.py tests/test_optional_reviewer_failure.py tests/test_verdict.py -q
```

- Postable findings require changed-code evidence, an actionable scenario, graph-owned classification, and a precise changed-code location when available. `tests/test_quality.py` owns the classifier boundary from typed `ReviewerResult` plus changed files, memory references, and omitted-context IDs into postable findings, local notes, clarification requests, suggested replies, and suppressed outputs.
- Diff-anchor harnesses should prove fixture-derived anchors bind to the current target head SHA, stay inside one changed range including `line_end`, preserve rename metadata, skip unavailable patches or unsupported statuses, render machine-visible anchor JSON, and keep explicit inline candidates dry-run-only/non-public.
- Findings that cite `trusted_memory` must cite concrete actionable memory IDs; findings that cite unknown, passive, or untrusted memory are suppressed before rendering.
- Medium-confidence concrete findings may remain postable only when non-blocking; low-confidence or intent-dependent mergeability concerns become clarification requests or suppressed output.
- Generic, speculative, pre-existing, reviewer-declared duplicate, omitted-context-dependent, or locationless issues are local notes or suppressed output.
- Suggested replies are local-only in MVP.
- Testing feedback is postable only with changed behavior, a concrete regression scenario, and identifiable missing coverage. `tests/test_quality_testing.py` is the focused testing-quality harness; it proves concrete testing findings are postable, generic or vague missing-test advice is suppressed, explicit testing local notes stay local-only, and suppressed testing output cannot enter candidate payload previews.

### Rendering And Redaction

- Dry-run output includes selected reviewer reasons, memory IDs, trust labels, resolved status, truncation status, local verdict, classified output, posting plan, and suppressed counts.
- Output distinguishes postable findings, local notes, clarification requests, suggested replies, and non-findings.
- Secret-like content is redacted before rendering, tracing, payload validation, live LLM requests, or posting.
- Candidate and final public payloads cannot contain untrusted comment bodies in MVP.
- Harnesses that model provider-bound payloads or trace/log persistence must record redaction status plus separate raw-provider and raw-trace opt-in flags.

### Side Effects

- Dry-run mode never invokes the writer.
- Rejected approval, missing approval, no approved findings, local-note-only, suggested-reply-only, suppressed-only, and clarification-only runs never invoke the writer.
- Required reviewer failure runs never invoke the writer: dry-run JSON must expose the graph error, failed reviewer result/status, no candidate payload, and local-only posting plan.
- Optional reviewer failure runs remain partial local reviews: `tests/test_optional_reviewer_failure.py` proves the failed optional reviewer is recorded in partial-review metadata, other reviewer output still classifies, later stages continue, and optional failure alone does not block post eligibility.
- Local verdict runs are private policy checks: `tests/test_verdict.py` proves ambiguity cannot become request-changes, graph errors disable post eligibility, dry-run output renders the local verdict, and GitHub payload previews remain issue comments without public request-changes wording by default.
- MVP payload kind is top-level `issue_comment`; formal PR reviews, inline comments, labels, statuses, `APPROVE`, and `REQUEST_CHANGES` are rejected.
- Non-interactive post mode fails closed before approval input and before final payload construction in CI, webhook, config-only, and non-TTY CLI contexts.
- Approval binds approved item IDs, review target, final full comment hash, actor, endpoint-specific issue-comment permission, and checked-at time.
- Actor/permission harnesses cover authenticated actor, credential principal/source, repo or installation permission, issue-comment endpoint write ability, role/token mismatch, stale-cache rejection, transport failures, redacted summaries, and stable reason codes.
- Actor/permission finalization preflight re-evaluates the current proof from a raw probe and explicit evaluated-at time, rejects cached pass objects, binds the proof to the approval snapshot, rejects checked-at regression, records redacted transport summaries, and never implies full payload finalization or writer reachability by itself.
- Finalization re-checks target freshness, actor, endpoint permission, redaction, payload hash, marker reconciliation, and duplicate fingerprints before writer reachability.
- Target freshness harnesses cover changed target fields plus timeout, rate limit, forbidden, not found, unavailable service, malformed response, stale-cache rejection, and proof that unknown freshness never reaches final payload construction or writer calls.
- Marker reconciliation paginates existing comments, trusts only the approved actor or configured ReviewGraph bot, reconciles trusted identical duplicate markers without another post, and fails closed on trusted malformed or conflicting markers for the same target.
- Writer idempotency harnesses prove retry safety for one approved run/retry sequence. Cross-process duplicate prevention is deferred unless an external lock/storage design is added.

## Tracer Bullets

Build these early vertical slices before expanding every policy:

1. Fixture dry run: fixture PR -> conversation memory -> always-on reviewer -> markdown/JSON -> no writer call.
2. Specialized reviewer: path, label, diff, or risk trigger introduces a focused reviewer with recorded stage and reason.
3. Logic ambiguity: logic reviewer returns a clarification request; graph stops before verdict/posting.
4. Clarification resume: supplied human answer is recorded and only affected reviewers rerun.
5. Quality gate: fake reviewer output splits into postable finding, local note, suggested reply, and suppressed non-finding.
6. Allowed post proof: item-approved top-level issue-comment payload calls the fake writer once; rejected or empty approval calls it zero times.
7. GitHub read proof: fake paginated GitHub read feeds the same graph path as fixtures.
8. Fail-closed proof: stale target, target-read failure, read gap, unknown actor, unknown endpoint permission, permission-read failure, non-interactive post mode, or marker conflict prevents writer reachability.

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
