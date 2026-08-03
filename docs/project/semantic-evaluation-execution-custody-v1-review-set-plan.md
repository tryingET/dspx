---
summary: "Strict exact-byte review concerns for Decision 105."
read_when:
  - "Executing or auditing Decision 105 strict review."
type: "review_set_plan"
status: "planned"
decision_id: 105
---
# Decision 105 strict review set

## Exact input

Review covers the problem brief, evidence note, RFC, and machine JSON committed together. Any byte change retires all outcomes.

## Required lanes

| Lane | Required question |
|---|---|
| DSPx owner/current capability | Does the packet match DSPx's runtime/evidence ownership and distinguish shipped primitives from target mechanics without inventing a custody broker? |
| Runtime and crash safety | Is the local machine closed, start-before-effect, non-retryable, and fail-closed under crash/replay ambiguity? |
| ROCS interface | Is the Decision 106 projection immutable, bounded, non-semantic, and incapable of transferring authority? |
| Security and source-owner separation | Are unsupported provider/process/data/network/publication claims impossible and every receipt downstream of observed effects? |

## Rules

- Every lane returns explicit `ACCEPT` or `REJECT` for the exact commit and tree.
- One rejection, silence, timeout, uncertainty, or byte drift blocks convergence.
- Reviewers may not demand implementation detail deliberately delegated to a later implementation decision unless the omission makes this architecture contradictory.
- Reviewers must reject prose that adds a state, transition, retry edge, or authority beyond the machine JSON.
- Tests and source observations are evidence, not acceptance.
- Review is read-only; task `4592` has one worktree writer.
- A controlling synthesis is required before ADR consideration.

## Stop rule

If review exposes a need for a generic broker, protected-data custody, OS process supervision, or a cross-owner machine, stop Decision 105 and create a separate owner decision. Do not grow this packet to absorb that system.
