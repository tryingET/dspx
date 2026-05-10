---
summary: "Dogfood receipt for verifying the real AK canonical binding for bounded Obsidian/PDF generated-program runtime activation."
read_when:
  - "You need proof that the Obsidian/PDF generated-runtime activation packet reached rollout preflight readiness through a verified AK binding."
  - "You are checking whether production activation was applied or only rollout preflight became legal."
type: "evidence"
---

# Obsidian/PDF canonical binding verification dogfood

Date: 2026-05-10
Task: AK-2773
AK decision: `#40`

## Scope

This slice verifies the canonical binding for the bounded Obsidian/PDF generated-program runtime activation path.

It does not activate production, route Obsidian through the generated program, mutate `Wiki/`, mutate `Atlas/`, or perform rollout. It only proves that the activation packet can move from `ready_for_canonical_binding` to `ready_for_rollout_preflight` through a real AK decision lookup and verification sidecar.

## Binding verified

Canonical binding ref:

```text
ak://decision/40#accepted
```

AK decision state at verification time:

```text
state: adr_recorded
outcome: accepted
adr_ref: docs/project/2026-05-10-decision-bounded-obsidian-pdf-generated-runtime.md
```

Verification sidecar:

```text
/tmp/dspx-target-fidelity-next-pdf.ZCg2c0/activation/canonical_binding_verification.json
```

Activation packet after verified binding:

```text
/tmp/dspx-target-fidelity-next-pdf.ZCg2c0/activation/obsidian_pdf_activation_packet.with_verified_binding.json
```

## Commands run

```bash
AK=/home/tryinget/ai-society/softwareco/owned/agent-kernel/target/release/ak

uv run dspx program-promote canonical-binding-verification \
  --canonical-binding-ref "ak://decision/40#accepted" \
  --decision-record /tmp/dspx-target-fidelity-next-pdf.ZCg2c0/activation/domain_decision_record.json \
  --ak-bin "$AK" \
  --out /tmp/dspx-target-fidelity-next-pdf.ZCg2c0/activation/canonical_binding_verification.json \
  --json

uv run dspx program-promote activation-packet \
  --manifest /tmp/dspx-target-fidelity-next-pdf.ZCg2c0/program/manifest.json \
  --owning-domain "obsidian/pdf-transition" \
  --activation-target "obsidian-pdf-transition-generated-program-runtime" \
  --authority-owner "obsidian-pdf-transition-governance" \
  --oracle-report /tmp/dspx-target-fidelity-next-pdf.ZCg2c0/runtime/program_oracle_report.json \
  --jury-results /tmp/dspx-target-fidelity-next-pdf.ZCg2c0/activation/jury_results.json \
  --review /tmp/dspx-target-fidelity-next-pdf.ZCg2c0/activation/promotion_review_refined.json \
  --decision-record /tmp/dspx-target-fidelity-next-pdf.ZCg2c0/activation/domain_decision_record.json \
  --canonical-binding-ref "ak://decision/40#accepted" \
  --canonical-binding-verification /tmp/dspx-target-fidelity-next-pdf.ZCg2c0/activation/canonical_binding_verification.json \
  --candidate-state /tmp/dspx-target-fidelity-next-pdf.ZCg2c0/meta_adjudication/program_candidate_state.target_fidelity.json \
  --obsidian-review-adapter-receipt /home/tryinget/Documents/Obsidian/_System/review/proposals/pdf-transition/doc:cd25bf38/adapter-receipt.json \
  --require-obsidian-review-adapter \
  --rollout-owner "obsidian-pdf-transition-runtime-operator" \
  --rollback-plan "Disable the generated DSPy PDF-transition runtime route and return to deterministic review-packet materialization only." \
  --out /tmp/dspx-target-fidelity-next-pdf.ZCg2c0/activation/obsidian_pdf_activation_packet.with_verified_binding.json \
  --json
```

## Observed summary

```json
{
  "ak_decision_outcome": "accepted",
  "ak_decision_state": "adr_recorded",
  "binding_ref": "ak://decision/40#accepted",
  "next_required_action": "run_owner_approved_rollout_preflight",
  "packet_status": "ready_for_rollout_preflight",
  "production_activation_applied": false,
  "remaining_activation_blockers": [],
  "verification_status": "verified"
}
```

## Interpretation

The canonical-binding stone is now turned over.

The activation packet is now:

```text
ready_for_rollout_preflight
```

This is not production activation. It means the next legal action is a rollout preflight owned by:

```text
obsidian-pdf-transition-runtime-operator
```

Rollout still must be explicit, separately evidenced, and reversible.

## Guardrail

`production_activation_applied=false` remains true in the activation packet. No Obsidian production route was changed by this slice.
