---
summary: "System4D: Engine (states/invariants/lifecycle) for DSPx"
read_when:
  - "When defining invariants and lifecycle"
  - "When understanding behavioral states"
---

# System4D — Engine

## Invariants (Non-Negotiable)

1. **Monorepo boundary** — Core never imports apps
2. **Receipt determinism** — Same input → same receipt hash
3. **Replay fidelity** — Receipt enables exact reproduction
4. **Test green** — All 358+ tests pass

## Lifecycle States

```
signature-gen → module-gen → forge-pipeline
      ↓              ↓              ↓
   receipt        receipt        receipt
      ↓              ↓              ↓
   Oracle index → embed → analyze → predict
```

## State Transitions

| From | To | Trigger |
|------|-----|---------|
| No signature | signature-gen | `dspx signature gen` |
| Signature | module-gen | `dspx module-gen` |
| Module | forge pipeline | `dspx forge run` |
| Execution | Oracle indexed | `dspx oracle index` |
| Indexed | Analyzed | `dspx oracle territory/attractors` |

## Quality Gates

```bash
just fmt lint typecheck test  # All must pass
just monorepo-check           # Boundary invariant
```

## Failure Modes

| Failure | Detection | Recovery |
|---------|-----------|----------|
| Receipt drift | `dspx run replay --check-only` | Re-run from receipt |
| Monorepo leak | `just monorepo-check` | Fix imports |
| Test regression | CI red | `git bisect` |
| Embedding mismatch | Oracle stats dimension check | Re-index |
