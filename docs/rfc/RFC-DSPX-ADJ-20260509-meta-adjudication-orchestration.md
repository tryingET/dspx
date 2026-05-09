---
summary: "RFC for a DSPx meta-adjudication layer that researches targets, selects/verifies juries, forms/verifies program adjudicators, and stores judging behavior for Oracle/Postgres + GEPA improvement."
read_when:
  - "You are implementing or reviewing generated-program jury/adjudicator orchestration."
  - "You are deciding how DSPx jury/adjudicator behavior should feed Oracle/Postgres and GEPA."
type: "rfc"
---

# RFC: DSPx meta-adjudication orchestration for generated DSPy programs

## 0) Metadata

- RFC ID: `RFC-DSPX-ADJ-20260509-meta-adjudication-orchestration`
- Status: `draft`
- Owner: `softwareco/dspx`
- Created: `2026-05-09`
- Target milestone: `generated-program activation evidence hardening`
- Related docs:
  - `docs/project/2026-05-09-problem-meta-adjudication-orchestration.md`
  - `docs/project/2026-05-09-evidence-meta-adjudication-orchestration.md`
  - `docs/project/generated-program-activation-boundary.md`
  - `docs/project/pdf-transition-program-gen.md`
  - `docs/project/2026-05-09-obsidian-pdf-transition-live-adapter-dogfood.md`
  - `docs/adr/20260506-oracle-evidence-publication-boundary.md`
  - `~/ai-society/holdingco/governance-kernel/docs/core/definitions/generated-dspy-program-promotion-governance.md`

## 1) Problem statement

DSPx has generated-program candidates, behavior evidence, Oracle reports, deterministic jury sidecars, promotion review sidecars, and activation evidence packets. It does not yet have an overarching adjudication layer that selects and verifies the right judging system for each generated program target.

The missing requirement is not a single static jury command. The desired architecture is:

1. research/discover the generated program's target;
2. select a target-suitable jury;
3. have the DSPx adjudicator judge that selected jury;
4. have the verified jury form the generated program's program-specific adjudicator;
5. have the DSPx adjudicator judge that program-specific adjudicator;
6. run program evidence adjudication;
7. store the whole behavior trace in shared Oracle/Postgres for analysis and eventual GEPA optimization;
8. keep production activation authority in AK/governance/domain owner surfaces.

## 2) Scope / non-goals

### In scope

- Define the meta-adjudication lifecycle above generated DSPy program candidates.
- Define sidecar contract names for target profile, jury selection, jury verification, program adjudicator formation, adjudicator verification, and adjudication behavior traces.
- Define how adjudication behavior should be published to shared Oracle/Postgres as empirical memory.
- Define the future GEPA optimization seam for improving jury/adjudicator behavior.
- Define a safe phased rollout starting with a local planner/packet, not a production authority mutation.

### Out of scope

- Automatic production activation.
- Canonical `Wiki/` / `Atlas/` mutation for Obsidian.
- Turning Oracle/Postgres into authority.
- Replacing governance-kernel activation semantics.
- Replacing human/domain final activation decisions.
- Broad model-backed execution before provider health, cost, privacy, and trace-retention constraints are explicit.

### Invariants

- DSPx jury/adjudicator outputs are evidence, not activation authority.
- Shared Oracle/Postgres stores behavior memory, not canonical decisions.
- Authority-mirror labels in Oracle require explicit external authority refs.
- GEPA may optimize judging behavior/policies, not silently alter production activation rules.
- Candidate-local `coordinates.db` files remain scratch indexes and are not migrated wholesale.
- Every adjudication artifact must carry non-authority flags, provider/model/runtime identity when model-backed, hashes, and provenance.

## 3) System4D target shape

### Container

```text
DSPx meta-adjudication layer
  -> target discovery
  -> jury selection
  -> DSPx adjudicator verification of selected jury
  -> program adjudicator formation
  -> DSPx adjudicator verification of program adjudicator
  -> program evidence adjudication
  -> behavior-trace publication

DSPx Oracle/Postgres
  -> empirical memory for traces, outcomes, failures, revisions, labels

GEPA/DSPy
  -> optimizes jury/adjudicator prompts and policies from curated examples

AK/governance/domain
  -> canonical activation decision and binding
```

### Compass

The purpose is to learn and improve what good judging looks like across generated DSPy programs, while keeping final authority outside DSPx.

### Motor

```text
program_candidate_created
-> target_discovery_started
-> target_profile_built
-> jury_requirements_derived
-> jury_panel_selected
-> dspx_adjudicator_reviews_jury
-> jury_panel_approved_or_revised
-> program_adjudicator_formed
-> dspx_adjudicator_reviews_program_adjudicator
-> adjudication_setup_approved_or_revised
-> program_evidence_judged
-> adjudication_behavior_trace_published
-> activation_packet_ready_for_domain_decision
```

### Fog

Main risks: recursion theater, authority drift, poor labels, sensitive trace leakage, provider/cost instability, and bootstrap ambiguity for the first DSPx adjudicator.

