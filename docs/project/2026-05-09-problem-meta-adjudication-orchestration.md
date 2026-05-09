---
summary: "Problem brief for a DSPx meta-adjudication layer above generated DSPy programs."
read_when:
  - "You are designing jury/adjudicator selection for generated DSPy programs."
  - "You are deciding how jury/adjudicator behavior should be stored for Oracle/Postgres and GEPA learning."
type: "problem"
---

# Problem: meta-adjudication orchestration for generated DSPy programs

## System4D frame

### Container — boundary

DSPx currently generates program candidates, local behavior evidence, Oracle-readable evidence, deterministic jury sidecars, promotion review sidecars, and non-authoritative activation packets. The missing boundary is an overarching DSPx adjudication layer that sits **above** generated program candidates and governs how each candidate gets an appropriate judging system.

This layer must remain evidence-producing. It must not become production activation authority.

```text
DSPx meta-adjudication = designs/verifies judging systems and emits evidence
DSPx Oracle/Postgres = durable empirical behavior memory
GEPA/DSPy = optimization of judging behavior from retained traces
AK/governance/domain = canonical activation authority where landed
```

### Compass — why this matters

The current generated-program path can answer: "did this candidate pass local behavior checks?"

It cannot yet answer: "was the right jury selected for this target, was that jury verified, did that jury form an appropriate program-specific adjudicator, and did DSPx verify that adjudicator before trusting the program evidence review?"

The goal is to make judging itself observable and improvable:

- discover the target domain and risks before selecting judges;
- select a jury suited to that target, not a generic static panel;
- have a DSPx adjudicator judge the selected jury;
- have the verified jury form the program-specific adjudicator;
- have the DSPx adjudicator judge that program-specific adjudicator;
- store all behavior traces in Oracle/Postgres for longitudinal analysis;
- use GEPA/DSPy to improve jury/adjudicator behavior over time.

### Motor — desired lifecycle

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

### Fog — risks and unknowns

- Recursive judging theater: judge-of-judge-of-judge without hard stop conditions.
- Authority drift: Oracle/Postgres or DSPx adjudicator results being treated as production activation.
- Weak labels: GEPA can optimize toward bad adjudication behavior if expected outcomes are poorly curated.
- Privacy/security: target discovery and adjudication traces may contain sensitive source material.
- Provider dependency: model-backed jury/adjudicator behavior needs provider/model health receipts and cost controls.
- Bootstrap problem: the first DSPx adjudicator must be explicit, versioned, and constrained before it can judge other judging systems.

## Current failure mode

For the Obsidian/PDF transition path, DSPx can now produce live-provider behavior evidence and materialize review-only artifacts into Obsidian. But the jury evidence remains local/deterministic and generic. It does not prove that the selected judges were correct for Obsidian's source-grounding, Wiki/Atlas mutation, review-queue, and rollout/rollback risks.

The missing evidence is therefore not merely "run a jury". It is:

1. discover the target;
2. select the right jury for that target;
3. verify the jury;
4. form and verify the program-specific adjudicator;
5. judge the candidate evidence;
6. publish the judging behavior as empirical memory;
7. keep final activation authority outside DSPx.
