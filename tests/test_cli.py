import ast
import json
import os
import subprocess
import sys
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


def test_cli_prints_markdown_by_default(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--fixture-pr", "basic-pr"]) == 0

    captured = capsys.readouterr()
    assert "# ReviewGraph Dry Run" in captured.out
    assert captured.err == ""


def test_cli_parse_errors_are_redacted(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--unknown", "ghp_abcdefghijklmnopqrstuvwxyz123456"]) == 2

    captured = capsys.readouterr()
    assert "unrecognized arguments" in captured.err
    assert "ghp_" not in captured.err
    assert "abcdefghijklmnopqrstuvwxyz" not in captured.err
    assert "[REDACTED]" in captured.err


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


def test_fixture_id_resolution_is_not_shadowed_by_local_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    Path("basic-pr").write_text("{}")

    result = run_fixture_dry_run(fixture_ref="basic-pr")

    assert result.json_data["fixture_id"] == "basic-pr"
    assert result.json_data["review"]["review_target"]["owner_repo"] == "acme/widgets"


def test_module_command_works_with_editable_install(tmp_path: Path) -> None:
    venv_dir = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
    python = venv_dir / "bin" / "python"
    subprocess.run([str(python), "-m", "pip", "install", "-e", "."], check=True, stdout=subprocess.DEVNULL)

    completed = subprocess.run(
        [str(python), "-m", "reviewgraph.cli", "--fixture-pr", "basic-pr", "--print-markdown"],
        check=True,
        capture_output=True,
        text=True,
    )

    assert "# ReviewGraph Dry Run" in completed.stdout
    assert completed.stderr == ""


def test_module_command_works_from_checkout_with_pythonpath() -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    completed = subprocess.run(
        [sys.executable, "-m", "reviewgraph.cli", "--fixture-pr", "basic-pr", "--print-markdown"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    assert "# ReviewGraph Dry Run" in completed.stdout
    assert completed.stderr == ""


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


def test_writer_proof_uses_per_run_delta() -> None:
    class ReusedWriter:
        call_count = 3

    result = run_fixture_dry_run(fixture_ref="basic-pr", writer_sentinel=ReusedWriter())

    assert result.writer_call_count == 0
    assert result.json_data["side_effects"] == {"writer_called": False, "writer_call_count": 0}


def test_fixture_run_redacts_secret_like_content(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "ghs_abcdefghijklmnopqrstuvwxyz123456")
    markdown_path = tmp_path / "review.md"
    json_path = tmp_path / "review.json"

    assert main(["--markdown-out", str(markdown_path), "--json-out", str(json_path)]) == 0

    serialized = markdown_path.read_text() + json_path.read_text()
    for leaked in ("sk_live", "ghp_", "ghs_", "abcdefghijklmnopqrstuvwxyz", "SECRET_TOKEN"):
        assert leaked not in serialized
    assert "[REDACTED]" in serialized


def test_top_level_json_envelope_redacts_fixture_strings(tmp_path: Path) -> None:
    fixture_path = tmp_path / "secret-ref.json"
    fixture = _basic_fixture()
    fixture["id"] = "ghp_abcdefghijklmnopqrstuvwxyz123456"
    fixture["pr_ref"] = "fixture:ghp_abcdefghijklmnopqrstuvwxyz123456"
    fixture_path.write_text(json.dumps(fixture))
    json_path = tmp_path / "review.json"

    assert main(["--fixture-pr", str(fixture_path), "--json-out", str(json_path)]) == 0

    serialized = json_path.read_text()
    assert "ghp_" not in serialized
    assert "abcdefghijklmnopqrstuvwxyz" not in serialized
    assert "[REDACTED]" in serialized


def test_renderer_outputs_redact_secret_like_target_and_path_metadata(tmp_path: Path) -> None:
    fixture_path = tmp_path / "secret-markdown.json"
    fixture = _basic_fixture()
    fixture["target"]["owner_repo"] = "ghp_abcdefghijklmnopqrstuvwxyz123456/repo"
    fixture["target"]["head_sha"] = "ghs_abcdefghijklmnopqrstuvwxyz123456"
    fixture["changed_files"][0]["path"] = "src/ghp_abcdefghijklmnopqrstuvwxyz123456.py"
    fixture["raw_reviewer_outputs"][0]["items"][0]["path"] = "src/ghp_abcdefghijklmnopqrstuvwxyz123456.py"
    fixture_path.write_text(json.dumps(fixture))

    result = run_fixture_dry_run(fixture_ref=str(fixture_path))

    serialized = result.markdown + json.dumps(result.rendered.json_data) + json.dumps(result.json_data)
    assert "ghp_" not in serialized
    assert "ghs_" not in serialized
    assert "abcdefghijklmnopqrstuvwxyz" not in serialized
    assert "[REDACTED]" in serialized


def test_secret_like_candidate_fingerprint_fails_closed(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    fixture_path = tmp_path / "secret-fingerprint.json"
    fixture = _basic_fixture()
    fixture["raw_reviewer_outputs"][0]["items"][0]["fingerprint"] = "ghp_abcdefghijklmnopqrstuvwxyz123456"
    fixture_path.write_text(json.dumps(fixture))

    assert main(["--fixture-pr", str(fixture_path)]) == 2

    stderr = capsys.readouterr().err
    assert "postable_finding.fingerprint requires a non-secret stable identity" in stderr
    assert "ghp_" not in stderr
    assert "abcdefghijklmnopqrstuvwxyz" not in stderr


def test_secret_like_fingerprint_with_clarification_fails_closed(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture_path = tmp_path / "secret-fingerprint-with-clarification.json"
    fixture = _basic_fixture()
    fixture["raw_reviewer_outputs"][0]["items"][0]["fingerprint"] = "ghp_abcdefghijklmnopqrstuvwxyz123456"
    fixture["raw_reviewer_outputs"][0]["items"].append(
        {
            "type": "clarification_request",
            "id": "clarify-intent",
            "question": "Is this behavior intentional?",
            "why_it_matters": "The mergeability decision depends on product intent.",
        }
    )
    fixture_path.write_text(json.dumps(fixture))

    assert main(["--fixture-pr", str(fixture_path)]) == 2

    stderr = capsys.readouterr().err
    assert "postable_finding.fingerprint requires a non-secret stable identity" in stderr
    assert "ghp_" not in stderr
    assert "abcdefghijklmnopqrstuvwxyz" not in stderr


def test_duplicate_fingerprints_with_clarification_fail_closed(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture_path = tmp_path / "duplicate-fingerprint-with-clarification.json"
    fixture = _basic_fixture()
    duplicate = dict(fixture["raw_reviewer_outputs"][0]["items"][0])
    duplicate["id"] = "finding-cache-stale-copy"
    fixture["raw_reviewer_outputs"][0]["items"].append(duplicate)
    fixture["raw_reviewer_outputs"][0]["items"].append(
        {
            "type": "clarification_request",
            "id": "clarify-intent",
            "question": "Is this behavior intentional?",
            "why_it_matters": "The mergeability decision depends on product intent.",
        }
    )
    fixture_path.write_text(json.dumps(fixture))

    assert main(["--fixture-pr", str(fixture_path)]) == 2
    assert "postable_finding.fingerprint must be unique" in capsys.readouterr().err


def test_duplicate_output_item_ids_with_clarification_fail_closed(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture_path = tmp_path / "duplicate-item-id-with-clarification.json"
    fixture = _basic_fixture()
    duplicate = dict(fixture["raw_reviewer_outputs"][0]["items"][0])
    duplicate["fingerprint"] = "fixture-basic-cache-stale-copy"
    fixture["raw_reviewer_outputs"][0]["items"].append(duplicate)
    fixture["raw_reviewer_outputs"][0]["items"].append(
        {
            "type": "clarification_request",
            "id": "clarify-intent",
            "question": "Is this behavior intentional?",
            "why_it_matters": "The mergeability decision depends on product intent.",
        }
    )
    fixture_path.write_text(json.dumps(fixture))

    assert main(["--fixture-pr", str(fixture_path)]) == 2
    assert "classified output item ids must be unique" in capsys.readouterr().err


def test_secret_like_output_item_id_fails_closed(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    fixture_path = tmp_path / "secret-item-id.json"
    fixture = _basic_fixture()
    fixture["raw_reviewer_outputs"][0]["items"][0]["id"] = "finding-ghp_abcdefghijklmnopqrstuvwxyz123456"
    fixture_path.write_text(json.dumps(fixture))

    assert main(["--fixture-pr", str(fixture_path)]) == 2

    stderr = capsys.readouterr().err
    assert "classified output item ids require non-secret stable identities" in stderr
    assert "ghp_" not in stderr
    assert "abcdefghijklmnopqrstuvwxyz" not in stderr


def test_generic_low_confidence_raw_finding_is_suppressed(tmp_path: Path) -> None:
    fixture_path = tmp_path / "generic-low-confidence.json"
    fixture = _basic_fixture()
    fixture["raw_reviewer_outputs"][0]["items"] = [
        {
            "type": "postable_finding",
            "id": "finding-generic-tests",
            "title": "Please add tests",
            "body": "Please add tests for this change.",
            "evidence": "Changed line 12.",
            "path": "src/cache.py",
            "line": 12,
            "priority": 2,
            "severity": "suggestion",
            "confidence": "low",
            "fingerprint": "fixture-generic-tests",
        }
    ]
    fixture_path.write_text(json.dumps(fixture))

    result = run_fixture_dry_run(fixture_ref=str(fixture_path))
    review = result.json_data["review"]

    assert result.json_data["local_verdict"] == "no_findings"
    assert result.json_data["post_enabled"] is False
    assert review["candidate_payload_preview"] is None
    assert review["classified_output"]["postable_findings"] == []
    assert review["classified_output"]["suppressed"] == [
        {
            "id": "finding-generic-tests",
            "classification": "non_finding",
            "reason": "Finding candidate did not meet postable quality policy.",
        }
    ]
    assert review["posting_plan"]["items"] == [
        {
            "id": "finding-generic-tests",
            "source_classification": "non_finding",
            "destination": "local_only",
            "public_payload_eligible": False,
            "fingerprint": None,
            "body": "Finding candidate did not meet postable quality policy.",
        }
    ]


def test_suggested_reply_fixture_is_local_only(tmp_path: Path) -> None:
    fixture_path = tmp_path / "suggested-reply.json"
    fixture = _basic_fixture()
    fixture["raw_reviewer_outputs"][0]["items"] = [
        {
            "type": "suggested_reply",
            "id": "reply-cache-question",
            "source_comment_id": "comment-1",
            "proposed_body": "Could you confirm the cache miss behavior?",
        }
    ]
    fixture_path.write_text(json.dumps(fixture))

    result = run_fixture_dry_run(fixture_ref=str(fixture_path))
    review = result.json_data["review"]

    assert result.json_data["local_verdict"] == "no_findings"
    assert result.json_data["post_enabled"] is False
    assert result.json_data["side_effects"] == {"writer_called": False, "writer_call_count": 0}
    assert review["candidate_payload_preview"] is None
    assert review["classified_output"]["suggested_replies"] == [
        {
            "id": "reply-cache-question",
            "classification": "suggested_reply",
            "source_comment_id": "comment-1",
            "proposed_body": "Could you confirm the cache miss behavior?",
        }
    ]
    assert review["posting_plan"]["items"] == [
        {
            "id": "reply-cache-question",
            "source_classification": "suggested_reply",
            "destination": "suggested_reply",
            "public_payload_eligible": False,
            "fingerprint": None,
            "body": "Could you confirm the cache miss behavior?",
        }
    ]


def test_fixture_run_redacts_standalone_underscore_api_key(tmp_path: Path) -> None:
    fixture_path = tmp_path / "standalone-secret.json"
    fixture = _basic_fixture()
    fixture["raw_reviewer_outputs"][0]["items"][0]["body"] = (
        "The new branch exposes sk_live_1234567890abcdef without a label."
    )
    fixture_path.write_text(json.dumps(fixture))

    result = run_fixture_dry_run(fixture_ref=str(fixture_path))

    serialized = result.markdown + json.dumps(result.rendered.json_data) + json.dumps(result.json_data)
    assert "sk_live" not in serialized
    assert "1234567890abcdef" not in serialized
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


def test_non_string_raw_output_type_returns_nonzero(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture_path = tmp_path / "bad-raw-type.json"
    fixture = _basic_fixture()
    fixture["raw_reviewer_outputs"][0]["items"][0]["type"] = {"not": "string"}
    fixture_path.write_text(json.dumps(fixture))

    assert main(["--fixture-pr", str(fixture_path)]) == 2
    assert "raw reviewer output item.type is required" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("field", "value", "expected_stderr"),
    (
        ("title", {"oops": "dict"}, "postable_finding.title is required"),
        ("body", ["not", "string"], "postable_finding.body is required"),
        ("fingerprint", 123, "postable_finding.fingerprint is required"),
    ),
)
def test_non_string_raw_finding_fields_return_nonzero(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    field: str,
    value: object,
    expected_stderr: str,
) -> None:
    fixture_path = tmp_path / "bad-raw-string.json"
    fixture = _basic_fixture()
    fixture["raw_reviewer_outputs"][0]["items"][0][field] = value
    fixture_path.write_text(json.dumps(fixture))

    assert main(["--fixture-pr", str(fixture_path)]) == 2
    assert expected_stderr in capsys.readouterr().err


@pytest.mark.parametrize(
    ("item_index", "field", "value", "expected_stderr"),
    (
        (1, "body", ["not", "string"], "local_note.body is required"),
        (2, "reason", {"not": "string"}, "suppressed.reason is required"),
    ),
)
def test_non_string_raw_local_fields_return_nonzero(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    item_index: int,
    field: str,
    value: object,
    expected_stderr: str,
) -> None:
    fixture_path = tmp_path / "bad-raw-local-string.json"
    fixture = _basic_fixture()
    fixture["raw_reviewer_outputs"][0]["items"][item_index][field] = value
    fixture_path.write_text(json.dumps(fixture))

    assert main(["--fixture-pr", str(fixture_path)]) == 2
    assert expected_stderr in capsys.readouterr().err


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


def test_invalid_truncation_boolean_returns_nonzero(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture_path = tmp_path / "bad-truncation-bool.json"
    fixture = _basic_fixture()
    fixture["truncation"][0]["truncated"] = "false"
    fixture_path.write_text(json.dumps(fixture))

    assert main(["--fixture-pr", str(fixture_path)]) == 2
    assert "truncation.truncated must be a boolean" in capsys.readouterr().err


def test_invalid_truncation_optional_count_returns_nonzero(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture_path = tmp_path / "bad-truncation-count.json"
    fixture = _basic_fixture()
    fixture["truncation"][0]["original_count"] = True
    fixture_path.write_text(json.dumps(fixture))

    assert main(["--fixture-pr", str(fixture_path)]) == 2
    assert "truncation.original_count must be an integer or null" in capsys.readouterr().err


def test_invalid_memory_body_type_returns_nonzero(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture_path = tmp_path / "bad-memory-body.json"
    fixture = _basic_fixture()
    fixture["memory"][0]["body"] = ["not", "a", "string"]
    fixture_path.write_text(json.dumps(fixture))

    assert main(["--fixture-pr", str(fixture_path)]) == 2
    assert "memory.body must be a string or null" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("fixture_mutation", "expected_stderr"),
    (
        (lambda data: data.pop("target"), "fixture.target is required"),
        (lambda data: data.update({"changed_files": []}), "fixture.changed_files"),
        (lambda data: data.update({"raw_reviewer_outputs": []}), "fixture.raw_reviewer_outputs"),
        (lambda data: data.update({"run_mode": "post"}), "fixture.run_mode must be dry_run"),
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


@pytest.mark.parametrize(
    ("mutation", "expected_stderr"),
    (
        (
            lambda agent: agent["triggers"].update({"stages": ["initial_triage"]}),
            "unsupported trigger fields",
        ),
        (lambda agent: agent.update({"verdict_power": "approve"}), "unsupported verdict_power"),
        (lambda agent: agent.update({"capabilities": ["github_write"]}), "unsupported capabilities"),
        (lambda agent: agent.update({"tools": ["github_write"]}), "unsupported tools"),
        (lambda agent: agent.update({"tools": ["env"]}), "unsupported tools"),
        (lambda agent: agent.update({"tools": ["llm"]}), "unsupported tools"),
        (lambda agent: agent.update({"unknown": True}), "unsupported fields"),
    ),
)
def test_unsupported_reviewer_config_fields_return_nonzero(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    mutation,
    expected_stderr: str,
) -> None:
    config = {
        "agents": {
            "correctness": {
                "stages": ["initial_triage"],
                "triggers": {"always": True},
                "verdict_power": "comment",
                "capabilities": ["diff_context"],
            }
        }
    }
    mutation(config["agents"]["correctness"])
    config_path = tmp_path / "reviewers.json"
    config_path.write_text(json.dumps(config))

    assert main(["--fixture-pr", "basic-pr", "--reviewer-config", str(config_path)]) == 2
    assert expected_stderr in capsys.readouterr().err


def test_broader_reviewer_config_with_one_eligible_reviewer_works(tmp_path: Path) -> None:
    config_path = tmp_path / "reviewers.json"
    config_path.write_text(
        json.dumps(
            {
                "agents": {
                    "correctness": {
                        "stages": ["initial_triage"],
                        "triggers": {"always": True},
                    },
                    "security": {
                        "stages": ["specialized_review"],
                        "triggers": {"paths": ["src/auth/**"]},
                    },
                }
            }
        )
    )

    result = run_fixture_dry_run(fixture_ref="basic-pr", reviewer_config_path=str(config_path))

    assert [reviewer["name"] for reviewer in result.json_data["selected_reviewers"]] == ["correctness"]


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


@pytest.mark.parametrize(
    ("field", "value", "expected_stderr"),
    (
        ("base_sha", None, "fixture.target.base_sha must be a non-empty string"),
        ("head_sha", "", "fixture.target.head_sha must be a non-empty string"),
        ("pr_number", "42", "fixture.target.pr_number must be a positive integer"),
        ("pr_number", True, "fixture.target.pr_number must be a positive integer"),
    ),
)
def test_invalid_target_metadata_returns_nonzero(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    field: str,
    value: object,
    expected_stderr: str,
) -> None:
    fixture_path = tmp_path / "bad-target.json"
    fixture = _basic_fixture()
    fixture["target"][field] = value
    fixture_path.write_text(json.dumps(fixture))

    assert main(["--fixture-pr", str(fixture_path)]) == 2
    assert expected_stderr in capsys.readouterr().err


@pytest.mark.parametrize(
    ("field", "value", "expected_stderr"),
    (
        ("line", True, "postable_finding.line must be an integer"),
        ("priority", True, "postable_finding.priority must be an integer"),
    ),
)
def test_boolean_finding_integer_fields_return_nonzero(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    field: str,
    value: object,
    expected_stderr: str,
) -> None:
    fixture_path = tmp_path / "bad-finding-int.json"
    fixture = _basic_fixture()
    fixture["raw_reviewer_outputs"][0]["items"][0][field] = value
    fixture_path.write_text(json.dumps(fixture))

    assert main(["--fixture-pr", str(fixture_path)]) == 2
    assert expected_stderr in capsys.readouterr().err


def test_missing_raw_output_for_selected_reviewer_returns_nonzero(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config_path = tmp_path / "reviewers.json"
    config_path.write_text(
        json.dumps(
            {
                "agents": {
                    "correctness": {
                        "stages": ["initial_triage"],
                        "triggers": {"always": True},
                    },
                    "security": {
                        "stages": ["initial_triage"],
                        "triggers": {"always": True},
                    },
                }
            }
        )
    )

    assert main(["--fixture-pr", "basic-pr", "--reviewer-config", str(config_path)]) == 2
    assert "missing raw reviewer output" in capsys.readouterr().err


def test_duplicate_raw_output_for_selected_reviewer_returns_nonzero(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture_path = tmp_path / "duplicate-output.json"
    fixture = _basic_fixture()
    fixture["raw_reviewer_outputs"].append(fixture["raw_reviewer_outputs"][0])
    fixture_path.write_text(json.dumps(fixture))

    assert main(["--fixture-pr", str(fixture_path)]) == 2
    assert "duplicated" in capsys.readouterr().err


def test_non_object_nested_fixture_entries_return_nonzero(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture_path = tmp_path / "bad-nested-entry.json"
    fixture = _basic_fixture()
    fixture["changed_files"][0]["changed_ranges"] = ["not-an-object"]
    fixture_path.write_text(json.dumps(fixture))

    assert main(["--fixture-pr", str(fixture_path)]) == 2
    assert "changed_ranges entries must be objects" in capsys.readouterr().err

    fixture = _basic_fixture()
    fixture["changed_files"][0]["changed_ranges"][0]["start"] = True
    fixture_path.write_text(json.dumps(fixture))

    assert main(["--fixture-pr", str(fixture_path)]) == 2
    assert "changed range start must be an integer" in capsys.readouterr().err

    fixture = _basic_fixture()
    fixture["raw_reviewer_outputs"] = ["not-an-object"]
    fixture_path.write_text(json.dumps(fixture))

    assert main(["--fixture-pr", str(fixture_path)]) == 2
    assert "raw_reviewer_outputs entries must be objects" in capsys.readouterr().err


def test_oversized_fixture_returns_nonzero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    fixture_path = tmp_path / "oversized.json"
    fixture_path.write_text(" " * (MAX_FIXTURE_BYTES + 1))

    assert main(["--fixture-pr", str(fixture_path)]) == 2
    assert "exceeds" in capsys.readouterr().err


def test_non_regular_fixture_path_returns_nonzero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    fixture_dir = tmp_path / "fixture-dir"
    fixture_dir.mkdir()

    assert main(["--fixture-pr", str(fixture_dir)]) == 2
    assert "regular file" in capsys.readouterr().err


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
