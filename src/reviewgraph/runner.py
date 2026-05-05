from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from reviewgraph.fixtures import (
    FixtureError,
    FixturePR,
    ReviewerConfig,
    assert_changed_line,
    load_fixture_pr,
    load_reviewer_config,
    redact_for_error,
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
    SuggestedReply,
    SuppressedOutput,
    TruncationNotice,
)
from reviewgraph.posting import (
    CandidateIssueCommentPayload,
    PostingDestination,
    PostingPlan,
    PostingPlanItem,
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
    writer_call_count_before = _writer_call_count(writer_sentinel)
    fixture = load_fixture_pr(fixture_ref)
    config = load_reviewer_config(reviewer_config_path)
    selected_reviewers = _select_reviewers(config)
    graph_trace = [_initial_triage_trace()]
    review_target = _review_target(fixture)
    memory_references = _memory_references(fixture)
    truncation_notices = _truncation_notices(fixture)
    classified = _classify_raw_outputs(fixture, selected_reviewers=selected_reviewers)
    _validate_output_item_ids(classified)
    _validate_finding_fingerprints(classified["findings"])
    local_verdict = _local_verdict(
        findings=classified["findings"],
        clarification_requests=classified["clarification_requests"],
    )
    post_enabled = local_verdict == ReviewVerdict.COMMENT and bool(classified["findings"])
    posting_plan = build_posting_plan(
        findings=classified["findings"],
        local_notes=classified["local_notes"],
        suggested_replies=classified["suggested_replies"],
        clarification_requests=classified["clarification_requests"],
        suppressed_outputs=classified["suppressed_outputs"],
    )
    if not post_enabled:
        posting_plan = _local_only_posting_plan(posting_plan)
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
        suggested_replies=classified["suggested_replies"],
        suppressed_outputs=classified["suppressed_outputs"],
        local_verdict=local_verdict,
        posting_plan=posting_plan,
        candidate_payload=candidate_payload,
        memory_references=memory_references,
        truncation_notices=truncation_notices,
    )
    writer_call_count = _writer_call_count(writer_sentinel) - writer_call_count_before
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
        owner_repo=target["owner_repo"],
        pr_number=target["pr_number"],
        base_sha=target["base_sha"],
        head_sha=target["head_sha"],
        merge_base_sha=target.get("merge_base_sha"),
        diff_basis=target["diff_basis"],
    )


def _memory_references(fixture: FixturePR) -> tuple[MemoryReference, ...]:
    memory_references: list[MemoryReference] = []
    for item in fixture.memory:
        _require_fields(item, ("id", "trust_label", "resolved_status", "source_type"), "memory")
        body = item.get("body")
        if body is not None and not isinstance(body, str):
            raise RunnerError("memory.body must be a string or null")
        memory_references.append(
            MemoryReference(
                id=_required_str(item, "id", "memory"),
                trust_label=_required_str(item, "trust_label", "memory"),
                resolved_status=_required_str(item, "resolved_status", "memory"),
                source_type=_required_str(item, "source_type", "memory"),
                body=body,
            )
        )
    return tuple(memory_references)


def _truncation_notices(fixture: FixturePR) -> tuple[TruncationNotice, ...]:
    notices: list[TruncationNotice] = []
    for item in fixture.truncation:
        _require_fields(item, ("resource", "truncated", "note"), "truncation")
        notices.append(
            TruncationNotice(
                resource=_required_str(item, "resource", "truncation"),
                truncated=_required_bool(item, "truncated", "truncation"),
                note=_required_str(item, "note", "truncation"),
                original_count=_optional_int(item, "original_count", "truncation"),
                retained_count=_optional_int(item, "retained_count", "truncation"),
                original_bytes=_optional_int(item, "original_bytes", "truncation"),
                retained_bytes=_optional_int(item, "retained_bytes", "truncation"),
            )
        )
    return tuple(notices)


