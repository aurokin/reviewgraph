import json

from reviewgraph.fixtures import load_fixture_pr, load_manifest
from reviewgraph.posting import findings_hash, full_body_hash, visible_body_hash
from reviewgraph.runner import run_fixture_dry_run


EXPECTED_TARGET = {
    "owner_repo": "acme/widgets",
    "pr_number": 42,
    "base_sha": "base123",
    "head_sha": "head456",
    "merge_base_sha": "merge789",
    "diff_basis": "merge_base",
}

EXPECTED_FINDING = {
    "id": "finding-cache-stale",
    "source_reviewer": "correctness",
    "source_stage": "initial_triage",
    "classification": "postable_finding",
    "priority": 1,
    "severity": "warning",
    "confidence": "high",
    "title": "Cache miss returns stale data",
    "body": "The new branch returns stale data when the cache misses. api_key = [REDACTED]",
    "evidence": "Changed line 12 returns the stale value.",
    "path": "src/cache.py",
    "line": 12,
    "fingerprint": "sha256:f057847d9ec647ddf253d83316a2a8edefff5bf4a3606d0b205872131c0459c1",
}

EXPECTED_LOCAL_NOTE = {
    "id": "note-review-size",
    "classification": "local_note",
    "title": "Review size",
    "body": "Fixture is intentionally small for the first CLI slice.",
    "evidence": "One changed file.",
}

EXPECTED_SUPPRESSED = {
    "id": "suppressed-generic-tests",
    "classification": "non_finding",
    "reason": "Generic missing-test advice without a concrete changed behavior was suppressed.",
}

EXPECTED_TRACE = {
    "active_stage_before": None,
    "active_stage_after": "initial_triage",
    "suspended_stage_before": None,
    "suspended_stage_after": None,
    "stage_queue_before": ["initial_triage", "specialized_review", "logic_review"],
    "stage_queue_after": ["specialized_review", "logic_review"],
    "transition_reason": "start_initial_triage",
}

EXPECTED_COMPLETED_TRACE = [
    EXPECTED_TRACE,
    {
        "active_stage_before": "initial_triage",
        "active_stage_after": "specialized_review",
        "suspended_stage_before": None,
        "suspended_stage_after": None,
        "stage_queue_before": ["specialized_review", "logic_review"],
        "stage_queue_after": ["logic_review"],
        "transition_reason": "complete_initial_triage_start_specialized_review",
    },
    {
        "active_stage_before": "specialized_review",
        "active_stage_after": "logic_review",
        "suspended_stage_before": None,
        "suspended_stage_after": None,
        "stage_queue_before": ["logic_review"],
        "stage_queue_after": [],
        "transition_reason": "complete_specialized_review_start_logic_review",
    },
    {
        "active_stage_before": "logic_review",
        "active_stage_after": None,
        "suspended_stage_before": None,
        "suspended_stage_after": None,
        "stage_queue_before": [],
        "stage_queue_after": [],
        "transition_reason": "finish_review_stages",
    },
]

EXPECTED_AMBIGUOUS_TRACE = EXPECTED_COMPLETED_TRACE[:-1] + [
    {
        "active_stage_before": "logic_review",
        "active_stage_after": None,
        "suspended_stage_before": None,
        "suspended_stage_after": None,
        "stage_queue_before": [],
        "stage_queue_after": [],
        "transition_reason": "clarification_needed_end",
    }
]

EXPECTED_REVIEWER = {
    "name": "correctness",
    "stage": "initial_triage",
    "reasons": ["initial_triage triggers.always=true"],
}


