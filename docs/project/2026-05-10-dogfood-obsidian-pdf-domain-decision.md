---
summary: "Dogfood receipt for recording the real Obsidian/PDF domain decision and advancing the activation packet to the canonical-binding gate."
read_when:
  - "You need evidence that the Obsidian/PDF generated-program runtime domain decision was recorded."
  - "You are checking the remaining blocker before rollout preflight."
type: "evidence"
---

# Obsidian/PDF domain decision dogfood

Date: 2026-05-10
Task: AK-2769
AK decision: `#40`

## Scope

This slice records the real domain decision for the current Obsidian/PDF generated DSPy candidate.

It does not activate production, route Obsidian through the generated program, mutate `Wiki/`, mutate `Atlas/`, or claim rollout preflight.

## Domain decision

AK decision created and advanced:

```text
#40 Authorize bounded Obsidian PDF generated-program runtime domain decision
state: adr_recorded
outcome: accepted
rfc_ref: docs/project/2026-05-10-decision-bounded-obsidian-pdf-generated-runtime.md
adr_ref: docs/project/2026-05-10-decision-bounded-obsidian-pdf-generated-runtime.md
evidence_ref: docs/project/2026-05-10-dogfood-obsidian-pdf-domain-decision.md
```

The decision accepts only bounded review/proposal runtime activation planning for:

```text
obsidian-pdf-transition-generated-program-runtime
```

Allowed effect:

```text
PDF/source package input -> generated DSPy behavior -> review/proposal packet
```

Forbidden effects remain:

- `Wiki/` mutation;
- `Atlas/` mutation;
- Zotero mutation;
- source-package mutation;
- puzzle-register mutation;
- automatic proposal acceptance;
- rollout without verified canonical binding.

## Sidecar decision record

A domain decision sidecar was written for the activation packet:

```text
/tmp/dspx-target-fidelity-next-pdf.ZCg2c0/activation/domain_decision_record.json
```

Important fields:

```json
{
  "schema_version": "program-promotion-decision-record-v1",
  "status": "recorded",
  "outcome": "promote",
  "promotion_state_after_decision": "domain_decision_recorded_pending_canonical_binding",
  "decided_by": "obsidian-pdf-transition-governance",
  "created_from": {
    "ak_decision_ref": "ak://decision/40#accepted",
    "ak_decision_state": "adr_recorded"
  },
  "non_authority": {
    "automatic_promotion": false,
    "external_mutation": false,
    "governance_authority": false,
    "oracle_promotion": false,
    "oracle_pruning": false,
    "oracle_ranking": false,
    "program_mutation": false
  }
}
```

The `outcome=promote` value means the domain decision gate is satisfied for the bounded activation path. It does not mean production activation has been applied.

## Activation packet after domain decision

Command run:

```bash
uv run dspx program-promote activation-packet \
  --manifest /tmp/dspx-target-fidelity-next-pdf.ZCg2c0/program/manifest.json \
  --owning-domain "obsidian/pdf-transition" \
  --activation-target "obsidian-pdf-transition-generated-program-runtime" \
  --authority-owner "obsidian-pdf-transition-governance" \
  --oracle-report /tmp/dspx-target-fidelity-next-pdf.ZCg2c0/runtime/program_oracle_report.json \
  --jury-results /tmp/dspx-target-fidelity-next-pdf.ZCg2c0/activation/jury_results.json \
  --review /tmp/dspx-target-fidelity-next-pdf.ZCg2c0/activation/promotion_review_refined.json \
  --decision-record /tmp/dspx-target-fidelity-next-pdf.ZCg2c0/activation/domain_decision_record.json \
  --candidate-state /tmp/dspx-target-fidelity-next-pdf.ZCg2c0/meta_adjudication/program_candidate_state.target_fidelity.json \
  --obsidian-review-adapter-receipt /home/tryinget/Documents/Obsidian/_System/review/proposals/pdf-transition/doc:cd25bf38/adapter-receipt.json \
  --require-obsidian-review-adapter \
  --rollout-owner "obsidian-pdf-transition-runtime-operator" \
  --rollback-plan "Disable the generated DSPy PDF-transition runtime route and return to deterministic review-packet materialization only." \
  --out /tmp/dspx-target-fidelity-next-pdf.ZCg2c0/activation/obsidian_pdf_activation_packet.with_domain_decision.json \
  --json
```

Observed summary:

```json
{
  "decision": {
    "decided_by": "obsidian-pdf-transition-governance",
    "outcome": "promote",
    "promotion_state_after_decision": "domain_decision_recorded_pending_canonical_binding"
  },
  "missing_required_evidence": [],
  "next_required_action": "bind_decision_into_ak_or_current_authority",
  "production_activation_applied": false,
  "remaining_activation_blockers": [
    "canonical_binding_ref"
  ],
  "status": "ready_for_canonical_binding"
}
```

## Interpretation

The domain-decision stone is now turned over.

The candidate moved from:

```text
ready_for_domain_adjudication
```

to:

```text
ready_for_canonical_binding
```

Remaining blocker:

```text
canonical_binding_ref
```

Because of AK-2760 hardening, later passing a non-empty binding string will not by itself authorize rollout preflight. The next slice must create and verify a real AK/current-authority binding for this activation target.
