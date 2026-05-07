import json
from pathlib import Path

import pytest

from reviewgraph.cli import main
from reviewgraph.targets import run_github_fake_dry_run


def test_cli_runs_github_pr_fake_data_through_dry_run_core(tmp_path: Path) -> None:
    data_path = tmp_path / "github-fake.json"
    config_path = tmp_path / "reviewers.json"
    json_path = tmp_path / "review.json"
    data_path.write_text(json.dumps(_github_fake_data()))
    config_path.write_text(json.dumps(_reviewer_config()))

    exit_code = main(
        [
            "--github-pr",
            "acme/widgets#42",
            "--github-fake-data",
            str(data_path),
            "--reviewer-config",
            str(config_path),
            "--json-out",
            str(json_path),
        ]
    )

    assert exit_code == 0
    data = json.loads(json_path.read_text())
    assert data["run_mode"] == "dry_run"
    assert data["post_enabled"] is True
    assert data["source_type"] == "github"
    assert data["source_id"] == "github:acme/widgets#42"
    assert data["source_ref"] == "github:acme/widgets#42"
    assert "fixture_id" not in data
    assert data["github_read"]["scope"] == "full_context"
    assert data["github_read"]["pr_ref"]["owner_repo"] == "acme/widgets"
    assert data["side_effects"] == {"writer_called": False, "writer_call_count": 0}
    assert data["review"]["review_target"]["owner_repo"] == "acme/widgets"
    assert data["review"]["memory"][0]["id"] == "github:issue_comment:issue-comment-1"
    assert data["review"]["memory"][0]["source_provider"] == "github"
    assert data["review"]["classified_output"]["postable_findings"][0]["diff_anchor"] == {
        "path": "src/cache.py",
        "old_path": None,
        "file_status": "modified",
        "hunk_id": "src/cache.py:10-11",
        "hunk_start": 10,
        "hunk_end": 11,
        "side": "RIGHT",
        "start_side": "RIGHT",
        "line": 11,
        "start_line": 11,
        "target_commit_sha": "head456",
    }
    assert data["review"]["candidate_payload_preview"]["artifact_kind"] == "issue_comment"


def test_cli_accepts_github_pr_url(tmp_path: Path) -> None:
    data_path = tmp_path / "github-fake.json"
    config_path = tmp_path / "reviewers.json"
    json_path = tmp_path / "review.json"
    data_path.write_text(json.dumps(_github_fake_data()))
    config_path.write_text(json.dumps(_reviewer_config()))

    exit_code = main(
        [
            "--github-pr",
            "https://github.com/acme/widgets/pull/42",
            "--github-fake-data",
            str(data_path),
            "--reviewer-config",
            str(config_path),
            "--json-out",
            str(json_path),
        ]
    )

    assert exit_code == 0
    data = json.loads(json_path.read_text())
    assert data["source_ref"] == "github:acme/widgets#42"


