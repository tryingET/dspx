---
summary: "Tier 1 pre-ADR review memo for the DSPx target-protocol fidelity gates RFC; outcome revise_rfc before ADR."
read_when:
  - "You are revising or re-reviewing RFC-DSPX-GEN-20260509-target-protocol-fidelity-gates."
  - "You need the first workflow-aware review findings for DSPx *-gen target-protocol fidelity gates."
type: "review"
review_outcome: "revise_rfc"
reviewed_artifact: "docs/rfc/RFC-DSPX-GEN-20260509-target-protocol-fidelity-gates.md"
---

# Review — DSPx target-protocol fidelity gates for `*-gen`

## System4D summary

- boundary: DSPx repo-wide `*-gen` target-protocol fidelity gates, starting with `program-gen`, before ADR commitment.
- primary driver: prevent runnable/schema-valid generated candidates from becoming semantically false success artifacts.
- main risks:
  - target contracts become checklist theater rather than semantic protocol constraints;
  - Obsidian/PDF failure overfits the shared generation contract;
  - risk-tier migration weakens fail-closed behavior for authority-adjacent flows;
  - ADR proceeds before contract authorship, validation semantics, and adapter gating are precise enough.

## Review chain status

- review kind: Tier 1 pre-ADR review attempt
- reviewed artifact: `docs/rfc/RFC-DSPX-GEN-20260509-target-protocol-fidelity-gates.md` — "RFC: DSPx target-protocol fidelity gates for `*-gen`"
- supporting docs read:
  - `docs/project/2026-05-09-problem-target-protocol-fidelity-gates.md`
  - `docs/project/2026-05-09-evidence-target-protocol-fidelity-gates.md`
  - `docs/project/2026-05-09-plan-target-protocol-fidelity-gates.md`
  - `docs/rfc/RFC-DSPX-ADJ-20260509-meta-adjudication-orchestration.md`
  - `docs/project/program-gen-walkthrough.md`
  - `docs/project/pdf-transition-program-gen.md`
  - `/home/tryinget/ai-society/holdingco/governance-kernel/docs/dev/decision-lifecycle.md`
- required lifecycle artifacts present:
  - problem brief
  - evidence note
  - RFC
  - implementation/rollout plan draft
  - this review attempt
- missing or unclear lifecycle artifacts:
  - revised RFC addressing review blockers
  - controlling review closure with `ready_for_adr`
  - ADR
  - post-ADR validation / rollout / rollback artifact, if the current plan is not meant to serve that later role
- ADR legal now?: no
- reason: the RFC is directionally strong but still leaves material contract-authority and testability questions open.

## Overall verdict

- revise before ADR
- one short reason: the proposal identifies the right failure mode, but the target-contract gate is not yet specific enough to prevent becoming self-attested process theater.

## Lens 1 — Core architecture / semantic contract

- strengths
  - Correctly names the key distinction: runnable candidate success is not target-protocol fidelity.
  - Correctly moves target protocol, forbidden shortcuts, adversarial cases, and traceability left of promotion evidence.
  - Preserves the existing two-layer generated-program adjudication model instead of replacing it.
  - Uses sidecar artifacts and explicit state names, which fits current DSPx artifact patterns.
- risks
  - `generation_target_contract.json` is underspecified as an authority object: it is unclear who authors it, who may synthesize it, and what makes it trustworthy before generation.
  - Deterministic preflight appears to validate completeness and identity binding, but not whether the contract actually captures the target protocol.
  - The Obsidian/PDF example is high-signal but could dominate the generic contract shape unless the shared core vs target profile boundary is made explicit.
  - "Target-bound" is central, but the RFC does not fully define how intent/prose/docs are classified into target-bound vs tutorial/local without operator ambiguity.
- must-fix issues
  - Define target-contract authorship/custody: hand-authored, generated from intent, generated from docs, or hybrid; include when human/operator confirmation is required.
  - Separate generic `gen-target-contract-v1` core fields from target-specific profile extensions such as Obsidian/PDF aliases.
  - Specify what the deterministic verifier can and cannot prove; avoid implying it proves semantic truth beyond declared contract sufficiency.
  - Define exact risk-tier classification inputs and fail-closed behavior for ambiguous cases.
- evidence quality
  - Strong evidence for the failure mode from Obsidian/PDF dogfood and current `program-gen` limitations.
  - Insufficient evidence that the proposed contract shape is minimal and reusable across `signature-gen`, `module-gen`, and future `*-gen`.

## Lens 2 — Runtime authority / platform boundary

- strengths
  - Non-authority posture is consistently stated: no production activation, no canonical Obsidian mutation, no AK/governance mutation, Oracle/Postgres as empirical memory only.
  - The RFC correctly distinguishes DSPx/meta pre-generation verification from generated-program adjudicators that do not exist until after candidate creation.
  - Adapter materialization is correctly gated on `fitness_passed` or failure-only/withheld packets.
  - Existing meta-adjudication RFC is integrated rather than duplicated.
- risks
  - `fitness_passed` is carefully described as non-authoritative, but its operational meaning could still drift into "promotion-ready" unless downstream commands have strict wording and state transitions.
  - Adapter behavior is asserted but not fully specified: what exact command refuses normal review queue materialization, and what exact sidecar proves refusal?
  - Oracle/GEPA integration is safe in principle, but curation labels and negative-example semantics are not tied to concrete schema obligations in this RFC.
  - Existing `program-loop` and tutorial flows may preserve legacy behavior too broadly if "tutorial/local" is not sharply bounded.
