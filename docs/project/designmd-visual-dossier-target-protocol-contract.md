---
summary: "DSPx-owned target-protocol contract skeleton for DesignMD visual-source dossier program generation."
read_when:
  - "Reviewing or implementing DSPx program-gen for DesignMD visual-source dossiers."
  - "Checking whether DesignMD visual-dossier requirements are sufficient to authorize candidate generation."
type: "target-protocol-contract"
system4d:
  container: "DSPx target-protocol contract for DesignMD visual-dossier candidate generation."
  compass: "Translate DesignMD requirements into DSPx-owned generation gates without accepting DesignMD authority drift."
  engine: "Requirements packet -> target contract -> adversarial fixtures -> candidate assembly -> execution episode -> receipt bundle -> Oracle/readout -> DesignMD review evidence only."
  fog: "Risk of treating a runnable generated analyzer, Oracle evidence, or DesignMD handoff packet as accepted design authority."
---

# DesignMD visual-dossier target-protocol contract

## Status

- status: draft contract
- owner: DSPx
- incoming requirement owner: DesignMD Foundry
- originating DesignMD packet: `designmd.dspx-visual-dossier-requirements.v1`
- related AK tasks: AK-3125, AK-3130

## Boundary decision

DSPx accepts the DesignMD visual-dossier requirements packet as **requirements intake only**.
It does not authorize program generation, execution episodes, Oracle indexing, candidate promotion, or DesignMD contract mutation.

Generation is allowed only after this DSPx-owned target-protocol contract has enough concrete fixtures, schemas, fitness gates, and forbidden-shortcut checks to satisfy the target-protocol fidelity lifecycle in [target-protocol fidelity gates](2026-05-09-problem-target-protocol-fidelity-gates.md).

## Owner split

| Concern | Owner |
|---|---|
| Visual-source storage, dossier state, Design Core roles, `DESIGN.md` hash, review records | DesignMD Foundry |
| Target-protocol contract, candidate assembly shape, execution episodes, receipt bundles, local eval, Oracle-readable evidence | DSPx |
| Canonical task/evidence/decision authority outside local repo scope | AK / owning governance surface |
| Production activation or durable design truth | Owning domain review; not DSPx output alone |

## Required incoming packet fields

A DesignMD requirements packet is eligible for DSPx target-protocol review only when it includes:

1. `schemaVersion` equal to `designmd.dspx-visual-dossier-requirements.v1`.
2. Visual source id, dossier id, analysis/run id where present, and current `DESIGN.md` hash.
3. Source index hash and packet freshness metadata.
4. Required role outputs for Design Core analysis roles.
5. Expected dossier output families:
   - role findings;
   - component inventory;
   - synthesis / coverage gaps;
   - image-generation prompt packs when applicable;
   - dossier markdown builder output.
6. Static-image inference labels: `observed`, `inferred`, `unverified`.
7. Copy-risk and generated-image safeguards.
8. Forbidden claims and authority language.
9. Minimum fixture expectations and fail-closed blockers.
10. Traceability expectations from source image to finding, component, synthesis, dossier section, and optional proposal context.

If any required identity, freshness, role, authority, or traceability field is absent, DSPx must return:

```text
generation_blocked: insufficient_target_contract
```

## DSPx candidate surface

The first candidate surface is not "an image analyzer" in the abstract.
It is a bounded candidate assembly that implements this target protocol:

```text
validated visual-source packet
+ Design Core role requirements
+ current DESIGN.md hash/context
+ fixture corpus
-> role finding packets
-> component inventory packet
-> synthesis and coverage-gap packet
-> dossier draft packet / markdown builder output
-> traceability matrix
-> receipt bundle
```

The candidate assembly must be executable in a local DSPx episode without mutating DesignMD state.

## Candidate assembly requirements

A valid DSPx candidate assembly must declare:

- target contract id: `dspx.designmd.visual-dossier-target-protocol.v1`;
- DesignMD requirement packet hash;
- code/artifact paths generated or selected by DSPx;
- accepted input packet schema refs;
- output schema refs;
- fixture dataset refs;
- command used for local execution;
- policy envelope forbidding DesignMD mutation, AK writes, and production activation claims;
- receipt output path.