@pytest.mark.parametrize(
    "argv, message",
    [
        (["--github-fake-data", "fake.json"], "--github-fake-data requires --github-pr"),
        (["--github-live-read"], "--github-live-read requires --github-pr"),
        (["--github-pr", "acme/widgets#42"], "--github-pr requires --github-fake-data or --github-live-read"),
        (
            ["--github-pr", "acme/widgets#42", "--github-fake-data", "fake.json", "--github-live-read"],
            "--github-fake-data and --github-live-read cannot be combined",
        ),
        (
            ["--fixture-pr", "basic-pr", "--github-pr", "acme/widgets#42", "--github-fake-data", "fake.json"],
            "not allowed with argument",
        ),
    ],
)
def test_github_cli_option_matrix_fails_closed(
    argv: list[str],
    message: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(argv) == 2
    assert message in capsys.readouterr().err


def test_github_live_read_is_explicit_but_deferred(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--github-pr", "acme/widgets#42", "--github-live-read"]) == 2
    assert "live read is deferred" in capsys.readouterr().err


def test_github_fake_data_fail_closed_read_gap_writes_artifact(tmp_path: Path) -> None:
    data_path = tmp_path / "github-fake.json"
    config_path = tmp_path / "reviewers.json"
    json_path = tmp_path / "review.json"
    fake_data = _github_fake_data()
    fake_data["transport"]["issue_comments"]["pages"] = [
        {
            "error": {
                "reason": "timeout",
                "message": "comments page 1 timed out for sk_live_1234567890abcdef",
            }
        }
    ]
    data_path.write_text(json.dumps(fake_data))
    config_path.write_text(json.dumps(_reviewer_config()))

    exit_code = main(
        [
            "--github-pr",
            "acme/widgets#42",
            "--github-fake-data",
            str(data_path),
            "--reviewer-config",
            str(config_path),
            "--json-out",
            str(json_path),
        ]
    )

    assert exit_code == 0
    data = json.loads(json_path.read_text())
    assert data["post_enabled"] is False
    assert data["selected_reviewers"] == []
    assert data["reviewer_results"] == []
    assert data["review"]["classified_output"]["postable_findings"] == []
    assert data["review"]["candidate_payload_preview"] is None
    assert data["github_read"]["page_gap_descriptors"][0]["resource"] == "comments"
    assert data["read_gaps"][0]["resource"] == "comments"
    assert data["side_effects"] == {"writer_called": False, "writer_call_count": 0}
    assert "sk_live" not in json.dumps(data)
    assert "[REDACTED]" in json.dumps(data)


def test_github_fake_data_rejects_unselected_raw_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data_path = tmp_path / "github-fake.json"
    config_path = tmp_path / "reviewers.json"
    fake_data = _github_fake_data()
    fake_data["raw_reviewer_outputs"][0]["reviewer"] = "extra"
    data_path.write_text(json.dumps(fake_data))
    config_path.write_text(json.dumps(_reviewer_config()))

    assert main([
        "--github-pr",
        "acme/widgets#42",
        "--github-fake-data",
        str(data_path),
        "--reviewer-config",
        str(config_path),
    ]) == 2
    assert "raw reviewer output was not selected" in capsys.readouterr().err


def test_github_fake_data_rejects_duplicate_raw_output_keys(tmp_path: Path) -> None:
    data_path = tmp_path / "github-fake.json"
    fake_data = _github_fake_data()
    fake_data["raw_reviewer_outputs"].append(dict(fake_data["raw_reviewer_outputs"][0]))
    data_path.write_text(json.dumps(fake_data))

    with pytest.raises(ValueError, match="duplicated"):
        run_github_fake_dry_run(github_pr_ref="acme/widgets#42", github_fake_data_path=data_path)


def test_github_changed_line_metadata_suppresses_unanchorable_findings(tmp_path: Path) -> None:
    data_path = tmp_path / "github-fake.json"
    fake_data = _github_fake_data()
    fake_data["transport"]["files"]["pages"][0]["items"][0]["patch"] = None
    fake_data["transport"]["files"]["pages"][0]["items"][0]["patch_status"] = "binary"
    data_path.write_text(json.dumps(fake_data))

    result = run_github_fake_dry_run(github_pr_ref="acme/widgets#42", github_fake_data_path=data_path)

    assert result.json_data["post_enabled"] is False
    assert result.json_data["github_read"]["anchor_unavailable"] == [
        {"path": "src/cache.py", "reason": "patch is binary"}
    ]
    assert result.json_data["review"]["classified_output"]["postable_findings"] == []
    assert result.json_data["review"]["classified_output"]["suppressed"][0] == {
        "id": "finding-cache-stale",
        "classification": "non_finding",
        "reason": "Finding candidate referenced context omitted by context budget.",
    }


def _reviewer_config() -> dict[str, object]:
    return {
        "agents": {
            "correctness": {
                "description": "Checks deterministic GitHub dry-run behavior.",
                "stages": ["initial_triage"],
                "triggers": {"always": True},
                "required": True,
                "verdict_power": "comment",
                "capabilities": ["diff_context"],
            }
        }
    }


def _github_fake_data() -> dict[str, object]:
    return {
        "transport": {
            "pull_request": {
                "title": "Fix cache fallback",
                "body": "PR body for GitHub dry-run.",
                "author": "contributor",
                "labels": ["backend"],
                "base": {"ref": "main", "sha": "base123"},
                "head": {"ref": "fix-cache", "sha": "head456"},
                "merge_base_sha": "merge789",
                "diff_basis": "merge_base",
            },
            "files": {
                "pages": [
                    {
                        "items": [
                            {
                                "path": "src/cache.py",
                                "status": "modified",
                                "additions": 1,
                                "deletions": 1,
                                "patch_status": "available",
                                "patch": "@@ -10,2 +10,2 @@\n def read_cache():\n-    return None\n+    return stale_value",
                            }
                        ],
                        "has_next_page": False,
                    }
                ]
            },
            "issue_comments": {
                "pages": [
                    {
                        "items": [
                            {
                                "id": "issue-comment-1",
                                "author": "maintainer",
                                "author_association": "MEMBER",
                                "author_type": "user",
                                "body": "Please check the cache miss fallback.",
                                "created_at": "2026-05-06T00:00:00Z",
                                "url": None,
                            }
                        ],
                        "has_next_page": False,
                    }
                ]
            },
            "review_comments": {"pages": [{"items": [], "has_next_page": False}]},
            "reviews": {"pages": [{"items": [], "has_next_page": False}]},
            "review_threads": {"pages": [{"items": [], "has_next_page": False}]},
        },
        "raw_reviewer_outputs": [
            {
                "reviewer": "correctness",
                "stage": "initial_triage",
                "items": [
                    {
                        "type": "finding",
                        "id": "finding-cache-stale",
                        "title": "Cache miss returns stale data",
                        "body": "The changed branch returns stale data when the cache misses.",
                        "evidence": "Changed line 11 now returns stale_value.",
                        "path": "src/cache.py",
                        "line": 11,
                        "severity": "warning",
                        "confidence": "high",
                    }
                ],
            }
        ],
    }
