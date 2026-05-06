import pytest

from reviewgraph.fixtures import load_fixture_pr
from reviewgraph.models import (
    ClarificationRequest,
    Confidence,
    LocalNote,
    MemoryReference,
    RawReviewerFinding,
    ReviewStage,
    ReviewerResult,
    ReviewerRunKey,
    Severity,
    SuggestedReply,
    SuppressedReviewerOutput,
)
from reviewgraph.quality import classify_review_quality


def test_quality_classifies_postable_finding_with_graph_owned_fields() -> None:
    result = classify_review_quality(
        changed_files=_changed_files(),
        reviewer_result=_result(findings=(_finding(),)),
        memory_references=(),
    )

    finding = result.findings[0]
    assert finding.classification.value == "postable_finding"
    assert finding.priority == 1
    assert finding.blocking is False
    assert finding.source_reviewer == "correctness"
    assert finding.source_stage == "initial_triage"
    assert finding.fingerprint.startswith("sha256:")
    assert result.suppressed_outputs == ()


def test_quality_allows_concrete_medium_confidence_non_blocking_finding() -> None:
    result = classify_review_quality(
        changed_files=_changed_files(),
        reviewer_result=_result(findings=(_finding(confidence=Confidence.MEDIUM),)),
        memory_references=(),
    )

    assert result.findings[0].confidence == Confidence.MEDIUM
    assert result.findings[0].blocking is False
    assert result.suppressed_outputs == ()


def test_quality_suppresses_low_confidence_finding() -> None:
    result = classify_review_quality(
        changed_files=_changed_files(),
        reviewer_result=_result(findings=(_finding(confidence=Confidence.LOW),)),
        memory_references=(),
    )

    assert result.findings == ()
    assert result.suppressed_outputs[0].reason == "Finding candidate did not meet postable quality policy."


def test_quality_suppresses_medium_confidence_critical_finding() -> None:
    result = classify_review_quality(
        changed_files=_changed_files(),
        reviewer_result=_result(
            findings=(
                _finding(
                    id="finding-critical-medium",
                    severity=Severity.CRITICAL,
                    confidence=Confidence.MEDIUM,
                ),
            )
        ),
        memory_references=(),
    )

    assert result.findings == ()
    assert result.suppressed_outputs[0].id == "finding-critical-medium"


def test_quality_preserves_line_end_when_supplied() -> None:
    result = classify_review_quality(
        changed_files=_changed_files(),
        reviewer_result=_result(findings=(_finding(line=12, line_end=14),)),
        memory_references=(),
    )

    assert result.findings[0].line == 12
    assert result.findings[0].line_end == 14


def test_quality_passes_through_local_notes_replies_clarifications_and_suppressed_outputs() -> None:
    run_key = _run_key()
    note = LocalNote(
        id="note-1",
        title="Local context",
        body="Keep this local.",
        evidence="Fixture metadata.",
    )
    request = ClarificationRequest(
        id="clarify-1",
        reviewer="logic",
        source_stage="logic_review",
        source_run_key=run_key,
        question="Is the fallback intentionally allowed to return stale values?",
        why_it_matters="The mergeability risk depends on intended cache behavior.",
        evidence_sources=("diff",),
    )
    reply = SuggestedReply(
        id="reply-1",
        source_comment_id="comment-1",
        proposed_body="I would wait for maintainer confirmation before replying.",
    )
    suppressed = SuppressedReviewerOutput(id="nonfinding-1", reason="Style-only observation.")

    result = classify_review_quality(
        changed_files=_changed_files(),
        reviewer_result=ReviewerResult(
            run_key=run_key,
            local_notes=(note,),
            clarification_requests=(request,),
            suggested_replies=(reply,),
            suppressed_outputs=(suppressed,),
        ),
        memory_references=(),
    )

    assert result.local_notes == (note,)
    assert result.clarification_requests == (request,)
    assert result.suggested_replies == (reply,)
    assert result.suppressed_outputs == (suppressed,)


