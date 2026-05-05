# ISSUE PLAN: AUR-209 Render Redacted Markdown And JSON

Historical execution artifact for this issue. Linear remains the durable source for issue status, blockers, and handoff details; if this file conflicts with Linear, Linear wins. Fetch current state from Linear before acting on this plan.

## Linear issue snapshot

- Issue: `AUR-209` / `RG-020: Render Redacted Markdown And JSON`
- Milestone: `PRD 0002: MVP Tracer Bullet`
- Status at planning: `In Progress`

## Acceptance criteria mapping

1. Markdown distinguishes postable findings, local notes, clarification requests, suggested replies, and suppressed counts.
   - Evidence target: `render_markdown(...)` has explicit sections for each class and reports suppressed/non-finding count.
2. JSON includes review target, selected reviewers, classified output, local verdict, and posting plan.
   - Evidence target: `render_json(...)` returns a deterministic dict with those fields and stable primitive values.
3. Token-like content is redacted from markdown and JSON.
   - Evidence target: renderer redacts all externally sourced text before output, including finding body/evidence, local notes, clarification questions, suggested replies, memory snippets, truncation notes, and payload previews.
4. Rendered output includes memory IDs, trust labels, resolved status, and truncation status that shaped the run.
   - Evidence target: minimal `MemoryReference` and `TruncationNotice` models plus markdown/JSON sections that expose IDs/status without turning memory bodies into public payload previews.
5. Rendered output includes truncation notes when context was bounded.
   - Evidence target: tests with bounded context assert markdown and JSON include truncation status and notes.
6. Output does not include public request-changes wording unless explicitly allowed.
   - Evidence target: local dry-run output may show the local verdict as private/run metadata, but default public candidate payload preview text suppresses `request_changes` phrasing.
7. Public payload preview fields never include untrusted comment bodies from #44.
   - Evidence target: tests with trusted and untrusted memory prove untrusted body text is absent from public payload preview fields, and candidate payload preview rendering fails closed or flags unsafe state if a postable finding copied an untrusted memory body into public payload text.

## Minimal foundation ownership

This issue may add only the foundation needed by renderer tests:

- `src/reviewgraph/render.py` with markdown and JSON rendering functions.
- Minimal render input/result dataclasses if needed. Put graph/memory-shaped data in `models.py` when it represents durable state (`SelectedReviewer`, `MemoryReference`, `TruncationNotice`); keep only renderer-owned result wrappers in `render.py`.
- Tests in `tests/test_render.py` with deterministic fixture objects built from the existing `models.py` and `posting.py` contracts.

Do not implement graph execution, CLI commands, fixture PR parsing, reviewer config loading, fake reviewer adapters, live GitHub reads, live LLM calls, approval, finalization, or writer behavior in this issue.

## Implementation plan

1. Add minimal renderer input contracts:
   - `SelectedReviewer` with reviewer name, stage, and trigger reasons.
   - `MemoryReference` with ID, trust label, resolved status, source type, and optional body.
   - `TruncationNotice` with resource, truncated flag, original count/bytes when available, retained count/bytes when available, and note.
   - `RenderedReview` with markdown, JSON dict, and redaction status.
2. Add `src/reviewgraph/render.py`:
   - `render_markdown(...)`
   - `render_json(...)`
   - `render_review(...)` convenience wrapper if useful
   - stable serialization helpers for review target, selected reviewers, classified outputs, posting plan, memory references, truncation, local verdict, and candidate payload preview metadata.
   - candidate payload preview serialization must consume an actual `CandidateIssueCommentPayload` from `posting.py`; it must not recompute body, hashes, target metadata, or fingerprints.
3. Keep renderer output deterministic:
   - preserve input order for selected reviewers and output items;
   - use primitive JSON values only;
   - avoid timestamps unless supplied by the caller;
   - do not include raw object reprs.
4. Apply `redact_text(...)` to every rendered external text field before it enters markdown or JSON. Reuse `RedactionStatus` and aggregate categories/counts.
5. Public payload preview handling:
   - include candidate payload kind, hashes, target metadata, redaction status, and item fingerprints directly from `CandidateIssueCommentPayload`;
   - include candidate body exactly from the existing candidate payload object after an additional renderer redaction pass verifies it is still safe;
   - never include untrusted memory bodies in public payload preview fields;
   - reject or flag unsafe preview state if the candidate body contains a known untrusted memory body substring;
   - keep local/private verdict metadata separate from candidate public text by default.
6. Add `tests/test_render.py` covering:
   - markdown sections for postable findings, local notes, clarification requests, suggested replies, suppressed count, selected reviewers, memory, truncation, local verdict, and posting plan;
   - JSON includes review target, selected reviewers, classified outputs, local verdict, posting plan, memory metadata, truncation notices, candidate payload preview, and redaction status;
   - candidate payload preview fields exactly match the supplied `CandidateIssueCommentPayload` kind, target, body, hashes, fingerprints, and redaction status after renderer safety checks;
   - API keys, bearer tokens, GitHub tokens, authorization headers, `.env` assignments, private key blocks, standalone provider keys, and JSON-style secret fields are absent from markdown and JSON string output;
   - untrusted memory body text is absent from public payload preview fields, including a regression where a finding body/evidence copied a unique untrusted comment body into the supplied candidate payload body;
   - trusted/untrusted labels, resolved status, memory IDs, and truncation status are present;
   - local dry-run metadata may record `request_changes`, but candidate public payload preview text does not include request-changes wording by default;
   - aggregated redaction status categories/counts are deterministic and include redactions from candidate payload preview plus rendered classified outputs;
   - `render_json(...)` output is JSON-serializable with only primitive containers, repeat-render equal, and free of enum/dataclass repr leakage;
   - rendering remains pure: no writer/transport/GitHub/approval/finalization imports in `render.py`.
7. Run:
   - `python -m pytest tests/test_render.py`
   - `python -m pytest`
   - `python -m py_compile src/reviewgraph/*.py`
   - `python scripts/check_docs.py`
   - `git diff --check`

## Out of scope

- No CLI.
- No graph runner or fixture PR parser.
- No reviewer config loader or fake reviewer adapter.
- No live GitHub, live LLM, approval, finalization, marker reconciliation, or writer adapter.
- No public posting of suggested replies, clarification requests, local notes, or untrusted memory bodies.

## Review approach

- Get fresh subagent plan review before implementation.
- After implementation, move `AUR-209` to `In Review`, run fresh code review subagents, fix material issues, and commit after each review cycle.
