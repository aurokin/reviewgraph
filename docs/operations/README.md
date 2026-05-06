# Operations Notes

This directory is for running ReviewGraph safely. The current runnable path is fixture-only and does not require credentials:

```bash
PYTHONPATH=src python -m reviewgraph.cli --fixture-pr basic-pr --print-markdown
```

Use the fixture path for local smoke tests until the later live-read, live-LLM, approval, and writer milestones land.

## Expected future docs

- `local-development.md` — local setup, API keys, and fake/live modes.
- `live-read.md` — safe read-only GitHub smoke tests.
- `live-post.md` — disposable PR posting smoke test with human approval.
- `tracing.md` — optional LangSmith tracing and privacy rules.

## Operating principle

Live APIs are opt-in. The default path should work with fixtures and fake LLM responses.
