from __future__ import annotations

import json
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any

from reviewgraph.redaction import redact_text


MAX_FIXTURE_BYTES = 1_048_576
DATA_PACKAGE = "reviewgraph"
DATA_ROOT = "fixtures_data"
ALLOWED_AGENT_FIELDS = {
    "capabilities",
    "context",
    "description",
    "model",
    "required",
    "stages",
    "tools",
    "triggers",
    "verdict_power",
}
ALLOWED_CAPABILITIES = {"none", "diff_context"}
ALLOWED_STAGES = {"initial_triage", "specialized_review", "logic_review"}
ALLOWED_TRIGGER_FIELDS = {
    "always",
    "changed_files_min",
    "changed_lines_min",
    "conversation_patterns",
    "diff_patterns",
    "labels",
    "max_files",
    "paths",
    "risk_min",
}
ALLOWED_VERDICT_POWERS = {"comment", "request_changes"}


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
    patch: str = ""

    def __post_init__(self) -> None:
        if not self.path:
            raise FixtureError("changed_files[].path is required")
        if not self.changed_ranges:
            raise FixtureError(f"changed_files[{self.path}].changed_ranges is required")

    def contains_line(self, line: int) -> bool:
        return any(changed_range.contains(line) for changed_range in self.changed_ranges)


@dataclass(frozen=True)
class FixturePR:
    id: str
    pr_ref: str
    target: dict[str, Any]
    changed_files: tuple[ChangedFile, ...]
    memory: tuple[dict[str, Any], ...]
    truncation: tuple[dict[str, Any], ...]
    raw_reviewer_outputs: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class ReviewerConfig:
    agents: dict[str, dict[str, Any]]


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
    data = _read_json_file(config_path, label="reviewer config")
    unknown_config_fields = set(data) - {"agents"}
    if unknown_config_fields:
        raise FixtureError(f"reviewer config has unsupported fields: {', '.join(sorted(unknown_config_fields))}")
    agents = data.get("agents")
    if not isinstance(agents, dict) or not agents:
        raise FixtureError("reviewer config agents must be a non-empty object")
    for name, agent in agents.items():
        if not isinstance(name, str) or not name:
            raise FixtureError("reviewer config agent names must be non-empty strings")
        if not isinstance(agent, dict):
            raise FixtureError(f"reviewer config agent {name} must be an object")
        _validate_reviewer_agent(name, agent)
    return ReviewerConfig(agents=agents)


def parse_fixture_pr(data: dict[str, Any]) -> FixturePR:
    required = ("id", "pr_ref", "target", "changed_files", "raw_reviewer_outputs")
    for field in required:
        if field not in data:
            raise FixtureError(f"fixture.{field} is required")
    if not isinstance(data["target"], dict):
        raise FixtureError("fixture.target must be an object")
    target = data["target"]
    for field in ("owner_repo", "base_sha", "head_sha", "diff_basis"):
        if not isinstance(target.get(field), str) or not target[field]:
            raise FixtureError(f"fixture.target.{field} must be a non-empty string")
    if not _is_json_int(target.get("pr_number")) or target["pr_number"] <= 0:
        raise FixtureError("fixture.target.pr_number must be a positive integer")
    if target.get("merge_base_sha") is not None and not isinstance(target.get("merge_base_sha"), str):
        raise FixtureError("fixture.target.merge_base_sha must be a string or null")

    changed_files = _parse_changed_files(data["changed_files"])
    raw_outputs = data["raw_reviewer_outputs"]
    if not isinstance(raw_outputs, list) or not raw_outputs:
        raise FixtureError("fixture.raw_reviewer_outputs must be a non-empty list")

    return FixturePR(
        id=_required_str(data, "id", "fixture"),
        pr_ref=_required_str(data, "pr_ref", "fixture"),
        target=data["target"],
        changed_files=changed_files,
        memory=tuple(_optional_list(data, "memory")),
        truncation=tuple(_optional_list(data, "truncation")),
        raw_reviewer_outputs=tuple(raw_outputs),
    )


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


