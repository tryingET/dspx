---
summary: "AK-4643/AK-4653 learning: preserve unresolved effects as terminal empirical uncertainty and verify artifact integrity separately from quality."
read_when:
  - "Designing or reviewing a one-shot live semantic evaluation."
  - "Interpreting effect-indeterminate empirical evidence or provider-free verification."
type: "learning"
execution_task_id: 4643
verifier_repair_task_id: 4653
---

# Oracle semantic-analysis v10 one-shot evaluation

## Context

V9 froze complete provider-visible meanings for all 26 semantic-analysis codes but authorized zero evaluation processes. AK-4643 materialized those reviewed semantics into a four-case v10 contract with one task-fixed corpus process, no health probe, fallback, DSPx retry, selective rerun, fixture process, or test-double process. Exact candidate review and a separate AK-evidence-backed live gate were required before the provider boundary.

## Observed outcome

The single authorized process used the requested/configured `dspy-lm-auth` route for `codex/gpt-5.6-sol` with reasoning effort `max`. The first `authority-boundary` case durably recorded `effect_possible` before the generate boundary. The process retained neither an attributable response nor a closed no-effect observation, so the case terminalized as `effect_outcome_unresolved` and the corpus as `effect_indeterminate`.

No later case or retry ran. The retained result therefore proves neither a semantic pass nor an ordinary scored failure. It preserves uncertainty about a possible external effect under the declared precedence `effect_indeterminate > error > failed > passed`.

## Discovery

1. **A one-process budget is not a transport-cardinality claim.** DSPx proved one corpus process and one reached generate boundary. It did not prove provider transport-call cardinality, provider-internal retry absence, or a response model identity.
2. **Normal case errors and setup/interruption projections are different fields.** A normal retained `case_error`, including `effect_outcome_unresolved` or `typed_response_error`, does not populate `result.preflight_error`. Outer processing, preflight, attempt, and interrupted classifications do. The first verifier collapsed those meanings and rejected truthful retained evidence.
3. **Verifier repair must not repair the experiment.** AK-4653 changed only provider-free verification and focused tests. It did not rewrite receipts, events, ledger, result, contract, source/request identities, route/dependency evidence, or empirical disposition.
4. **Rowless errors still require causal-state binding.** A rowless effect-unresolved classification is lawful only while an effect remains open; rowless case-incomplete or outer-processing classifications require no open effect. Adversarial review found and the repair rejected cross-state relabels.
5. **Artifact integrity and empirical quality are orthogonal.** The final verification is `artifact_integrity_review=accepted` while `empirical_gate=effect_indeterminate`. Both statements are necessary; neither may silently replace the other.

## Evidence

- Execution candidate/tree: `486352e540d6f4c425419ce6145ca598b826b63e` / `668ddde4193502a936c346896374920b13ecbcdc`.
- V10 contract SHA-256: `fb90f0c266e984489110fc3ae945c3bd37bf71b6ec8f725f56d6167241ab4128`.
- Terminal result SHA-256: `e8f4de5a8d5ddc25281d294dcad60f5201f21cf94d597c04004edd66014ab49d`.
- Verifier repair/tree: `d2a5af2f05ea12833fd6ddc402478e80688c67d6` / `a722eac443ccc46ec7261b1a800582bb669bf861`.
- Independent verification SHA-256: `bd09f20b1379fd5e54ae66d0b0e335e42fc47f4494dc64d5cbb27ebb8a7da93e`.
- Exact repair review: `dispatch-1785835911739` returned `ACCEPT_EXACT_VERIFIER_REPAIR`.
- Adversarial repair test: `dispatch-1785835911740` returned `PASS` after all four prior rowless-classification forgeries rejected.
- AK evidence: `6531` records the terminal packet; `6532` records deterministic verification.

## Application

For later one-shot empirical work:

- consume the attempt before fallible post-entry work;
- mark possible effects durably before invocation;
- preserve unresolved effects as terminal indeterminate evidence;
- never use recovery or verification as same-attempt retry authority;
- bind rowless classifications to observed effect state;
- keep execution-candidate review separate from live authority and terminal artifact review;
- report integrity disposition and empirical disposition side by side;
- use a fresh successor task/version for any new provider attempt.

This learning does not establish ROCS conformance, broad semantic correctness, statistical representativeness, executed provider/model identity, shared Oracle publication, release readiness, or activation authority. Decisions 105, 106, and 107 remain unchanged.

## TIP Candidate

Yes. Candidate principle: **when a bounded external effect cannot be closed as observed response or proven no-effect, preserve terminal uncertainty; later verification may accept custody and consistency but must not upgrade the empirical result or authorize retry.**
