from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TextIO

from reviewgraph.fixtures import FixtureError, redact_for_error
from reviewgraph.runner import RunnerError, run_fixture_dry_run


class _RedactingArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(2, f"{self.prog}: error: {redact_for_error(message)}\n")


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 2
    try:
        result = run_fixture_dry_run(
            fixture_ref=args.fixture_pr,
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
    parser.add_argument(
        "--fixture-pr",
        default="basic-pr",
        help="Fixture PR ID from package data or explicit fixture JSON path.",
    )
    parser.add_argument(
        "--reviewer-config",
        default=None,
        help="Reviewer config JSON path. Defaults to package fixture config.",
    )
    parser.add_argument("--markdown-out", default=None, help="Path to write rendered markdown.")
    parser.add_argument("--json-out", default=None, help="Path to write deterministic JSON envelope.")
    parser.add_argument("--print-markdown", action="store_true", help="Print rendered markdown to stdout.")
    return parser


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
