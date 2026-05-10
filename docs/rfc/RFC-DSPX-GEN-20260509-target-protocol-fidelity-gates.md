---
summary: "RFC for DSPx-wide evaluator-first target-protocol fidelity gates across *-gen surfaces, starting with program-gen."
read_when:
  - "You are designing or implementing DSPx generation contracts, traceability, or fitness gates."
  - "You are deciding how program-gen should avoid runnable but semantically false generated DSPy programs."
type: "rfc"
---

# RFC: DSPx target-protocol fidelity gates for `*-gen`

## 0) Metadata

- RFC ID: `RFC-DSPX-GEN-20260509-target-protocol-fidelity-gates`
- Status: `draft`
- Owner: `softwareco/dspx`
- Created: `2026-05-09`
- Target milestone: `generated-program target-fidelity hardening`
- Related docs:
  - `docs/project/2026-05-09-problem-target-protocol-fidelity-gates.md`
  - `docs/project/2026-05-09-evidence-target-protocol-fidelity-gates.md`
  - `docs/project/2026-05-09-plan-target-protocol-fidelity-gates.md`
  - `docs/rfc/RFC-DSPX-ADJ-20260509-meta-adjudication-orchestration.md`
  - `docs/project/program-gen-walkthrough.md`
  - `docs/project/pdf-transition-program-gen.md`
  - `docs/project/generated-program-activation-boundary.md`
  - `/home/tryinget/Documents/Obsidian/_System/architecture/pdf-transition-architecture.md`
  - `/home/tryinget/Documents/Obsidian/_System/architecture/distillation-method-architecture.md`
  - `/home/tryinget/Documents/Obsidian/_System/architecture/merge-before-create-architecture.md`
  - `/home/tryinget/ai-society/holdingco/governance-kernel/docs/core/definitions/generated-dspy-program-promotion-governance.md`

## 1) Problem statement

DSPx `*-gen` can currently create artifacts that are locally coherent, runnable, schema-valid, replayable, and inspectable by downstream sidecars. That is not enough.

The Obsidian/PDF transition dogfood showed the failure mode clearly: the generated candidate and runtime infrastructure worked, but the candidate's outputs were semantically wrong for the target workflow. It produced plausible-looking Wiki create proposals and draft-like text from source material that should have moved through source package, reading/synthesis, evidence-card, merge-before-create, and review gates before any canonical note action.

This is a repo-wide generation problem, not an Obsidian adapter problem. Any `*-gen` surface can produce a false success if DSPx proves only candidate materialization and local execution rather than target-protocol fidelity.

## 2) Scope / non-goals

### In scope

- Define a shared `*-gen` target-protocol fidelity contract.
- Require target-bound generation to establish the contract before candidate creation.
- Define adversarial fitness suites before promotion evidence is accepted.
- Define traceability from target requirements to generated surfaces and evidence.
- Integrate the contract with existing meta-adjudication, Oracle/Postgres behavior memory, and future GEPA curation.
- Start implementation with `program-gen`, then generalize to `signature-gen`, `module-gen`, and future `*-gen` surfaces by risk tier.

### Out of scope

- Automatic production activation.
- Canonical Obsidian `Wiki/` / `Atlas/` mutation.
- Replacing the existing two-layer DSPx/meta plus generated-program jury/adjudicator model.
- Replacing governance-kernel/domain activation authority.
- Turning Oracle/Postgres into authority.
- Training GEPA from unlabeled or invalid dogfood.

### Invariants

- A runnable generated candidate can still be invalid.
- Target-protocol fitness is a first-class gate, not a UI review enhancement.
- DSPx evidence remains non-authoritative unless accepted by the owning authority path.
- Oracle/Postgres stores empirical behavior memory, not production activation truth.
- Candidate-local SQLite indexes remain scratch evidence stores.
- Generated-program juries/adjudicators are distinct from DSPx/meta juries/adjudicators.
- Invalid dogfood is valuable as failure evidence, not as a promotion example.

## 3) Current-state evidence

Current `program-gen` already produces rich local evidence:

```text
candidate assembly
-> replay metadata
-> execution episode
-> behavior results
-> Oracle-readable evidence
-> jury/promotion shells
-> optional runtime episodes
-> optional meta-adjudication sidecars
```

Current meta-adjudication can verify target/jury/adjudicator/evidence after a candidate exists. Current `program-run` can expose real-input behavior failures. Current Oracle publication preflights can package behavior evidence without shared mutation.

