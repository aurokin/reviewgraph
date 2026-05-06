from reviewgraph.graph import run_empty_fixture_dry_run_graph
from reviewgraph.models import ReviewState, RunMode


EXPECTED_TARGET = {
    "owner_repo": "acme/widgets",
    "pr_number": 42,
    "base_sha": "base123",
    "head_sha": "head456",
    "merge_base_sha": "merge789",
    "diff_basis": "merge_base",
}


def test_empty_fixture_graph_initializes_dry_run_state_without_reviewers() -> None:
    writer = RaisingWriter()

    result = run_empty_fixture_dry_run_graph(fixture_ref="basic-pr", writer_sentinel=writer)
    data = result.json_data

    assert isinstance(result.review_state, ReviewState)
    assert result.review_state.run_mode == RunMode.DRY_RUN
    assert result.review_state.post_enabled is False
    assert result.review_state.local_verdict is None
    assert result.review_state.selected_reviewers == []
    assert result.review_state.findings == []
    assert result.graph_trace == ("initialize_review_state", "emit_dry_run")
    assert data["run_mode"] == "dry_run"
    assert data["post_enabled"] is False
    assert data["fixture_ref"] == "fixture:basic-pr"
    assert data["graph_trace"] == ["initialize_review_state", "emit_dry_run"]
    assert data["review_target"] == EXPECTED_TARGET
    assert data["stage_cursor"] == {
        "active_stage": None,
        "suspended_stage": None,
        "stage_queue": ["initial_triage", "specialized_review", "logic_review"],
        "completed_stages": [],
        "ready_clarification_ids": [],
        "active_clarification_id": None,
    }
    assert data["selected_reviewers"] == []
    assert data["local_verdict"] is None
    assert data["classified_output"] == {
        "findings": [],
        "local_notes": [],
        "suggested_replies": [],
        "suppressed_outputs": [],
        "clarification_requests": [],
    }
    assert data["memory"]["entry_count"] == len(result.review_state.conversation_memory.entries)
    assert data["memory"]["entry_count"] > 0
    assert data["context_budget"]["changed_file_count"] == 1
    assert data["side_effects"] == {"writer_called": False, "writer_call_count": 0}
    assert writer.call_count == 0


class RaisingWriter:
    call_count = 0

    def post(self, *_args: object, **_kwargs: object) -> None:
        self.call_count += 1
        raise AssertionError("dry-run graph must not reach writer")
