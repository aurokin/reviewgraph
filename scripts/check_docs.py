#!/usr/bin/env python3
"""Validate ReviewGraph documentation contracts and optional Linear backlog order."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_DOC_INDEX_LINKS = [
    "architecture/overview.md",
    "architecture/state-graph.md",
    "prds/README.md",
    "decisions/README.md",
    "harnesses/harness-engineering.md",
    "plans/implementation-plan.md",
]

LINK_TARGET_DOCS = [
    "docs/README.md",
    "docs/decisions/README.md",
]

IMPLEMENTATION_PLAN_PHRASES = [
    "dry-run",
    "item-level approval",
    "top-level PR comment",
    "Formal GitHub review submission",
    "target freshness",
    "actor/permission",
    "redaction",
    "marker",
    "local verdict",
    "structured findings",
    "fixtures",
    "fake",
    "opt-in",
    "Side effects are last",
    "Linear",
]

AGENTS_PHRASES = [
    "behavior changes",
    "update the narrowest durable doc",
]

DECISION_PHRASES = [
    "Dry-run first",
    "Staged LangGraph review",
    "Codex-inspired review quality bar",
    "Linear backlog, docs as contracts",
]


class ValidationError(Exception):
    pass


@dataclass(frozen=True)
class Issue:
    id: str
    title: str
    status_type: str
    blocked_by: tuple[str, ...]
    index: int


def read_text(relative: str) -> str:
    path = ROOT / relative
    if not path.exists():
        raise ValidationError(f"missing required file: {relative}")
    return path.read_text(encoding="utf-8")


def require_phrases(label: str, text: str, phrases: list[str]) -> list[str]:
    errors: list[str] = []
    lowered = text.lower()
    for phrase in phrases:
        if phrase.lower() not in lowered:
            errors.append(f"{label}: missing phrase {phrase!r}")
    return errors


def markdown_links(text: str) -> list[str]:
    return re.findall(r"\[[^\]]+\]\(([^)]+)\)", text)


def check_docs() -> list[str]:
    errors: list[str] = []

    docs_index = read_text("docs/README.md")
    links = set(markdown_links(docs_index))
    for required in REQUIRED_DOC_INDEX_LINKS:
        if required not in links:
            errors.append(f"docs/README.md: missing required link {required!r}")
        elif not (ROOT / "docs" / required).exists():
            errors.append(f"docs/README.md: required link target does not exist: {required}")

    errors.extend(
        require_phrases(
            "docs/plans/implementation-plan.md",
            read_text("docs/plans/implementation-plan.md"),
            IMPLEMENTATION_PLAN_PHRASES,
        )
    )
    errors.extend(require_phrases("AGENTS.md", read_text("AGENTS.md"), AGENTS_PHRASES))
    errors.extend(
        require_phrases(
            "docs/decisions/README.md",
            read_text("docs/decisions/README.md"),
            DECISION_PHRASES,
        )
    )
    for relative in LINK_TARGET_DOCS:
        errors.extend(check_markdown_link_targets(relative, read_text(relative)))

    return errors


def check_markdown_link_targets(relative: str, text: str) -> list[str]:
    errors: list[str] = []
    source_path = ROOT / relative
    source_dir = source_path.parent
    for link in markdown_links(text):
        if (
            not link
            or link.startswith("#")
            or "://" in link
            or link.startswith("mailto:")
        ):
            continue
        target = link.split("#", 1)[0]
        if not target:
            continue
        target_path = (source_dir / target).resolve()
        try:
            target_path.relative_to(ROOT)
        except ValueError:
            errors.append(f"{relative}: link escapes repository: {link!r}")
            continue
        if not target_path.exists():
            errors.append(f"{relative}: link target does not exist: {link!r}")
    return errors


def parse_backlog_export(path: Path) -> tuple[dict[str, Any], list[Issue], int]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationError(f"{path}: invalid JSON: {exc}") from exc

    if not isinstance(raw, dict):
        raise ValidationError("backlog export must be a JSON object")
    if raw.get("source") != "Linear":
        raise ValidationError("backlog export source must be 'Linear'")
    for field in ("project", "milestone", "exported_at", "issues"):
        if field not in raw:
            raise ValidationError(f"backlog export missing required field: {field}")
    for field in ("project", "milestone", "exported_at"):
        if not isinstance(raw[field], str) or not raw[field]:
            raise ValidationError(f"backlog export field {field!r} must be a non-empty string")
    if not isinstance(raw["issues"], list):
        raise ValidationError("backlog export field 'issues' must be an array")

    active: list[Issue] = []
    skipped_canceled = 0
    for index, item in enumerate(raw["issues"], start=1):
        if not isinstance(item, dict):
            raise ValidationError(f"issue at position {index} must be an object")
        for field in ("id", "title", "status_type", "blocked_by"):
            if field not in item:
                raise ValidationError(f"issue at position {index} missing required field: {field}")
        issue_id = item["id"]
        title = item["title"]
        status_type = item["status_type"]
        blocked_by = item["blocked_by"]
        if not isinstance(issue_id, str) or not issue_id:
            raise ValidationError(f"issue at position {index} has invalid id")
        if not isinstance(title, str):
            raise ValidationError(f"{issue_id}: title must be a string")
        if not isinstance(status_type, str) or not status_type:
            raise ValidationError(f"{issue_id}: status_type must be a non-empty string")
        if not isinstance(blocked_by, list) or not all(
            isinstance(blocker, str) and blocker for blocker in blocked_by
        ):
            raise ValidationError(f"{issue_id}: blocked_by must be an array of issue IDs")
        if status_type == "canceled":
            skipped_canceled += 1
            continue
        active.append(
            Issue(
                id=issue_id,
                title=title,
                status_type=status_type,
                blocked_by=tuple(blocked_by),
                index=index,
            )
        )

    return raw, active, skipped_canceled


def find_cycle(edges: dict[str, tuple[str, ...]]) -> list[str] | None:
    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def visit(issue_id: str) -> list[str] | None:
        if issue_id in visited:
            return None
        if issue_id in visiting:
            start = stack.index(issue_id)
            return stack[start:] + [issue_id]
        visiting.add(issue_id)
        stack.append(issue_id)
        for blocker in edges.get(issue_id, ()):
            cycle = visit(blocker)
            if cycle:
                return cycle
        stack.pop()
        visiting.remove(issue_id)
        visited.add(issue_id)
        return None

    for issue_id in edges:
        cycle = visit(issue_id)
        if cycle:
            return cycle
    return None


def check_backlog_export(path: Path, verbose: bool = False) -> list[str]:
    raw, issues, skipped_canceled = parse_backlog_export(path)
    errors: list[str] = []
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]

    positions: dict[str, int] = {}
    for ordinal, issue in enumerate(issues, start=1):
        if issue.id in positions:
            errors.append(
                f"duplicate active issue id {issue.id!r} at active positions "
                f"{positions[issue.id]} and {ordinal}"
            )
        positions[issue.id] = ordinal

    edges = {issue.id: issue.blocked_by for issue in issues}
    edge_count = sum(len(issue.blocked_by) for issue in issues)

    for issue in issues:
        for blocker in issue.blocked_by:
            if blocker not in positions:
                errors.append(f"{issue.id}: missing blocker reference {blocker}")
                continue
            if positions[blocker] >= positions[issue.id]:
                errors.append(
                    f"{issue.id}: blocker {blocker} appears at active position "
                    f"{positions[blocker]}, not before dependent position {positions[issue.id]}"
                )

    cycle = find_cycle(edges)
    if cycle:
        errors.append("dependency cycle: " + " -> ".join(cycle))

    print(
        "backlog order check:",
        f"path={str(path)!r}",
        f"sha256={digest}",
        f"source={raw['source']!r}",
        f"project={raw['project']!r}",
        f"milestone={raw['milestone']!r}",
        f"exported_at={raw['exported_at']!r}",
        f"active_issues={len(issues)}",
        f"edges={edge_count}",
        f"skipped_canceled={skipped_canceled}",
    )
    print("active order:", ", ".join(issue.id for issue in issues) or "<empty>")
    if edge_count:
        for issue in issues:
            for blocker in issue.blocked_by:
                print(f"edge: {issue.id} blocked_by {blocker}")
    elif verbose:
        print("edges: <none>")
    if errors:
        for error in errors:
            print(f"backlog order error: {error}", file=sys.stderr)

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--backlog-export",
        type=Path,
        help="Path to a canonical Linear backlog queue export JSON file.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print the full active backlog order when checking an export.",
    )
    args = parser.parse_args(argv)

    errors = check_docs()
    if args.backlog_export:
        try:
            errors.extend(check_backlog_export(args.backlog_export, verbose=args.verbose))
        except ValidationError as exc:
            errors.append(str(exc))

    if errors:
        for error in errors:
            print(f"validation error: {error}", file=sys.stderr)
        return 1

    print("documentation contract check: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
