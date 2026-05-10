---
summary: "Dogfood receipt for resolving the evidence-side Obsidian/PDF generated-program activation blockers and surfacing remaining authority blockers."
read_when:
  - "You need the current Obsidian/PDF generated-program activation blocker state after jury and refined review evidence were attached."
  - "You are deciding whether to record a domain decision or bind activation into AK/current authority."
type: "evidence"
---

# Obsidian/PDF generated-program activation blockers resolved to domain-adjudication gate

Date: 2026-05-10
Task: AK-2754

## Scope

This slice resolves the evidence-side blockers exposed by `AK-2750` for the current Obsidian/PDF generated DSPy candidate.

It does not activate production, route Obsidian through the generated program, mutate `Wiki/`, mutate `Atlas/`, publish new Oracle records, or create a canonical AK activation decision.

## Inputs

Dogfood root:

```text
/tmp/dspx-target-fidelity-next-pdf.ZCg2c0
```

Candidate manifest used for generated-program sidecars:

```text
/tmp/dspx-target-fidelity-next-pdf.ZCg2c0/program/manifest.json
```

Runtime Oracle report:

```text
/tmp/dspx-target-fidelity-next-pdf.ZCg2c0/runtime/program_oracle_report.json
```

Target-aware candidate state:

```text
/tmp/dspx-target-fidelity-next-pdf.ZCg2c0/meta_adjudication/program_candidate_state.target_fidelity.json
```

Obsidian adapter receipt:

```text
/home/tryinget/Documents/Obsidian/_System/review/proposals/pdf-transition/doc:cd25bf38/adapter-receipt.json
```

## Evidence produced

Generated-program jury results:

```text
/tmp/dspx-target-fidelity-next-pdf.ZCg2c0/activation/jury_results.json
```

Refinement proposal:

```text
/tmp/dspx-target-fidelity-next-pdf.ZCg2c0/activation/refinement_proposal.json
```

Refined promotion-review packet:

```text
/tmp/dspx-target-fidelity-next-pdf.ZCg2c0/activation/promotion_review_refined.json
```

Activation packet after attaching jury/review evidence:

```text
/tmp/dspx-target-fidelity-next-pdf.ZCg2c0/activation/obsidian_pdf_activation_packet.with_jury_review.json
```

## Commands run

```bash
uv run dspx program-promote jury \
  --manifest /tmp/dspx-target-fidelity-next-pdf.ZCg2c0/program/manifest.json \
  --out /tmp/dspx-target-fidelity-next-pdf.ZCg2c0/activation/jury_results.json \
  --json

uv run dspx program-refine propose \
  --manifest /tmp/dspx-target-fidelity-next-pdf.ZCg2c0/program/manifest.json \
  --oracle-report /tmp/dspx-target-fidelity-next-pdf.ZCg2c0/runtime/program_oracle_report.json \
  --out /tmp/dspx-target-fidelity-next-pdf.ZCg2c0/activation/refinement_proposal.json \
  --json

uv run dspx program-promote review \
  --manifest /tmp/dspx-target-fidelity-next-pdf.ZCg2c0/program/manifest.json \
  --oracle-report /tmp/dspx-target-fidelity-next-pdf.ZCg2c0/runtime/program_oracle_report.json \
  --refinement-proposal /tmp/dspx-target-fidelity-next-pdf.ZCg2c0/activation/refinement_proposal.json \
  --out /tmp/dspx-target-fidelity-next-pdf.ZCg2c0/activation/promotion_review_refined.json \
  --json

uv run dspx program-promote activation-packet \
  --manifest /tmp/dspx-target-fidelity-next-pdf.ZCg2c0/program/manifest.json \
  --owning-domain "obsidian/pdf-transition" \
  --activation-target "obsidian-pdf-transition-generated-program-runtime" \
  --authority-owner "obsidian-pdf-transition-governance" \
  --oracle-report /tmp/dspx-target-fidelity-next-pdf.ZCg2c0/runtime/program_oracle_report.json \
  --jury-results /tmp/dspx-target-fidelity-next-pdf.ZCg2c0/activation/jury_results.json \
  --review /tmp/dspx-target-fidelity-next-pdf.ZCg2c0/activation/promotion_review_refined.json \
  --candidate-state /tmp/dspx-target-fidelity-next-pdf.ZCg2c0/meta_adjudication/program_candidate_state.target_fidelity.json \
  --obsidian-review-adapter-receipt /home/tryinget/Documents/Obsidian/_System/review/proposals/pdf-transition/doc:cd25bf38/adapter-receipt.json \
  --require-obsidian-review-adapter \
  --rollout-owner "obsidian-pdf-transition-runtime-operator" \
  --rollback-plan "Disable the generated DSPy PDF-transition runtime route and return to deterministic review-packet materialization only." \
  --out /tmp/dspx-target-fidelity-next-pdf.ZCg2c0/activation/obsidian_pdf_activation_packet.with_jury_review.json \
  --json
```

## Observed activation-packet summary

```json
{
  "decision": {
    "decided_by": null,
    "outcome": null,
    "promotion_state_after_decision": null
  },
  "missing_required_evidence": [],
  "next_required_action": "record_domain_decision",
  "production_activation_applied": false,
  "remaining_activation_blockers": [
    "domain_decision_record",
    "canonical_binding_ref"
  ],
  "status": "ready_for_domain_adjudication",
  "target_review_admission_status": "review_admitted"
}
```

## What changed relative to AK-2750

Resolved blockers:

- `jury_results`
- `refined_promotion_review`

Remaining blockers:

- `domain_decision_record`
- `canonical_binding_ref`

## Interpretation

The candidate has now crossed from:

```text
review-admitted but evidence-blocked
```

to:

```text
ready_for_domain_adjudication
```

That is still not production activation.

The remaining blockers are authority blockers, not DSPx evidence-generation blockers. Closing them means the Obsidian/PDF owning domain or delegated governing body must record an explicit activation decision, and that decision must be bound into AK/current authority before rollout preflight can be claimed.

## Guardrail

Do not satisfy `canonical_binding_ref` with a fake string. It must refer to a real AK/current-authority decision/evidence/transition binding for this activation target.

Until that exists, the only active Obsidian effect remains the review/proposal packet under:

```text
_System/review/proposals/pdf-transition/doc:cd25bf38/
```
