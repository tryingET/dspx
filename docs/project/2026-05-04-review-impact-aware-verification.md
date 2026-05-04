---
summary: "Current-track review memo for the impact-aware verification RFC, concluding it is ready for ADR recording with conservative rollout boundaries."
read_when:
  - "You are reviewing the impact-aware verification RFC or ADR."
  - "You need the review closure rationale for AK decision #26."
---

# Review memo — Impact-aware verification RFC

- Date: 2026-05-04
- Decision: `#26 Adopt deterministic impact-aware verification planning for DSPx`
- Reviewed artifact: `docs/rfc/RFC-DSPX-VERIFY-20260504-impact-aware-verification.md`
- Review outcome: `ready_for_adr`

## Review summary

The RFC is ready for ADR recording as an accepted architecture decision. It identifies a real workflow gap: `just verify-full` remains necessary as a broad confidence gate, but it is too slow and coarse for every local slice. The proposed impact-aware tier is useful because it turns repeated maintainer judgment about targeted validation into a deterministic, auditable plan.

## Key tensions reviewed

### Speed versus confidence

The RFC does not pretend that partial validation is equivalent to full validation. It preserves `just verify-full` as the broad gate and positions `verify-impact` as a local development tier. That separation is the central safety property.

### Determinism versus intelligence

The chosen approach rejects semantic guessing, AI-selected tests, and dynamic coverage inference for the first slice. The plan is table-driven and auditable. This is the right first contract because DSPx has many generated-artifact, governance, and boundary invariants that import graphs or model inference would miss.

### Usefulness versus fail-wide conservatism

The RFC is intentionally conservative but still useful because it starts with known high-frequency seams: docs, governance/task-scope projections, program-gen, Oracle/refinement, candidate comparison, and boundary-sensitive services. Unknown files and broad changes escalate rather than silently skipping checks.

### Planner simplicity versus CI sprawl

The RFC constrains the planner to selecting existing commands. It does not create a new test framework, mutate state, or own runtime authority. That keeps the first slice small enough to maintain.

## Required ADR constraints

The ADR should preserve these constraints:

- `verify-full` remains unchanged and remains the final confidence gate.
- `verify-impact-plan` must print a deterministic plan and execute nothing.
- `verify-impact` may run only selected existing commands.
- Unknown, CI/dependency, broad shared, and cross-domain changes fail wide.
- The impact map is checked in and tested.
- No AK, governance, Oracle, generated artifact, or external authority mutation occurs as part of planning.

## Review conclusion

The RFC is ready for ADR recording. The decision should be recorded as an accepted ADR for the architecture direction, while implementation remains a separate follow-up slice that must validate the command surface before normal workflow adoption.
