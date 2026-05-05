# Decision 0001: Dry-run first

## Status

Accepted

## Context

A PR review bot can affect developer trust quickly if it posts noisy or incorrect reviews. The artifact should demonstrate production-grade side-effect discipline.

## Decision

ReviewGraph defaults to dry-run mode. GitHub writes require explicit human approval after rendering the exact payload.

## Consequences

- The first implementation can be useful before write support exists.
- Tests can prove no side effects occur by default.
- Future webhook/CI modes need a separate approval policy before posting.
