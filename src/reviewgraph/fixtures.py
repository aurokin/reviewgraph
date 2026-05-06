from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from reviewgraph.config import ConfigError, load_reviewer_config as load_config_reviewer_config
from reviewgraph.models import ReviewConfig as ReviewerConfig
from reviewgraph.models import (
    PullRequestChangedFile,
    PullRequestComment,
    PullRequestContext,
    PullRequestReview,
    PullRequestReviewThread,
    ReviewTarget,
)
from reviewgraph.redaction import redact_text


MAX_FIXTURE_BYTES = 1_048_576
DATA_PACKAGE = "reviewgraph"
DATA_ROOT = "fixtures_data"


class FixtureError(ValueError):
    pass


@dataclass(frozen=True)
class ChangedRange:
    start: int
    end: int

    def __post_init__(self) -> None:
        if self.start <= 0 or self.end < self.start:
            raise FixtureError("changed_ranges entries require positive start and end >= start")

    def contains(self, line: int) -> bool:
        return self.start <= line <= self.end


@dataclass(frozen=True)
class ChangedFile:
    path: str
    changed_ranges: tuple[ChangedRange, ...]
    patch: str | None = ""
    additions: int = 0
    deletions: int = 0
    status: str = "modified"
    previous_path: str | None = None
    patch_status: str = "available"

    def __post_init__(self) -> None:
        if not self.path:
            raise FixtureError("changed_files[].path is required")
        if not self.changed_ranges:
            raise FixtureError(f"changed_files[{self.path}].changed_ranges is required")
        if self.patch is not None and not isinstance(self.patch, str):
            raise FixtureError("changed_files[].patch must be a string or null")
        if self.patch is None and self.patch_status == "available":
            raise FixtureError("changed_files[].patch_status must explain missing patch")

    def contains_line(self, line: int) -> bool:
        return any(changed_range.contains(line) for changed_range in self.changed_ranges)


@dataclass(frozen=True)
class FixturePR:
    id: str
    pr_ref: str
    review_target: ReviewTarget
    pr: PullRequestContext
    labels: tuple[str, ...]
    changed_files: tuple[ChangedFile, ...]
    memory: tuple[dict[str, Any], ...]
    truncation: tuple[dict[str, Any], ...]
    raw_reviewer_outputs: tuple[dict[str, Any], ...]

    @property
    def target(self) -> dict[str, Any]:
        return self.review_target.to_ordered_dict()


def default_reviewer_config_path() -> Path:
    return _resource_path("reviewer-configs/basic-reviewers.json")


def load_manifest(path: Path | None = None) -> dict[str, Any]:
    manifest_path = path or _resource_path("manifest.json")
    data = _read_json_file(manifest_path, label="manifest")
    fixtures = data.get("fixtures")
    if not isinstance(fixtures, list):
        raise FixtureError("manifest.fixtures must be a list")
    for entry in fixtures:
        if not isinstance(entry, dict) or not entry.get("id") or not entry.get("path"):
            raise FixtureError("manifest fixtures require id and path")
    scenarios = data.get("corpus_scenarios", [])
    if not isinstance(scenarios, list):
        raise FixtureError("manifest.corpus_scenarios must be a list")
    for entry in scenarios:
        if not isinstance(entry, dict) or not entry.get("id"):
            raise FixtureError("manifest corpus_scenarios require id")
        if "path" in entry and (not isinstance(entry["path"], str) or not entry["path"]):
            raise FixtureError("manifest corpus_scenarios path must be a non-empty string")
    return data


def resolve_fixture_ref(fixture_ref: str) -> Path:
    manifest = load_manifest()
    for entry in manifest["fixtures"]:
        if entry["id"] == fixture_ref:
            return _resource_path(entry["path"])

    candidate = Path(fixture_ref)
    if candidate.exists():
        return candidate
    raise FixtureError(f"fixture reference not found: {redact_for_error(fixture_ref)}")


