import ast
import json
from importlib import resources
from pathlib import Path

import pytest

from reviewgraph.cli import main
from reviewgraph.fixtures import FixtureError, MAX_FIXTURE_BYTES, load_manifest, resolve_fixture_ref
from reviewgraph.runner import run_fixture_dry_run


def test_cli_writes_markdown_and_json_for_fixture_id(tmp_path: Path) -> None:
    markdown_path = tmp_path / "review.md"
    json_path = tmp_path / "review.json"

    exit_code = main(
        [
            "--fixture-pr",
            "basic-pr",
            "--markdown-out",
            str(markdown_path),
            "--json-out",
            str(json_path),
        ]
    )

    assert exit_code == 0
    markdown = markdown_path.read_text()
    data = json.loads(json_path.read_text())

    assert "## Postable Findings" in markdown
    assert "## Local Notes" in markdown
    assert "## Candidate Payload Preview" in markdown
    assert data["run_mode"] == "dry_run"
    assert data["post_enabled"] is True
    assert data["fixture_id"] == "basic-pr"
    assert data["side_effects"] == {"writer_called": False, "writer_call_count": 0}
    assert data["graph_trace"][0] == {
        "active_stage_before": None,
        "active_stage_after": "initial_triage",
        "suspended_stage_before": None,
        "suspended_stage_after": None,
        "stage_queue_before": ["initial_triage", "specialized_review", "logic_review"],
        "stage_queue_after": ["specialized_review", "logic_review"],
        "transition_reason": "start_initial_triage",
    }
    assert data["selected_reviewers"][0]["reasons"] == ["initial_triage triggers.always=true"]
    review = data["review"]
    assert review["review_target"]["owner_repo"] == "acme/widgets"
    assert review["classified_output"]["postable_findings"][0]["id"] == "finding-cache-stale"
    assert review["classified_output"]["local_notes"][0]["id"] == "note-review-size"
    assert review["posting_plan"]["items"][0]["destination"] == "review_body_item"
    assert review["candidate_payload_preview"]["artifact_kind"] == "issue_comment"
    assert review["memory"][0]["id"] == "mem-trusted"
    assert review["memory"][1]["body"] is None


def test_cli_json_is_byte_stable(tmp_path: Path) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"

    assert main(["--fixture-pr", "basic-pr", "--json-out", str(first)]) == 0
    assert main(["--fixture-pr", "basic-pr", "--json-out", str(second)]) == 0

    assert first.read_bytes() == second.read_bytes()


