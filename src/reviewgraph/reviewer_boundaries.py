from __future__ import annotations

from reviewgraph.models import ReviewerRunKey
from reviewgraph.reviewer_context import ReviewerContextPackage


ALLOWED_REVIEWER_ADAPTER_CAPABILITIES = frozenset({"none", "diff_context"})


class ReviewerAdapterBoundaryError(ValueError):
    pass


def validate_reviewer_adapter_input(
    *,
    package: ReviewerContextPackage,
    run_key: ReviewerRunKey,
) -> ReviewerContextPackage:
    _require_context_package(package)
    _require_reviewer_run_key(run_key)
    if run_key.target_hash != package.review_target.target_hash():
        raise ReviewerAdapterBoundaryError("reviewer adapter run key target does not match package")
    if run_key.reviewer != package.reviewer.name:
        raise ReviewerAdapterBoundaryError("reviewer adapter run key reviewer does not match package")
    if run_key.stage.value != package.active_stage:
        raise ReviewerAdapterBoundaryError("reviewer adapter run key active stage does not match package")
    if run_key.stage.value != package.reviewer.stage:
        raise ReviewerAdapterBoundaryError("reviewer adapter run key reviewer stage does not match package")
    _validate_capability_policy(package)
    return package


def require_context_package(package: object) -> ReviewerContextPackage:
    return _require_context_package(package)


def require_reviewer_run_key(run_key: object) -> ReviewerRunKey:
    return _require_reviewer_run_key(run_key)


def _require_context_package(package: object) -> ReviewerContextPackage:
    if not isinstance(package, ReviewerContextPackage):
        raise ReviewerAdapterBoundaryError("reviewer adapter package must be a ReviewerContextPackage")
    return package


def _require_reviewer_run_key(run_key: object) -> ReviewerRunKey:
    if not isinstance(run_key, ReviewerRunKey):
        raise ReviewerAdapterBoundaryError("reviewer adapter run_key must be a ReviewerRunKey")
    return run_key


def _validate_capability_policy(package: ReviewerContextPackage) -> None:
    if package.capability_policy.capabilities != package.reviewer_config.capabilities:
        raise ReviewerAdapterBoundaryError("reviewer adapter capability policy must match reviewer config")
    if unsupported := sorted(set(package.capability_policy.capabilities) - ALLOWED_REVIEWER_ADAPTER_CAPABILITIES):
        raise ReviewerAdapterBoundaryError(
            "reviewer adapter capability policy contains unsupported capabilities: "
            + ", ".join(unsupported)
        )
    if package.capability_policy.github_writes_available:
        raise ReviewerAdapterBoundaryError("reviewer adapter capability policy must not expose GitHub writes")
    if package.capability_policy.repository_access_available:
        raise ReviewerAdapterBoundaryError("reviewer adapter capability policy must not expose repository access")
    if package.capability_policy.live_provider_calls_available:
        raise ReviewerAdapterBoundaryError("reviewer adapter capability policy must not expose provider calls")
