---
summary: "Problem brief for DSPx-wide target-protocol fidelity gates before and during *-gen candidate creation."
read_when:
  - "You are designing or reviewing DSPx signature-gen, module-gen, program-gen, or future *-gen surfaces."
  - "You need to understand why runnable generated artifacts are insufficient without target-protocol proof."
type: "problem"
---

# Problem: target-protocol fidelity gates for DSPx *-gen

## System4D frame

### Container — boundary

DSPx `*-gen` surfaces can produce valid local artifacts, receipts, replay metadata, behavior evidence, jury sidecars, and non-authoritative promotion packets. That is necessary, but it is not sufficient.

The missing boundary is a **pre-generation target-protocol contract**: before a generator creates a candidate, DSPx must prove that it understands the workflow, artifact families, invariants, forbidden shortcuts, and evidence expectations of the target it is implementing.

```text
intent / prose / docs
-> target protocol contract
-> adversarial fitness tests
-> candidate generation
-> traceability matrix
-> jury / adjudication
-> dogfood
-> promotion evidence
```

Today, the strongest target-sensitive judging surfaces are mostly downstream of a candidate. That means DSPx can discover too late that a generated candidate is runnable but semantically false.

### Compass — why this matters

The purpose of DSPx generation is not to create plausible code-shaped output. It is to create useful, inspectable, improvable cognition/program artifacts that implement the intended target protocol truthfully enough for downstream evidence, review, and optimization.

A generated artifact that passes schema and runtime checks but skips the target workflow creates negative value:

- it consumes review attention with plausible nonsense;
- it pollutes behavior evidence unless clearly labeled as failure evidence;
- it can train later optimization on the wrong behavior if not blocked;
- it creates authority drift by making invalid artifacts look process-complete.

### Motor — desired lifecycle

Every architecture-significant `*-gen` flow should move through this lifecycle:

```text
request_received
-> target_docs_and_owner_refs_declared
-> target_protocol_contract_built
-> target_protocol_contract_verified
-> adversarial_fitness_suite_built
-> generation_allowed
-> candidate_generated
-> candidate_traceability_written
-> fitness_suite_executed
-> target_protocol_fidelity_judged
-> dogfood_on_realistic_inputs
-> promotion_evidence_or_withhold_recorded
```

If the target contract is insufficient, the generator must stop before candidate creation:

```text
generation_blocked: insufficient_target_contract
```

### Fog — risks and unknowns

- Overfitting the contract to one Obsidian/PDF failure instead of making a repo-wide generation contract.
- Turning the pre-generation gate into checklist theater rather than actual target-protocol proof.
- Blocking small low-risk generators with too much process.
- Letting post-hoc meta-adjudication compensate for missing pre-generation target review.
- Treating Oracle/Postgres failure evidence as activation authority.
- Creating unlabeled GEPA examples from invalid dogfood.

## Current failure mode

The Obsidian/PDF transition dogfood exposed the systemic gap.

DSPx could generate a program candidate, run it on real PDF-derived inputs, write runtime episode sidecars, index local Oracle evidence, and materialize review-only proposal artifacts. The infrastructure worked.

But the candidate did not truthfully implement the Obsidian target protocol. It produced plausible-looking Wiki create proposals such as `create Wiki/Herstellung von Gefühlskarten.md` from a source where the required flow was not direct note creation. It also drifted away from the original source language and skipped the target workflow defined in Obsidian `_System` docs.

The target protocol includes both canonical normalized stages and target-specific aliases. A normalized PDF-transition flow is:

```text
source package
-> section units
-> distillation frames
-> evidence cards / board packets
-> merge-before-create proposals
-> review
-> canonical notes only after acceptance
```

For the Obsidian reading profile, that normalized flow must also preserve aliases and constraints such as `chapter_reading` by default, `passage_reading` only when selected, and `chapter_synthesis_check` before note-shaped proposals.

DSPx had evidence that the candidate could run. It did not have pre-generation evidence that the candidate had to implement that target protocol and fail closed on forbidden shortcuts.

## Problem statement

DSPx `*-gen` currently overweights these questions:

- Did a candidate materialize?
- Are files, schemas, receipts, and hashes coherent?
- Can local behavior examples run?
- Can downstream juries/adjudicators inspect sidecars?

It underweights the more important first question:

> What exactly is this generator required to implement, and how do we prove the candidate did not skip or falsify that target protocol?

The required change is to move target-protocol discovery, contract verification, and adversarial fitness design **before** generation, then preserve traceability through generation, runtime, jury/adjudication, dogfood, Oracle evidence, and GEPA curation.
