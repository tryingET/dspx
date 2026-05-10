---
summary: "Adopt target-protocol fidelity gates for DSPx generation: shared invariant plus program-gen first implementation, without automatic enforcement across all *-gen surfaces."
read_when:
  - "You are changing program-gen, program-loop, program-run, generated-program adapters, or target-fidelity sidecars."
  - "You need the accepted boundary between runnable generated candidates and target-protocol fitness."
  - "You are extending target-protocol fidelity gates to signature-gen, module-gen, or future *-gen surfaces."
system4d:
  container:
    boundary: "DSPx target-protocol fidelity gates for generation, starting with program-gen."
    edges:
      - "docs/rfc/RFC-DSPX-GEN-20260509-target-protocol-fidelity-gates.md"
      - "docs/project/2026-05-10-review-target-protocol-fidelity-gates-multi.md"
      - "docs/project/2026-05-10-rereview-target-protocol-fidelity-gates.md"
      - "docs/rfc/RFC-DSPX-ADJ-20260509-meta-adjudication-orchestration.md"
      - "docs/project/pdf-transition-program-gen.md"
  compass:
    driver: "Prevent runnable/schema-valid generated candidates from being mistaken for truthful target-protocol implementations."
    outcome: "Target-bound program generation fails closed unless target contract and adversarial fitness evidence constrain generation and later promotion evidence."
  engine:
    invariants:
      - "A runnable generated candidate can still be invalid."
      - "Deterministic preflight proves declared contract/suite sufficiency, not semantic truth."
      - "fitness_passed means eligible for downstream evidence review only, not approval, promotion, activation, or domain acceptance."
      - "Tutorial/local mode cannot bypass target-bound, adapter-bound, authority-adjacent, publication, or promotion/export/activation flows."
      - "Oracle/Postgres and GEPA consume curated empirical evidence only; they do not become authority."
  fog:
    risks:
      - "Contracts become checklist theater."
      - "Obsidian/PDF overfits the shared contract."
      - "Tutorial/local escape hatches weaken target-bound enforcement."
      - "Target-fitness language drifts into promotion or activation language."
---

# ADR 20260510 — Target-Protocol Fidelity Gates for DSPx Generation

## Status

- accepted
- date: 2026-05-10
- owner: DSPx core
- reviewers: DSPx workflow-aware RFC reviewers
- AK decision: `#34 Adopt target-protocol fidelity gates for DSPx generation`
- related_docs:
  - `docs/rfc/RFC-DSPX-GEN-20260509-target-protocol-fidelity-gates.md`
  - `docs/project/2026-05-09-problem-target-protocol-fidelity-gates.md`
  - `docs/project/2026-05-09-evidence-target-protocol-fidelity-gates.md`
  - `docs/project/2026-05-09-plan-target-protocol-fidelity-gates.md`
  - `docs/project/2026-05-10-review-target-protocol-fidelity-gates-multi.md`
  - `docs/project/2026-05-10-rereview-target-protocol-fidelity-gates.md`
  - `docs/rfc/RFC-DSPX-ADJ-20260509-meta-adjudication-orchestration.md`
  - `docs/project/program-gen-walkthrough.md`
  - `docs/project/pdf-transition-program-gen.md`
  - `docs/project/generated-program-activation-boundary.md`

## Executive summary

DSPx will adopt target-protocol fidelity gates for generation.

The accepted decision is deliberately scoped:

```text
accepted now: shared target-fidelity invariant + program-gen first implementation path
not accepted now: automatic hard enforcement across every existing *-gen surface
future gates: per-surface acceptance before signature-gen/module-gen/future *-gen enforcement
```

Target-bound `program-gen` must move from candidate-first generation to evaluator-first generation:

```text
intent / prose / docs
-> target protocol contract
-> adversarial fitness suite
-> deterministic generation gate preflight
-> generated candidate
-> traceability matrix
-> fitness results
-> jury / adjudication
-> dogfood
-> promotion evidence or withhold evidence
```

A generated candidate that runs, has coherent files, and passes schema/replay checks can still be invalid if it skips or falsifies the target protocol.

## Context

DSPx currently has mature local-first generated-program infrastructure:

- `program-gen` materializes program-shaped candidate assemblies;
- `program-loop` can compose generation, replay check, candidate-local Oracle indexing/reporting, and candidate-state summary;
- `program-run` can run an existing generated candidate on explicit runtime inputs;
- meta-adjudication sidecars can inspect generated candidates after they exist;
- Oracle/Postgres publication preflights can package empirical behavior evidence without granting authority.

The Obsidian/PDF transition dogfood exposed the remaining gap. The generated candidate could run on real PDF-derived source-package input, and DSPx could write coherent runtime/Oracle sidecars. But the candidate produced semantically wrong review artifacts: plausible Wiki create proposals and draft-like text from source material that should have moved through source package, section units, distillation frames, evidence cards, merge-before-create, and review gates before any canonical note action.

