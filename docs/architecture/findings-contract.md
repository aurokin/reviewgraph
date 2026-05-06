# Findings Contract

Reviewers return structured findings or structured clarification requests. Markdown is rendered later.

Reviewer output is not automatically postable. The graph first classifies each item according to `review-quality.md`.

## Raw reviewer output envelope

Fixture and adapter outputs identify the selected reviewer run at the envelope level. Individual items must not set graph-owned routing, posting, verdict, priority, fingerprint, reviewer, stage, or resume metadata. If they do, normalization suppresses that item and records a structured normalization error instead of stripping the field silently.

```json
{
  "reviewer": "security",
  "stage": "specialized_review",
  "items": []
}
```

## Raw reviewer finding schema

Reviewers may propose findings, but they do not decide postability, blocking status, or final priority. The graph owns those decisions in `classify_review_quality`.

```json
{
  "id": "stable-or-generated-id",
  "severity": "critical | warning | suggestion | nit",
  "confidence": "high | medium | low",
  "confidence_score": 0.91,
  "path": "src/example.ts",
  "line": 42,
  "line_end": 42,
  "title": "User-controlled path reaches file read",
  "rationale": "The new code joins user input into a filesystem path without normalization.",
  "evidence": "diff excerpt or PR context reference",
  "evidence_sources": ["diff"],
  "evidence_memory_ids": [],
  "suggested_fix": "Normalize and validate path under an allowed root before reading."
}
```

`evidence_sources` may include `diff` or `trusted_memory`. If a finding cites
`trusted_memory`, it must also cite concrete `evidence_memory_ids`. Unknown,
untrusted, resolved-passive, or otherwise non-actionable memory cannot support a
postable finding. Existing path, line, and evidence fields still carry the human
readable claim; provenance fields let the graph decide whether PR conversation
memory is being used safely.

## Classified finding schema

```json
{
  "id": "stable-or-generated-id",
  "source_reviewer": "security",
  "source_stage": "specialized_review",
  "classification": "postable_finding",
  "priority": 1,
  "severity": "critical",
  "confidence": "high",
  "confidence_score": 0.91,
  "path": "src/example.ts",
  "line": 42,
  "line_end": 42,
  "diff_anchor": {
    "path": "src/example.ts",
    "old_path": null,
    "file_status": "modified",
    "hunk_id": "src/example.ts:40-45",
    "side": "RIGHT",
    "start_side": "RIGHT",
    "line": 42,
    "start_line": 42,
    "target_commit_sha": "abc123"
  },
  "title": "User-controlled path reaches file read",
  "body": "When the route parameter contains `../`, this joins user input into a filesystem path without constraining it to the allowed root.",
  "evidence": "diff excerpt or PR context reference",
  "suggested_fix": "Normalize and validate path under an allowed root before reading.",
  "blocking": true,
  "fingerprint": "stable-finding-fingerprint"
}
```

## Clarification request schema

If a reviewer cannot make a high-confidence mergeability recommendation without human context, it should return a clarification request instead of inflating confidence.

Raw reviewer clarification items only provide the request content and evidence provenance. The graph derives reviewer, source stage, run key, status, and resume target from the current run.

```json
{
  "id": "stable-or-generated-id",
  "question": "Is this endpoint intentionally allowed to bypass the normal authorization path?",
  "why_it_matters": "If not intentional, the change may expose data across tenants.",
  "evidence_sources": ["diff"],
  "evidence_memory_ids": [],
  "blocks_verdict": true
}
```

Rendered dry-run output includes graph-owned metadata:

```json
{
  "id": "stable-or-generated-id",
  "reviewer": "logic",
  "source_stage": "logic_review",
  "source_run_key": "{\"attempt\":1,\"clarification_id\":null,\"config_hash\":\"sha256:...\",\"retry_of\":null,\"reviewer\":\"logic\",\"stage\":\"logic_review\",\"target_hash\":\"sha256:...\"}",
  "status": "pending",
  "resume_target": {
    "stage": "clarification_review",
    "reviewers": ["logic"]
  },
  "path": "src/example.ts",
  "line": 42,
  "question": "Is this endpoint intentionally allowed to bypass the normal authorization path?",
  "why_it_matters": "If not intentional, the change may expose data across tenants.",
  "evidence_sources": ["diff"],
  "evidence_memory_ids": [],
  "blocks_verdict": true
}
```

Clarification requests affect the local verdict, so they follow the same memory
provenance rule as findings. If passive memory metadata is visible to a reviewer, a
clarification request must declare safe evidence provenance; copied passive
comment text cannot create a verdict-blocking clarification, even if mislabeled
as diff evidence.

## Local note schema

Local notes are useful to the user but should not become GitHub comments.

