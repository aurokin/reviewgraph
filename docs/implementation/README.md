# Implementation Notes

This directory is for narrow implementation contracts once code exists. Keep broad product and architecture material in `docs/product/` and `docs/architecture/`.

## Expected future docs

- `models.md` — Pydantic/state model contracts.
- `adapters.md` — GitHub, LLM, and side-effect adapter interfaces.
- `prompts.md` — reviewer prompt structure and output repair policy.
- `cli.md` — CLI commands, flags, exit codes, and output paths.

## Rule

Only add implementation docs when there is code or an imminent implementation task that needs a stable contract. Do not duplicate the implementation plan here.
