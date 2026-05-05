# Agent Instructions

Review this file before changing the repository.

## Project posture

ReviewGraph is documentation-first. Preserve the product contract, state graph, side-effect boundaries, and harness strategy before adding implementation code.

## Read order

1. `README.md`
2. `docs/product/vision.md`
3. `docs/product/rules.md`
4. `docs/architecture/overview.md`
5. `docs/architecture/state-graph.md`
6. `docs/harnesses/harness-engineering.md`
7. `docs/plans/implementation-plan.md`

## Product guardrails

- Dry-run is the default behavior.
- GitHub write operations require explicit human approval.
- Reviewer agent selection must be explainable.
- Findings must be structured before they are rendered as markdown.
- Critical/request-changes verdicts require high-confidence evidence.
- Side effects belong at the end of the graph behind an approval gate.
- Keep LangGraph state explicit; do not hide routing decisions inside prompts.
- Do not couple reviewer prompts directly to GitHub transport code.

## Implementation posture

- Prefer small vertical slices with tests.
- Add harness tests before implementation where possible.
- Keep external API calls behind adapters so tests can use fixtures.
- Use fixture PRs and deterministic fake LLM responses before live API calls.
- Any live GitHub posting feature must include dry-run proof and approval proof.

## Documentation updates

When behavior changes, update the narrowest durable doc:

- Product behavior -> `docs/product/`
- Architecture or graph shape -> `docs/architecture/`
- Harness or verification -> `docs/harnesses/`
- Implementation sequencing -> `docs/plans/`
- Durable tradeoff -> `docs/decisions/`