def _classify_raw_outputs(
    fixture: FixturePR,
    *,
    selected_reviewers: tuple[SelectedReviewer, ...],
) -> dict[str, tuple[Any, ...]]:
    findings: list[ClassifiedFinding] = []
    local_notes: list[LocalNote] = []
    clarification_requests: list[ClarificationRequest] = []
    suggested_replies: list[SuggestedReply] = []
    suppressed_outputs: list[SuppressedOutput] = []
    selected_keys = {(reviewer.name, reviewer.stage) for reviewer in selected_reviewers}
    seen_keys: set[tuple[str, str]] = set()
    for reviewer_output in fixture.raw_reviewer_outputs:
        if not isinstance(reviewer_output, dict):
            raise RunnerError("raw_reviewer_outputs entries must be objects")
        reviewer = _required_str(reviewer_output, "reviewer", "raw_reviewer_outputs[]")
        stage = _required_str(reviewer_output, "stage", "raw_reviewer_outputs[]")
        if (reviewer, stage) not in selected_keys:
            raise RunnerError(f"raw reviewer output {reviewer}/{stage} was not selected")
        if (reviewer, stage) in seen_keys:
            raise RunnerError(f"raw reviewer output {reviewer}/{stage} is duplicated")
        seen_keys.add((reviewer, stage))
        items = reviewer_output.get("items")
        if not reviewer or not stage or not isinstance(items, list):
            raise RunnerError("raw reviewer output requires reviewer, stage, and items")
        for item in items:
            if not isinstance(item, dict):
                raise RunnerError("raw reviewer output items must be objects")
            item_type = _required_str(item, "type", "raw reviewer output item")
            if item_type == "postable_finding":
                finding = _classified_finding(fixture, reviewer=reviewer, stage=stage, item=item)
                if _is_postable_finding(finding):
                    findings.append(finding)
                else:
                    suppressed_outputs.append(
                        SuppressedOutput(
                            id=finding.id,
                            reason="Finding candidate did not meet postable quality policy.",
                        )
                    )
            elif item_type == "local_note":
                _require_fields(item, ("id", "title", "body", "evidence"), "local_note")
                local_notes.append(
                    LocalNote(
                        id=_required_str(item, "id", "local_note"),
                        title=_required_str(item, "title", "local_note"),
                        body=_required_str(item, "body", "local_note"),
                        evidence=_required_str(item, "evidence", "local_note"),
                    )
                )
            elif item_type == "clarification_request":
                _require_fields(item, ("id", "question", "why_it_matters"), "clarification_request")
                clarification_requests.append(
                    ClarificationRequest(
                        id=_required_str(item, "id", "clarification_request"),
                        reviewer=reviewer,
                        question=_required_str(item, "question", "clarification_request"),
                        why_it_matters=_required_str(item, "why_it_matters", "clarification_request"),
                    )
                )
            elif item_type == "suggested_reply":
                _require_fields(item, ("id", "source_comment_id", "proposed_body"), "suggested_reply")
                suggested_replies.append(
                    SuggestedReply(
                        id=_required_str(item, "id", "suggested_reply"),
                        source_comment_id=_required_str(item, "source_comment_id", "suggested_reply"),
                        proposed_body=_required_str(item, "proposed_body", "suggested_reply"),
                    )
                )
            elif item_type == "suppressed":
                _require_fields(item, ("id", "reason"), "suppressed")
                suppressed_outputs.append(
                    SuppressedOutput(
                        id=_required_str(item, "id", "suppressed"),
                        reason=_required_str(item, "reason", "suppressed"),
                    )
                )
            else:
                raise RunnerError(f"unsupported raw reviewer output type: {item_type}")
    missing_keys = sorted(selected_keys - seen_keys)
    if missing_keys:
        missing = ", ".join(f"{reviewer}/{stage}" for reviewer, stage in missing_keys)
        raise RunnerError(f"missing raw reviewer output for selected reviewer: {missing}")
    return {
        "findings": tuple(findings),
        "local_notes": tuple(local_notes),
        "clarification_requests": tuple(clarification_requests),
        "suggested_replies": tuple(suggested_replies),
        "suppressed_outputs": tuple(suppressed_outputs),
    }


