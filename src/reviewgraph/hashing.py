from __future__ import annotations

import hashlib
import json
import re
from typing import Iterable


HASH_PREFIX = "sha256:"
HASH_RE = r"sha256:[0-9a-f]{64}"
RUN_ID_RE = r"(?P<run_id>[A-Za-z0-9][A-Za-z0-9._:/#-]{0,127})"
REVIEWGRAPH_MARKER_RE = re.compile(
    rf"^<!-- reviewgraph:v1 "
    rf"run_id={RUN_ID_RE} "
    rf"target=(?P<target>{HASH_RE}) "
    rf"payload=(?P<payload>{HASH_RE}) "
    rf"findings=(?P<findings>{HASH_RE}) -->$"
)


def sha256_text(text: str) -> str:
    return HASH_PREFIX + hashlib.sha256(text.encode("utf-8")).hexdigest()


def canonical_json_hash(data: object) -> str:
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256_text(encoded)


def domain_json_hash(domain: str, data: object) -> str:
    encoded = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256_text(f"{domain}\n{encoded}")


def canonical_text_body(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return normalized.rstrip("\n") + "\n"


def is_exact_reviewgraph_v1_marker_line(line: str) -> bool:
    return REVIEWGRAPH_MARKER_RE.fullmatch(line) is not None


def parse_reviewgraph_v1_marker_line(line: str) -> dict[str, str] | None:
    if not isinstance(line, str):
        return None
    match = REVIEWGRAPH_MARKER_RE.fullmatch(line)
    if match is None:
        return None
    return {
        "run_id": match.group("run_id"),
        "target": match.group("target"),
        "payload": match.group("payload"),
        "findings": match.group("findings"),
    }


def canonical_visible_body(text: str) -> str:
    canonical = canonical_text_body(text)
    lines = canonical.split("\n")
    if len(lines) >= 2 and is_exact_reviewgraph_v1_marker_line(lines[-2]):
        return "\n".join(lines[:-2]).rstrip("\n") + "\n"
    return canonical


def visible_body_hash(text: str) -> str:
    return sha256_text(canonical_visible_body(text))


def marker_payload_hash(final_body_without_marker: str) -> str:
    return visible_body_hash(final_body_without_marker)


def final_payload_hash(full_final_body: str) -> str:
    return sha256_text(canonical_text_body(full_final_body))


def findings_hash(fingerprints: Iterable[str]) -> str:
    ordered = sorted(fingerprints)
    if len(set(ordered)) != len(ordered):
        raise ValueError("duplicate finding fingerprints are not allowed")
    return canonical_json_hash(ordered)


def review_target_hash(ordered_target: object) -> str:
    return domain_json_hash("reviewgraph.review_target.v1", ordered_target)