## Execution episode requirements

Each execution episode must record:

- candidate assembly id;
- source packet ids and hashes;
- `DESIGN.md` hash supplied to the candidate;
- fixture id or real local source id;
- provider/runtime settings;
- model/provider identity if any;
- command argv;
- start/end timestamps;
- output packet paths and hashes;
- evaluation results;
- fail-closed blockers.

Episodes are behavior evidence, not DesignMD acceptance.

## Receipt bundle requirements

A receipt bundle must include:

- candidate assembly identity;
- target contract id and version;
- input packet hashes;
- output packet hashes;
- traceability matrix hash;
- fitness result summary;
- failure/withhold status when any required gate fails;
- Oracle-readable evidence references when produced;
- explicit non-authority statement:

```text
DSPx visual-dossier outputs are proposal_context or review_evidence only. They do not accept dossier guidance, mutate DESIGN.md, approve docs/design, create AK/society authority, or activate generated programs for production use.
```

## Fitness gates

A generated candidate is withheld unless all required gates pass.

### Schema fidelity

- Consumes only the declared visual-source and dossier packet families.
- Emits all required output packet families.
- Emits static-image inference labels for every visual claim.
- Emits source/design hash binding in every top-level output packet.

### Role coverage

- Covers every required Design Core role in the incoming requirements packet.
- Does not collapse role-specific findings into one untyped summary.
- Preserves uncertainty rather than inventing missing observations.

### Traceability

- Every component claim traces to at least one source image or explicitly marks itself `inferred`/`unverified`.
- Every dossier section traces to role findings and component inventory entries.
- Every prompt-pack recommendation traces to source observations and copy-risk checks.

### Authority boundary

- Does not write `DESIGN.md`.
- Does not mark dossier guidance reviewed or accepted.
- Does not approve `docs/design`.
- Does not create AK/society evidence or decisions.
- Does not claim target-protocol fitness until all DSPx gates pass.

### Copy-risk and generated-image safety

- Flags external-reference imitation risks.
- Distinguishes generated images, operator-provided images, and external references.
- Blocks direct style-copy instructions.
- Requires prompt packs to be transformation guidance, not asset/style cloning.

### Freshness

- Blocks stale source index hashes.
- Blocks stale `DESIGN.md` hash inputs.
- Blocks missing source/dossier identity.

## Adversarial fixture minimum

Before `program-gen` is allowed, DSPx must have fixtures for:

1. Missing or stale `DESIGN.md` hash.
2. Missing source index hash.
3. Partial image inventory.
4. Mixed generated and operator-provided images.
5. External-reference copy-risk lure.
6. Ambiguous component claim with no visible evidence.
7. Dossier draft that contradicts current `DESIGN.md`.
8. Prompt-pack output that attempts direct style cloning.
9. Role output collapse into generic summary.
10. Candidate attempting to write or imply `DESIGN.md` mutation.

## Generation gate

Before any DSPx program generation for this target, the generation request must prove:

```text
target_docs_and_owner_refs_declared: pass
target_protocol_contract_built: pass
target_protocol_contract_verified: pass
adversarial_fitness_suite_built: pass
generation_allowed: pass
```

Otherwise generation remains blocked.

## Oracle and promotion boundary

Oracle may interpret DSPx execution behavior only after receipt bundles exist.
Oracle evidence can inform review, but it does not approve DesignMD outcomes.

Allowed downstream posture inside DesignMD:

```text
proposal_context
review_evidence
```

Forbidden downstream posture from DSPx alone:

```text
reviewed_dossier_guidance
accepted_contract_truth
production_activation
```

## First implementation slice

The next implementation slice should not start with full program generation.
It should implement the smallest DSPx-native pre-generation review path:

1. Parse or ingest a saved `designmd.dspx-visual-dossier-requirements.v1` packet.
2. Validate required identity, freshness, role, fixture, and authority fields.
3. Emit `generation_blocked: insufficient_target_contract` for incomplete packets.
4. Emit a target-protocol review report when the packet is complete enough for fixture binding.
5. Add the adversarial fixture manifest skeleton.

Only after that slice passes should DSPx consider a generated candidate assembly.
