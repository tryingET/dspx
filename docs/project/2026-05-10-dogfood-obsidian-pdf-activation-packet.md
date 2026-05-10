---
summary: "Dogfood receipt for Obsidian/PDF generated DSPy runtime activation packet blockers."
read_when:
  - "You need to know why the current Obsidian/PDF generated DSPy program is review-admitted but not production-activated."
  - "You are deciding the next blockers before activating a generated program runtime."
type: "evidence"
---

# Obsidian/PDF generated-program activation packet dogfood

Date: 2026-05-10
Task: AK-2750

## Scope

This slice makes the production-activation question explicit for the current Obsidian/PDF DSPy candidate.

It does not activate production, route Obsidian through the generated program, mutate `Wiki/`, mutate `Atlas/`, publish new Oracle records, or bind an AK activation decision.

## Implemented behavior

`dspx program-promote activation-packet` now accepts target-review admission evidence:

```bash
--candidate-state <program-candidate-state-v1>
--obsidian-review-adapter-receipt <dspy-pdf-transition-review-adapter-receipt-v1>
--require-obsidian-review-adapter
```

When required, the activation packet validates that:

- candidate state identity matches the candidate manifest;
- target-aware candidate state does not claim production/domain activation;
- target-aware candidate state does not allow canonical mutation;
- the Obsidian adapter receipt materialized a review packet only;
- the adapter receipt records no canonical, Wiki, Atlas, Zotero, source-package, puzzle-register, or external mutation;
- the adapter receipt is tied to the candidate-state hash.

The packet now includes:

- `target_review_admission` — review-only admission readback;
- `remaining_activation_blockers` — all still-open activation gates, not only the currently staged missing-evidence list.

## Dogfood input

Dogfood root:

```text
/tmp/dspx-target-fidelity-next-pdf.ZCg2c0
```

Candidate/runtime manifest:

```text
/tmp/dspx-target-fidelity-next-pdf.ZCg2c0/runtime/manifest.json
```

Oracle report:

```text
/tmp/dspx-target-fidelity-next-pdf.ZCg2c0/runtime/program_oracle_report.json
```

Target-aware candidate state:

```text
/tmp/dspx-target-fidelity-next-pdf.ZCg2c0/meta_adjudication/program_candidate_state.target_fidelity.json
```

Obsidian review adapter receipt:

```text
/home/tryinget/Documents/Obsidian/_System/review/proposals/pdf-transition/doc:cd25bf38/adapter-receipt.json
```

## Command run

```bash
uv run dspx program-promote activation-packet \
  --manifest /tmp/dspx-target-fidelity-next-pdf.ZCg2c0/runtime/manifest.json \
  --owning-domain "obsidian/pdf-transition" \
  --activation-target "obsidian-pdf-transition-generated-program-runtime" \
  --authority-owner "obsidian-pdf-transition-governance" \
  --oracle-report /tmp/dspx-target-fidelity-next-pdf.ZCg2c0/runtime/program_oracle_report.json \
  --candidate-state /tmp/dspx-target-fidelity-next-pdf.ZCg2c0/meta_adjudication/program_candidate_state.target_fidelity.json \
  --obsidian-review-adapter-receipt /home/tryinget/Documents/Obsidian/_System/review/proposals/pdf-transition/doc:cd25bf38/adapter-receipt.json \
  --require-obsidian-review-adapter \
  --rollout-owner "obsidian-pdf-transition-runtime-operator" \
  --rollback-plan "Disable the generated DSPy PDF-transition runtime route and return to deterministic review-packet materialization only." \
  --out /tmp/dspx-target-fidelity-next-pdf.ZCg2c0/activation/obsidian_pdf_activation_packet.json \
  --json
```

## Observed summary

```json
{
  "missing_required_evidence": [
    "jury_results",
    "refined_promotion_review"
  ],
  "next_required_action": "collect_missing_evidence",
  "production_activation_applied": false,
  "remaining_activation_blockers": [
    "jury_results",
    "refined_promotion_review",
    "domain_decision_record",
    "canonical_binding_ref"
  ],
  "review_packet_materialized": true,
  "status": "blocked",
  "target_protocol_fidelity_judgment": "supports_domain_review",
  "target_review_admission_status": "review_admitted"
}
```

## Interpretation

The current candidate is no longer blocked at the review-admission layer:

```text
target-fidelity passed
-> DSPx target-protocol adjudication supports domain review
-> Obsidian adapter materialized a review packet
```

It is still blocked as a production-activated generated-program runtime because the activation packet lacks:

1. generated-program jury results for this activation candidate;
2. refined promotion-review evidence;
3. a domain decision record;
4. a canonical binding ref in AK/current authority.

The rollout owner and rollback plan were supplied only as packet fields. They do not activate anything.

## Next blockers to close

The next safe sequence is:

1. produce/attach generated-program jury results for the Obsidian/PDF candidate;
2. produce/attach refined promotion-review evidence;
3. ask the domain/delegated adjudicator to record an explicit decision;
4. bind the accepted decision into AK/current authority;
5. only then run a rollout preflight for the generated-program runtime route.

Follow-up evidence: `docs/project/2026-05-10-dogfood-obsidian-pdf-activation-blockers-resolved.md` completed steps 1 and 2 and moved the packet to `ready_for_domain_adjudication`. The remaining blockers are now the domain decision record and real canonical binding ref.

Until those are complete, the only allowed Obsidian effect remains the review/proposal packet under:

```text
_System/review/proposals/pdf-transition/doc:cd25bf38/
```