def test_basic_fixture_tracer_golden_run() -> None:
    fixture = load_fixture_pr("basic-pr")
    raw_items = fixture.raw_reviewer_outputs[0]["items"]

    writer = RaisingWriter()
    result = run_fixture_dry_run(fixture_ref="basic-pr", writer_sentinel=writer)
    data = result.json_data
    review = data["review"]
    classified = review["classified_output"]

    assert result.writer_call_count == 0
    assert writer.call_count == 0
    assert data["run_mode"] == "dry_run"
    assert data["post_enabled"] is True
    assert data["fixture_id"] == "basic-pr"
    assert data["fixture_ref"] == "fixture:basic-pr"
    assert data["local_verdict"] == "comment"
    assert data["side_effects"] == {"writer_called": False, "writer_call_count": 0}
    assert data["graph_trace"] == EXPECTED_COMPLETED_TRACE
    assert data["selected_reviewers"] == [EXPECTED_REVIEWER]
    assert review["selected_reviewers"] == [EXPECTED_REVIEWER]

    assert [item["id"] for item in raw_items] == [
        "finding-cache-stale",
        "note-review-size",
        "suppressed-generic-tests",
    ]
    assert [item["type"] for item in raw_items] == [
        "finding",
        "local_note",
        "suppressed",
    ]
    assert classified["postable_findings"] == [EXPECTED_FINDING]
    assert classified["local_notes"] == [EXPECTED_LOCAL_NOTE]
    assert classified["suppressed"] == [EXPECTED_SUPPRESSED]
    assert classified["suppressed_count"] == 1
    assert classified["clarification_requests"] == []
    assert classified["suggested_replies"] == []

    assert review["review_target"] == EXPECTED_TARGET
    assert review["local_verdict"] == "comment"
    assert review["memory"] == [
        {
            "id": "comment-cache-intent",
            "trust_label": "trusted",
            "resolved_status": "unresolved",
            "source_type": "issue_comment",
            "role": "trusted_actionable_data",
            "body": "Please check the cache miss fallback.",
            "author": "maintainer",
            "author_association": "MEMBER",
            "author_type": "user",
            "created_at": "2026-05-06T00:00:00Z",
            "url": None,
            "path": None,
            "line": None,
            "actionable": True,
            "passive_reason": None,
        },
        {
            "id": "review-cache-1",
            "trust_label": "trusted",
            "resolved_status": "unresolved",
            "source_type": "review",
            "role": "passive_data",
            "body": "Initial cache review.",
            "author": "reviewer",
            "author_association": "MEMBER",
            "author_type": "user",
            "created_at": "2026-05-06T00:00:00Z",
            "url": None,
            "path": None,
            "line": None,
            "actionable": False,
            "passive_reason": "review summary is passive until a later node interprets it",
        },
        {
            "id": "thread-comment-cache-1",
            "trust_label": "trusted",
            "resolved_status": "resolved",
            "source_type": "review_thread",
            "role": "passive_data",
            "body": "The cache token in the patch should be redacted.",
            "author": "reviewer",
            "author_association": "MEMBER",
            "author_type": "user",
            "created_at": "2026-05-06T00:01:00Z",
            "url": None,
            "path": "src/cache.py",
            "line": 12,
            "actionable": False,
            "passive_reason": "resolved thread",
        },
    ]
    assert review["truncation"] == [
        {
            "resource": "patch",
            "truncated": False,
            "note": "Fixture patch stayed within context budget.",
            "original_count": None,
            "retained_count": None,
            "original_bytes": None,
            "retained_bytes": None,
        }
    ]

    assert review["posting_plan"]["items"] == [
        {
            "id": "finding-cache-stale",
            "source_classification": "postable_finding",
            "destination": "review_body_item",
            "public_payload_eligible": True,
            "fingerprint": "sha256:f057847d9ec647ddf253d83316a2a8edefff5bf4a3606d0b205872131c0459c1",
            "body": "The new branch returns stale data when the cache misses. api_key = [REDACTED]",
        },
        {
            "id": "note-review-size",
            "source_classification": "local_note",
            "destination": "local_only",
            "public_payload_eligible": False,
            "fingerprint": None,
            "body": "Fixture is intentionally small for the first CLI slice.",
        },
        {
            "id": "suppressed-generic-tests",
            "source_classification": "non_finding",
            "destination": "local_only",
            "public_payload_eligible": False,
            "fingerprint": None,
            "body": "Generic missing-test advice without a concrete changed behavior was suppressed.",
        },
    ]

    preview = review["candidate_payload_preview"]
    assert preview["artifact_kind"] == "issue_comment"
    assert preview["review_target"] == EXPECTED_TARGET
    assert preview["body"] == (
        "ReviewGraph dry-run candidate\n"
        "Target: acme/widgets#42\n"
        "Head: head456\n"
        "\n"
        "Postable findings:\n"
        "- P1 Cache miss returns stale data: The new branch returns stale data when the cache misses. "
        "api_key = [REDACTED] (src/cache.py:12)\n"
    )
    assert preview["item_fingerprints"] == ["sha256:f057847d9ec647ddf253d83316a2a8edefff5bf4a3606d0b205872131c0459c1"]
    assert preview["visible_body_hash"] == visible_body_hash(preview["body"])
    assert preview["full_body_hash"] == full_body_hash(preview["body"])
    assert preview["findings_hash"] == findings_hash(preview["item_fingerprints"])
    assert preview["redaction_status"] == {
        "redacted": True,
        "replacement_count": 1,
        "categories": ["api_key"],
    }

    assert review["redaction_status"]["redacted"] is True
    assert review["redaction_status"]["replacement_count"] > 0
    assert "api_key" in review["redaction_status"]["categories"]
    _assert_markdown_sections(result.markdown)
    _assert_secret_like_fixture_content_absent(result)
    _assert_manifest_consumes_tracer_harness()


def test_basic_fixture_tracer_json_is_stable() -> None:
    first = run_fixture_dry_run(fixture_ref="basic-pr")
    second = run_fixture_dry_run(fixture_ref="basic-pr")

    assert _stable_json(first.json_data) == _stable_json(second.json_data)


