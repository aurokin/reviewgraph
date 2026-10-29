# Implementation Notes

This directory is for narrow implementation contracts once code exists. Keep broad product and architecture material in `docs/product/` and `docs/architecture/`.

## Working from issues

Concrete implementation work is tracked as GitHub issues and pull requests on this repository, sequenced by `docs/plans/implementation-plan.md`. Do not add generated planning files. Each task should be executable from:

- the issue or PR description and the plan phase it belongs to;
- the narrowest durable doc that defines the behavior;
- the harness proof contract in `docs/harnesses/harness-engineering.md`;
- any blocking issues named in the issue or PR.

When a task exposes a missing durable rule, update the narrowest doc instead of adding a one-off local planning file.

## Validation

Run the default handoff validation sequence before handing off implementation work. The sequence assumes the project test extra is installed (`python -m pip install -e ".[test]"`):

```bash
python -m pytest -q
python -m ruff check src tests scripts
python -m py_compile src/reviewgraph/*.py
python scripts/check_docs.py
git diff --check
```

The default sequence must use fixtures and fake transports only. It must not require credentials, call live LLM providers, post to GitHub, or wait for human input. Marked live smoke tests are collected but skipped unless their explicit opt-in environment variables are set.

Run the documentation contract check before handing off documentation-only or planning work:

```bash
python scripts/check_docs.py
```

## Expected future docs

- `models.md` — Pydantic/state model contracts.
- `adapters.md` — GitHub, LLM, and side-effect adapter interfaces.
- `prompts.md` — reviewer prompt structure and output repair policy.
- `cli.md` — CLI commands, flags, exit codes, and output paths.

## Rule

Only add implementation docs when there is code or an imminent implementation task that needs a stable contract. Do not duplicate the implementation plan here.
