from __future__ import annotations

from collections.abc import Iterable, Mapping

from reviewgraph.clarification import ClarificationGateResult
from reviewgraph.models import ClassifiedFinding, Confidence, GraphError, ReviewVerdict, Severity


def compute_local_verdict(
    *,
    findings: Iterable[ClassifiedFinding],
    clarification_gate: ClarificationGateResult,
    reviewer_verdict_powers: Mapping[str, str] | None = None,
) -> ReviewVerdict:
    postable_findings = tuple(findings)
    if clarification_gate.blocks_posting:
        return ReviewVerdict.NEEDS_CLARIFICATION
    if not postable_findings:
        return ReviewVerdict.NO_FINDINGS
    if any(
        _can_recommend_request_changes(
            finding,
            reviewer_verdict_powers=reviewer_verdict_powers or {},
        )
        for finding in postable_findings
    ):
        return ReviewVerdict.REQUEST_CHANGES
    return ReviewVerdict.COMMENT


def compute_post_enabled(
    *,
    errors: Iterable[GraphError],
    clarification_gate: ClarificationGateResult,
    local_verdict: ReviewVerdict,
    findings: Iterable[ClassifiedFinding],
) -> bool:
    return not tuple(errors) and not clarification_gate.blocks_posting and bool(tuple(findings))


def _can_recommend_request_changes(
    finding: ClassifiedFinding,
    *,
    reviewer_verdict_powers: Mapping[str, str],
) -> bool:
    return (
        reviewer_verdict_powers.get(finding.source_reviewer) == "request_changes"
        and finding.confidence == Confidence.HIGH
        and (finding.severity == Severity.CRITICAL or finding.blocking)
    )