def _validate_reviewer_agent(name: str, agent: dict[str, Any]) -> None:
    unknown_fields = set(agent) - ALLOWED_AGENT_FIELDS
    if unknown_fields:
        raise FixtureError(f"reviewer config agent {name} has unsupported fields: {', '.join(sorted(unknown_fields))}")
    _validate_optional_str(agent, "description", name)
    stages = agent.get("stages")
    if not isinstance(stages, list) or not stages:
        raise FixtureError(f"reviewer config agent {name} must include stages")
    if not all(isinstance(stage, str) and stage in ALLOWED_STAGES for stage in stages):
        raise FixtureError(f"reviewer config agent {name} has unsupported stage")
    if len(set(stages)) != len(stages):
        raise FixtureError(f"reviewer config agent {name} has duplicate stages")
    triggers = agent.get("triggers")
    if not isinstance(triggers, dict):
        raise FixtureError(f"reviewer config agent {name} must include triggers")
    _validate_triggers(name, triggers)
    if "required" in agent and type(agent["required"]) is not bool:
        raise FixtureError(f"reviewer config agent {name}.required must be a boolean")
    verdict_power = agent.get("verdict_power", "comment")
    if not isinstance(verdict_power, str) or verdict_power not in ALLOWED_VERDICT_POWERS:
        raise FixtureError(f"reviewer config agent {name} has unsupported verdict_power")
    capabilities = agent.get("capabilities", ["diff_context"])
    if not isinstance(capabilities, list) or not capabilities:
        raise FixtureError(f"reviewer config agent {name}.capabilities must be a non-empty list")
    if not all(isinstance(capability, str) and capability in ALLOWED_CAPABILITIES for capability in capabilities):
        raise FixtureError(f"reviewer config agent {name} has unsupported capabilities")
    _validate_optional_str(agent, "model", name)
    _validate_optional_list_of_str(agent, "tools", name)
    if "context" in agent and not isinstance(agent["context"], (str, dict)):
        raise FixtureError(f"reviewer config agent {name}.context must be a string or object")


def _validate_triggers(name: str, triggers: dict[str, Any]) -> None:
    if not triggers:
        raise FixtureError(f"reviewer config agent {name}.triggers must be non-empty")
    unknown_trigger_fields = set(triggers) - ALLOWED_TRIGGER_FIELDS
    if unknown_trigger_fields:
        raise FixtureError(
            f"reviewer config agent {name} has unsupported trigger fields: "
            f"{', '.join(sorted(unknown_trigger_fields))}"
        )
    if "always" in triggers and type(triggers["always"]) is not bool:
        raise FixtureError(f"reviewer config agent {name}.triggers.always must be a boolean")
    for field in ("paths", "labels", "diff_patterns", "conversation_patterns"):
        _validate_optional_list_of_str(triggers, field, f"{name}.triggers")
    for field in ("max_files", "changed_lines_min", "changed_files_min"):
        if field in triggers and (type(triggers[field]) is not int or triggers[field] <= 0):
            raise FixtureError(f"reviewer config agent {name}.triggers.{field} must be a positive integer")
    _validate_optional_str(triggers, "risk_min", f"{name}.triggers")


def _validate_optional_str(data: dict[str, Any], field: str, label: str) -> None:
    if field in data and (not isinstance(data[field], str) or not data[field]):
        raise FixtureError(f"reviewer config agent {label}.{field} must be a non-empty string")


def _validate_optional_list_of_str(data: dict[str, Any], field: str, label: str) -> None:
    if field not in data:
        return
    value = data[field]
    if not isinstance(value, list) or not value:
        raise FixtureError(f"reviewer config agent {label}.{field} must be a non-empty list")
    if not all(isinstance(item, str) and item for item in value):
        raise FixtureError(f"reviewer config agent {label}.{field} must contain non-empty strings")


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
                patch=str(entry.get("patch", "")),
            )
        )
    return tuple(changed_files)


def _optional_list(data: dict[str, Any], field: str) -> list[dict[str, Any]]:
    value = data.get(field, [])
    if not isinstance(value, list):
        raise FixtureError(f"fixture.{field} must be a list")
    if not all(isinstance(item, dict) for item in value):
        raise FixtureError(f"fixture.{field} entries must be objects")
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