def test_quality_suppresses_unsafe_clarification_provenance() -> None:
    passive_body = "Is this endpoint intentionally allowed to bypass the normal authorization path?"
    request = ClarificationRequest(
        id="clarify-passive",
        reviewer="logic",
        question=passive_body,
        why_it_matters="If not intentional, the change may expose data across tenants.",
    )

    result = classify_review_quality(
        changed_files=_changed_files(),
        reviewer_result=_result(clarification_requests=(request,)),
        memory_references=(
            MemoryReference(
                id="mem-passive",
                trust_label="untrusted",
                resolved_status="unresolved",
                source_type="issue_comment",
                body=passive_body,
                actionable=False,
            ),
        ),
    )

    assert result.clarification_requests == ()
    assert result.suppressed_outputs[0].id == "clarify-passive"
    assert result.suppressed_outputs[0].reason == (
        "Clarification request used passive or untrusted memory as evidence."
    )


def test_quality_suppresses_clarification_that_cites_omitted_memory() -> None:
    request = ClarificationRequest(
        id="clarify-omitted-memory",
        reviewer="logic",
        question="Is the cache fallback intended to use the stale value?",
        why_it_matters="The mergeability risk depends on intended cache behavior.",
        evidence_sources=("trusted_memory",),
        evidence_memory_ids=("mem-omitted",),
    )

    result = classify_review_quality(
        changed_files=_changed_files(),
        reviewer_result=_result(clarification_requests=(request,)),
        memory_references=(
            MemoryReference(
                id="mem-omitted",
                trust_label="trusted",
                resolved_status="unresolved",
                source_type="issue_comment",
                body=None,
                author="maintainer",
                author_association="MEMBER",
                author_type="user",
                actionable=True,
            ),
        ),
        omitted_memory_ids=("mem-omitted",),
    )

    assert result.clarification_requests == ()
    assert result.suppressed_outputs[0].reason == "Clarification request referenced context omitted by context budget."


@pytest.mark.parametrize(
    ("finding_kwargs", "expected_id"),
    (
        (
            {
                "id": "finding-generic",
                "title": "Add more tests",
                "rationale": "This change should improve coverage.",
                "evidence": "Changed line 12.",
            },
            "finding-generic",
        ),
        (
            {
                "id": "finding-speculative",
                "rationale": "The new branch might fail when the cache misses.",
                "evidence": "Changed line 12 returns a value.",
            },
            "finding-speculative",
        ),
        (
            {
                "id": "finding-preexisting",
                "rationale": "This was already failing before the PR changed the branch.",
                "evidence": "Changed line 12 returns a stale value.",
            },
            "finding-preexisting",
        ),
    ),
)
def test_quality_suppresses_generic_speculative_and_preexisting_findings(
    finding_kwargs: dict[str, object],
    expected_id: str,
) -> None:
    finding = _finding(**finding_kwargs)

    result = classify_review_quality(
        changed_files=_changed_files(),
        reviewer_result=_result(findings=(finding,)),
        memory_references=(),
    )

    assert result.findings == ()
    assert result.suppressed_outputs[0].id == expected_id


@pytest.mark.parametrize(
    "rationale",
    (
        "Please request changes until this cache issue is fixed.",
        "The new branch returns stale data when the cache misses. Also, the module should be split.",
        " ".join(["The new branch returns stale data when the cache misses."] * 25),
    ),
)
def test_quality_suppresses_public_verdict_pressure_multi_issue_or_verbose_body(rationale: str) -> None:
    result = classify_review_quality(
        changed_files=_changed_files(),
        reviewer_result=_result(findings=(_finding(id="finding-comment-shape", rationale=rationale),)),
        memory_references=(),
    )

    assert result.findings == ()
    assert result.suppressed_outputs[0].id == "finding-comment-shape"


def test_quality_suppresses_public_verdict_pressure_in_title() -> None:
    results = (
        classify_review_quality(
            changed_files=_changed_files(),
            reviewer_result=_result(
                findings=(
                    _finding(
                        id="finding-title-verdict-pressure",
                        title="Request changes: Cache miss returns stale data",
                    ),
                )
            ),
            memory_references=(),
        ),
        classify_review_quality(
            changed_files=_changed_files(),
            reviewer_result=_result(
                findings=(
                    _finding(
                        id="finding-title-enum-verdict-pressure",
                        title="REQUEST_CHANGES: Cache miss returns stale data",
                    ),
                )
            ),
            memory_references=(),
        ),
    )

    assert [result.findings for result in results] == [(), ()]
    assert [result.suppressed_outputs[0].id for result in results] == [
        "finding-title-verdict-pressure",
        "finding-title-enum-verdict-pressure",
    ]


