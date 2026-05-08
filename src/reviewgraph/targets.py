from __future__ import annotations

from pathlib import Path
from typing import Any

from reviewgraph.fixtures import load_reviewer_config
from reviewgraph.github import (
    GitHubReadResult,
    load_paginated_fake_github_transport,
    read_github_pr_with_paginated_fake_transport,
)
from reviewgraph.read_gaps import FailClosedReadOutcome
from reviewgraph.runner import (
    DryRunResult,
    _DryRunInput,
    _config_with_live_settings,
    _fail_closed_dry_run_result,
    _run_dry_run_core,
    _writer_call_count,
)


def run_github_fake_dry_run(
    *,
    github_pr_ref: str,
    github_fake_data_path: str | Path,
    reviewer_config_path: str | None = None,
    writer_sentinel: object | None = None,
    live_llm_settings: dict[str, object] | None = None,
    live_llm_transport: object | None = None,
    live_llm_opt_in_source: str | None = None,
) -> DryRunResult:
    writer_call_count_before = _writer_call_count(writer_sentinel)
    config = load_reviewer_config(reviewer_config_path)
    config = _config_with_live_settings(config, live_llm_settings)
    transport, raw_reviewer_outputs = load_paginated_fake_github_transport(github_fake_data_path)
    read_result = read_github_pr_with_paginated_fake_transport(transport, github_pr_ref)
    writer_call_count = _writer_call_count(writer_sentinel) - writer_call_count_before
    if isinstance(read_result, FailClosedReadOutcome):
        return _fail_closed_dry_run_result(outcome=read_result, writer_call_count=writer_call_count)
    return _run_dry_run_core(
        dry_run_input=_input_from_github_read_result(
            read_result,
            raw_reviewer_outputs=raw_reviewer_outputs,
        ),
        config=config,
        writer_call_count_before=writer_call_count_before,
        writer_sentinel=writer_sentinel,
        live_llm_transport=live_llm_transport,
        live_llm_opt_in_source=live_llm_opt_in_source,
    )


def _input_from_github_read_result(
    read_result: GitHubReadResult,
    *,
    raw_reviewer_outputs: tuple[dict[str, Any], ...],
) -> _DryRunInput:
    return _DryRunInput(
        source_type="github",
        source_id=f"github:{read_result.pr_ref.owner_repo}#{read_result.pr_ref.pr_number}",
        source_ref=f"github:{read_result.pr_ref.owner_repo}#{read_result.pr_ref.pr_number}",
        pr=read_result.pr,
        review_target=read_result.review_target,
        changed_files=read_result.changed_file_lines,
        raw_reviewer_outputs=raw_reviewer_outputs,
        github_read=read_result.to_dict(),
    )