def load_fixture_pr(fixture_ref: str) -> FixturePR:
    path = resolve_fixture_ref(fixture_ref)
    data = _read_json_file(path, label="fixture")
    return parse_fixture_pr(data)


def load_reviewer_config(path: str | Path | None = None) -> ReviewerConfig:
    config_path = Path(path) if path is not None else default_reviewer_config_path()
    try:
        return load_config_reviewer_config(config_path)
    except ConfigError as exc:
        raise FixtureError(str(exc)) from exc


def parse_fixture_pr(data: dict[str, Any]) -> FixturePR:
    required = (
        "id",
        "pr_ref",
        "target",
        "title",
        "labels",
        "changed_files",
        "comments",
        "reviews",
        "review_threads",
        "raw_reviewer_outputs",
    )
    for field in required:
        if field not in data:
            raise FixtureError(f"fixture.{field} is required")
    run_mode = data.get("run_mode", "dry_run")
    if run_mode != "dry_run":
        raise FixtureError("fixture.run_mode must be dry_run when present")
    review_target = _parse_review_target(data["target"])
    changed_files = _parse_changed_files(data["changed_files"])
    pr_context = PullRequestContext(
        review_target=review_target,
        title=_required_str(data, "title", "fixture"),
        body=_optional_nullable_str(data, "body", "fixture"),
        labels=tuple(_optional_str_list(data, "labels", "fixture")),
        changed_files=tuple(
            PullRequestChangedFile(
                path=changed_file.path,
                patch=changed_file.patch,
                additions=changed_file.additions,
                deletions=changed_file.deletions,
                status=changed_file.status,
                previous_path=changed_file.previous_path,
                patch_status=changed_file.patch_status,
            )
            for changed_file in changed_files
        ),
        comments=_parse_comments(data["comments"], "fixture.comments"),
        reviews=_parse_reviews(data["reviews"]),
        review_threads=_parse_review_threads(data["review_threads"]),
    )
    raw_outputs = data["raw_reviewer_outputs"]
    if not isinstance(raw_outputs, list) or not raw_outputs:
        raise FixtureError("fixture.raw_reviewer_outputs must be a non-empty list")

    return FixturePR(
        id=_required_str(data, "id", "fixture"),
        pr_ref=_required_str(data, "pr_ref", "fixture"),
        review_target=review_target,
        pr=pr_context,
        labels=pr_context.labels,
        changed_files=changed_files,
        memory=tuple(_optional_list(data, "memory")),
        truncation=tuple(_optional_list(data, "truncation")),
        raw_reviewer_outputs=tuple(raw_outputs),
    )


def _parse_review_target(value: object) -> ReviewTarget:
    if not isinstance(value, dict):
        raise FixtureError("fixture.target must be an object")
    for field in ("owner_repo", "base_sha", "head_sha", "diff_basis"):
        if not isinstance(value.get(field), str) or not value[field]:
            raise FixtureError(f"fixture.target.{field} must be a non-empty string")
    if not _is_json_int(value.get("pr_number")) or value["pr_number"] <= 0:
        raise FixtureError("fixture.target.pr_number must be a positive integer")
    if value.get("merge_base_sha") is not None and not isinstance(value.get("merge_base_sha"), str):
        raise FixtureError("fixture.target.merge_base_sha must be a string or null")
    try:
        return ReviewTarget(
            owner_repo=value["owner_repo"],
            pr_number=value["pr_number"],
            base_sha=value["base_sha"],
            head_sha=value["head_sha"],
            merge_base_sha=value.get("merge_base_sha"),
            diff_basis=value["diff_basis"],
        )
    except ValueError as exc:
        raise FixtureError(str(exc)) from exc


def assert_changed_line(fixture: FixturePR, *, path: str, line: int) -> None:
    for changed_file in fixture.changed_files:
        if changed_file.path == path and changed_file.contains_line(line):
            return
    raise FixtureError(f"postable finding {path}:{line} does not overlap fixture changed lines")


def redact_for_error(value: str) -> str:
    return redact_text(value).text


