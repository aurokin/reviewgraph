import pytest

from reviewgraph.diff_anchor import attach_diff_anchors, derive_diff_anchor
from reviewgraph.fixtures import ChangedFile, ChangedRange, load_fixture_pr
from reviewgraph.models import ClassifiedFinding, Confidence, DiffAnchor, ReviewTarget, Severity
from reviewgraph.posting import PostingDestination, PostingPlanError, build_candidate_issue_comment_payload, build_posting_plan
from reviewgraph.runner import run_fixture_dry_run


def test_derive_diff_anchor_from_fixture_changed_range() -> None:
    anchor = derive_diff_anchor(
        changed_files=(_changed_file(),),
        review_target=_target(),
        finding=_finding(),
    )

    assert anchor == DiffAnchor(
        path="src/cache.py",
        line=12,
        target_commit_sha="head456",
        hunk_start=10,
        hunk_end=14,
        hunk_id="src/cache.py:10-14",
        start_line=12,
        file_status="modified",
    )
    assert anchor.validates_finding_location(
        path="src/cache.py",
        line=12,
        line_end=None,
        target_commit_sha="head456",
    )


def test_derive_diff_anchor_keeps_multiline_findings_inside_one_range() -> None:
    inside = derive_diff_anchor(
        changed_files=(_changed_file(),),
        review_target=_target(),
        finding=_finding(line=12, line_end=14),
    )
    outside = derive_diff_anchor(
        changed_files=(_changed_file(),),
        review_target=_target(),
        finding=_finding(line=12, line_end=15),
    )

    assert inside is not None
    assert inside.validates_finding_location(
        path="src/cache.py",
        line=12,
        line_end=14,
        target_commit_sha="head456",
    )
    assert outside is None


def test_derive_diff_anchor_carries_rename_metadata() -> None:
    anchor = derive_diff_anchor(
        changed_files=(
            _changed_file(
                path="src/cache_new.py",
                status="renamed",
                previous_path="src/cache_old.py",
            ),
        ),
        review_target=_target(),
        finding=_finding(path="src/cache_new.py"),
    )

    assert anchor is not None
    assert anchor.file_status == "renamed"
    assert anchor.old_path == "src/cache_old.py"


@pytest.mark.parametrize(
    "changed_file_kwargs",
    (
        {"patch_status": "budget_truncated"},
        {"status": "removed"},
        {"changed_ranges": (ChangedRange(20, 24),)},
    ),
)
def test_derive_diff_anchor_returns_none_for_non_inlineable_context(
    changed_file_kwargs: dict[str, object],
) -> None:
    assert derive_diff_anchor(
        changed_files=(_changed_file(**changed_file_kwargs),),
        review_target=_target(),
        finding=_finding(),
    ) is None


def test_attach_diff_anchors_replaces_frozen_findings_without_mutation() -> None:
    finding = _finding()

    anchored = attach_diff_anchors(
        changed_files=(_changed_file(),),
        review_target=_target(),
        findings=(finding,),
    )

    assert finding.diff_anchor is None
    assert anchored[0].diff_anchor is not None
    assert anchored[0] is not finding


def test_inline_candidate_plan_requires_valid_multiline_anchor() -> None:
    bad_anchor = DiffAnchor(
        path="src/cache.py",
        line=12,
        target_commit_sha="head456",
        hunk_start=10,
        hunk_end=14,
        hunk_id="src/cache.py:10-14",
        start_line=12,
    )

    with pytest.raises(PostingPlanError, match="diff anchor"):
        build_posting_plan(
            findings=[_finding(line=12, line_end=15, diff_anchor=bad_anchor)],
            review_target=_target(),
            inline_candidate_ids={"finding-cache-stale"},
        )


def test_explicit_inline_candidate_is_non_public_and_excluded_from_candidate_payload() -> None:
    inline = attach_diff_anchors(
        changed_files=(_changed_file(),),
        review_target=_target(),
        findings=(_finding(finding_id="finding-inline", fingerprint="fp-inline"),),
    )[0]
    top_level = _finding(finding_id="finding-top", fingerprint="fp-top")
    plan = build_posting_plan(
        findings=[inline, top_level],
        review_target=_target(),
        inline_candidate_ids={"finding-inline"},
    )
    payload = build_candidate_issue_comment_payload(
        review_target=_target(),
        posting_plan=plan,
        findings=[inline, top_level],
    )

    inline_item = next(item for item in plan.items if item.id == "finding-inline")
    top_level_item = next(item for item in plan.items if item.id == "finding-top")
    assert inline_item.destination == PostingDestination.INLINE_CANDIDATE
    assert inline_item.public_payload_eligible is False
    assert top_level_item.destination == PostingDestination.REVIEW_BODY_ITEM
    assert payload.item_fingerprints == ("fp-top",)
    assert "finding-inline" not in payload.body
    assert "Cache miss returns stale data" in payload.body


def test_fixture_dry_run_renders_diff_anchor_without_changing_default_posting_plan() -> None:
    result = run_fixture_dry_run(fixture_ref="basic-pr")
    finding = result.json_data["review"]["classified_output"]["postable_findings"][0]
    plan_item = result.json_data["review"]["posting_plan"]["items"][0]

    assert result.json_data["post_enabled"] is True
    assert finding["diff_anchor"] == {
        "path": "src/cache.py",
        "old_path": None,
        "file_status": "modified",
        "hunk_id": "src/cache.py:10-14",
        "hunk_start": 10,
        "hunk_end": 14,
        "side": "RIGHT",
        "start_side": "RIGHT",
        "line": 12,
        "start_line": 12,
        "target_commit_sha": "head456",
    }
    assert plan_item["id"] == "finding-cache-stale"
    assert plan_item["destination"] == "review_body_item"
    assert plan_item["public_payload_eligible"] is True
    assert result.json_data["review"]["candidate_payload_preview"]["item_fingerprints"] == [
        finding["fingerprint"]
    ]


def _target() -> ReviewTarget:
    return load_fixture_pr("basic-pr").review_target


def _changed_file(
    *,
    path: str = "src/cache.py",
    status: str = "modified",
    previous_path: str | None = None,
    patch_status: str = "available",
    changed_ranges: tuple[ChangedRange, ...] = (ChangedRange(10, 14),),
) -> ChangedFile:
    return ChangedFile(
        path=path,
        status=status,
        previous_path=previous_path,
        patch_status=patch_status,
        changed_ranges=changed_ranges,
        patch="+    return stale_value\n",
    )


def _finding(
    *,
    finding_id: str = "finding-cache-stale",
    path: str = "src/cache.py",
    line: int = 12,
    line_end: int | None = None,
    fingerprint: str = "fp-cache",
    diff_anchor: DiffAnchor | None = None,
) -> ClassifiedFinding:
    return ClassifiedFinding(
        id=finding_id,
        source_reviewer="correctness",
        source_stage="initial_triage",
        title="Cache miss returns stale data",
        body="The new branch returns stale data when the cache misses.",
        evidence="Changed line 12 returns stale value when the cache misses.",
        path=path,
        line=line,
        line_end=line_end,
        priority=1,
        severity=Severity.WARNING,
        confidence=Confidence.HIGH,
        fingerprint=fingerprint,
        diff_anchor=diff_anchor,
    )
