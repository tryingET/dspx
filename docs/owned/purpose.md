---
summary: "DSPx purpose and delivery baseline"
read_when:
  - "When deciding if work is in scope"
  - "When aligning Oracle phases with delivery priorities"
---

# Purpose

DSPx is a behavioral intelligence layer for DSPy programs:

- **Core**: Generate, refine, and manage DSPy signatures/modules
- **Oracle**: Behavioral calculus → topology → time travel → dreaming → consciousness
- **Forge**: Pipeline for automated improvement workflows

## In Scope

- Signature generation and refinement
- Module generation with template adapters
- Oracle behavioral analysis (Phases A-E)
- Receipt-based replay and explain
- MLflow integration (optional)

## Out of Scope

- Direct DSPy core modifications (upstream PRs instead)
- Template-adapter upstream fixes themselves (DSPx uses a local provider-runtime workaround instead)
- MLflow core changes (upstream PRs instead)

## Delivery Baseline

- Python 3.13 + uv + just
- Quality gates: ruff + ty + pytest
- 354+ tests must pass
- Monorepo boundary enforced (apps → core OK, core → apps forbidden)