def test_cli_prints_markdown(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--fixture-pr", "basic-pr", "--print-markdown"]) == 0

    captured = capsys.readouterr()
    assert "# ReviewGraph Dry Run" in captured.out
    assert captured.err == ""


def test_explicit_fixture_path_works(tmp_path: Path) -> None:
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(_basic_fixture_text())
    json_path = tmp_path / "review.json"

    assert main(["--fixture-pr", str(fixture_path), "--json-out", str(json_path)]) == 0

    assert json.loads(json_path.read_text())["fixture_id"] == "basic-pr"


def test_package_fixture_data_is_available() -> None:
    assert resolve_fixture_ref("basic-pr").exists()
    data_root = resources.files("reviewgraph").joinpath("fixtures_data")
    assert data_root.joinpath("manifest.json").is_file()
    assert data_root.joinpath("prs/basic-pr.json").is_file()


def test_manifest_registry_includes_consumed_basic_fixture() -> None:
    manifest = load_manifest()

    basic = [entry for entry in manifest["fixtures"] if entry["id"] == "basic-pr"]
    assert basic
    assert "tests/test_cli.py" in basic[0]["consumed_by"]


def test_runner_does_not_call_raising_writer_sentinel() -> None:
    class RaisingWriter:
        call_count = 0

        def __call__(self) -> None:
            self.call_count += 1
            raise AssertionError("writer must not be called")

    result = run_fixture_dry_run(fixture_ref="basic-pr", writer_sentinel=RaisingWriter())

    assert result.writer_call_count == 0
    assert result.json_data["side_effects"]["writer_called"] is False


def test_fixture_run_redacts_secret_like_content(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "ghs_abcdefghijklmnopqrstuvwxyz123456")
    markdown_path = tmp_path / "review.md"
    json_path = tmp_path / "review.json"

    assert main(["--markdown-out", str(markdown_path), "--json-out", str(json_path)]) == 0

    serialized = markdown_path.read_text() + json_path.read_text()
    for leaked in ("sk_live", "ghp_", "ghs_", "abcdefghijklmnopqrstuvwxyz", "SECRET_TOKEN"):
        assert leaked not in serialized
    assert "[REDACTED]" in serialized


def test_clarification_only_fixture_is_not_post_enabled(tmp_path: Path) -> None:
    fixture_path = tmp_path / "clarify.json"
    fixture = _basic_fixture()
    fixture["id"] = "clarify-pr"
    fixture["raw_reviewer_outputs"][0]["items"] = [
        {
            "type": "clarification_request",
            "id": "clarify-intent",
            "question": "Is this behavior intentional?",
            "why_it_matters": "The mergeability decision depends on product intent.",
        }
    ]
    fixture_path.write_text(json.dumps(fixture))

    result = run_fixture_dry_run(fixture_ref=str(fixture_path))

    assert result.json_data["local_verdict"] == "needs_clarification"
    assert result.json_data["post_enabled"] is False
    assert result.json_data["side_effects"]["writer_call_count"] == 0
    assert result.json_data["review"]["candidate_payload_preview"] is None
    assert result.json_data["review"]["posting_plan"]["items"][0]["destination"] == "local_only"


def test_finding_with_clarification_keeps_posting_plan_local_only(tmp_path: Path) -> None:
    fixture_path = tmp_path / "finding-with-clarification.json"
    fixture = _basic_fixture()
    fixture["id"] = "finding-with-clarification"
    fixture["raw_reviewer_outputs"][0]["items"].append(
        {
            "type": "clarification_request",
            "id": "clarify-intent",
            "question": "Is this behavior intentional?",
            "why_it_matters": "The mergeability decision depends on product intent.",
        }
    )
    fixture_path.write_text(json.dumps(fixture))

    result = run_fixture_dry_run(fixture_ref=str(fixture_path))

    assert result.json_data["local_verdict"] == "needs_clarification"
    assert result.json_data["post_enabled"] is False
    assert result.json_data["review"]["candidate_payload_preview"] is None
    plan_items = result.json_data["review"]["posting_plan"]["items"]
    assert {item["id"] for item in plan_items} >= {"finding-cache-stale", "clarify-intent"}
    assert all(item["destination"] == "local_only" for item in plan_items)


def test_no_finding_fixture_is_not_post_enabled(tmp_path: Path) -> None:
    fixture_path = tmp_path / "no-findings.json"
    fixture = _basic_fixture()
    fixture["id"] = "no-findings"
    fixture["raw_reviewer_outputs"][0]["items"] = []
    fixture_path.write_text(json.dumps(fixture))

    result = run_fixture_dry_run(fixture_ref=str(fixture_path))

    assert result.json_data["local_verdict"] == "no_findings"
    assert result.json_data["post_enabled"] is False
    assert result.json_data["review"]["candidate_payload_preview"] is None


def test_postable_finding_must_overlap_changed_lines(tmp_path: Path) -> None:
    fixture_path = tmp_path / "bad-line.json"
    fixture = _basic_fixture()
    fixture["raw_reviewer_outputs"][0]["items"][0]["line"] = 99
    fixture_path.write_text(json.dumps(fixture))

    exit_code = main(["--fixture-pr", str(fixture_path)])

    assert exit_code == 2


def test_raw_output_reviewer_must_be_selected(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    fixture_path = tmp_path / "unselected-reviewer.json"
    fixture = _basic_fixture()
    fixture["raw_reviewer_outputs"][0]["reviewer"] = "security"
    fixture["raw_reviewer_outputs"][0]["stage"] = "logic_review"
    fixture_path.write_text(json.dumps(fixture))

    assert main(["--fixture-pr", str(fixture_path)]) == 2
    assert "was not selected" in capsys.readouterr().err


def test_malformed_raw_output_field_returns_nonzero(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture_path = tmp_path / "missing-raw-field.json"
    fixture = _basic_fixture()
    del fixture["raw_reviewer_outputs"][0]["items"][0]["path"]
    fixture_path.write_text(json.dumps(fixture))

    assert main(["--fixture-pr", str(fixture_path)]) == 2
    assert "postable_finding.path is required" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("field", "nested_field", "expected_stderr"),
    (
        ("memory", "trust_label", "memory.trust_label is required"),
        ("truncation", "note", "truncation.note is required"),
    ),
)
def test_malformed_nested_fixture_field_returns_nonzero(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    field: str,
    nested_field: str,
    expected_stderr: str,
) -> None:
    fixture_path = tmp_path / "missing-nested-field.json"
    fixture = _basic_fixture()
    del fixture[field][0][nested_field]
    fixture_path.write_text(json.dumps(fixture))

    assert main(["--fixture-pr", str(fixture_path)]) == 2
    assert expected_stderr in capsys.readouterr().err


@pytest.mark.parametrize(
    ("fixture_mutation", "expected_stderr"),
    (
        (lambda data: data.pop("target"), "fixture.target is required"),
        (lambda data: data.update({"changed_files": []}), "fixture.changed_files"),
        (lambda data: data.update({"raw_reviewer_outputs": []}), "fixture.raw_reviewer_outputs"),
    ),
)
def test_invalid_fixture_returns_nonzero(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    fixture_mutation,
    expected_stderr: str,
) -> None:
    fixture = _basic_fixture()
    fixture_mutation(fixture)
    fixture_path = tmp_path / "invalid.json"
    fixture_path.write_text(json.dumps(fixture))

    exit_code = main(["--fixture-pr", str(fixture_path)])

    assert exit_code == 2
    assert expected_stderr in capsys.readouterr().err


def test_invalid_json_and_missing_path_return_nonzero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{")

    assert main(["--fixture-pr", str(bad_json)]) == 2
    assert "fixture JSON is invalid" in capsys.readouterr().err

    assert main(["--fixture-pr", str(tmp_path / "missing.json")]) == 2
    assert "fixture reference not found" in capsys.readouterr().err


def test_invalid_reviewer_config_returns_nonzero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config_path = tmp_path / "reviewers.json"
    config_path.write_text(json.dumps({"agents": {}}))

    assert main(["--fixture-pr", "basic-pr", "--reviewer-config", str(config_path)]) == 2
    assert "reviewer config agents" in capsys.readouterr().err


def test_no_eligible_reviewer_returns_nonzero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config_path = tmp_path / "reviewers.json"
    config_path.write_text(
        json.dumps(
            {
                "agents": {
                    "logic": {
                        "stages": ["logic_review"],
                        "triggers": {"always": True},
                    }
                }
            }
        )
    )

    assert main(["--fixture-pr", "basic-pr", "--reviewer-config", str(config_path)]) == 2
    assert "initial_triage" in capsys.readouterr().err


def test_oversized_fixture_returns_nonzero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    fixture_path = tmp_path / "oversized.json"
    fixture_path.write_text(" " * (MAX_FIXTURE_BYTES + 1))

    assert main(["--fixture-pr", str(fixture_path)]) == 2
    assert "exceeds" in capsys.readouterr().err


def test_unwritable_output_path_returns_nonzero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    assert main(["--fixture-pr", "basic-pr", "--json-out", str(output_dir)]) == 2
    assert "failed to write output path" in capsys.readouterr().err


def test_malformed_manifest_is_rejected(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({"fixtures": [{"id": "broken"}]}))

    with pytest.raises(FixtureError, match="manifest fixtures"):
        load_manifest(path=manifest_path)


def test_cli_does_not_expose_post_flag() -> None:
    assert main(["--post"]) != 0


def test_cli_runner_and_fixture_modules_have_no_side_effect_imports() -> None:
    forbidden = {"side_effects", "github", "transport", "approval", "finalization", "marker", "os"}
    for path in (Path("src/reviewgraph/cli.py"), Path("src/reviewgraph/runner.py"), Path("src/reviewgraph/fixtures.py")):
        tree = ast.parse(path.read_text())
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)
        assert not any(
            any(part == forbidden_name for part in imported.split("."))
            for imported in imports
            for forbidden_name in forbidden
        )


def _basic_fixture_text() -> str:
    return resources.files("reviewgraph").joinpath("fixtures_data/prs/basic-pr.json").read_text()


def _basic_fixture() -> dict[str, object]:
    return json.loads(_basic_fixture_text())
