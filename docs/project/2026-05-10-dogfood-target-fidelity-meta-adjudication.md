---
summary: "Dogfood receipt for integrating generation target-fidelity sidecars into DSPx meta-adjudication."
read_when:
  - "You are checking whether target-fidelity evidence reaches DSPx/meta adjudication."
  - "You are continuing Wave 4 target-fidelity/adjudication integration."
type: "evidence"
---

# Target-fidelity sidecars in meta-adjudication dogfood

Date: 2026-05-10
Task: AK-2735

## Scope

This slice connects Wave 3 generation target-fidelity sidecars into DSPx/meta adjudication evidence.

It does not add production activation, owner acceptance, shared Oracle publication, or GEPA training labels.

## Implemented behavior

Meta-adjudication now recognizes these generation sidecars:

```text
generation_target_contract.json       # gen-target-contract-v1
generation_fitness_suite.json         # gen-fitness-suite-v1
generation_gate_preflight.json        # gen-generation-gate-preflight-v1
generation_traceability.json          # gen-traceability-v1
generation_fitness_results.json       # gen-fitness-results-v1
```

When present, target profile derivation adds target-fidelity evidence and the `target_protocol_fidelity` risk. Jury requirements then include a `target_protocol_fidelity` perspective.

Program evidence adjudication can consume:

```bash
--generation-traceability <generation_traceability.json>
--generation-fitness-results <generation_fitness_results.json>
```

The target-fidelity perspective:

- asks for more evidence when `generation_fitness_results.json` is missing;
- withholds when fitness is not `fitness_passed`;
- withholds when `fitness_passed` is rendered as anything other than `eligible_for_downstream_evidence_review`;
- otherwise allows downstream evidence review only, not approval or activation.

## Dogfood input

This used the next-PDF dogfood root from AK-2730:

```text
/tmp/dspx-target-fidelity-next-pdf.ZCg2c0
```

Source package:

```text
/home/tryinget/Documents/Obsidian/_System/pdf-pipeline/packages/doc:cd25bf38
```

Meta-adjudication dogfood root:

```text
/tmp/dspx-target-fidelity-next-pdf.ZCg2c0/meta_adjudication
```

## Commands run

The dogfood chain wrote:

```text
target_profile.json
jury_requirements.json
meta_jury_selection.json
jury_verification.json
program_adjudicator_formation.json
program_adjudicator_verification.json
program_adjudicator_delegation.json
program_evidence_adjudication.json
adjudication_behavior_trace.json
meta_adjudication_plan.json
```

with generation sidecars supplied from the next-PDF dogfood root.

## Observed summary

```json
{
  "adjudication_ready_for_domain_decision": false,
  "adjudication_recommendation": "revise_or_collect_missing_evidence",
  "blocking_perspectives": [
    "rollout_rollback"
  ],
  "dogfood_root": "/tmp/dspx-target-fidelity-next-pdf.ZCg2c0/meta_adjudication",
  "fitness_status_in_profile": "fitness_passed",
  "plan_generation_fitness_sidecar_status": "present",
  "target_fidelity_perspective_present": true,
  "target_fidelity_risk_present": true,
  "target_fitness_evidence_ref_present": true
}
```

Role judgments included:

```text
target_protocol_fidelity -> supports_domain_review
rollout_rollback -> needs_more_evidence: activation_packet.json
```

## Interpretation

The meaningful gap is now narrowed:

```text
mechanical target-fidelity sidecars
-> meta-adjudication target profile
-> target-fidelity jury perspective
-> evidence adjudication readback
-> behavior trace
```

The result is correctly **not** ready for domain decision because rollout/activation evidence is missing. This is expected and desirable: target-fitness evidence can permit downstream review without becoming activation authority.

## Remaining gap

Next meaningful slice:

1. Convert quarantined old Obsidian/PDF DSPy outputs into explicit negative/failure fixtures.
2. Prove those fixtures fail target-fidelity/adjudication checks.
3. Only then decide whether a new PDF result may enter the real active Obsidian review path.
