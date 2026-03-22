---
summary: "System4D: Fog (risks/assumptions/exceptions/debt) for DSPx"
read_when:
  - "When tracking uncertainty"
  - "Before making architectural changes"
---

# System4D — Fog

## Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Template adapter upstream stalls | High | Medium | Vendor patched version if needed |
| Oracle embedding backend unavailable | Medium | Low | Mock backend for CI/testing |
| MLflow callback changes break integration | Low | Medium | Oracle detects behavioral drift |

## Assumptions

- MLflow is optional (can be disabled)
- Template adapter has fallback
- Oracle is additive (doesn't change existing behavior)
- Receipts are deterministic (same input → same hash)

## Exceptions

- DSPx repo moved from `~/programming/dspx` to `~/ai-society/softwareco/owned/dspx`
- Git history preserved via copy
- Template applied via copier (updateable)

## Debt

| Debt | Interest | Payoff Plan |
|------|----------|-------------|
| Template adapter upstream issues | Exact-fidelity adapter remains deferred | Monitor upstream while using provider-runtime v4 for the supported local path |
| Oracle coverage heuristics are approximate | May mislead users | Document as heuristic, improve with data |
| Knowledge Crystallized embedded in NEXT_STEPS.md | Mixed concerns | Migrated to docs/learnings/ |

## What's Clear

- Oracle Phases A and B are solid
- Receipt v2 enables Phase C
- 358 tests provide safety net

## What's Uncertain

- Upstream PR timelines (DSPy, MLflow, template-adapter)
- Phase D/E architecture
- Production deployment model