def _resource_path(relative: str) -> Path:
    return Path(str(resources.files(DATA_PACKAGE).joinpath(DATA_ROOT, relative)))


def _read_json_file(path: Path, *, label: str) -> dict[str, Any]:
    try:
        if not path.is_file():
            raise FixtureError(f"{label} path must be a regular file: {redact_for_error(str(path))}")
        with path.open("rb") as handle:
            raw = handle.read(MAX_FIXTURE_BYTES + 1)
    except OSError as exc:
        raise FixtureError(f"{label} file is not readable: {redact_for_error(str(path))}") from exc
    if len(raw) > MAX_FIXTURE_BYTES:
        raise FixtureError(f"{label} file exceeds {MAX_FIXTURE_BYTES} bytes: {redact_for_error(str(path))}")
    try:
        data = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise FixtureError(f"{label} JSON is invalid at line {exc.lineno}: {exc.msg}") from exc
    except UnicodeDecodeError as exc:
        raise FixtureError(f"{label} JSON must be UTF-8") from exc
    except OSError as exc:
        raise FixtureError(f"{label} file is not readable: {redact_for_error(str(path))}") from exc
    if not isinstance(data, dict):
        raise FixtureError(f"{label} JSON must be an object")
    return data


def _parse_changed_files(value: object) -> tuple[ChangedFile, ...]:
    if not isinstance(value, list) or not value:
        raise FixtureError("fixture.changed_files must be a non-empty list")
    changed_files: list[ChangedFile] = []
    for entry in value:
        if not isinstance(entry, dict):
            raise FixtureError("fixture.changed_files entries must be objects")
        ranges = entry.get("changed_ranges")
        if not isinstance(ranges, list) or not ranges:
            raise FixtureError("fixture.changed_files[].changed_ranges must be a non-empty list")
        for item in ranges:
            if not isinstance(item, dict):
                raise FixtureError("fixture.changed_files[].changed_ranges entries must be objects")
        changed_files.append(
            ChangedFile(
                path=_required_str(entry, "path", "changed_files[]"),
                changed_ranges=tuple(
                    ChangedRange(start=_required_int(item, "start"), end=_required_int(item, "end"))
                    for item in ranges
                ),
                patch=_optional_str(entry, "patch", "changed_files[]", default=""),
                additions=_optional_non_negative_int(entry, "additions", "changed_files[]"),
                deletions=_optional_non_negative_int(entry, "deletions", "changed_files[]"),
                status=_optional_str(entry, "status", "changed_files[]", default="modified") or "modified",
                previous_path=_optional_nullable_str(entry, "previous_path", "changed_files[]"),
                patch_status=_optional_str(entry, "patch_status", "changed_files[]", default="available")
                or "available",
            )
        )
    return tuple(changed_files)


def _parse_comments(value: object, label: str) -> tuple[PullRequestComment, ...]:
    if not isinstance(value, list):
        raise FixtureError(f"{label} must be a list")
    comments: list[PullRequestComment] = []
    for entry in value:
        if not isinstance(entry, dict):
            raise FixtureError(f"{label} entries must be objects")
        try:
            comments.append(
                PullRequestComment(
                    id=_required_str(entry, "id", label),
                    author=_required_str(entry, "author", label),
                    author_association=_required_str(entry, "author_association", label),
                    body=_required_str(entry, "body", label),
                    created_at=_required_str(entry, "created_at", label),
                    trust_label=_required_str(entry, "trust_label", label),
                    source_type=_required_str(entry, "source_type", label),
                    path=_optional_nullable_str(entry, "path", label),
                    line=_optional_positive_int(entry, "line", label),
                    side=_optional_nullable_str(entry, "side", label),
                    commit_sha=_optional_nullable_str(entry, "commit_sha", label),
                    position=_optional_positive_int(entry, "position", label),
                )
            )
        except ValueError as exc:
            raise FixtureError(str(exc)) from exc
    return tuple(comments)


