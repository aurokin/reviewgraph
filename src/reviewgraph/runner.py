from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from reviewgraph.fixtures import (
    FixtureError,
    FixturePR,
    ReviewerConfig,
    assert_changed_line,
    load_fixture_pr,
    load_reviewer_config,
)
from reviewgraph.models import (
    ClarificationRequest,
    ClassifiedFinding,
    Confidence,
    LocalNote,
    MemoryReference,
    ReviewTarget,
    ReviewVerdict,
    SelectedReviewer,
    Severity,
    SuppressedOutput,
    TruncationNotice,
)
from reviewgraph.posting import (
    CandidateIssueCommentPayload,
    PostingPlan,
    build_candidate_issue_comment_payload,
    build_posting_plan,
)
from reviewgraph.render import RenderedReview, render_review


class RunnerError(ValueError):
    pass


@dataclass(frozen=True)
class DryRunResult:
    markdown: str
    json_data: dict[str, Any]
    rendered: RenderedReview
    writer_call_count: int


def run_fixture_dry_run(
    *,
    fixture_ref: str,
    reviewer_config_path: str | None = None,
    writer_sentinel: object | None = None,
) -> DryRunResult:
    fixture = load_fixture_pr(fixture_ref)
    config = load_reviewer_config(reviewer_config_path)
    selected_reviewers = _select_reviewers(config)
    graph_trace = [_initial_triage_trace()]
    review_target = _review_target(fixture)
    memory_references = _memory_references(fixture)
    truncation_notices = _truncation_notices(fixture)
    classified = _classify_raw_outputs(fixture)
    local_verdict = _local_verdict(
        findings=classified["findings"],
        clarification_requests=classified["clarification_requests"],
    )
    post_enabled = local_verdict == ReviewVerdict.COMMENT and bool(classified["findings"])
    posting_plan = build_posting_plan(
        findings=classified["findings"] if post_enabled else (),
        local_notes=classified["local_notes"],
        clarification_requests=classified["clarification_requests"],
        suppressed_outputs=classified["suppressed_outputs"],
    )
    candidate_payload = _candidate_payload(
        enabled=post_enabled,
        review_target=review_target,
        posting_plan=posting_plan,
        findings=classified["findings"],
    )
    rendered = render_review(
        review_target=review_target,
        selected_reviewers=selected_reviewers,
        findings=classified["findings"],
        local_notes=classified["local_notes"],
        clarification_requests=classified["clarification_requests"],
        suppressed_outputs=classified["suppressed_outputs"],
        local_verdict=local_verdict,
        posting_plan=posting_plan,
        candidate_payload=candidate_payload,
        memory_references=memory_references,
        truncation_notices=truncation_notices,
    )
    writer_call_count = _writer_call_count(writer_sentinel)
    envelope = _json_envelope(
        fixture=fixture,
        post_enabled=post_enabled,
        local_verdict=local_verdict,
        selected_reviewers=selected_reviewers,
        graph_trace=graph_trace,
        writer_call_count=writer_call_count,
        rendered=rendered,
    )
    return DryRunResult(
        markdown=rendered.markdown,
        json_data=envelope,
        rendered=rendered,
        writer_call_count=writer_call_count,
    )


def _select_reviewers(config: ReviewerConfig) -> tuple[SelectedReviewer, ...]:
    selected: list[SelectedReviewer] = []
    for name in sorted(config.agents):
        agent = config.agents[name]
        stages = agent.get("stages")
        triggers = agent.get("triggers")
        if isinstance(stages, list) and "initial_triage" in stages and isinstance(triggers, dict):
            if triggers.get("always") is True:
                selected.append(
                    SelectedReviewer(
                        name=name,
                        stage="initial_triage",
                        reasons=("initial_triage triggers.always=true",),
                    )
                )
    if not selected:
        raise RunnerError("reviewer config has no eligible initial_triage always-on reviewer")
    return tuple(selected)


def _initial_triage_trace() -> dict[str, Any]:
    return {
        "active_stage_before": None,
        "active_stage_after": "initial_triage",
        "suspended_stage_before": None,
        "suspended_stage_after": None,
        "stage_queue_before": ["initial_triage", "specialized_review", "logic_review"],
        "stage_queue_after": ["specialized_review", "logic_review"],
        "transition_reason": "start_initial_triage",
    }


def _review_target(fixture: FixturePR) -> ReviewTarget:
    target = fixture.target
    return ReviewTarget(
        owner_repo=str(target["owner_repo"]),
        pr_number=int(target["pr_number"]),
        base_sha=str(target["base_sha"]),
        head_sha=str(target["head_sha"]),
        merge_base_sha=target.get("merge_base_sha"),
        diff_basis=str(target["diff_basis"]),
    )


def _memory_references(fixture: FixturePR) -> tuple[MemoryReference, ...]:
    return tuple(
        MemoryReference(
            id=str(item["id"]),
            trust_label=str(item["trust_label"]),
            resolved_status=str(item["resolved_status"]),
            source_type=str(item["source_type"]),
            body=item.get("body"),
        )
        for item in fixture.memory
    )


