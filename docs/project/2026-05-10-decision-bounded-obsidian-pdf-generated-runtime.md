---
summary: "Domain decision for bounded Obsidian/PDF generated DSPy runtime activation, limited to review/proposal packets and still blocked before rollout until canonical binding verification."
read_when:
  - "You need the Obsidian/PDF domain decision for the current generated DSPy PDF-transition candidate."
  - "You are checking what the domain accepted and what remains forbidden before rollout."
type: "decision"
---

# Decision — bounded Obsidian/PDF generated-program runtime activation

Date: 2026-05-10
Task: AK-2769
AK decision: `#40`
Owning domain: `obsidian/pdf-transition`
Authority owner / delegated adjudicator: `obsidian-pdf-transition-governance`
Activation target: `obsidian-pdf-transition-generated-program-runtime`
Subject candidate: `doc:cd25bf38` / `prog-cand-668a02406848`

## Decision

Accept the current DSPx-generated Obsidian/PDF transition candidate for **bounded generated-program runtime activation planning**, limited to producing review/proposal packets for the PDF-transition review queue.

This is a domain decision to proceed to canonical binding, not a rollout receipt and not canonical note mutation authority.

## Allowed effect

After canonical binding is verified and rollout preflight passes, the generated DSPy program may be routed as a bounded runtime for:

```text
PDF/source package input
-> generated DSPy PDF-transition behavior
-> Obsidian review/proposal packet under _System/review/proposals/pdf-transition/<doc_id>/
```

Allowed output surface:

```text
_System/review/proposals/pdf-transition/<doc_id>/
```

Allowed document class:

```text
review/proposal packets only
```

## Forbidden effect

This decision does not allow:

- canonical `Wiki/` mutation;
- canonical `Atlas/` mutation;
- Zotero identity mutation;
- source-package mutation;
- puzzle-register mutation;
- automatic acceptance of proposals;
- GEPA winner selection or training-label promotion;
- broad replacement of the deterministic Obsidian/PDF pipeline;
- production rollout before canonical binding verification and rollout preflight.

## Evidence reviewed

DSPx evidence:

- `/tmp/dspx-target-fidelity-next-pdf.ZCg2c0/generation_gate_preflight.json`
- `/tmp/dspx-target-fidelity-next-pdf.ZCg2c0/generation_fitness_results.json`
- `/tmp/dspx-target-fidelity-next-pdf.ZCg2c0/generation_traceability.json`
- `/tmp/dspx-target-fidelity-next-pdf.ZCg2c0/meta_adjudication/program_candidate_state.target_fidelity.json`
- `/tmp/dspx-target-fidelity-next-pdf.ZCg2c0/activation/jury_results.json`
- `/tmp/dspx-target-fidelity-next-pdf.ZCg2c0/activation/promotion_review_refined.json`
- `/tmp/dspx-target-fidelity-next-pdf.ZCg2c0/activation/obsidian_pdf_activation_packet.hardened.json`

Obsidian evidence:

- `/home/tryinget/Documents/Obsidian/_System/review/proposals/pdf-transition/doc:cd25bf38/adapter-receipt.json`
- `/home/tryinget/Documents/Obsidian/_System/review/proposals/pdf-transition/doc:cd25bf38/review.html`
- `/home/tryinget/Documents/Obsidian/_System/pdf-pipeline/dspy-generated-review-adapter.md`

Review/hardening evidence:

- `docs/project/2026-05-10-dogfood-obsidian-pdf-activation-packet.md`
- `docs/project/2026-05-10-dogfood-obsidian-pdf-activation-blockers-resolved.md`
- `docs/project/2026-05-10-review-bounded-obsidian-pdf-activation-many-greats.md`

## Rationale

The candidate has passed target-fidelity gating and DSPx/meta target-protocol adjudication for downstream domain review. The Obsidian adapter materialized a review/proposal packet without canonical mutation. Evidence-side blockers were closed with generated-program jury results and refined promotion-review evidence. Activation-gate hardening now prevents loose Oracle reports, mismatched behavior evidence, blocking target judgments, wrong-owner decision records, and fake binding strings from silently unlocking rollout preflight.

The domain decision is therefore to proceed one step: from `ready_for_domain_adjudication` to `ready_for_canonical_binding`.

## Current AK decision state

```text
#40 state: adr_recorded
#40 outcome: accepted
```

This records the domain decision. It is not yet the verified activation binding consumed by rollout preflight.

## Remaining blocker

A real AK/current-authority canonical binding must still be created and verified before rollout preflight.

A non-empty string is not enough. The binding must refer to a real accepted decision/evidence/transition authority record for this activation target.

## Rollout owner and rollback plan

Rollout owner:

```text
obsidian-pdf-transition-runtime-operator
```

Rollback plan:

```text
Disable the generated DSPy PDF-transition runtime route and return to deterministic review-packet materialization only.
```

## Decision outcome

```text
outcome: promote
scope: bounded review/proposal runtime only
production_activation_applied: false
canonical_mutation_allowed: false
next_required_action: bind_decision_into_ak_or_current_authority
```