The gap is the left side of the lifecycle:

```text
target protocol contract
-> adversarial fitness design
-> generation allowed / blocked
```

Without that left-side gate, DSPx can generate a candidate that later produces confusing artifacts and only then discover it never implemented the actual target protocol.

## 4) Option analysis

### Option A: keep generation as-is and improve review UI/adapters

- Design: preserve `program-gen` behavior and patch downstream review surfaces to make artifacts easier to inspect.
- Pros: low implementation cost; preserves current workflows.
- Cons: does not stop false programs; makes bad outputs more legible but not more truthful.
- Risks: operator confusion, plausible nonsense, invalid GEPA examples, authority drift.

### Option B: rely on post-hoc meta-adjudication only

- Design: keep generation target-light, then let DSPx/meta and generated-program adjudicators withhold bad candidates after generation.
- Pros: reuses recently implemented adjudication sidecars; preserves separation between generation and judging.
- Cons: detects failures late; wastes provider/runtime/dogfood cycles; can still materialize misleading review artifacts before the target protocol is enforced.
- Risks: recursion theater and late-stage cleanup replacing early target understanding.

### Option C: evaluator-first target-protocol gates before and after generation

- Design: require target-bound `*-gen` flows to create/verify a target protocol contract and adversarial fitness suite before generation, then write traceability and fitness results after generation. Feed those artifacts into the existing two-layer adjudication and Oracle/GEPA paths.
- Pros: blocks false generation early; preserves downstream adjudication; turns failures into labeled evidence; generalizes across `*-gen` surfaces.
- Cons: adds schemas, gates, and migration work; requires risk-tiered defaults so tutorials remain usable.
- Risks: over-process if every small generator needs the strongest gate.

## 5) Proposed decision

Choose Option C.

DSPx should adopt a shared Gen Contract vNext:

```text
intent/prose/docs
-> target protocol contract
-> adversarial fitness suite
-> generated candidate
-> traceability matrix
-> fitness results
-> jury/adjudication
-> dogfood
-> promotion evidence or withhold evidence
```

The first implementation target should be `program-gen`, because it has the clearest target-protocol risk and the strongest current failure evidence.

The pre-generation verifier is a DSPx/meta verifier, not the generated-program adjudicator. The generated-program adjudicator does not exist until after candidate creation. Therefore the first gate must be deterministic and local: it validates target-contract completeness, fitness-suite completeness, identity/hash binding, non-authority flags, and risk-tier classification before `program-gen` is allowed to materialize a target-bound candidate.

## 6) Target architecture

### 6.1 Sidecar contracts

| Artifact | Schema | Purpose | Required before candidate? |
| --- | --- | --- | --- |
| `generation_target_contract.json` | `gen-target-contract-v1` | Declares target owner/docs, protocol stages, artifact families, invariants, forbidden shortcuts, authority boundaries, and source/provenance/language requirements. | Yes for target-bound generation |
| `generation_fitness_suite.json` | `gen-fitness-suite-v1` | Declares adversarial and positive cases that must expose protocol violations before promotion. | Yes for target-bound generation |
| `generation_traceability.json` | `gen-traceability-v1` | Maps target requirements to generated surfaces, tests/evidence, jury coverage, and status. | No; written after generation |
| `generation_fitness_results.json` | `gen-fitness-results-v1` | Records execution of the fitness suite and target-fidelity verdicts. | No; written after generation |

### 6.2 Pre-generation verifier and command shape

The first verifier is a deterministic DSPx/meta preflight, shaped as local evidence only. It does not call providers, create candidates, mutate Oracle/Postgres, mutate AK/governance, or approve activation.

