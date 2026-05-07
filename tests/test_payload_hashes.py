import pytest

from reviewgraph.hashing import (
    canonical_text_body,
    canonical_visible_body,
    final_payload_hash,
    findings_hash,
    is_exact_reviewgraph_v1_marker_line,
    marker_payload_hash,
    review_target_hash,
    visible_body_hash,
)
from reviewgraph.models import ReviewTarget


TARGET_HASH = "sha256:b0b1700548a7afe8fda856a5128dd4dc3059e7b67bf19aa730bee6a5a9cf4376"
VISIBLE_BODY_HASH = "sha256:106a40d32d329b5b429aec2b78e53b278cf66bda3815f53a1cc6d3a0ceb3239a"
FINDINGS_HASH = "sha256:49113a9c08f5fd7850b7e050966113aee6e623b9ae1677511710f926bc30d4d0"
FINAL_PAYLOAD_HASH = "sha256:9f1d0a8601caa7f1f5ab0e73163d9f4e000c59b82eb9f26e2a03963448c0d6af"


def target() -> ReviewTarget:
    return ReviewTarget(
        owner_repo="acme/widgets",
        pr_number=42,
        base_sha="base123",
        head_sha="head456",
        merge_base_sha=None,
        diff_basis="merge_base",
    )


def visible_body() -> str:
    return "ReviewGraph final comment\n\n- P1 Cache miss returns stale data.\n"


def marker_line() -> str:
    return (
        "<!-- reviewgraph:v1 run_id=run-123 "
        f"target={TARGET_HASH} "
        f"payload={VISIBLE_BODY_HASH} "
        f"findings={FINDINGS_HASH} -->"
    )


def test_payload_hash_domains_have_pinned_golden_digests() -> None:
    body_with_crlf = "ReviewGraph final comment\r\n\r\n- P1 Cache miss returns stale data.\n\n"
    full_body = visible_body() + marker_line() + "\n"

    assert canonical_text_body(body_with_crlf) == visible_body()
    assert visible_body_hash(body_with_crlf) == VISIBLE_BODY_HASH
    assert marker_payload_hash(body_with_crlf) == VISIBLE_BODY_HASH
    assert findings_hash(("fp-1", "fp-0", "fp-2")) == FINDINGS_HASH
    assert final_payload_hash(full_body) == FINAL_PAYLOAD_HASH
    assert final_payload_hash(full_body.replace("\n", "\r\n")) == FINAL_PAYLOAD_HASH
    assert target().target_hash() == TARGET_HASH
    assert review_target_hash(target().to_ordered_dict()) == TARGET_HASH


def test_visible_body_hash_excludes_only_exact_final_v1_marker() -> None:
    full_body = visible_body() + marker_line() + "\n"
    github_run_marker = marker_line().replace("run_id=run-123", "run_id=github:acme/widgets#42")

    assert is_exact_reviewgraph_v1_marker_line(marker_line())
    assert is_exact_reviewgraph_v1_marker_line(github_run_marker)
    assert canonical_visible_body(full_body) == visible_body()
    assert canonical_visible_body(visible_body() + github_run_marker + "\n") == visible_body()
    assert visible_body_hash(full_body) == VISIBLE_BODY_HASH
    assert visible_body_hash(visible_body() + "\n" + marker_line()) == VISIBLE_BODY_HASH
    assert visible_body_hash(marker_line() + "\n" + visible_body()) != VISIBLE_BODY_HASH


@pytest.mark.parametrize(
    "bad_marker",
    [
        "<!-- reviewgraph:payload -->",
        "<!-- reviewgraph:v2 run_id=run-123 "
        f"target={TARGET_HASH} payload={VISIBLE_BODY_HASH} findings={FINDINGS_HASH} -->",
        f"<!-- reviewgraph:v1 run_id=run-123 target={TARGET_HASH} payload={VISIBLE_BODY_HASH} -->",
        "<!-- reviewgraph:v1 run_id= "
        f"target={TARGET_HASH} payload={VISIBLE_BODY_HASH} findings={FINDINGS_HASH} -->",
        "<!-- reviewgraph:v1 run_id=bad=value "
        f"target={TARGET_HASH} payload={VISIBLE_BODY_HASH} findings={FINDINGS_HASH} -->",
        "<!-- reviewgraph:v1 run_id='quoted' "
        f"target={TARGET_HASH} payload={VISIBLE_BODY_HASH} findings={FINDINGS_HASH} -->",
        "<!-- reviewgraph:v1 run_id=bad!value "
        f"target={TARGET_HASH} payload={VISIBLE_BODY_HASH} findings={FINDINGS_HASH} -->",
        f"<!-- reviewgraph:v1 run_id=run-123 target={TARGET_HASH} findings={FINDINGS_HASH} payload={VISIBLE_BODY_HASH} -->",
        "<!-- reviewgraph:v1  run_id=run-123 "
        f"target={TARGET_HASH} payload={VISIBLE_BODY_HASH} findings={FINDINGS_HASH} -->",
        "<!-- reviewgraph:v1 run_id=run-123 "
        f"target={TARGET_HASH} payload={VISIBLE_BODY_HASH} findings={FINDINGS_HASH} extra=1 -->",
    ],
)
def test_malformed_marker_lines_are_not_stripped(bad_marker: str) -> None:
    body = visible_body() + bad_marker + "\n"

    assert not is_exact_reviewgraph_v1_marker_line(bad_marker)
    assert canonical_visible_body(body) == body
    assert visible_body_hash(body) != VISIBLE_BODY_HASH


def test_selected_fingerprint_hash_rejects_duplicates() -> None:
    with pytest.raises(ValueError, match="duplicate"):
        findings_hash(("fp-1", "fp-0", "fp-1"))