- must-fix issues
  - Define the authoritative command/state transition that blocks target-bound candidate creation and adapter materialization.
  - Add explicit state-transition rules: which states permit generation, adjudication, adapter materialization, Oracle publication preflight, and GEPA curation.
  - Make `fitness_passed` wording command-safe: eligible for downstream evidence review only, never promotion/activation approval.
  - Specify how invalid dogfood is labeled so it cannot become a positive GEPA/training example by default.
- evidence quality
  - Strong current-state evidence from `program-gen` walkthrough and meta-adjudication sidecars.
  - Insufficient command-level evidence for how the new gate composes with existing `program-loop`, `program-run`, adapter preflights, and promotion commands.

## Lens 3 — Verification / rollout / rollback

- strengths
  - Rollout is phased and starts with schemas/pure validators before provider calls or shared mutations.
  - Negative tests are named for missing owner refs, forbidden shortcuts, language policy, identity binding, and runnable-but-failed target fitness.
  - Rollback strategy preserves existing sidecars and relaxes by risk tier instead of removing fail-closed behavior globally.
  - Historical bad Obsidian/PDF behavior is correctly treated as failure evidence.
- risks
  - Validation still leans heavily on field presence; it does not yet define adversarial fixture quality thresholds.
  - Rollback says existing behavior can remain behind legacy/tutorial profile, but does not define sunset criteria or prevent target-bound users from escaping into tutorial mode.
  - The RFC has an implementation plan before ADR; useful as planning evidence, but it must not become implementation authorization before review closure and ADR.
  - Generalization to other `*-gen` surfaces is mostly conceptual; the first ADR may be too broad if it claims repo-wide adoption without concrete per-surface acceptance criteria.
- must-fix issues
  - Add executable acceptance criteria for adversarial fitness suites, not only required JSON fields.
  - Define tutorial/local escape-hatch constraints and warnings so target-bound generation cannot bypass the gate accidentally.
  - Scope the ADR basis explicitly: either approve `program-gen` first with a reusable contract direction, or approve all `*-gen` surfaces with clear per-surface rollout gates.
  - Add rollback/readback expectations for partially migrated candidate assemblies and legacy sidecars.
- evidence quality
  - Good validation direction and plausible tests.
  - Insufficient evidence that the repo-wide migration path is safe beyond `program-gen`.

## Cross-cutting contradictions

- The RFC says the pre-generation verifier is deterministic, but the core failure is semantic target understanding; deterministic completeness checks alone cannot prove that understanding.
- The RFC wants a shared `*-gen` contract, but most concrete evidence and schema examples come from Obsidian/PDF.
- The RFC says tutorial/local profiles preserve usability, but also says ambiguous classification must block or choose the stricter tier; the escape hatch needs sharper boundaries.
- The RFC says downstream adjudication remains valid, but target-fitness states could become de facto promotion states unless command semantics are locked down.

## Must-fix before ADR

1. Define target-contract authorship, custody, and trust model.
2. Separate shared contract core from target-specific profile extensions.
3. Specify deterministic verifier guarantees and non-guarantees.
4. Define exact risk-tier classification and ambiguous-case behavior.
5. Add command/state transition rules for generation, adapter materialization, adjudication, Oracle publication, and GEPA curation.
6. Add executable adversarial-suite acceptance criteria beyond field presence.
7. Clarify ADR scope: `program-gen` first with reusable pattern, or repo-wide `*-gen` commitment with per-surface gates.
8. Define tutorial/local escape-hatch constraints and migration sunset/readback behavior.

## Nice-to-have improvements

- Include one minimal valid `gen-target-contract-v1` tutorial/local example.
- Include one invalid target-bound example showing blocked generation.
- Include a state machine table from `contract_missing` through `withheld_for_target_protocol_failure`.
- Add a short "what this does not prove" section for the deterministic gate.
- Add schema snippets for GEPA label states and negative-example curation.

## Questions reviewers should force the authors to answer

1. Who is allowed to author or synthesize `generation_target_contract.json`, and what makes it trusted?
2. What exact check prevents a generated or shallow contract from merely restating the intent?
3. What command refuses to create a target-bound candidate, and what sidecar records the refusal?
4. What command refuses adapter materialization for `fitness_failed` candidates?
5. Can a user opt into tutorial/local mode while providing owner refs or adapter outputs?
6. Is the first ADR approving only `program-gen`, or the full `*-gen` policy?
7. What minimum adversarial cases prove the Obsidian/PDF failure is caught before regeneration?
8. How are failed dogfood traces labeled so GEPA cannot treat them as positive examples?

## Workflow result

- review_outcome: `revise_rfc`
- next legal move: `revise_rfc`
- controlling rationale:
  - The RFC is substantively strong on problem framing and broad direction.
  - ADR progression is blocked by unresolved contract-authority, verifier-semantics, and risk-tier migration details.
  - The current artifact is good evidence for a revised RFC, not yet a durable decision basis.
  - Implementation should not proceed beyond docs/review alignment until a revised RFC passes review.
- missing artifacts or gates:
  - revised RFC
  - new review attempt against the revised RFC
  - `ready_for_adr` controlling closure
  - ADR after review closure
  - post-ADR implementation/validation/rollout/rollback artifact set
- notes on legality vs quality:
  - Substantive quality is high: the failure is real and the proposed direction is likely correct.
  - ADR legality is still no: unresolved review blockers mean the latest review outcome is `revise_rfc`.

## Final recommendation

- request another RFC revision round
- reasons:
  1. The target-protocol fidelity problem is real and well evidenced.
  2. Option C is likely the right direction.
  3. The contract gate needs a clearer authority and trust model.
  4. The deterministic verifier and risk-tier escape hatches need sharper command-level semantics.
  5. A revised RFC should be able to reach ADR readiness if it resolves the must-fix items above.
