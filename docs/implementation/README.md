# Implementation Notes

This directory is for narrow implementation contracts once code exists. Keep broad product and architecture material in `docs/product/` and `docs/architecture/`.

## Working from Linear

Concrete implementation work is tracked in Linear, not in generated files inside this repository. Each Linear issue should be executable from:

- the issue description and linked milestone;
- the narrowest durable doc that defines the behavior;
- the harness proof contract in `docs/harnesses/harness-engineering.md`;
- the linked blocker relationships in Linear.

When a Linear issue exposes a missing durable rule, update the narrowest doc instead of adding a one-off local planning file.

## Expected future docs

- `models.md` — Pydantic/state model contracts.
- `adapters.md` — GitHub, LLM, and side-effect adapter interfaces.
- `prompts.md` — reviewer prompt structure and output repair policy.
- `cli.md` — CLI commands, flags, exit codes, and output paths.

## Rule

Only add implementation docs when there is code or an imminent implementation task that needs a stable contract. Do not duplicate the implementation plan here.
