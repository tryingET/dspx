---
summary: "Governed many-of-the-greats review of evidence-only Core activation under a solo operator."
read_when:
  - "You are reviewing the solo-authority evidence activation RFC or future release consumer boundary."
type: "review"
---

# Review — Core Evidence Activation Under Solo Authority

## Question

Can authenticated public Core evidence custody activate without three release-owner bindings, while preserving the accepted separation between workload authenticity and release authority?

## Mode 1 — many of the greats

### Constitutional governance

- Core claim: a threshold is real only when principals are independently controlled and independently judge.
- Premises: role aliases do not create people; cryptography authenticates a principal but does not create independent intent.
- Strongest case: the existing empty roster is safer and more truthful than three accounts or keys held by one operator.
- What it sees: structural 2-of-3 checks can become a dangerous authority proxy when authentication and independence are absent.

### Supply-chain security

- Core claim: workload authenticity and bounded custody should operate before release authority exists.
- Premises: exact Sigstore identity, public disclosure preflight, signed receipts, and current availability create empirical value without package-write permission.
- Strongest case: the workflow and artifacts already hard-code non-authority; blocking them on human quorum conflates evidence production with release intent.
- What it sees: live negative-path dogfood finds provider and certificate drift that offline fixtures cannot.

### Solo-builder operationalism

- Core claim: a solo project needs an honest single-operator path rather than dormant enterprise theater.
- Premises: concentrated authority can be declared and compensated with strong technical controls, but cannot be disguised as a multi-person quorum.
- Strongest case: progressive assurance enables evidence now and leaves any future solo release policy to an explicit risk decision.
- What it sees: organizational maturity cannot be manufactured by schema.

## Mode 2 — confrontation

### Quorum versus evidence activation

The contradiction is not fundamental. Quorum governs human release intent; Sigstore and custody govern machine-produced evidence. Requiring quorum for a no-publication evidence workflow adds no independent judgment to the signature and prevents empirical validation.

### Quorum versus solo release authority

The contradiction is fundamental. One operator cannot produce three independent principals. Multiple credentials, services, or factors under the same operator improve compromise resistance but do not provide independent judgment. Any consumer that counts them as three owners is invalid.

### Operationalism versus policy immutability

Operational convenience cannot reinterpret accepted policy v1. If a future solo-owner authority model is selected, it must be a new monotonic policy and selector decision with explicit concentrated-risk acceptance.

## Mode 3 — contextual dominance

- Chosen path: contextual dominance.
- Evidence-plane result: supply-chain empiricism dominates. Activate exact evidence signing and custody with the unbound roster validated in its disabled posture.
- Release-plane result: constitutional governance dominates under policy v1. Release authority remains impossible.
- Future result: a separately reviewed solo-owner policy is a legitimate candidate, but no mechanism is selected in this review.

## Findings

1. **Accept:** decouple evidence-only workflow activation from `require_bindings`.
2. **Reject:** fake roster bindings, role aliases, bot principals, or technical factors counted as independent owners.
3. **Require:** every live receipt and report preserve `release_authority=false` and `package_publication=false`.
4. **Require:** treat a same-principal GitHub environment reviewer as a deliberate-action control only.
5. **Defer:** release-authorization consumer activation until an owner-authentication mechanism is separately accepted.
6. **Preserve:** policy v1 and selector v1 bytes and authority lineage.

## Review outcome

`ready_for_adr`