The infrastructure worked. The target protocol was not sufficiently enforced before generation.

## Problem statement

DSPx generation must not merely prove:

- candidate generated;
- files exist;
- schemas are valid;
- replay works;
- local examples run;
- downstream juries/adjudicators can inspect sidecars.

For target-bound flows, DSPx must also prove:

- what target protocol is being implemented;
- which owner docs and artifact families define the protocol;
- which workflow stages are required;
- which shortcuts are forbidden;
- which adversarial cases expose plausible nonsense;
- how generated surfaces trace back to target requirements;
- whether the candidate passed or failed target-fidelity checks.

Without this, generated programs can be formally valid but semantically false.

## Decision drivers

- Prevent runnable generated candidates from being mistaken for useful target implementations.
- Preserve authority boundaries: DSPx evidence is not activation authority.
- Keep the existing two-layer adjudication architecture:
  1. DSPx/meta jury + adjudicator verify the generated program's judging setup.
  2. Generated-program jury + adjudicator judge candidate evidence within delegated scope.
- Move target-protocol discovery and adversarial fitness design before generation.
- Keep tutorial/local examples usable without creating a bypass for target-bound flows.
- Retain invalid dogfood as failure evidence without training GEPA on unlabeled bad behavior.
- Start with `program-gen`, where evidence is strongest, and widen by per-surface gates.

## Decision

Adopt Option C from the revised RFC: evaluator-first target-protocol gates before and after generation.

The first implementation path is `program-gen`.

### Accepted target-bound generation model

Target-bound `program-gen` must require these pre-candidate sidecars or inline equivalent verifier inputs:

```text
generation_target_contract.json       # gen-target-contract-v1
generation_fitness_suite.json         # gen-fitness-suite-v1
generation_gate_preflight.json        # gen-generation-gate-preflight-v1
```

After generation, target-bound candidates must produce:

```text
generation_traceability.json          # gen-traceability-v1
generation_fitness_results.json       # gen-fitness-results-v1
```

### Deterministic verifier boundary

The deterministic DSPx/meta preflight verifies declared sufficiency. It checks target-contract completeness, fitness-suite completeness, identity/hash binding, non-authority flags, and risk-tier classification.

It does **not** prove semantic truth. Semantic target fitness is tested through fitness execution, traceability, adjudication, dogfood, and later domain outcomes.

### Contract authorship and trust

Target contracts may be:

- hand-authored or domain/operator-confirmed;
- generated from structured intent fields when all target-owner, protocol, forbidden-shortcut, and risk-tier fields are explicit;
- generated from docs/prose only as draft until confirmation;
- never inferred from objective alone for target-bound generation.

Objective-only inference must block target-bound generation with `insufficient_target_contract`.

### Shared core plus target profile

`gen-target-contract-v1` has a shared core plus optional target profile extensions.

The shared core carries identity, target owner refs, contract source, confirmation status, risk tier, required stages, artifact families, forbidden shortcuts, adversarial cases, non-authority flags, and effect flags.

Target profiles may add aliases, owner-specific stage names, domain vocabulary, and adapter-specific refusal rules. They must not redefine shared core semantics.

### Risk tiers

DSPx will classify generation risk before applying gates:

| Tier | Trigger | Gate |
| --- | --- | --- |
| tutorial/local | no external owner refs, no adapter materialization, no authority-adjacent outputs | minimal embedded profile allowed |
| protocol-bound | target docs/owner refs, external workflow name, or required artifact-family protocol | target contract + fitness suite required |
| authority-adjacent | outputs feed promotion/export/activation evidence or domain review adapters | full contract + fitness + traceability + adjudication required |
| external mutation capable | any future generator can mutate owner surfaces | explicit owner/governance activation gate required before mutation |

Ambiguous classification must choose the stricter tier or block.

Tutorial/local mode is not allowed when owner refs, adapter materialization, authority refs, canonical/proposal/review artifact families, shared Oracle publication, or promotion/export/activation evidence are present.

### Command-safe states

`fitness_passed` means only:

```text
eligible_for_downstream_evidence_review
```

It must not be rendered as:

```text
approved
promoted
activated
ready_for_domain_decision
canonical_acceptance
```

Adapter materialization for target-bound flows requires `fitness_passed` or must write a failure-only/withheld packet. Failed target-fidelity outputs must not enter normal review queues.

### GEPA and Oracle labels

Oracle/Postgres publication and GEPA curation are empirical-memory surfaces only.

GEPA examples from target-fidelity traces must use explicit label states:

```text
curated_pending_outcome_label
curated_negative_failure_example
curated_positive_after_domain_outcome
quarantined_invalid_or_untrusted
```