def test_specialized_review_fixture_proves_staged_reviewer_introduction() -> None:
    result = run_fixture_dry_run(fixture_ref="specialized-review-pr")
    data = result.json_data
    review = data["review"]

    assert data["run_mode"] == "dry_run"
    assert data["post_enabled"] is True
    assert data["local_verdict"] == "comment"
    assert data["side_effects"] == {"writer_called": False, "writer_call_count": 0}
    assert data["selected_reviewers"] == [
        {
            "name": "correctness",
            "stage": "initial_triage",
            "reasons": ["initial_triage triggers.always=true"],
        },
        {
            "name": "security",
            "stage": "specialized_review",
            "reasons": ["specialized_review triggers.paths=src/auth/*"],
        },
    ]
    assert data["graph_trace"] == EXPECTED_COMPLETED_TRACE
    assert review["classified_output"]["local_notes"][0]["id"] == "note-auth-shape"
    assert review["classified_output"]["postable_findings"][0]["id"] == "finding-test-mode-mfa"
    assert review["candidate_payload_preview"]["artifact_kind"] == "issue_comment"
    assert review["candidate_payload_preview"]["item_fingerprints"] == [
        "sha256:a8a4e55fdce99b9d0dbea51fc7326e36f2824a2a2094c456a12078b75862186c"
    ]


def test_ambiguous_logic_fixture_stops_for_clarification_without_candidate_payload() -> None:
    writer = RaisingWriter()
    result = run_fixture_dry_run(fixture_ref="ambiguous-logic-pr", writer_sentinel=writer)
    data = result.json_data
    review = data["review"]
    classified = review["classified_output"]

    assert result.writer_call_count == 0
    assert writer.call_count == 0
    assert data["run_mode"] == "dry_run"
    assert data["post_enabled"] is False
    assert data["local_verdict"] == "needs_clarification"
    assert data["side_effects"] == {"writer_called": False, "writer_call_count": 0}
    assert data["selected_reviewers"] == [
        {
            "name": "correctness",
            "stage": "initial_triage",
            "reasons": ["initial_triage triggers.always=true"],
        },
        {
            "name": "logic",
            "stage": "logic_review",
            "reasons": ["logic_review triggers.diff_patterns=requires product intent"],
        },
    ]
    assert data["graph_trace"] == EXPECTED_AMBIGUOUS_TRACE
    assert classified["postable_findings"] == []
    assert classified["local_notes"][0]["id"] == "note-discount-shape"
    assert classified["clarification_requests"] == [
        {
            "id": "clarify-expired-coupon-intent",
            "classification": "clarification_request",
            "reviewer": "logic",
            "question": "Should expired coupons preserve legacy discounts for existing carts?",
            "why_it_matters": (
                "Without product intent, the reviewer cannot decide whether the changed billing behavior is a bug "
                "or an intended migration."
            ),
            "blocks_verdict": True,
        }
    ]
    assert review["candidate_payload_preview"] is None
    assert all(not item["public_payload_eligible"] for item in review["posting_plan"]["items"])
    assert "## Clarification Requests" in result.markdown
    assert "Should expired coupons preserve legacy discounts" in result.markdown


class RaisingWriter:
    def __init__(self) -> None:
        self.call_count = 0

    def __call__(self) -> None:
        self.call_count += 1
        raise AssertionError("writer must not be called")


def _assert_markdown_sections(markdown: str) -> None:
    for section in (
        "# ReviewGraph Dry Run",
        "## Target",
        "## Selected Reviewers",
        "## Postable Findings",
        "## Local Notes",
        "## Clarification Requests",
        "## Suggested Replies",
        "## Suppressed Outputs",
        "## Memory",
        "## Truncation",
        "## Posting Plan",
        "## Candidate Payload Preview",
    ):
        assert section in markdown
    for snippet in (
        "Cache miss returns stale data",
        "Review size",
        "suppressed-generic-tests",
        "issue_comment",
        "- None",
    ):
        assert snippet in markdown


def _assert_secret_like_fixture_content_absent(result) -> None:
    serialized = result.markdown + _stable_json(result.rendered.json_data) + _stable_json(result.json_data)
    for leaked in ("sk_live", "ghp_", "ghs_", "SECRET_TOKEN", "abcdefghijklmnopqrstuvwxyz"):
        assert leaked not in serialized
    assert "[REDACTED]" in serialized


def _assert_manifest_consumes_tracer_harness() -> None:
    manifest = load_manifest()
    fixtures_by_id = {entry["id"]: entry for entry in manifest["fixtures"]}
    basic_reviewers = next(entry for entry in manifest["reviewer_configs"] if entry["id"] == "basic-reviewers")
    for fixture_id in ("basic-pr", "specialized-review-pr", "ambiguous-logic-pr"):
        assert set(fixtures_by_id[fixture_id]["consumed_by"]) >= {
            "tests/test_cli.py",
            "tests/test_tracer_fixture_run.py",
        }
    assert set(basic_reviewers["consumed_by"]) >= {"tests/test_cli.py", "tests/test_tracer_fixture_run.py"}


def _stable_json(data: dict[str, object]) -> str:
    return json.dumps(data, sort_keys=True, indent=2)
