---
summary: "Implementation plan for DSPx-wide target-protocol fidelity gates across *-gen surfaces, starting with program-gen."
read_when:
  - "You are implementing target-protocol fidelity gates for DSPx generation."
  - "You need the phased rollout from RFC to schemas, program-gen adoption, dogfood, and GEPA curation."
type: "plan"
---

# Plan: target-protocol fidelity gates for DSPx *-gen

## Goal

Make DSPx generation evaluator-first and protocol-bound.

A `*-gen` command should not only prove that a candidate can be generated, run, and emit schema-valid sidecars. It should prove that the candidate implements the target protocol truthfully enough to be useful, or fail closed before/after generation with explicit evidence.

## Phase 0 — RFC and current-state alignment

Deliverables:

- `docs/project/2026-05-09-problem-target-protocol-fidelity-gates.md`
- `docs/project/2026-05-09-evidence-target-protocol-fidelity-gates.md`
- `docs/project/2026-05-09-plan-target-protocol-fidelity-gates.md`
- `docs/rfc/RFC-DSPX-GEN-20260509-target-protocol-fidelity-gates.md`

Validation:

```bash
node ~/ai-society/core/agent-scripts/scripts/docs-list.mjs --docs . --strict --full-list
git diff --check
just task-scope-check task_id=2712 mode=working-tree
```

## Phase 1 — shared generation contract schemas

Add shared sidecar contracts:

```text
generation_target_contract.json       # gen-target-contract-v1
generation_fitness_suite.json         # gen-fitness-suite-v1
generation_traceability.json          # gen-traceability-v1
generation_fitness_results.json       # gen-fitness-results-v1
generation_gate_preflight.json        # gen-generation-gate-preflight-v1
```

Minimum contract fields:

- target owner and owner refs;
- target docs and evidence refs;
- target protocol stages;
- required artifact families;
- invariants and forbidden shortcuts;
- source/provenance/language requirements;
- authority/mutation boundaries;
- required juror/adjudicator perspectives;
- adversarial fixtures / traps;
- identity/hash binding to intent, contract, suite, candidate, evidence, and validator version;
- fail-closed reasons.

Validation:

- schema/unit tests for required fields;
- fail-closed tests for missing owner refs, stages, forbidden shortcuts, source/provenance/language policy, identity binding, or adversarial fixtures;
- docs strict.

## Phase 2 — `program-gen` preflight gate

Add deterministic DSPx/meta preflight paths before candidate creation. These gates are local evidence only: no provider call, no candidate creation, no shared Oracle write, no AK/governance mutation, and no activation authority.

Proposed command shape:

```bash
dspx program-gen target-contract \
  --intent <intent.yaml> \
  --out <outdir>/generation_target_contract.json \
  --json

dspx program-gen fitness-suite \
  --target-contract <outdir>/generation_target_contract.json \
  --out <outdir>/generation_fitness_suite.json \
  --json

dspx program-gen verify-generation-gate \
  --intent <intent.yaml> \
  --target-contract <outdir>/generation_target_contract.json \
  --fitness-suite <outdir>/generation_fitness_suite.json \
  --out <outdir>/generation_gate_preflight.json \
  --json

# Later, integrated generation should require one of:
# --generation-gate-preflight <preflight.json>
# --target-contract <contract.json> --fitness-suite <suite.json>
# --allow-tutorial-contract-profile   # only for deterministic tutorial/local tier
```

Generation must fail closed when target contract or fitness-suite quality is insufficient:

```text
generation_blocked: insufficient_target_contract
generation_blocked: missing_required_target_docs
generation_blocked: missing_forbidden_shortcuts
generation_blocked: missing_adversarial_fitness_cases
generation_blocked: missing_identity_or_hash_binding
generation_blocked: ambiguous_risk_tier
```

Validation:

- `program-gen` cannot create a target-bound candidate when contract fields are missing;
- `program-gen` cannot create a target-bound candidate when fitness-suite fields are missing;
- low-risk tutorial examples can still use a small local contract profile;
- existing fixture tests either provide contracts or explicitly opt into tutorial/local profile with warning sidecar.