def test_quality_preserves_legacy_testing_compatibility() -> None:
    generic = _finding(
        id="finding-generic-tests",
        reviewer="testing",
        title="Add tests",
        rationale="This change should add tests for coverage.",
        evidence="Changed line 12.",
    )
    concrete = _finding(
        id="finding-cache-coverage",
        reviewer="testing",
        title="Missing cache miss regression coverage",
        rationale="The new branch lacks regression coverage when the cache misses.",
        evidence="Changed line 12 returns stale value when the cache misses.",
    )

    generic_result = classify_review_quality(
        changed_files=_changed_files(),
        reviewer_result=_result(reviewer="testing", findings=(generic,)),
        memory_references=(),
    )
    concrete_result = classify_review_quality(
        changed_files=_changed_files(),
        reviewer_result=_result(reviewer="testing", findings=(concrete,)),
        memory_references=(),
    )

    assert generic_result.findings == ()
    assert concrete_result.findings[0].id == "finding-cache-coverage"


def test_quality_allows_logic_finding_with_cross_file_evidence_anchored_to_changed_line() -> None:
    finding = _finding(
        id="finding-cross-file",
        reviewer="logic",
        stage=ReviewStage.LOGIC_REVIEW,
        title="Cache invariant breaks callers",
        rationale=(
            "When the cache misses, the changed line now returns stale data to callers "
            "that expect fresh values from src/service.py."
        ),
        evidence="Changed line 12 returns stale value while src/service.py expects fresh cache data.",
    )

    result = classify_review_quality(
        changed_files=_changed_files(),
        reviewer_result=_result(reviewer="logic", stage=ReviewStage.LOGIC_REVIEW, findings=(finding,)),
        memory_references=(),
    )

    assert result.findings[0].id == "finding-cross-file"
    assert result.findings[0].path == "src/cache.py"
    assert result.findings[0].line == 12


def test_quality_preserves_ambiguous_logic_clarification_artifact() -> None:
    request = ClarificationRequest(
        id="clarify-cache-intent",
        reviewer="logic",
        question="Is returning stale cache data on misses intentional?",
        why_it_matters="If not intentional, the changed branch may break callers.",
        evidence_sources=("diff",),
    )

    result = classify_review_quality(
        changed_files=_changed_files(),
        reviewer_result=_result(reviewer="logic", stage=ReviewStage.LOGIC_REVIEW, clarification_requests=(request,)),
        memory_references=(),
    )

    assert result.clarification_requests == (request,)
    assert result.findings == ()


def test_quality_suppresses_generic_architecture_advice() -> None:
    result = classify_review_quality(
        changed_files=_changed_files(),
        reviewer_result=_result(
            findings=(
                _finding(
                    id="finding-architecture",
                    title="Refactor the cache helper",
                    rationale="This helper could be refactored for better modularity when this grows.",
                    evidence="Changed line 12.",
                ),
            )
        ),
        memory_references=(),
    )

    assert result.findings == ()
    assert result.suppressed_outputs[0].id == "finding-architecture"


def test_quality_suppresses_findings_that_use_unsafe_memory_provenance() -> None:
    result = classify_review_quality(
        changed_files=_changed_files(),
        reviewer_result=_result(
            findings=(
                _finding(
                    id="finding-memory",
                    evidence="Changed line 12 returns stale value after the cache misses.",
                    evidence_sources=("trusted_memory",),
                ),
            )
        ),
        memory_references=(),
    )

    assert result.findings == ()
    assert result.suppressed_outputs[0].reason == "Finding candidate used passive or untrusted memory as evidence."


def test_quality_suppresses_findings_that_copy_passive_memory_into_public_body() -> None:
    passive_body = "Changed line 12 returns stale value after the cache misses for external callers."

    result = classify_review_quality(
        changed_files=_changed_files(),
        reviewer_result=_result(findings=(_finding(rationale=passive_body),)),
        memory_references=(
            MemoryReference(
                id="mem-passive",
                trust_label="untrusted",
                resolved_status="unresolved",
                source_type="issue_comment",
                body=passive_body,
                actionable=False,
            ),
        ),
    )

    assert result.findings == ()
    assert result.suppressed_outputs[0].reason == "Finding candidate used passive or untrusted memory as evidence."


