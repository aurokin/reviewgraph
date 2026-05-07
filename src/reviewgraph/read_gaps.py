from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from reviewgraph.models import GraphError, ReadGap, RedactionStatus, ReviewTarget
from reviewgraph.redaction import redact_data, redact_text


GITHUB_READ_GAP_TRACE = "github_read_gap_fail_closed"

_REASON_RETRYABLE = {
    "forbidden": False,
    "not_found": False,
    "rate_limited": True,
    "timeout": True,
    "unavailable": False,
    "pagination_incomplete": True,
    "thread_state_unknown": False,
    "not_fetched_in_scope": True,
}


class PullRequestRefContext(Protocol):
    owner_repo: str
    pr_number: int


@dataclass(frozen=True)
class GitHubPageGapDescriptor:
    resource: str
    missing_page: int
    underlying_reason: str
    would_affect: tuple[str, ...]
    examples: tuple[str, ...] = ()


@dataclass(frozen=True)
class FailClosedReadOutcome:
    pr_ref: PullRequestRefContext | None
    review_target: ReviewTarget | None
    read_gaps: tuple[ReadGap, ...]
    errors: tuple[GraphError, ...]
    post_enabled: bool
    selected_reviewers: tuple[Any, ...]
    reviewer_run_status: tuple[Any, ...]
    reviewer_results: tuple[Any, ...]
    findings: tuple[Any, ...]
    posting_plan: None
    candidate_payload: None
    graph_trace: tuple[str, ...]


@dataclass(frozen=True)
class TargetlessReadFailureRender:
    markdown: str
    json_data: dict[str, Any]
    redaction_status: RedactionStatus


def classify_github_read_gap(
    *,
    resource: str,
    required: bool,
    status: int | None = None,
    reason: str | None = None,
    message: str | None = None,
    page: int | None = None,
) -> ReadGap:
    reason_code = _reason_from_status_or_code(status=status, reason=reason)
    retryable = _REASON_RETRYABLE[reason_code]
    return ReadGap(
        resource=resource,
        required=required,
        reason=reason_code,
        retryable=retryable,
    )


def graph_errors_from_read_gaps(read_gaps: tuple[ReadGap, ...] | list[ReadGap]) -> tuple[GraphError, ...]:
    return tuple(
        GraphError(
            code="github_read_gap",
            message=f"Required GitHub read gap for {gap.resource}: {gap.reason}",
            retryable=gap.retryable,
        )
        for gap in read_gaps
        if gap.required
    )


def build_fail_closed_read_outcome(
    *,
    pr_ref: PullRequestRefContext | None,
    read_gaps: tuple[ReadGap, ...],
    review_target: ReviewTarget | None = None,
    errors: tuple[GraphError, ...] | None = None,
) -> FailClosedReadOutcome:
    if not any(gap.required for gap in read_gaps):
        raise ValueError("fail-closed read outcome requires at least one required GitHub read gap")
    derived_errors = graph_errors_from_read_gaps(read_gaps)
    return FailClosedReadOutcome(
        pr_ref=pr_ref,
        review_target=review_target,
        read_gaps=read_gaps,
        errors=derived_errors + tuple(errors or ()),
        post_enabled=False,
        selected_reviewers=(),
        reviewer_run_status=(),
        reviewer_results=(),
        findings=(),
        posting_plan=None,
        candidate_payload=None,
        graph_trace=(GITHUB_READ_GAP_TRACE,),
    )


def render_targetless_read_failure(
    *,
    pr_ref: PullRequestRefContext,
    read_gaps: tuple[ReadGap, ...],
    error_message: str,
) -> TargetlessReadFailureRender:
    outcome = build_fail_closed_read_outcome(pr_ref=pr_ref, read_gaps=read_gaps)
    data = {
        "run_mode": "dry_run",
        "post_enabled": False,
        "pr_ref": {
            "owner_repo": pr_ref.owner_repo,
            "pr_number": pr_ref.pr_number,
        },
        "review_target": None,
        "graph_trace": list(outcome.graph_trace),
        "selected_reviewers": [],
        "read_gaps": [_raw_read_gap_json(gap) for gap in read_gaps],
        "errors": [_raw_error_json(error) for error in outcome.errors],
        "error_message": error_message,
        "review": {
            "postable_findings": [],
            "candidate_payload_preview": None,
        },
    }
    redacted = redact_data(data)
    if not isinstance(redacted.data, dict):
        raise ValueError("targetless read failure render must produce an object")
    status = RedactionStatus(
        redacted=redacted.redaction_status.redacted,
        replacement_count=redacted.redaction_status.replacement_count,
        categories=redacted.redaction_status.categories,
    )
    redacted.data["redaction_status"] = {
        "redacted": status.redacted,
        "replacement_count": status.replacement_count,
        "categories": list(status.categories),
    }
    markdown = _targetless_markdown(redacted.data)
    return TargetlessReadFailureRender(
        markdown=markdown,
        json_data=redacted.data,
        redaction_status=status,
    )


def read_gap_json(
    gap: ReadGap,
    *,
    page_gap: GitHubPageGapDescriptor | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "resource": redact_text(gap.resource).text,
        "required": gap.required,
        "reason": redact_text(gap.reason).text,
        "retryable": gap.retryable,
        "usage": "required_fail_closed" if gap.required else "visible_only_not_routing_evidence_or_public_payload",
    }
    if page_gap is not None:
        data["page_gap"] = {
            "resource": redact_text(page_gap.resource).text,
            "missing_page": page_gap.missing_page,
            "underlying_reason": redact_text(page_gap.underlying_reason).text,
            "would_affect": [redact_text(item).text for item in page_gap.would_affect],
            "examples": [redact_text(example).text for example in page_gap.examples],
        }
    return data


def _reason_from_status_or_code(*, status: int | None, reason: str | None) -> str:
    if reason in _REASON_RETRYABLE:
        return reason
    if status == 403:
        return "forbidden"
    if status == 404:
        return "not_found"
    if status == 429:
        return "rate_limited"
    return "unavailable"


def _error_json(error: GraphError) -> dict[str, Any]:
    return {
        "code": redact_text(error.code).text,
        "message": redact_text(error.message).text,
        "retryable": error.retryable,
    }


def _raw_read_gap_json(gap: ReadGap) -> dict[str, Any]:
    return {
        "resource": gap.resource,
        "required": gap.required,
        "reason": gap.reason,
        "retryable": gap.retryable,
        "usage": "required_fail_closed" if gap.required else "visible_only_not_routing_evidence_or_public_payload",
    }


def _raw_error_json(error: GraphError) -> dict[str, Any]:
    return {
        "code": error.code,
        "message": error.message,
        "retryable": error.retryable,
    }


def _targetless_markdown(data: dict[str, Any]) -> str:
    lines = [
        "# ReviewGraph Dry Run",
        "",
        "## Read Failure",
        f"- PR: {data['pr_ref']['owner_repo']}#{data['pr_ref']['pr_number']}",
        f"- Post enabled: {str(data['post_enabled']).lower()}",
        f"- Error: {data['error_message']}",
        "",
        "## Read Gaps",
    ]
    read_gaps = data.get("read_gaps", [])
    if read_gaps:
        for gap in read_gaps:
            lines.append(
                f"- {gap['resource']}: required={str(gap['required']).lower()}, "
                f"retryable={str(gap['retryable']).lower()} - {gap['reason']}"
            )
    else:
        lines.append("- None")
    lines.extend(["", "## Candidate Payload Preview", "- None"])
    return "\n".join(lines) + "\n"
