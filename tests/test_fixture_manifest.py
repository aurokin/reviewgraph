from reviewgraph.fixtures import load_manifest


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

REQUIRED_SHAPE_FIELDS = {
    "comments",
    "review_comments",
    "reviews",
    "thread_state",
    "labels",
    "changed_files",
    "patches",
    "base_sha",
    "head_sha",
    "merge_base_sha",
    "diff_basis",
}


def test_fixture_corpus_manifest_names_required_scenarios_once() -> None:
    manifest = load_manifest()
    scenarios = manifest["corpus_scenarios"]
    ids = [scenario["id"] for scenario in scenarios]

    assert set(ids) == REQUIRED_CORPUS_SCENARIOS
    assert len(ids) == len(set(ids))


def test_fixture_corpus_manifest_maps_each_scenario_to_consumers_and_shape() -> None:
    manifest = load_manifest()

    for scenario in manifest["corpus_scenarios"]:
        assert scenario["behavior"]
        assert scenario["consumed_by"]
        assert all(consumer.startswith("AUR-") or consumer.startswith("tests/") for consumer in scenario["consumed_by"])
        assert set(scenario["fixture_shape"]) == REQUIRED_SHAPE_FIELDS
        assert all(scenario["fixture_shape"][field] for field in REQUIRED_SHAPE_FIELDS)


def test_fixture_corpus_manifest_has_schema_valid_fixture_paths() -> None:
    manifest = load_manifest()

    for scenario in manifest["corpus_scenarios"]:
        assert scenario["requires_live_github"] is False
        assert scenario["requires_live_llm"] is False
        assert scenario["schema_valid_fixture"] is True
        assert scenario["path"].startswith("prs/")


def test_fixture_corpus_manifest_preserves_runnable_packaged_fixtures() -> None:
    manifest = load_manifest()
    fixture_ids = {entry["id"] for entry in manifest["fixtures"]}

    assert {"basic-pr", "specialized-review-pr", "ambiguous-logic-pr"}.issubset(fixture_ids)