def _parse_reviews(value: object) -> tuple[PullRequestReview, ...]:
    if not isinstance(value, list):
        raise FixtureError("fixture.reviews must be a list")
    reviews: list[PullRequestReview] = []
    for entry in value:
        if not isinstance(entry, dict):
            raise FixtureError("fixture.reviews entries must be objects")
        try:
            reviews.append(
                PullRequestReview(
                    id=_required_str(entry, "id", "fixture.reviews"),
                    author=_required_str(entry, "author", "fixture.reviews"),
                    author_association=_required_str(entry, "author_association", "fixture.reviews"),
                    state=_required_str(entry, "state", "fixture.reviews"),
                    created_at=_required_str(entry, "created_at", "fixture.reviews"),
                    trust_label=_required_str(entry, "trust_label", "fixture.reviews"),
                    source_type=_required_str(entry, "source_type", "fixture.reviews"),
                    body=_optional_nullable_str(entry, "body", "fixture.reviews"),
                )
            )
        except ValueError as exc:
            raise FixtureError(str(exc)) from exc
    return tuple(reviews)


def _parse_review_threads(value: object) -> tuple[PullRequestReviewThread, ...]:
    if not isinstance(value, list):
        raise FixtureError("fixture.review_threads must be a list")
    threads: list[PullRequestReviewThread] = []
    for entry in value:
        if not isinstance(entry, dict):
            raise FixtureError("fixture.review_threads entries must be objects")
        comments = entry.get("comments")
        if not isinstance(comments, list) or not comments:
            raise FixtureError("fixture.review_threads.comments must be a non-empty list")
        try:
            threads.append(
                PullRequestReviewThread(
                    id=_required_str(entry, "id", "fixture.review_threads"),
                    path=_required_str(entry, "path", "fixture.review_threads"),
                    resolved_status=_required_str(entry, "resolved_status", "fixture.review_threads"),
                    comments=_parse_comments(comments, "fixture.review_threads.comments"),
                )
            )
        except ValueError as exc:
            raise FixtureError(str(exc)) from exc
    return tuple(threads)


def _optional_list(data: dict[str, Any], field: str) -> list[dict[str, Any]]:
    value = data.get(field, [])
    if not isinstance(value, list):
        raise FixtureError(f"fixture.{field} must be a list")
    if not all(isinstance(item, dict) for item in value):
        raise FixtureError(f"fixture.{field} entries must be objects")
    return value


def _optional_str_list(data: dict[str, Any], field: str, label: str) -> list[str]:
    value = data.get(field, [])
    if not isinstance(value, list):
        raise FixtureError(f"{label}.{field} must be a list")
    if not all(isinstance(item, str) and item for item in value):
        raise FixtureError(f"{label}.{field} entries must be non-empty strings")
    return value


def _optional_str(data: dict[str, Any], field: str, label: str, *, default: str | None = None) -> str | None:
    if field not in data:
        return default
    value = data[field]
    if value is None:
        return None
    if not isinstance(value, str):
        raise FixtureError(f"{label}.{field} must be a string or null")
    return value


def _optional_nullable_str(data: dict[str, Any], field: str, label: str) -> str | None:
    return _optional_str(data, field, label)


def _optional_non_negative_int(data: dict[str, Any], field: str, label: str) -> int:
    value = data.get(field, 0)
    if not _is_json_int(value) or value < 0:
        raise FixtureError(f"{label}.{field} must be a non-negative integer")
    return value


def _optional_positive_int(data: dict[str, Any], field: str, label: str) -> int | None:
    value = data.get(field)
    if value is None:
        return None
    if not _is_json_int(value) or value <= 0:
        raise FixtureError(f"{label}.{field} must be a positive integer or null")
    return value


def _required_str(data: dict[str, Any], field: str, label: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value:
        raise FixtureError(f"{label}.{field} is required")
    return value


def _required_int(data: dict[str, Any], field: str) -> int:
    value = data.get(field)
    if not _is_json_int(value):
        raise FixtureError(f"changed range {field} must be an integer")
    return value


def _is_json_int(value: object) -> bool:
    return type(value) is int
