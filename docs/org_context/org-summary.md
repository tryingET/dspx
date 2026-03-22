---
summary: "Organization context for DSPx within ai-society"
read_when:
  - "Understanding DSPx's place in the larger system"
  - "Cross-referencing governance decisions"
---

# Organization Context

DSPx is an **owned repo** within `ai-society/softwareco/owned/`.

## Lane: Owned

- We operate this codebase directly
- Full control over architecture and release cadence
- Participates in KES (Knowledge Evolution System)

## Upstream Dependencies

| Dependency | Relationship | Status |
|------------|--------------|--------|
| DSPy | Upstream | PRs prepared, not merged |
| MLflow | Upstream | Optional, callback improvements planned |
| dspy-template-adapter | Upstream | Exact-fidelity path still blocked on issues #1, #2, #6; local provider-runtime v4 adopted instead |

## Downstream Consumers

- `apps/forge/` — Pipeline automation
- External users via PyPI (future)

## Governance Alignment

- Follows `ai-society/holdingco/governance-kernel` consent model
- TIPs for process improvements (domain-only, no meta escalation)
- Diary entries in workspace `~/ai-society/AGENTS.md`

## Behavioral + Process Crystallization

DSPx uniquely bridges two crystallization systems:

| Oracle (Behavioral) | KES (Process) |
|---------------------|---------------|
| Runs → embeddings | Sessions → patterns |
| Topology → attractors | Learnings → TIPs |
| Causal chains | Propagation |

The enables correlating **what the system does** with **how we work on it**.