```json
{
  "id": "stable-or-generated-id",
  "title": "PR may be difficult to review as one change",
  "body": "The diff changes config loading, CLI behavior, and output rendering. Consider splitting the config loader first.",
  "evidence": "changed files summary"
}
```

## Suggested reply schema

Suggested replies are local-only output for human-authored PR comments or review threads.

```json
{
  "id": "stable-or-generated-id",
  "classification": "suggested_reply",
  "source_comment_id": "123456",
  "source_thread_id": "thread-1",
  "source_author": "octocat",
  "source_author_trusted": true,
  "proposed_body": "I think this is already covered by the new guard in `validatePath`, but I would wait for maintainer confirmation before replying."
}
```

## Normalization error schema

Reviewer results in the dry-run JSON include structured normalization errors for malformed or rejected raw output. Fatal errors fail the reviewer result atomically: valid sibling items from the same malformed output do not flow into classified output. Nonfatal errors record suppressed graph-owned item fields while allowing valid sibling items to continue.

Repairable malformed selected-reviewer output gets one deterministic fake repair attempt only when it arrives through the strict fake repair envelope with exactly top-level `reviewer`, `stage`, `raw_output`, and `repair_output`, and the envelope reviewer/stage match the selected reviewer run. Direct legacy mapping output keeps the existing fake reviewer normalization behavior and is not repaired. Valid JSON object strings normalize directly, valid non-object JSON strings fail schema validation without repair, and invalid strings trigger repair. `repair_record` is present when repair was attempted, whether the repair succeeded or failed. It preserves JSON-compatible original and repaired payloads, attempt count, status, and structured errors. Successful repair still keeps `raw_output` as the original malformed output for auditability; repaired artifacts enter the normal typed normalization and quality-classification path.

```json
{
  "reviewer": "security",
  "stage": "specialized_review",
  "status": "failed",
  "errors": ["fake reviewer output requires an items list"],
  "normalization_errors": [
    {
      "code": "invalid_items",
      "message": "fake reviewer output requires an items list",
      "run_key": "{\"attempt\":1,\"clarification_id\":null,\"config_hash\":\"sha256:...\",\"retry_of\":null,\"reviewer\":\"security\",\"stage\":\"specialized_review\",\"target_hash\":\"sha256:...\"}",
      "repairable": true,
      "fatal": true,
      "item_id": null,
      "item_index": null,
      "rejected_fields": []
    }
  ],
  "repair_record": null,
  "raw_output": {
    "reviewer": "security",
    "stage": "specialized_review",
    "items": "not-a-list"
  }
}
```

```json
{
  "reviewer": "security",
  "stage": "specialized_review",
  "status": "completed",
  "errors": [],
  "normalization_errors": [],
  "repair_record": {
    "attempt_count": 1,
    "status": "succeeded",
    "original_output": "{\"items\": [",
    "repaired_output": {
      "items": []
    },
    "errors": [
      {
        "code": "invalid_json",
        "message": "fake reviewer output is not valid JSON",
        "run_key": "{\"attempt\":1,\"clarification_id\":null,\"config_hash\":\"sha256:...\",\"retry_of\":null,\"reviewer\":\"security\",\"stage\":\"specialized_review\",\"target_hash\":\"sha256:...\"}",
        "repairable": true,
        "fatal": true,
        "item_id": null,
        "item_index": null,
        "rejected_fields": []
      }
    ]
  },
  "raw_output": "{\"items\": ["
}
```

## Severity policy

- `critical`: security, data loss, auth bypass, or severe correctness issue with high confidence.
- `warning`: should fix before merge, but not catastrophic.
- `suggestion`: useful improvement, not blocking.
- `nit`: tiny style/readability issue; should be rare.

## Confidence policy

- `high`: directly supported by diff or surrounding context.
- `medium`: likely issue but needs maintainer judgment.
- `low`: speculative; cannot block.

## Filtering policy

Suppress findings when they are generic, unsupported by the PR context, reviewer-declared duplicates, dependent on omitted context, lack an actionable fix, cannot identify a scenario where the issue occurs, attempt to self-declare postability/blocking without evidence, or use passive/untrusted memory as evidence. Semantic deduplication across reviewer outputs is deferred until a deterministic policy is designed and tested.

## Location policy

Postable findings should include a changed-file location with the shortest practical line range. Inline candidates must overlap the diff. Findings without a precise location should remain local notes unless a top-level post format is explicitly approved.

`DiffAnchor` is separate from user-facing location. It exists to support future inline comments and must include path, old path when renamed, file status, hunk ID, side/start side, line/start line, and target commit SHA. MVP does not post inline comments; it may render inline candidates in dry-run output only.

## Priority policy

`priority` is stored as an integer from `0` to `3`. Renderers may display this as `P0` through `P3`, but schemas and policy use the integer.