def _validate_finding_fingerprints(findings: tuple[ClassifiedFinding, ...]) -> None:
    seen: set[str] = set()
    for finding in findings:
        if redact_for_error(finding.fingerprint) != finding.fingerprint:
            raise RunnerError("postable_finding.fingerprint requires a non-secret stable identity")
        if finding.fingerprint in seen:
            raise RunnerError("postable_finding.fingerprint must be unique")
        seen.add(finding.fingerprint)


def _validate_output_item_ids(classified: dict[str, tuple[Any, ...]]) -> None:
    seen: set[str] = set()
    for collection in classified.values():
        for item in collection:
            item_id = item.id
            if redact_for_error(item_id) != item_id:
                raise RunnerError("classified output item ids require non-secret stable identities")
            if item_id in seen:
                raise RunnerError("classified output item ids must be unique")
            seen.add(item_id)


def _classified_finding(
    fixture: FixturePR,
    *,
    reviewer: str,
    stage: str,
    item: dict[str, Any],
) -> ClassifiedFinding:
    _require_fields(
        item,
        (
            "id",
            "title",
            "body",
            "evidence",
            "path",
            "line",
            "priority",
            "severity",
            "confidence",
            "fingerprint",
        ),
        "postable_finding",
    )
    path = _required_str(item, "path", "postable_finding")
    line = _required_int(item, "line", "postable_finding")
    assert_changed_line(fixture, path=path, line=line)
    return ClassifiedFinding(
        id=_required_str(item, "id", "postable_finding"),
        source_reviewer=reviewer,
        source_stage=stage,
        title=_required_str(item, "title", "postable_finding"),
        body=_required_str(item, "body", "postable_finding"),
        evidence=_required_str(item, "evidence", "postable_finding"),
        path=path,
        line=line,
        priority=_required_int(item, "priority", "postable_finding"),
        severity=Severity(_required_str(item, "severity", "postable_finding")),
        confidence=Confidence(_required_str(item, "confidence", "postable_finding")),
        fingerprint=_required_str(item, "fingerprint", "postable_finding"),
    )


def _is_postable_finding(finding: ClassifiedFinding) -> bool:
    if finding.confidence != Confidence.HIGH:
        return False
    if not _has_concrete_finding_evidence(finding.evidence):
        return False
    text = f"{finding.title}\n{finding.body}\n{finding.evidence}".casefold()
    if _is_testing_advice(finding, text):
        return _has_testing_finding_shape(text)
    if _is_generic_speculative_advice(text):
        return False
    if not _has_non_testing_finding_shape(text):
        return False
    generic_refactor_advice = (
        "clean this up",
        "cleaner structure",
        "could be refactored",
        "easier maintenance",
        "easier to maintain",
        "easier to read",
        "cleaner code",
        "better organization",
        "better structure",
        "better modularity",
        "decoupling",
        "modularity",
        "testability",
        "improve maintainability",
        "abstractions",
        "future maintainer",
        "future maintainers",
        "improve readability",
        "refactor this",
        "simplify this code",
        "when this grows",
    )
    return not any(phrase in text for phrase in generic_refactor_advice)


def _has_concrete_finding_evidence(evidence: str) -> bool:
    normalized = evidence.casefold().strip()
    return not bool(re.fullmatch(r"changed line \d+\.?", normalized))


def _is_testing_advice(finding: ClassifiedFinding, text: str) -> bool:
    if finding.source_reviewer == "testing":
        return True
    testing_terms = (
        "add tests",
        "improve coverage",
        "missing coverage",
        "missing test",
        "missing tests",
        "no regression coverage",
        "no test coverage",
        "please add tests",
        "regression test",
        "test coverage",
        "without tests",
    )
    return any(term in text for term in testing_terms)