def test_quality_suppresses_short_passive_memory_copy_before_rendering() -> None:
    result = classify_review_quality(
        changed_files=_changed_files(),
        reviewer_result=_result(findings=(_finding(rationale="Ship it now"),)),
        memory_references=(
            MemoryReference(
                id="mem-passive",
                trust_label="untrusted",
                resolved_status="unresolved",
                source_type="issue_comment",
                body="Ship it now",
                actionable=False,
            ),
        ),
    )

    assert result.findings == ()
    assert result.suppressed_outputs[0].reason == "Finding candidate used passive or untrusted memory as evidence."


def test_quality_suppresses_findings_that_reference_omitted_context() -> None:
    result = classify_review_quality(
        changed_files=_changed_files(),
        reviewer_result=_result(findings=(_finding(path="src/cache.py"),)),
        memory_references=(),
        omitted_file_paths=("src/cache.py",),
    )

    assert result.findings == ()
    assert result.suppressed_outputs[0].reason == "Finding candidate referenced context omitted by context budget."


def test_quality_suppresses_findings_that_cite_omitted_memory_context() -> None:
    result = classify_review_quality(
        changed_files=_changed_files(),
        reviewer_result=_result(
            findings=(
                _finding(
                    id="finding-omitted-memory",
                    evidence_sources=("trusted_memory",),
                    evidence_memory_ids=("mem-omitted",),
                ),
            )
        ),
        memory_references=(
            MemoryReference(
                id="mem-omitted",
                trust_label="trusted",
                resolved_status="unresolved",
                source_type="issue_comment",
                body=None,
                author="maintainer",
                author_association="MEMBER",
                author_type="user",
                actionable=True,
            ),
        ),
        omitted_memory_ids=("mem-omitted",),
    )

    assert result.findings == ()
    assert result.suppressed_outputs[0].reason == "Finding candidate referenced context omitted by context budget."


def test_quality_suppresses_invalid_changed_line_location() -> None:
    result = classify_review_quality(
        changed_files=_changed_files(),
        reviewer_result=_result(findings=(_finding(line=99),)),
        memory_references=(),
    )

    assert result.findings == ()
    assert result.suppressed_outputs[0].reason == "Finding candidate location did not overlap changed code."


def _changed_files():
    return load_fixture_pr("basic-pr").changed_files


def _run_key(
    *,
    reviewer: str = "correctness",
    stage: ReviewStage = ReviewStage.INITIAL_TRIAGE,
) -> ReviewerRunKey:
    return ReviewerRunKey(
        target_hash="sha256:target",
        config_hash="sha256:config",
        stage=stage,
        reviewer=reviewer,
    )


def _result(
    *,
    reviewer: str = "correctness",
    stage: ReviewStage = ReviewStage.INITIAL_TRIAGE,
    findings: tuple[RawReviewerFinding, ...] = (),
    clarification_requests: tuple[ClarificationRequest, ...] = (),
) -> ReviewerResult:
    return ReviewerResult(
        run_key=_run_key(reviewer=reviewer, stage=stage),
        findings=findings,
        clarification_requests=clarification_requests,
    )


def _finding(
    *,
    id: str = "finding-cache-stale",
    reviewer: str = "correctness",
    stage: ReviewStage = ReviewStage.INITIAL_TRIAGE,
    severity: Severity = Severity.WARNING,
    confidence: Confidence = Confidence.HIGH,
    path: str = "src/cache.py",
    line: int = 12,
    line_end: int | None = None,
    title: str = "Cache miss returns stale data",
    rationale: str = "The new branch returns stale data when the cache misses.",
    evidence: str = "Changed line 12 returns stale value when the cache misses.",
    evidence_sources: tuple[str, ...] = ("diff",),
    evidence_memory_ids: tuple[str, ...] = (),
) -> RawReviewerFinding:
    _ = reviewer, stage
    return RawReviewerFinding(
        id=id,
        severity=severity,
        confidence=confidence,
        path=path,
        line=line,
        line_end=line_end,
        title=title,
        rationale=rationale,
        evidence=evidence,
        evidence_sources=evidence_sources,
        evidence_memory_ids=evidence_memory_ids,
    )