def _truncation_notices(fixture: FixturePR) -> tuple[TruncationNotice, ...]:
    return tuple(
        TruncationNotice(
            resource=str(item["resource"]),
            truncated=bool(item["truncated"]),
            note=str(item["note"]),
            original_count=item.get("original_count"),
            retained_count=item.get("retained_count"),
            original_bytes=item.get("original_bytes"),
            retained_bytes=item.get("retained_bytes"),
        )
        for item in fixture.truncation
    )


def _classify_raw_outputs(fixture: FixturePR) -> dict[str, tuple[Any, ...]]:
    findings: list[ClassifiedFinding] = []
    local_notes: list[LocalNote] = []
    clarification_requests: list[ClarificationRequest] = []
    suppressed_outputs: list[SuppressedOutput] = []
    for reviewer_output in fixture.raw_reviewer_outputs:
        reviewer = str(reviewer_output.get("reviewer", ""))
        stage = str(reviewer_output.get("stage", ""))
        items = reviewer_output.get("items")
        if not reviewer or not stage or not isinstance(items, list):
            raise RunnerError("raw reviewer output requires reviewer, stage, and items")
        for item in items:
            if not isinstance(item, dict):
                raise RunnerError("raw reviewer output items must be objects")
            item_type = item.get("type")
            if item_type == "postable_finding":
                finding = _classified_finding(fixture, reviewer=reviewer, stage=stage, item=item)
                findings.append(finding)
            elif item_type == "local_note":
                local_notes.append(
                    LocalNote(
                        id=str(item["id"]),
                        title=str(item["title"]),
                        body=str(item["body"]),
                        evidence=str(item["evidence"]),
                    )
                )
            elif item_type == "clarification_request":
                clarification_requests.append(
                    ClarificationRequest(
                        id=str(item["id"]),
                        reviewer=reviewer,
                        question=str(item["question"]),
                        why_it_matters=str(item["why_it_matters"]),
                    )
                )
            elif item_type == "suppressed":
                suppressed_outputs.append(SuppressedOutput(id=str(item["id"]), reason=str(item["reason"])))
            else:
                raise RunnerError(f"unsupported raw reviewer output type: {item_type}")
    return {
        "findings": tuple(findings),
        "local_notes": tuple(local_notes),
        "clarification_requests": tuple(clarification_requests),
        "suppressed_outputs": tuple(suppressed_outputs),
    }


def _classified_finding(
    fixture: FixturePR,
    *,
    reviewer: str,
    stage: str,
    item: dict[str, Any],
) -> ClassifiedFinding:
    path = str(item["path"])
    line = int(item["line"])
    assert_changed_line(fixture, path=path, line=line)
    return ClassifiedFinding(
        id=str(item["id"]),
        source_reviewer=reviewer,
        source_stage=stage,
        title=str(item["title"]),
        body=str(item["body"]),
        evidence=str(item["evidence"]),
        path=path,
        line=line,
        priority=int(item["priority"]),
        severity=Severity(str(item["severity"])),
        confidence=Confidence(str(item["confidence"])),
        fingerprint=str(item["fingerprint"]),
    )


def _local_verdict(
    *,
    findings: tuple[ClassifiedFinding, ...],
    clarification_requests: tuple[ClarificationRequest, ...],
) -> ReviewVerdict:
    if clarification_requests:
        return ReviewVerdict.NEEDS_CLARIFICATION
    if findings:
        return ReviewVerdict.COMMENT
    return ReviewVerdict.NO_FINDINGS


def _candidate_payload(
    *,
    enabled: bool,
    review_target: ReviewTarget,
    posting_plan: PostingPlan,
    findings: tuple[ClassifiedFinding, ...],
) -> CandidateIssueCommentPayload | None:
    if not enabled:
        return None
    return build_candidate_issue_comment_payload(
        review_target=review_target,
        posting_plan=posting_plan,
        findings=findings,
    )


def _writer_call_count(writer_sentinel: object | None) -> int:
    if writer_sentinel is None:
        return 0
    value = getattr(writer_sentinel, "call_count", 0)
    if not isinstance(value, int):
        return 0
    return value


def _json_envelope(
    *,
    fixture: FixturePR,
    post_enabled: bool,
    local_verdict: ReviewVerdict,
    selected_reviewers: tuple[SelectedReviewer, ...],
    graph_trace: list[dict[str, Any]],
    writer_call_count: int,
    rendered: RenderedReview,
) -> dict[str, Any]:
    return {
        "run_mode": "dry_run",
        "post_enabled": post_enabled,
        "fixture_id": fixture.id,
        "fixture_ref": fixture.pr_ref,
        "graph_trace": graph_trace,
        "local_verdict": local_verdict.value,
        "selected_reviewers": [
            {"name": reviewer.name, "stage": reviewer.stage, "reasons": list(reviewer.reasons)}
            for reviewer in selected_reviewers
        ],
        "side_effects": {
            "writer_called": writer_call_count > 0,
            "writer_call_count": writer_call_count,
        },
        "review": rendered.json_data,
    }
