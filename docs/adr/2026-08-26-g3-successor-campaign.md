---
summary: "Accepted G3 successor empirical protocol (conditioned on the EC candidate-5 binding, AK 5096): 36 distinct convention-space instances × 2 families = 72 pairs, pooled exact-McNemar primary with floored template-level co-primary guard, simulation-disclosed power, one-shot extension rule, no substitution channel."
read_when:
  - "Freezing, executing, or reviewing the G3 successor campaign (AK 5095)."
  - "Consuming the reopened G3 question after the stopped 5059 campaign."
---

# ADR — Accept the G3 successor empirical protocol

## Status

Accepted under AK decision (DSPx-side, architecture, repo-scoped to
`softwareco/owned/dspx`), **conditioned on the engineering-core binding
AK 5096** (candidate-5 = `main@cde7f142ebd07527d865eded4bbbadf9fda9409f`,
wheel sha `921bff5ef60ee8dea112cdaf8825e809bb484f1e518a06080e853c7e52288ab0`,
commit `145c889`). Replaces the superseded-intent decision 137 (incident
recorded as AK evidence 7840).

## Decision

Accept `docs/v1-proof/g3-successor-campaign-design.md` (REV 3) as the
successor empirical protocol for the reopened G3 question, succeeding the
operator-stopped, ceiling-limited 5059 campaign (127/168 pairs, both arms
≥ 0.9167 — instrument-limited null).

Binding properties:

- **Corpus:** 36 DISTINCT derived instances (12 class-level convention-space
  templates × 3 distinct instances; byte-identical reuse of observed v3/v3b
  instances prohibited). Difficulty-only promotion; static-arm target
  [0.4, 0.6]; saturation guard at 0.8; one evidence-failure hard cell by
  rule.
- **Design:** 72 pairs (36 instances × 2 families), ≤144 executions; arms
  differ only by guidance presence; advisor gpt-5.6-terra uniform for A/C
  evidence arms.
- **Primary endpoint:** pooled pair-level exact McNemar (two-sided) over
  receipt-backed pairs — honestly labeled; pair independence is NOT claimed.
- **Co-primary template guard (floored):** ≥ 4 discordant templates AND
  strict majority evidence-dominant; d < 4 ⇒ cannot PASS (INCONCLUSIVE,
  insufficient template dispersion). Mirrored FAIL guard.
- **Required sensitivity (never sufficient):** template-cluster design-effect
  report; pinned at freeze.
- **Power:** disclosed by pre-freeze Monte Carlo simulation of the JOINT
  criterion under clustered DGMs including adversarial concentration
  (extended to exactly-at-floor d=4 scenarios per review observe N2);
  withdrawal of any closed-form ≥0.80 claim is intentional.
- **Interim:** one look at N=48 (balanced cohort); efficacy p<0.001;
  futility asymmetry ≤0.5 ⇒ INCONCLUSIVE (futility).
- **Extension:** one-shot 72→96 pairs on low conditional power only,
  operator budget re-authorization required in AK first.
- **No substitution channel** of any kind; <70% receipt-backed completion ⇒
  INCONCLUSIVE (infrastructure). All outcomes INCONCLUSIVE by default —
  never PASS-by-default.
- **Preconditions:** AK 5092 runner hardening BEFORE execution; wheel sha
  verified at freeze; single-variable (candidate-5 only).

## Sentences that travel verbatim

1. **Construct boundary:** the instrument measures *convention-conformance
   lift* — a necessary, not sufficient, proxy for engineering value.
2. **Confound:** v3→v3b differed by fix + wheel identity; the glm recovery
   read is not single-variable causal evidence for the AK-5082 fix.
3. **Enrichment disclosure:** the template family was selected because
   diagnostics showed it separates arms; difficulty-based promotion and
   distinct-instance derivation mitigate instance-level circularity, and the
   template-level enrichment is disclosed as part of what this decision
   accepts.

## Consequences

- G3's successor instrument is frozeable and executable under AK 5095 after
  AK 5092 lands; gate consumption remains a future owner fan-in act — this
  decision grants no gate verdict.
- Frozen G0–G4 records stay candidate-4 (per AK 5096 scope discipline).
- Review observes N1–N6 are recorded pre-freeze conditions to be discharged
  in the freeze manifest (wording clause, simulation scenario extension, DE
  computation pinning, manifest budget value, CP estimator note, freeze-time
  re-check).

## Review record

Three-pass independent adversarial review with computational verification:
`docs/v1-proof/g3-successor-review-memo.md` — REV 1 `revise_rfc` (blocker F1:
clustering), REV 2 delta `revise_rfc` (must-fixes D1: mislabeled primary,
D2: unfloored guard), REV 3 delta **`ready_for_adr`** (observes N1–N6).
