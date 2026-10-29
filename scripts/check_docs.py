#!/usr/bin/env python3
"""Validate ReviewGraph documentation contracts."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import unquote


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
    "GitHub issues",
]

AGENTS_PHRASES = [
    "behavior changes",
    "update the narrowest durable doc",
]

DECISION_PHRASES = [
    "Dry-run first",
    "Staged LangGraph review",
    "Codex-inspired review quality bar",
    "Docs and GitHub are the backlog",
]


class ValidationError(Exception):
    pass


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
        target, fragment = split_markdown_target(link)
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
            continue
        if fragment and target_path.suffix.lower() == ".md":
            anchors = markdown_heading_anchors(target_path.read_text(encoding="utf-8"))
            if fragment not in anchors:
                errors.append(f"{relative}: link anchor does not exist: {link!r}")
    return errors


def split_markdown_target(link: str) -> tuple[str, str | None]:
    target, separator, fragment = link.partition("#")
    if not separator:
        return link, None
    return target, unquote(fragment)


def markdown_heading_anchors(text: str) -> set[str]:
    anchors: set[str] = set()
    counts: dict[str, int] = {}
    in_fence = False
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if not match:
            continue
        base = github_heading_slug(match.group(2))
        count = counts.get(base, 0)
        counts[base] = count + 1
        anchors.add(base if count == 0 else f"{base}-{count}")
    return anchors


def github_heading_slug(text: str) -> str:
    slug = text.strip().lower()
    slug = re.sub(r"`([^`]*)`", r"\1", slug)
    slug = re.sub(r"<[^>]+>", "", slug)
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"\s+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)

    errors = check_docs()

    if errors:
        for error in errors:
            print(f"validation error: {error}", file=sys.stderr)
        return 1

    print("documentation contract check: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
