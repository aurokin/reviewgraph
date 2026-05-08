# Implementation Notes

This directory is for narrow implementation contracts once code exists. Keep broad product and architecture material in `docs/product/` and `docs/architecture/`.

## Working from Linear

Concrete implementation work is tracked in Linear, not in generated files inside this repository. Each Linear issue should be executable from:

- the issue description and linked milestone;
- the narrowest durable doc that defines the behavior;
- the harness proof contract in `docs/harnesses/harness-engineering.md`;
- the linked blocker relationships in Linear.

When a Linear issue exposes a missing durable rule, update the narrowest doc instead of adding a one-off local planning file.

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

To prove a Linear issue queue export is dependency-ordered, pass a canonical export:

```bash
python scripts/check_docs.py --backlog-export path/to/linear-backlog-export.json
```

The export must be a JSON object with `source: "Linear"`, `project`, `milestone`, `exported_at`, and an ordered `issues` array. Each issue uses `id`, `title`, `status_type`, and `blocked_by`. The checker filters issues whose `status_type` is `canceled`, then fails on duplicate active IDs, missing blockers, cycles, or blockers that appear after their dependent issue. It prints source, project, milestone, timestamp, active issue count, dependency edge count, and skipped canceled count.

Synthetic examples live in `docs/plans/fixtures/`. They are parser/checker examples only and are not the ReviewGraph backlog.

## Expected future docs

- `models.md` — Pydantic/state model contracts.
- `adapters.md` — GitHub, LLM, and side-effect adapter interfaces.
- `prompts.md` — reviewer prompt structure and output repair policy.
- `cli.md` — CLI commands, flags, exit codes, and output paths.

## Rule

Only add implementation docs when there is code or an imminent implementation task that needs a stable contract. Do not duplicate the implementation plan here.