## 4) Option analysis

### Option A: static jury per generated program

- Design: keep using deterministic `jury.json`, `jury_selection.json`, `jury_rubric.json`, and `program-promote jury` as the core evidence.
- Pros: simple, deterministic, already implemented.
- Cons: target-blind, not enough for domain-specific risks, not GEPA-rich.
- Risks: rubber-stamp or irrelevant juries.

### Option B: program-specific model jury only

- Design: run a model-backed jury directly against behavior evidence for each program.
- Pros: richer critique than deterministic sidecars.
- Cons: skips the question of whether the jury itself is legitimate.
- Risks: opaque judge selection, authority drift, fragile provider-dependent outcomes.

### Option C: meta-adjudication orchestration with behavior memory

- Design: add an overarching DSPx layer that researches target, selects jury, verifies jury, has jury form program-specific adjudicator, verifies that adjudicator, adjudicates evidence, and publishes behavior traces to Oracle/Postgres for GEPA learning.
- Pros: target-sensitive, auditable, optimizable, authority-preserving.
- Cons: more sidecars, more lifecycle states, more provider/cost/privacy controls needed.
- Risks: recursion theater if stop conditions are not explicit.

## 5) Proposed decision

Choose Option C, implemented in phases.

The first accepted implementation slice should be local-only and non-authoritative: a meta-adjudication planning/packet command that inspects an existing generated-program candidate and writes the target/jury/adjudicator plan with missing evidence and next commands. It should not call models, publish shared Oracle records, mutate AK, or claim activation.

## 6) Target contracts

### 6.1 Sidecar artifacts

Proposed schemas:

| Artifact | Purpose | Authority posture |
| --- | --- | --- |
| `program-target-profile-v1` | Target discovery summary, target owner, risks, evidence needs. | Evidence only |
| `program-jury-requirements-v1` | Required juror perspectives, qualifications, conflicts, coverage. | Evidence only |
| `program-meta-jury-selection-v1` | Selected jury panel and selection rationale. | Evidence only |
| `program-jury-verification-v1` | DSPx adjudicator review of selected jury fitness. | Evidence only |
| `program-adjudicator-formation-v1` | Program-specific adjudicator proposed by verified jury. | Evidence only |
| `program-adjudicator-verification-v1` | DSPx adjudicator review of program adjudicator fitness. | Evidence only |
| `program-evidence-adjudication-v1` | Program evidence judgment by verified program adjudicator. | Evidence only |
| `program-adjudication-behavior-trace-v1` | Combined trace for Oracle/Postgres publication and GEPA training. | Empirical memory only |
| `program-adjudication-gepa-example-v1` | Curated train/validation example derived from trace + later outcome. | Optimization input only |

### 6.2 State values

```text
draft
planned_not_executed
target_profile_ready
jury_selected
jury_verification_failed
jury_verified
program_adjudicator_formed
program_adjudicator_verification_failed
program_adjudicator_verified
evidence_adjudicated
published_to_oracle_empirical_memory
ready_for_domain_decision
```

### 6.3 Non-authority fields

Every artifact should include:

```json
{
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

### 6.4 Oracle/Postgres publication shape

Adjudication behavior traces should be published as curated empirical records, for example:

```text
publication_label=adjudication_behavior_trace
retention_class=retained
redaction_status=reviewed_no_secrets_claimed
activation_authority=false
authority_ref_required=false
```

Authority-mirror labels such as `accepted_for_review`, `promote_decision_recorded`, `activated`, or `rolled_back` still require explicit AK/governance/domain refs.

## 7) GEPA improvement lane

GEPA should optimize model-backed judging modules only after enough traces and curated labels exist.

Candidate DSPy modules:

- `TargetDiscoveryModule`
- `JurySelectionModule`
- `JuryVerificationModule`
- `ProgramAdjudicatorFormationModule`
- `ProgramAdjudicatorVerificationModule`
- `EvidenceAdjudicationModule`

GEPA examples should include:

- target profile inputs;
- candidate behavior evidence;
- selected jury/adjudicator setup;
- later human/domain outcome;
- rollback or post-activation incident signals when available;
- expected judgment and rationale;
- feedback describing missed risks, authority drift, over-conservatism, or weak evidence handling.

Metric shape:

```python
def adjudication_metric(gold, pred, trace=None, pred_name=None, pred_trace=None):
    return dspy.Prediction(score=score, feedback=feedback)
