import copy
import json
import re
from importlib import resources
from pathlib import Path

import pytest

from reviewgraph.fixtures import FixtureError, load_fixture_pr, load_manifest, parse_fixture_pr
from reviewgraph.models import PullRequestContext, ReviewTarget


REQUIRED_CORPUS_SCENARIOS = {
    "frontend-state-change",
    "security-sensitive-change",
    "docs-only-change",
    "mixed-risk-change",
    "ambiguous-logic-change",
    "breaking-api-change",
    "oversized-change",
    "stale-approval-change",
    "untrusted-comment-injection",
    "paginated-github-read",
}


def test_all_corpus_scenarios_have_schema_valid_fixture_files() -> None:
    manifest = load_manifest()
    scenarios = {scenario["id"]: scenario for scenario in manifest["corpus_scenarios"]}
    fixture_entries = {entry["id"]: entry for entry in manifest["fixtures"]}

    assert set(scenarios) == REQUIRED_CORPUS_SCENARIOS
    for scenario_id, scenario in scenarios.items():
        assert scenario["path"] == fixture_entries[scenario_id]["path"]
        fixture = load_fixture_pr(scenario_id)
        assert fixture.id == scenario_id
        assert fixture.pr_ref == f"fixture:{scenario_id}"
        assert isinstance(fixture.review_target, ReviewTarget)
        assert isinstance(fixture.pr, PullRequestContext)


def test_every_fixture_manifest_entry_has_consumers() -> None:
    manifest = load_manifest()

    for collection in ("fixtures", "corpus_scenarios", "reviewer_configs"):
        for entry in manifest[collection]:
            assert entry["consumed_by"], f"{collection}.{entry['id']} must name consumers"


def test_parsed_fixture_exposes_typed_review_target_and_pr_context() -> None:
    fixture = load_fixture_pr("untrusted-comment-injection")

    assert fixture.review_target.owner_repo == "acme/widgets"
    assert fixture.review_target.target_hash().startswith("sha256:")
    assert fixture.target == fixture.review_target.to_ordered_dict()
    assert fixture.pr.review_target == fixture.review_target
    assert fixture.pr.labels == ("security",)
    assert fixture.pr.changed_files[0].path == "src/auth/redirects.py"
    assert fixture.pr.changed_files[0].patch_status == "available"
    assert fixture.pr.comments[0].author == "external-contributor"
    assert fixture.pr.comments[0].author_association == "CONTRIBUTOR"
    assert fixture.pr.comments[0].trust_label == "untrusted"
    assert fixture.pr.reviews[0].author_association == "MEMBER"
    assert fixture.pr.reviews[0].created_at == "2026-05-06T00:26:30Z"
    assert fixture.pr.reviews[0].trust_label == "trusted"
    assert fixture.pr.reviews[0].source_type == "review"
    assert fixture.pr.review_threads[0].resolved_status == "unresolved"
    thread_comment = fixture.pr.review_threads[0].comments[0]
    assert thread_comment.trust_label == "untrusted"
    assert thread_comment.path == "src/auth/redirects.py"
    assert thread_comment.line == 30
    assert thread_comment.side == "RIGHT"
    assert thread_comment.commit_sha == "head-injection"
    assert thread_comment.position == 1


def test_parsed_fixture_preserves_nullable_or_truncated_patch_metadata() -> None:
    fixture = load_fixture_pr("oversized-change")

    changed_file = fixture.pr.changed_files[0]
    assert changed_file.patch is None
    assert changed_file.patch_status == "truncated"
    assert changed_file.additions == 620
    assert fixture.changed_files[0].patch is None
    assert fixture.changed_files[0].contains_line(200)


def test_review_target_hash_changes_for_base_head_and_diff_basis() -> None:
    data = _fixture_data("frontend-state-change")
    fixture = parse_fixture_pr(data)
    original_hash = fixture.review_target.target_hash()

    for field, value in (
        ("base_sha", "other-base"),
        ("head_sha", "other-head"),
        ("diff_basis", "head"),
    ):
        mutated = copy.deepcopy(data)
        mutated["target"][field] = value
        assert parse_fixture_pr(mutated).review_target.target_hash() != original_hash


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda data: data["target"].update({"head_sha": ""}), "fixture.target.head_sha must be a non-empty string"),
        (lambda data: data.update({"labels": ["security", ""]}), "fixture.labels entries must be non-empty strings"),
        (lambda data: data["changed_files"][0].update({"path": ""}), "changed_files[].path is required"),
        (
            lambda data: data["changed_files"][0].update({"patch": None, "patch_status": "available"}),
            "changed_files[].patch_status must explain missing patch",
        ),
        (lambda data: data["comments"][0].pop("author_association"), "fixture.comments.author_association is required"),
        (lambda data: data["comments"][0].pop("trust_label"), "fixture.comments.trust_label is required"),
        (lambda data: data["reviews"][0].pop("created_at"), "fixture.reviews.created_at is required"),
        (lambda data: data["reviews"][0].pop("source_type"), "fixture.reviews.source_type is required"),
        (lambda data: data["reviews"][0].update({"author_association": ""}), "fixture.reviews.author_association is required"),
        (
            lambda data: data["review_threads"][0].update({"resolved_status": "maybe"}),
            "pull request review thread resolved_status",
        ),
        (
            lambda data: data["review_threads"][0].pop("comments"),
            "fixture.review_threads.comments must be a non-empty list",
        ),
        (
            lambda data: data["review_threads"][0]["comments"][0].update({"line": True}),
            "fixture.review_threads.comments.line must be a positive integer or null",
        ),
    ],
)
def test_invalid_fixture_shapes_fail_with_clear_errors(mutate: object, message: str) -> None:
    data = _fixture_data("untrusted-comment-injection")
    mutate(data)

    with pytest.raises(FixtureError, match=re.escape(message)):
        parse_fixture_pr(data)


def test_manifest_corpus_paths_exist() -> None:
    manifest = load_manifest()

    for scenario in manifest["corpus_scenarios"]:
        assert _fixtures_root().parent.joinpath(scenario["path"]).is_file()


def test_existing_packaged_dry_run_fixtures_still_parse() -> None:
    for fixture_id in ("basic-pr", "specialized-review-pr", "ambiguous-logic-pr"):
        fixture = load_fixture_pr(fixture_id)
        assert fixture.review_target.target_hash().startswith("sha256:")
        assert fixture.pr.changed_files
        assert fixture.raw_reviewer_outputs


def _fixture_data(fixture_id: str) -> dict[str, object]:
    fixture = load_fixture_pr(fixture_id)
    path = _fixtures_root().joinpath(f"{fixture.id}.json")
    return json.loads(path.read_text())


def _fixtures_root() -> Path:
    return Path(str(resources.files("reviewgraph").joinpath("fixtures_data/prs")))