Only accepted outcome labels or explicitly reviewed negative examples may be used for training/validation.

## Alternatives considered

### Option A — Keep generation as-is and improve review UI/adapters

Rejected. It would make bad outputs easier to inspect without preventing false generated programs.

### Option B — Rely on post-hoc meta-adjudication only

Rejected as insufficient. Existing meta-adjudication remains valid, but late detection wastes generation/dogfood cycles and can still surface misleading artifacts before the target protocol is enforced.

### Option C — Evaluator-first target-protocol gates before and after generation

Accepted. It blocks false generation earlier, preserves downstream adjudication, turns failures into labeled evidence, and allows careful per-surface rollout.

## Consequences

Positive:

- `program-gen` becomes target-protocol-aware rather than merely candidate-materialization-aware.
- False successes can be blocked before candidate creation or withheld before adapter materialization.
- Historical bad Obsidian/PDF behavior becomes a reusable failure fixture.
- Existing two-layer jury/adjudicator architecture gets stronger inputs.
- Oracle/Postgres and GEPA receive better-labeled empirical traces.

Costs / tradeoffs:

- Target-bound generation requires more explicit pre-generation artifacts.
- Schema, CLI, and test surfaces must be added before implementation can proceed.
- Tutorial/local mode needs careful wording so it remains useful but cannot bypass target-bound gates.
- Broad `*-gen` enforcement will require per-surface rollout work after `program-gen` proves the contract.

Risks:

- Contracts could become checklist theater if adversarial suites are weak.
- Domain confirmation could be low-quality unless review discipline remains strong.
- Users could misread target-fitness pass as activation unless CLI/UI wording stays strict.
- Legacy `program-loop` behavior could accidentally preserve target-bound bypasses if not migrated carefully.

## Follow-through obligations

Before implementation:

1. keep the accepted ADR scope narrow: shared invariant + `program-gen` first;
2. create an implementation task for shared sidecar schema/validator helpers;
3. preserve the deterministic verifier's non-guarantee: declared sufficiency, not semantic truth;
4. keep tutorial/local mode disallowed for owner-bound, adapter-bound, authority-adjacent, publication, or promotion/export/activation flows.

For Phase 1 implementation:

1. implement schemas/helpers for:
   - `gen-target-contract-v1`;
   - `gen-fitness-suite-v1`;
   - `gen-generation-gate-preflight-v1`;
   - `gen-traceability-v1`;
   - `gen-fitness-results-v1`;
2. add fail-closed validators for missing owner refs, forbidden shortcuts, source/provenance/language policy, identity/hash binding, and missing adversarial cases;
3. add tutorial/local profile validation and explicit no-target-fidelity-claim output;
4. add readback state for partially migrated candidates: `target_fidelity_unknown`.

For Phase 2+ implementation:

1. add `program-gen` target-contract, fitness-suite, and generation-gate preflight commands or equivalent inline verifier path;
2. make target-bound `program-gen` fail closed before candidate creation when the gate fails;
3. write traceability and fitness results after generation;
4. make adapter materialization reject failed/missing target-fitness results unless writing failure-only evidence;
5. integrate generation contract and fitness sidecars into meta-adjudication;
6. ensure Oracle/Postgres publication and GEPA curation preserve non-authority labels and redacted custody.

Before widening beyond `program-gen`:

1. write a per-surface acceptance note for `signature-gen`, `module-gen`, or any future `*-gen`;
2. define that surface's minimal contract, tutorial/local profile, target-bound triggers, and failure fixtures;
3. prove focused validation and dogfood before enforcement.

## Validation expectations

For this ADR recording:

- docs strict validation;
- task-scope validation;
- `git diff --check`;
- `just verify-fast`.

For implementation tasks:

- missing owner ref blocks target-bound generation;
- missing forbidden shortcut list blocks target-bound generation;
- missing source/provenance/language policy blocks target-bound generation;
- missing identity/hash binding blocks target-bound generation;
- generated-from-docs contract without operator/domain confirmation blocks target-bound generation;
- tutorial/local mode is rejected when owner refs, adapter materialization, authority refs, or publication requests are present;
- adversarial suite without executable/checkable cases is insufficient;
- runnable/schema-valid candidate can still fail target fitness;
- adapter materialization refuses failed-fitness target-bound candidates unless writing a failure-only packet;
- GEPA curation refuses unlabeled invalid dogfood as a positive example;
- `fitness_passed` is never rendered as approval, promotion, activation, or domain decision readiness.

## Current implementation status

Accepted architecture. No target-protocol sidecar implementation is approved by this ADR alone beyond the next scoped implementation tasks.

The next legal move is post-ADR implementation planning and Phase 1 schema/validator implementation.
