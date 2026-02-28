---
summary: "System4D: Container (boundary/constraints) for DSPx"
read_when:
  - "When scoping work"
  - "When evaluating in vs out of scope"
---

# System4D — Container

## Boundary

```
DSPx
├── packages/dspx-core/    # Core library (no app imports)
│   ├── cli/               # Command modules
│   ├── services/          # Business logic
│   ├── coordinates/       # Oracle behavioral analysis
│   └── ...
├── apps/forge/            # Forge pipeline (imports core)
├── tests/                 # Test suite
├── docs/                  # Documentation + KES
└── generated/             # Output artifacts
```

## Constraints

| Constraint | Type | Reason |
|------------|------|--------|
| Python 3.13+ | HARD | Type system features |
| uv + just | HARD | Build system |
| No core → apps imports | HARD | Monorepo boundary |
| MLflow optional | SOFT | Can disable |
| Template adapter optional | SOFT | Has fallback |
| Oracle requires embeddings | SOFT | Mock available |

## In Scope

- Signature/module generation
- Oracle Phases A-E
- Receipt-based replay/explain
- Forge pipeline
- MLflow integration (optional)

## Out of Scope

- DSPy core modifications → upstream PRs
- MLflow core modifications → upstream PRs
- Template adapter fixes → blocked on upstream issues #1, #2, #6

## Capacity

- Single maintainer velocity
- Incremental delivery preferred
- Quality gates non-negotiable
- KES integration via ai-society workspace

## Integration Points

| System | Direction | Notes |
|--------|-----------|-------|
| ai-society | Upstream | KES, cognitive tools, docs discovery |
| DSPy | Upstream | PRs for callback improvements |
| MLflow | Upstream | PRs for tracking improvements |
| template-adapter | Upstream | Blocked on issues |
