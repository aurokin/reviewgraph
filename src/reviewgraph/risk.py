from __future__ import annotations

from reviewgraph.models import PullRequestContext, RiskAssessment, RiskLevel, RiskThresholds


DEFAULT_RISK_THRESHOLDS = RiskThresholds(
    changed_files_medium=3,
    changed_files_high=10,
    changed_lines_medium=50,
    changed_lines_high=500,
)


_SURFACE_PATH_PREFIXES: tuple[tuple[str, str], ...] = (
    ("docs/", "docs"),
    ("src/api/", "api"),
    ("src/auth/", "auth"),
    ("src/cache", "cache"),
    ("src/frontend/", "frontend"),
    ("src/settings/", "settings"),
)

_SURFACE_LABELS: tuple[tuple[str, str], ...] = (
    ("api", "api"),
    ("backend", "backend"),
    ("docs", "docs"),
    ("frontend", "frontend"),
    ("large-pr", "large-pr"),
    ("security", "security"),
)

_DIFF_HINT_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("auth", ("auth", "permission", "unauthorized")),
    ("billing", ("billing", "checkout", "calculate_total", "total(")),
    ("migration", ("migration", "migrate")),
    ("product_intent", ("product intent", "semantics", "behavior")),
    ("secret", ("api_key", "password", "secret", "token=")),
    ("truncated_patch", ()),
)


def classify_change_risk(
    pr: PullRequestContext,
    *,
    thresholds: RiskThresholds = DEFAULT_RISK_THRESHOLDS,
) -> RiskAssessment:
    changed_file_count = len(pr.changed_files)
    changed_line_count = sum(changed_file.additions + changed_file.deletions for changed_file in pr.changed_files)
    touched_surfaces = _touched_surfaces(pr)
    labels = tuple(sorted(pr.labels, key=str.casefold))
    diff_pattern_hints = _diff_pattern_hints(pr)
    risk_level, reasons = _risk_level_and_reasons(
        changed_file_count=changed_file_count,
        changed_line_count=changed_line_count,
        touched_surfaces=touched_surfaces,
        diff_pattern_hints=diff_pattern_hints,
        thresholds=thresholds,
    )
    return RiskAssessment(
        changed_file_count=changed_file_count,
        changed_line_count=changed_line_count,
        touched_surfaces=touched_surfaces,
        labels=labels,
        diff_pattern_hints=diff_pattern_hints,
        configured_thresholds=thresholds,
        risk_level=risk_level,
        reasons=reasons,
    )


def risk_assessment_to_json(assessment: RiskAssessment) -> dict[str, object]:
    thresholds = assessment.configured_thresholds
    return {
        "changed_file_count": assessment.changed_file_count,
        "changed_line_count": assessment.changed_line_count,
        "touched_surfaces": list(assessment.touched_surfaces),
        "labels": list(assessment.labels),
        "diff_pattern_hints": list(assessment.diff_pattern_hints),
        "configured_thresholds": {
            "changed_files_medium": thresholds.changed_files_medium,
            "changed_files_high": thresholds.changed_files_high,
            "changed_lines_medium": thresholds.changed_lines_medium,
            "changed_lines_high": thresholds.changed_lines_high,
            "risk_min": thresholds.risk_min.value if thresholds.risk_min else None,
        },
        "risk_level": assessment.risk_level.value,
        "reasons": list(assessment.reasons),
    }


def _touched_surfaces(pr: PullRequestContext) -> tuple[str, ...]:
    surfaces: set[str] = set()
    for changed_file in pr.changed_files:
        path = changed_file.path.casefold()
        matched = False
        for prefix, surface in _SURFACE_PATH_PREFIXES:
            if path.startswith(prefix):
                surfaces.add(surface)
                matched = True
        if not matched:
            surfaces.add(path.split("/", 1)[0])
    labels = {label.casefold() for label in pr.labels}
    for label, surface in _SURFACE_LABELS:
        if label in labels:
            surfaces.add(surface)
    return tuple(sorted(surfaces))


def _diff_pattern_hints(pr: PullRequestContext) -> tuple[str, ...]:
    patches = "\n".join(changed_file.patch or "" for changed_file in pr.changed_files).casefold()
    labels = " ".join(pr.labels).casefold()
    paths = "\n".join(changed_file.path for changed_file in pr.changed_files).casefold()
    corpus = "\n".join((patches, labels, paths))
    hints: set[str] = set()
    for hint, patterns in _DIFF_HINT_PATTERNS:
        if hint == "truncated_patch":
            if any(changed_file.patch is None or changed_file.patch_status != "available" for changed_file in pr.changed_files):
                hints.add(hint)
            continue
        if any(pattern in corpus for pattern in patterns):
            hints.add(hint)
    return tuple(sorted(hints))


def _risk_level_and_reasons(
    *,
    changed_file_count: int,
    changed_line_count: int,
    touched_surfaces: tuple[str, ...],
    diff_pattern_hints: tuple[str, ...],
    thresholds: RiskThresholds,
) -> tuple[RiskLevel, tuple[str, ...]]:
    reasons: list[str] = []
    level = RiskLevel.LOW

    if changed_file_count >= thresholds.changed_files_high:
        level = RiskLevel.HIGH
        reasons.append(f"changed_files>={thresholds.changed_files_high}")
    elif changed_file_count >= thresholds.changed_files_medium:
        level = _max_risk(level, RiskLevel.MEDIUM)
        reasons.append(f"changed_files>={thresholds.changed_files_medium}")

    if changed_line_count >= thresholds.changed_lines_high:
        level = RiskLevel.HIGH
        reasons.append(f"changed_lines>={thresholds.changed_lines_high}")
    elif changed_line_count >= thresholds.changed_lines_medium:
        level = _max_risk(level, RiskLevel.MEDIUM)
        reasons.append(f"changed_lines>={thresholds.changed_lines_medium}")

    high_hints = {"auth", "secret", "truncated_patch"}
    medium_hints = {"billing", "migration", "product_intent"}
    matched_high_hints = tuple(hint for hint in diff_pattern_hints if hint in high_hints)
    matched_medium_hints = tuple(hint for hint in diff_pattern_hints if hint in medium_hints)
    if matched_high_hints:
        level = RiskLevel.HIGH
        reasons.append("diff_hints_high=" + ",".join(matched_high_hints))
    if matched_medium_hints and level is not RiskLevel.HIGH:
        level = _max_risk(level, RiskLevel.MEDIUM)
        reasons.append("diff_hints_medium=" + ",".join(matched_medium_hints))

    if len(touched_surfaces) >= 2 and level is not RiskLevel.HIGH:
        level = _max_risk(level, RiskLevel.MEDIUM)
        reasons.append("touched_surfaces>=2")

    if not reasons:
        reasons.append("within_low_risk_thresholds")
    return level, tuple(reasons)


def _max_risk(left: RiskLevel, right: RiskLevel) -> RiskLevel:
    rank = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2}
    return left if rank[left] >= rank[right] else right
