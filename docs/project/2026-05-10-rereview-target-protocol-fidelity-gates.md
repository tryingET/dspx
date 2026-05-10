---
summary: "Re-review memo for the revised DSPx target-protocol fidelity gates RFC; outcome ready_for_adr."
read_when:
  - "You are drafting or checking the ADR for DSPx target-protocol fidelity gates."
  - "You need the controlling latest review outcome for RFC-DSPX-GEN-20260509-target-protocol-fidelity-gates."
type: "review"
review_outcome: "ready_for_adr"
reviewed_artifact: "docs/rfc/RFC-DSPX-GEN-20260509-target-protocol-fidelity-gates.md"
prior_review_artifact: "docs/project/2026-05-10-review-target-protocol-fidelity-gates-multi.md"
---

# Re-review — DSPx target-protocol fidelity gates for `*-gen`

## System4D summary

- boundary: revised `docs/rfc/RFC-DSPX-GEN-20260509-target-protocol-fidelity-gates.md`
- mode: lite
- review basis:
  - prior outcome: `revise_rfc`
  - legal question: whether prior blockers are resolved enough to move to ADR
- primary judgment: the revised RFC now provides a sufficient ADR basis for the shared invariant plus `program-gen` first implementation path.

## Review chain status

- review kind: re-review after `revise_rfc`
- reviewed artifact: `docs/rfc/RFC-DSPX-GEN-20260509-target-protocol-fidelity-gates.md`
- prior review artifact: `docs/project/2026-05-10-review-target-protocol-fidelity-gates-multi.md`
- supporting docs inspected:
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
  - revised RFC
  - prior review attempt with `revise_rfc`
  - this re-review attempt
- missing or unclear lifecycle artifacts:
  - ADR
  - post-ADR implementation/validation/rollout/rollback artifact set
- ADR legal now?: yes, if this review is recorded as the controlling latest review attempt.
- reason: prior material blockers are resolved at decision-basis depth.

## Overall verdict

- ready for ADR
- one short reason: the revision resolves the prior material blockers at decision-basis depth; remaining issues are implementation/ADR precision items, not RFC blockers.

## Lens 1 — Core architecture / semantic contract

- strengths
  - The RFC now explicitly says the deterministic verifier does not prove semantic truth.
  - It separates declared contract sufficiency from later semantic fitness through execution, traceability, adjudication, dogfood, and domain outcomes.
  - Authorship/custody is materially improved:
    - hand-authored/operator-domain confirmed contracts are strongest;
    - generated-from-docs contracts are draft until confirmation;
    - objective-only inference blocks.
  - Shared core vs target profile is now explicit enough to avoid Obsidian/PDF overfitting.
  - ADR scope is narrowed correctly:
    - commit now to shared invariant + `program-gen` first;
    - do not auto-enforce every `*-gen` surface yet;
    - require per-surface gates for later `signature-gen` / `module-gen`.
- risks
  - The contract still cannot guarantee that the operator/domain confirmation itself is high quality.
  - The Obsidian/PDF example remains the dominant concrete example.
  - The exact schema-level shape for target profile extensions is still future implementation work.
- must-fix issues
  - none before ADR
- evidence quality
  - sufficient for ADR basis around shared invariant + `program-gen` first.

## Lens 2 — Runtime authority / platform boundary

- strengths
  - Non-authority posture remains consistent.
  - `fitness_passed` is now command-safe: eligible for downstream evidence review only, not approval/activation.
  - Command/state transition table materially improves operational semantics.
  - Adapter materialization now requires `fitness_passed` or failure-only/withheld packet.
  - Oracle/GEPA handling now has explicit label states and prevents raw invalid dogfood from becoming positive training data.
- risks
  - The RFC names operation-level transitions, not final exact CLI names for every adapter/materialization refusal path.
  - Existing `program-loop` composition will need careful implementation so it does not preserve target-bound legacy behavior accidentally.
  - Oracle publication redaction/custody fields are directionally clear but still need schema tests.
- must-fix issues
  - none before ADR
- evidence quality
  - sufficient for ADR basis; detailed command wiring belongs in post-ADR implementation planning.

## Lens 3 — Verification / rollout / rollback

- strengths
  - Adversarial suite acceptance is now stronger than field presence:
    - fixtures or references;
    - allowed artifact families;
    - forbidden outputs/effects;
    - provenance/language assertions;
    - executable or mechanically checkable command;
    - expected failure label;
    - hash/provenance binding.
  - Tutorial/local escape hatch is now bounded and cannot be used with owner refs, adapter materialization, authority refs, canonical/proposal/review families, publication, or promotion/export/activation evidence.
  - Partially migrated candidates read back as `target_fidelity_unknown`.
  - Rollout to non-`program-gen` surfaces is gated on later per-surface acceptance notes.
- risks
  - Tutorial/local minimum valid profile remains an open question.
  - The RFC still leaves some post-ADR validation/rollout details to implementation plans.
  - Broad repo-wide invariant needs careful communication so it is not mistaken for immediate broad enforcement.
- must-fix issues
  - none before ADR
- evidence quality
  - sufficient for ADR basis; exact schema/CLI/test details belong to implementation planning.

## Cross-cutting contradictions

No remaining contradiction blocks ADR.

The previous contradiction between deterministic verification and semantic target understanding is now explicitly handled: deterministic gate proves declared sufficiency, not truth.

The previous tension between repo-wide policy and `program-gen` evidence is now handled by scoping: shared invariant now, `program-gen` first implementation, later per-surface gates.

The previous tutorial/local bypass risk is now materially constrained.

## Must-fix before ADR

None.

## ADR should explicitly preserve these constraints

1. ADR scope is `program-gen` first plus reusable shared invariant, not automatic enforcement across all `*-gen`.
2. Deterministic preflight proves contract/suite sufficiency, not semantic truth.
3. Tutorial/local mode is not permitted for owner-bound, adapter-bound, authority-adjacent, publication, or promotion/export/activation flows.
4. `fitness_passed` must not be rendered as approved, promoted, activated, or ready for domain decision.
5. GEPA positive examples require later accepted outcome labels; invalid dogfood defaults to pending/quarantined or curated negative only.

## Workflow result

- review_outcome: `ready_for_adr`
- next legal move: `open_adr_pack`
- controlling rationale:
  - Prior `revise_rfc` blockers were addressed at RFC-decision depth.
  - Remaining issues are appropriate ADR constraints and implementation validation obligations.
  - The revised RFC is now a durable enough decision basis for the lifecycle's ADR stage.
- missing artifacts or gates:
  - ADR
  - post-ADR implementation/validation/rollout/rollback artifact set
- notes on legality vs quality:
  - ADR is legal after this re-review if recorded as the latest controlling review attempt.
  - Implementation is still not authorized until ADR and post-ADR execution planning are complete.

## Final recommendation

- approve RFC as ADR basis
- reasons:
  1. Prior `revise_rfc` blockers were addressed.
  2. The target-protocol fidelity problem is real and well evidenced.
  3. The revised RFC now scopes the durable decision to shared invariant + `program-gen` first.
  4. The deterministic verifier's guarantees and non-guarantees are explicit.
  5. Remaining work is implementation planning, not RFC redesign.
