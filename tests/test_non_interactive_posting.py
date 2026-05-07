import ast
from pathlib import Path

import pytest

from reviewgraph.cli import _parser, main
from reviewgraph.post_interaction import NON_INTERACTIVE_POST_MODE_ERROR_CODE
from reviewgraph.runner import run_fixture_dry_run, run_fixture_non_interactive_post_attempt


def test_default_dry_run_does_not_evaluate_post_interaction_gate() -> None:
    result = run_fixture_dry_run(fixture_ref="basic-pr")

    assert result.json_data["run_mode"] == "dry_run"
    assert "## Postable Findings" in result.markdown
    assert "post_interaction_gate" not in result.json_data
    assert "approval" not in result.json_data
    assert all(
        entry.get("event") != "post_mode_interaction_gate"
        for entry in result.json_data["graph_trace"]
        if isinstance(entry, dict)
    )


def test_cli_post_flag_is_not_public(capsys: pytest.CaptureFixture[str]) -> None:
    parser = _parser()

    assert main(["--post"]) == 2
    captured = capsys.readouterr()
    assert "unrecognized arguments" in captured.err
    assert "--post" not in parser.format_help()
    assert "--post" not in {
        option
        for action in parser._actions
        for option in action.option_strings
    }


@pytest.mark.parametrize(
    "reason",
    ("ci", "webhook", "config_only", "non_tty_cli"),
)
def test_non_interactive_post_attempt_fails_closed_before_side_effects(reason: str) -> None:
    class RaisingWriter:
        call_count = 0

        def __call__(self) -> None:
            self.call_count += 1
            raise AssertionError("writer must not be called")

    def approval_prompt() -> object:
        raise AssertionError("approval prompt must not be called")

    def final_payload_builder() -> object:
        raise AssertionError("final payload builder must not be called")

    result = run_fixture_non_interactive_post_attempt(
        fixture_ref="basic-pr",
        writer_sentinel=RaisingWriter(),
        non_interactive_reason=reason,
        approval_prompt=approval_prompt,
        final_payload_builder=final_payload_builder,
    )

    data = result.json_data
    assert data["run_mode"] == "post"
    assert data["post_enabled"] is False
    assert data["post_interaction_gate"] == {
        "status": "fail",
        "interactive": False,
        "reason": f"non_interactive_posting_requires_future_policy:{reason}",
    }
    assert data["side_effects"] == {"writer_called": False, "writer_call_count": 0}
    assert result.writer_call_count == 0
    assert data["review"]["candidate_payload_preview"]["artifact_kind"] == "issue_comment"
    assert data["approval"] is None
    assert data["final_github_payload"] is None
    assert data["final_payload_hash"] is None
    assert data["marker_reconciliation"] is None
    assert data["writer_result"] is None
    assert any(
        error["code"] == NON_INTERACTIVE_POST_MODE_ERROR_CODE
        and "future explicit approval policy" in error["message"]
        for error in data["errors"]
    )
    assert "future explicit approval policy" in result.markdown


def test_non_interactive_post_trace_stops_before_approval_and_finalization() -> None:
    result = run_fixture_non_interactive_post_attempt(fixture_ref="basic-pr")
    events = [
        entry.get("event")
        for entry in result.json_data["graph_trace"]
        if isinstance(entry, dict)
    ]

    assert events[-2:] == ["render_review", "post_mode_interaction_gate"]
    assert "approval_gate" not in events
    assert "finalize_github_payload" not in events
    assert "post_or_emit" not in events


def test_post_interaction_gate_module_keeps_side_effect_boundaries() -> None:
    forbidden_roots = {
        "datetime",
        "github",
        "os",
        "requests",
        "subprocess",
        "sys",
        "time",
    }
    forbidden_reviewgraph_modules = {
        "reviewgraph.approval",
        "reviewgraph.finalization",
        "reviewgraph.github",
        "reviewgraph.markers",
        "reviewgraph.side_effects",
        "reviewgraph.transport",
        "reviewgraph.writer",
    }
    tree = ast.parse(Path("src/reviewgraph/post_interaction.py").read_text())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    assert not (imported & forbidden_reviewgraph_modules)
    assert not ({name.split(".", 1)[0] for name in imported} & forbidden_roots)