def _has_testing_finding_shape(text: str) -> bool:
    missing_coverage = (
        ("coverage" in text or "test" in text)
        and any(term in text for term in ("missing", "no ", "without", "lacks", "not covered", "does not cover"))
    )
    changed_behavior = any(
        term in text
        for term in (
            "changed behavior",
            "changed line",
            "new branch",
            "introduced",
            "now ",
            "regress",
            "returns",
            "raises",
            "fails",
            "skips",
            "drops",
            "leaks",
            "breaks",
        )
    )
    scenario = bool(re.search(r"\b(when|if|after|before|with|without|on)\b", text))
    return (
        missing_coverage
        and changed_behavior
        and scenario
        and not _has_vague_testing_scenario(text)
        and _has_specific_testing_target(text)
    )


def _has_vague_testing_scenario(text: str) -> bool:
    return any(phrase in text for phrase in ("for this change", "when this changes", "this changes", "changed behavior"))


def _has_specific_testing_target(text: str) -> bool:
    return bool(
        re.search(
            r"\b(cache|auth|login|redirect|filename|visibility|session|token|header|api|request|response|caller|input|path)\b",
            text,
        )
    )


def _is_generic_speculative_advice(text: str) -> bool:
    speculative_terms = (
        "could cause problems",
        "may cause problems",
        "might cause problems",
        "potential issue",
        "requires investigation",
        "should investigate",
    )
    return any(term in text for term in speculative_terms)


def _has_non_testing_finding_shape(text: str) -> bool:
    changed_behavior = any(
        term in text
        for term in (
            "accepts",
            "allows",
            "breaks",
            "bypasses",
            "cannot",
            "corrupts",
            "drops",
            "exposes",
            "fails",
            "hangs",
            "ignores",
            "includes",
            "leaks",
            "misroutes",
            "omits",
            "permits",
            "raises",
            "regress",
            "rejects",
            "returns",
            "skips",
            "stale",
            "unauthorized",
            "open redirect",
            "path traversal",
            "unauthenticated access",
        )
    )
    scenario = bool(re.search(r"\b(when|if|after|before|with|without|for|on|in|to|via|from|while|where)\b", text))
    return changed_behavior and scenario


def _require_fields(data: dict[str, Any], fields: tuple[str, ...], label: str) -> None:
    for field in fields:
        if field not in data:
            raise RunnerError(f"{label}.{field} is required")


def _required_str(data: dict[str, Any], field: str, label: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value:
        raise RunnerError(f"{label}.{field} is required")
    return value


def _required_int(data: dict[str, Any], field: str, label: str) -> int:
    value = data.get(field)
    if type(value) is not int:
        raise RunnerError(f"{label}.{field} must be an integer")
    return value


def _required_bool(data: dict[str, Any], field: str, label: str) -> bool:
    value = data.get(field)
    if type(value) is not bool:
        raise RunnerError(f"{label}.{field} must be a boolean")
    return value


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


def _local_only_posting_plan(posting_plan: PostingPlan) -> PostingPlan:
    return PostingPlan(
        items=tuple(
            item
            if not item.public_payload_eligible
            else PostingPlanItem(
                id=item.id,
                source_classification=item.source_classification,
                destination=PostingDestination.LOCAL_ONLY,
                public_payload_eligible=False,
                fingerprint=item.fingerprint,
                body=item.body,
            )
            for item in posting_plan.items
        )
    )


def _writer_call_count(writer_sentinel: object | None) -> int:
    if writer_sentinel is None:
        return 0
    value = getattr(writer_sentinel, "call_count", 0)
    if type(value) is not int:
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
    return _redact_json_value({
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
    })


def _optional_int(data: dict[str, Any], field: str, label: str) -> int | None:
    value = data.get(field)
    if value is None:
        return None
    if type(value) is not int:
        raise RunnerError(f"{label}.{field} must be an integer or null")
    return value


def _redact_json_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_for_error(value)
    if isinstance(value, list):
        return [_redact_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _redact_json_value(item) for key, item in value.items()}
    return value