```

GEPA outputs versioned judging policies/rubrics/prompts. They do not mutate activation state.

## 8) Rollout plan

### Phase 1 — local meta-adjudication plan

Implementation evidence: `docs/project/2026-05-09-meta-adjudication-planner-implementation.md`.

- Add a local planner service/CLI that reads `manifest.json` and known sidecars.
- Emits `program-meta-adjudication-plan-v1` with target, required sidecars, missing evidence, and exact next commands.
- No model calls, no Oracle writes, no AK/governance mutation.

### Phase 2 — deterministic target profile and jury requirements

Implementation evidence: `docs/project/2026-05-09-meta-adjudication-planner-implementation.md`.

- Build deterministic target profile from intent, manifest, behavior evidence, declared external systems, and docs refs.
- Emit `program-target-profile-v1` and `program-jury-requirements-v1`.
- Add tests for Obsidian/PDF risk discovery: source grounding, review-only adapter, Wiki/Atlas mutation boundary, rollout/rollback.

### Phase 3 — jury-panel selection and verification

Implementation evidence for deterministic Phase 3a: `docs/project/2026-05-09-meta-adjudication-planner-implementation.md`.

- Add deterministic jury-panel selection and DSPx-adjudicator verification sidecars first.
- Add provider-backed proposal commands for jury selection and program adjudicator formation only behind explicit provider flags later.
- Require provider health receipts, model identity, budget controls, and privacy/redaction posture before model-backed phases.
- Keep deterministic baseline jurors as guardrails.

### Phase 4 — program-adjudicator formation and verification

Implementation evidence for deterministic Phase 4a: `docs/project/2026-05-09-meta-adjudication-planner-implementation.md`.

- Form a deterministic program-specific adjudicator from the verified meta-jury.
- Have the DSPx adjudicator verify that program-adjudicator contract before it is allowed to judge program evidence.
- Keep this phase sidecar-only: no model calls, no shared Oracle writes, and no activation authority.

### Phase 5 — program evidence adjudication and local behavior trace

Implementation evidence for deterministic Phase 5a: `docs/project/2026-05-09-meta-adjudication-planner-implementation.md`.

- Judge generated-program evidence with the verified deterministic program adjudicator.
- Emit `program-evidence-adjudication-v1` with role judgments, missing evidence, and a non-authoritative ready-for-domain-decision recommendation.
- Emit `program-adjudication-behavior-trace-v1` as a local empirical-memory trace for later publication preflight.
- Keep this phase sidecar-only: no model calls, no shared Oracle writes, and no activation authority.

### Phase 6 — Oracle/Postgres behavior publication

- Extend publication preflight/publish to include adjudication trace sidecars.
- Publish failures, revisions, and withholds as first-class empirical memory, not only promoted candidates.

### Phase 7 — GEPA optimization pilot

- Derive curated `program-adjudication-gepa-example-v1` datasets.
- Optimize one judging module using `dspy.GEPA` with separate train/validation sets.
- Emit optimized policy sidecars with lineage and non-authority labels.

## 9) Validation plan

Phase 1 focused tests:

```text
tests/test_program_meta_adjudication_plan.py
```

Required checks for a docs/plan slice:

```bash
node ~/ai-society/core/agent-scripts/scripts/docs-list.mjs --docs . --strict --full-list
git diff --check
```

Required checks for implementation phases:

```bash
uv run pytest tests/test_program_meta_adjudication_plan.py tests/test_program_workflow.py tests/test_program_activation_packet.py -q
just verify-fast
```

## 10) Operational impact

- Phase 1 has negligible cost: local JSON/Markdown sidecars only.
- Model-backed phases add provider calls and must expose cost/time/provider health.
- Oracle/Postgres phase adds retained trace storage and backup/retention implications.
- GEPA phase adds potentially expensive reflective optimization and must be bounded by explicit budgets.

## 11) Risk register

| Risk | Trigger | Mitigation | Rollback |
| --- | --- | --- | --- |
| Recursion theater | endless judge verification loops | fixed two-level stop: DSPx adjudicator verifies jury and program adjudicator; final domain authority remains outside | disable model-backed phases; keep local planner |
| Authority drift | jury/adjudicator result called approval | mandatory non-authority flags and activation-packet blockers | remove adjudication refs from activation packet until wording fixed |
| Bad GEPA labels | optimized judge learns wrong behavior | curated examples, separate validation, human/domain outcome refs | revert optimized policy version |
| Sensitive trace leakage | target discovery includes private source data | redaction status, publisher custody, provider privacy checks | retract publication, rotate policy, disable external providers |
| Provider instability/cost | model-backed phases time out or exceed budget | provider health receipts, budget caps, deterministic fallback | use deterministic planner/jury only |

## 12) Open questions

1. What is the initial bootstrap identity and versioned rubric for the DSPx adjudicator?
2. Should target discovery be deterministic first, model-backed first, or hybrid?
3. Which adjudication traces are safe to publish to shared Oracle/Postgres by default?
4. What labels should distinguish jury-selection failures from program-evidence failures?
5. How should later human/domain outcomes be attached back to Oracle records for GEPA datasets?
6. Should the Obsidian/PDF adapter be the first pilot target after Phase 1?

## 13) Execution checklist

- [ ] Review this RFC.
- [ ] Add Phase 1 local planner service/CLI.
- [ ] Add focused tests for planner states and non-authority flags.
- [ ] Dogfood planner on Obsidian/PDF live-provider candidate.
- [ ] Decide whether to proceed to ADR before model-backed phases.
- [ ] Keep activation authority in governance/domain path.