## Phase 3 — traceability and fitness execution

After candidate generation, write:

```text
generation_traceability.json
generation_fitness_results.json
```

The traceability matrix should map:

```text
target requirement -> generated surface -> test/evidence -> juror/adjudicator coverage -> status
```

The fitness suite should include adversarial tests before promotion evidence is accepted.

Validation:

- candidate surfaces without traceability are not promotion-ready;
- runnable/schema-valid candidates can still fail target fitness;
- the existing `pdf_transition_review` runtime contract is represented as a target-fitness sub-check, not as a replacement for the full target contract;
- failure evidence is retained but labeled as withhold/failure evidence.

## Phase 4 — integrate with existing meta-adjudication

Connect generation contract outputs into the existing two-layer adjudication chain:

1. DSPx/meta adjudicator verifies the generated program's jury/adjudicator setup.
2. The generated-program adjudicator judges evidence within delegated scope.

New behavior:

- target profile and jury requirements should consume `generation_target_contract.json` when present;
- evidence adjudication should include `generation_traceability.json` and `generation_fitness_results.json`;
- delegated generated-program adjudicator decisions must distinguish runnable-success from target-protocol-success.

Validation:

- Obsidian/PDF candidate with skipped stage or note-creation shortcut must be withheld;
- adjudication behavior trace records the contract, fitness failures, and withhold rationale;
- publication preflight remains non-authoritative.

## Phase 5 — dogfood on Obsidian/PDF as failure fixture and then regenerated candidate

Use the current flawed Obsidian/PDF real-PDF episodes as adversarial failure fixtures.

Required failure cases:

- direct or draft-like Wiki creation before review/acceptance;
- section heading inflated into concept identity;
- skipped chapter/passage/synthesis gates;
- source language drift;
- missing merge-before-create conservatism;
- canonical mutation or authority ambiguity.

Then regenerate the Obsidian/PDF candidate only after the target contract and fitness suite exist.

Target-bound adapter materialization must require `fitness_passed` or write an explicit failure-only/withheld packet. It must not put failed-fitness artifacts into the normal review queue.

Validation:

- bad historical behavior fails target fitness;
- regenerated candidate emits transition artifacts in the right family and language posture;
- adapter materialization refuses failed-fitness target-bound candidates unless writing failure-only evidence;
- review artifacts remain review-only and do not claim canonical note authority;
- runtime episodes are recorded as evidence, not activation.

## Phase 6 — widen to `signature-gen`, `module-gen`, and future `*-gen`

Generalize the contract by risk tier:

| Tier | Trigger | Gate strength |
| --- | --- | --- |
| tutorial/local | no external owner refs, no adapter materialization, no authority-adjacent outputs | minimal embedded contract profile allowed |
| protocol-bound | target docs/owner refs, external workflow name, or required artifact-family protocol | full target contract + fitness suite required |
| authority-adjacent | outputs feed promotion/export/activation evidence or domain review adapters | full contract + fitness + traceability + adjudication required |
| external mutation capable | any future generator that can mutate owner surfaces | explicit owner/governance activation gate required |

Validation:

- no generator can silently claim target protocol fidelity without a contract;
- small local examples stay usable without fake process burden;
- docs and CLI help explain risk tiers.

## Phase 7 — Oracle/Postgres and GEPA curation

Publish contract/fitness/adjudication traces as empirical memory only when explicitly configured and redacted.

GEPA examples must not train from unlabeled or invalid dogfood. Invalid dogfood can become negative examples only after curated labels are attached.

Validation:

- pending examples are marked `curated_pending_outcome_label`;
- failure examples distinguish observed bad behavior from expected behavior;
- Oracle/Postgres records preserve non-authority flags.

## Rollback strategy

- Keep existing `program-gen` behavior behind a legacy/tutorial profile only while migration is in progress.
- Do not delete current runtime/adjudication sidecars; they remain useful evidence.
- If contract enforcement blocks too much existing local development, relax by risk tier, not by removing fail-closed behavior for target-bound generation.