Proposed commands:

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
```

Target-bound `program-gen` must require either an explicit successful `generation_gate_preflight.json` or enough explicit inputs to run the same deterministic verifier inline. The verifier outputs `generation_allowed` or `generation_blocked` with fail-closed reasons.

### 6.3 Minimum target contract shape

```json
{
  "schema_version": "gen-target-contract-v1",
  "identity": {
    "intent_sha256": "...",
    "contract_sha256": "...",
    "validator": "dspx.gen_target_contract.v1"
  },
  "target": {
    "id": "obsidian_pdf_transition",
    "owner": "obsidian/_System",
    "owner_refs": ["/home/tryinget/Documents/Obsidian/_System/architecture/pdf-transition-architecture.md"],
    "owner_ref_custody": "local_path_reference_not_publishable_without_redaction"
  },
  "protocol": {
    "required_stages": [
      "source_package",
      "section_units",
      "distillation_frames",
      "evidence_cards",
      "merge_before_create",
      "review",
      "canonical_notes_after_acceptance"
    ],
    "profile_aliases": {
      "chapter_reading": "source_package_to_section_units_default_reading",
      "passage_reading": "selected_passage_reading_only",
      "chapter_synthesis_check": "distillation_and_merge_before_create_check"
    },
    "artifact_families": ["source", "transition", "proposal", "review", "canonical"],
    "forbidden_shortcuts": [
      "draft_canonical_note_before_review",
      "canonical_mutation_from_runtime_evidence",
      "section_heading_as_note_identity_without_merge_gate"
    ]
  },
  "fitness": {
    "required_adversarial_cases": [
      "plausible_section_heading_inflated_into_wiki_create",
      "source_language_drift",
      "missing_merge_before_create_gate"
    ]
  },
  "non_authority": {
    "activation_authority": false,
    "promotion_authority": false,
    "oracle_authority": false,
    "governance_authority": false,
    "external_mutation": false
  },
  "effect": {
    "candidate_files_mutated": false,
    "canonical_target_mutated": false,
    "ak_mutated": false,
    "governance_mutated": false
  }
}
```

The Obsidian/PDF profile distinguishes canonical normalized stages from target-specific aliases. Validators must check the normalized required stages while preserving aliases so domain wording such as `chapter_reading`, `passage_reading`, and `chapter_synthesis_check` is not lost.

### 6.4 State values

```text
contract_missing
contract_insufficient
generation_blocked
contract_verified
fitness_suite_ready
candidate_generated
traceability_ready
fitness_failed
fitness_passed
withheld_for_target_protocol_failure
eligible_for_meta_adjudication
```

`fitness_passed` only means the candidate is eligible for downstream adjudication/promotion evidence. It does not mean ready for domain decision, production activation, external mutation, or canonical owner acceptance.

### 6.5 Fail-closed reasons

```text
insufficient_target_contract
missing_target_owner_ref
missing_required_protocol_stage
missing_artifact_family_boundary
missing_forbidden_shortcut_list
missing_adversarial_fitness_case
missing_authority_boundary
missing_source_language_policy
missing_identity_or_hash_binding
```

### 6.6 Risk-tier classification

DSPx should classify generation risk deterministically before applying gates:

| Tier | Trigger | Gate |
| --- | --- | --- |
| tutorial/local | no external owner refs, no adapter materialization, no authority-adjacent outputs | minimal embedded contract profile allowed |
| protocol-bound | target docs/owner refs, external workflow name, or required artifact-family protocol | target contract + fitness suite required |
| authority-adjacent | outputs feed promotion/export/activation evidence or domain review adapters | full contract + fitness + traceability + adjudication required |
| external mutation capable | any future generator can mutate owner surfaces | explicit owner/governance activation gate required before mutation |

If classification is ambiguous, DSPx must choose the stricter tier or block with `generation_blocked: insufficient_target_contract`.

## 7) Integration with existing meta-adjudication

The existing meta-adjudication RFC remains valid. This RFC moves target-protocol evidence earlier and gives the adjudication layer stronger inputs.

New integration points:

- target profile should prefer `generation_target_contract.json` when present;
- jury requirements should include target-protocol fidelity perspectives;
- program adjudicator verification should check whether the generated-program adjudicator is allowed to judge target fitness;
- evidence adjudication should consume `generation_traceability.json` and `generation_fitness_results.json`;
- behavior traces should preserve target-contract and fitness failure summaries for Oracle/Postgres and GEPA curation.

For target-bound flows, adapter materialization must require `fitness_passed` or write an explicitly withheld/failure-only packet. Review/proposal adapters must not turn failed target-fidelity outputs into normal review queues.

## 8) Rollout plan

### Phase 0 — RFC and docs

Create this RFC plus problem/evidence/plan docs. No code changes.

### Phase 1 — schemas and pure validators

Add dataclasses/helpers and tests for the four sidecars plus `generation_gate_preflight.json`. No provider calls, no shared Oracle writes, no AK/governance mutation.

### Phase 2 — `program-gen` contract and fitness preflight

Add explicit `target-contract`, `fitness-suite`, and `verify-generation-gate` commands plus an inline generation gate. Target-bound generation blocks when the contract or suite is insufficient. Tutorial/local generation may use a minimal embedded profile with a visible risk tier.

### Phase 3 — traceability and fitness results

Write traceability and fitness result sidecars after generation. Make promotion/adjudication status distinguish runnable success from target-protocol success.

### Phase 4 — Obsidian/PDF failure fixture and regeneration

Turn the current bad Obsidian/PDF outputs into adversarial failure fixtures. Regenerate only after the contract and fitness suite can catch the old failure.

### Phase 5 — widen by risk tier

Apply the contract model to `signature-gen`, `module-gen`, and future `*-gen` surfaces based on risk tier.

### Phase 6 — Oracle/Postgres and GEPA

Publish curated target-fidelity traces as empirical memory only. Mark examples without accepted outcome labels as pending and not trainable.

## 9) Compatibility and migration

- Existing local examples should keep working through a low-risk tutorial profile during migration.
- Existing candidate sidecars remain readable.
- Existing meta-adjudication sidecars remain useful and should gain optional inputs rather than being replaced.
- Old bad dogfood should be relabeled as failure evidence, not deleted from learning context.

## 10) Validation plan

Docs/RFC slice:

```bash
node ~/ai-society/core/agent-scripts/scripts/docs-list.mjs --docs . --strict --full-list
git diff --check
just task-scope-check task_id=2712 mode=working-tree
```

Implementation slices:

```bash
uv run pytest tests/test_program_generation_contract.py tests/test_program_gen_pdf_transition.py tests/test_program_meta_adjudication.py -q
uv run ruff check packages/dspx-core/src/dspx/services tests/test_program_generation_contract.py
uv run ty check packages/dspx-core/src/dspx/services
just verify-fast
```

Negative implementation tests:

- missing owner ref blocks target-bound generation;
- missing forbidden shortcut list blocks target-bound generation;
- missing source/provenance/language policy blocks target-bound generation;
- missing identity/hash binding blocks target-bound generation;
- runnable/schema-valid candidate can still fail target fitness;
- adapter materialization refuses failed-fitness target-bound candidates unless writing a failure-only packet.

Dogfood gate:

- run historical bad Obsidian/PDF case and observe `fitness_failed` / withheld;
- prove the current `pdf_transition_review` runtime contract is represented as a target-fitness sub-check rather than a replacement for full target fidelity;
- regenerate target-bound candidate and prove it preserves transition/review boundaries;
- run real-PDF runtime episode and verify failure/success labels are not conflated with activation.

## 11) Operational impact

- More explicit pre-generation planning work.
- Fewer misleading generated artifacts reaching review surfaces.
- Better negative examples for Oracle/GEPA once labeled.
- Higher-quality promotion packets because target-fidelity evidence is available before adjudication.

## 12) Risk register

| Risk | Trigger | Mitigation | Rollback |
| --- | --- | --- | --- |
| Process overload | simple tutorial generation blocked by full contract | risk-tiered profiles | temporarily allow tutorial profile only |
| Checklist theater | contract exists but does not encode adversarial traps | require fitness suite and failure fixtures | block target-bound generation until traps exist |
| Post-hoc leakage | bad candidates still materialized to domain review surfaces | require fitness pass before adapter materialization for target-bound flows | disable adapter dogfood for failed candidates |
| Authority drift | fitness pass called activation | non-authority flags and governance boundary docs | remove activation wording from sidecars |
| Bad GEPA labels | invalid dogfood used as positive training data | pending-label state and curated negative examples | quarantine examples |

## 13) Open questions

1. What exact minimal fields should the tutorial/local embedded contract profile require?
2. Should `generation_target_contract.json` be authored by a standalone command, generated from intent, or both?
3. Which `signature-gen` / `module-gen` cases need full target contracts versus minimal IO contracts?
4. How should later domain outcomes attach to target-fidelity traces for GEPA datasets?

## 14) Execution checklist

- [x] Create problem, evidence, plan, and RFC docs.
- [ ] Review RFC with multi-perspective architecture review.
- [ ] Revise RFC from review findings.
- [ ] Accept/record decision through the repo's decision workflow if required.
- [ ] Implement shared sidecar schemas.
- [ ] Add `program-gen` contract preflight/gate.
- [ ] Add traceability and fitness results.
- [ ] Dogfood on Obsidian/PDF failure fixtures and regenerated candidate.
- [ ] Publish only curated empirical traces to Oracle/Postgres.
