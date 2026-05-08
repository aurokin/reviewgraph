from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TextIO

from reviewgraph.fixtures import FixtureError, redact_for_error
from reviewgraph.runner import RunnerError, run_fixture_dry_run
from reviewgraph.targets import run_github_fake_dry_run


class _RedactingArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: error: {redact_for_error(message)}\n")


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    try:
        args = parser.parse_args(argv)
        _validate_target_args(parser, args)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 2
    try:
        if args.live_llm:
            raise RunnerError(
                "Live LLM execution is opt-in and requires the live transport harness; "
                "default CLI review remains fake-provider-free."
            )
        if args.github_pr is not None:
            if args.github_live_read:
                raise RunnerError(
                    "GitHub live read is deferred to a later milestone; use --github-fake-data for this dry-run."
                )
            result = run_github_fake_dry_run(
                github_pr_ref=args.github_pr,
                github_fake_data_path=args.github_fake_data,
                reviewer_config_path=args.reviewer_config,
            )
        else:
            result = run_fixture_dry_run(
                fixture_ref=args.fixture_pr or "basic-pr",
                reviewer_config_path=args.reviewer_config,
            )
        if args.markdown_out is not None:
            _write_text(Path(args.markdown_out), result.markdown)
        if args.json_out is not None:
            _write_text(Path(args.json_out), _stable_json(result.json_data))
        if args.print_markdown or _has_no_output_target(args):
            sys.stdout.write(result.markdown)
        return 0
    except (FixtureError, RunnerError, OSError, ValueError) as exc:
        _print_error(str(exc), sys.stderr)
        return 2


def _parser() -> argparse.ArgumentParser:
    parser = _RedactingArgumentParser(description="Run a ReviewGraph fixture dry-run.")
    target = parser.add_mutually_exclusive_group()
    target.add_argument(
        "--fixture-pr",
        default=None,
        help="Fixture PR ID from package data or explicit fixture JSON path.",
    )
    target.add_argument(
        "--github-pr",
        default=None,
        help="GitHub PR target as owner/repo#number or https://github.com/owner/repo/pull/number.",
    )
    parser.add_argument(
        "--github-fake-data",
        default=None,
        help="Path to paginated fake GitHub read data for --github-pr.",
    )
    parser.add_argument(
        "--github-live-read",
        action="store_true",
        help="Opt into live read-only GitHub mode. Deferred in this milestone.",
    )
    parser.add_argument(
        "--reviewer-config",
        default=None,
        help="Reviewer config JSON path. Defaults to package fixture config.",
    )
    parser.add_argument("--markdown-out", default=None, help="Path to write rendered markdown.")
    parser.add_argument("--json-out", default=None, help="Path to write deterministic JSON envelope.")
    parser.add_argument("--print-markdown", action="store_true", help="Print rendered markdown to stdout.")
    parser.add_argument("--live-llm", action="store_true", help="Opt into live LLM reviewer execution.")
    parser.add_argument("--live-llm-provider", default=None, help="Live LLM provider for --live-llm.")
    parser.add_argument("--live-llm-model", default=None, help="Live LLM model for --live-llm.")
    parser.add_argument(
        "--live-llm-max-calls",
        type=int,
        default=None,
        help="Maximum live LLM provider calls allowed for --live-llm.",
    )
    return parser


def _validate_target_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.github_fake_data is not None and args.github_pr is None:
        parser.error("--github-fake-data requires --github-pr")
    if args.github_live_read and args.github_pr is None:
        parser.error("--github-live-read requires --github-pr")
    if args.github_pr is not None and args.github_fake_data is not None and args.github_live_read:
        parser.error("--github-fake-data and --github-live-read cannot be combined")
    if args.github_pr is not None and args.github_fake_data is None and not args.github_live_read:
        parser.error("--github-pr requires --github-fake-data or --github-live-read")
    if not args.live_llm and (
        args.live_llm_provider is not None
        or args.live_llm_model is not None
        or args.live_llm_max_calls is not None
    ):
        parser.error("--live-llm-provider, --live-llm-model, and --live-llm-max-calls require --live-llm")
    if args.live_llm:
        if args.live_llm_provider is None:
            parser.error("--live-llm requires --live-llm-provider")
        if args.live_llm_model is None:
            parser.error("--live-llm requires --live-llm-model")
        if args.live_llm_max_calls is None or args.live_llm_max_calls <= 0:
            parser.error("--live-llm requires positive --live-llm-max-calls")


def _write_text(path: Path, text: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise OSError(f"failed to write output path {redact_for_error(str(path))}: {exc.strerror}") from exc


def _stable_json(data: dict[str, object]) -> str:
    return json.dumps(data, sort_keys=True, indent=2) + "\n"


def _has_no_output_target(args: argparse.Namespace) -> bool:
    return not args.print_markdown and args.markdown_out is None and args.json_out is None


def _print_error(message: str, stderr: TextIO) -> None:
    stderr.write(f"reviewgraph: {redact_for_error(message)}\n")


if __name__ == "__main__":
    raise SystemExit(main())
