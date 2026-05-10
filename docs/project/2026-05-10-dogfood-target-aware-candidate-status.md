---
summary: "Dogfood receipt for target-aware program candidate status and Obsidian review-admission readiness."
read_when:
  - "You are checking whether DSPx can summarize target-fidelity and adjudication readiness in one candidate status packet."
  - "You are deciding whether a DSPx PDF-transition candidate may be materialized into Obsidian review."
type: "evidence"
---

# Target-aware candidate status dogfood

Date: 2026-05-10
Task: AK-2748

## Scope

This slice exposes target-fidelity and DSPx/meta-adjudication readiness through the existing `program-promote status` surface.

It does not automate `program-loop`, activate production, mutate Obsidian, publish Oracle evidence, train GEPA, or grant canonical Wiki/Atlas authority.

## Implemented behavior

`dspx program-promote status` now accepts optional target-fidelity evidence:

```bash
--generation-gate-preflight <generation_gate_preflight.json>
--generation-fitness-results <generation_fitness_results.json>
--program-evidence-adjudication <program_evidence_adjudication.json>
```

The resulting `program-candidate-state-v1` sidecar includes `target_fidelity_state` with:

- generation gate status and fail-closed reasons;
- generation fitness status/rendered state;
- target-protocol fidelity adjudicator judgment;
- downstream evidence-review eligibility;
- Obsidian review-adapter materialization readiness;
- explicit false production/domain activation and canonical mutation claims.

The key admission flag is intentionally narrow:

```text
target_fidelity_state.obsidian_review_adapter_materialization_allowed
```

When true, it means only that the candidate may be materialized as an Obsidian review packet. It does not mean the generated content is semantically accepted, production activated, canonical, or GEPA-training-ready.

## Dogfood input

Existing next-PDF dogfood root:

```text
/tmp/dspx-target-fidelity-next-pdf.ZCg2c0
```

Candidate manifest:

```text
/tmp/dspx-target-fidelity-next-pdf.ZCg2c0/program/manifest.json
```

Meta-adjudication sidecar:

```text
/tmp/dspx-target-fidelity-next-pdf.ZCg2c0/meta_adjudication/program_evidence_adjudication.json
```

## Command run

```bash
uv run dspx program-promote status \
  --manifest /tmp/dspx-target-fidelity-next-pdf.ZCg2c0/program/manifest.json \
  --generation-gate-preflight /tmp/dspx-target-fidelity-next-pdf.ZCg2c0/generation_gate_preflight.json \
  --generation-fitness-results /tmp/dspx-target-fidelity-next-pdf.ZCg2c0/generation_fitness_results.json \
  --program-evidence-adjudication /tmp/dspx-target-fidelity-next-pdf.ZCg2c0/meta_adjudication/program_evidence_adjudication.json \
  --out /tmp/dspx-target-fidelity-next-pdf.ZCg2c0/meta_adjudication/program_candidate_state.target_fidelity.json \
  --json
```

## Observed summary

```json
{
  "canonical_mutation_allowed": false,
  "downstream_evidence_review_eligible": true,
  "obsidian_review_adapter_materialization_allowed": true,
  "production_or_domain_activation_allowed": false,
  "state_status": "not_promoted_materialized",
  "target_fitness_rendered_state": "eligible_for_downstream_evidence_review",
  "target_fitness_status": "fitness_passed",
  "target_protocol_judgment": "supports_domain_review",
  "truth_summary_adapter_allowed": true
}
```

## Interpretation

The DSPx product loop now has a compact status packet for the question:

```text
Can this target-bound generated candidate enter downstream review?
```

For the dogfood candidate, the answer is:

```text
yes, review materialization is allowed;
no, production/domain activation is not allowed;
no, canonical Wiki/Atlas mutation is not allowed.
```

## Propagation boundary

DSPx updates do not automatically rewrite the Obsidian vault or an already-materialized review packet.

Propagation into Obsidian is a separate adapter/materialization step. For PDF transition, the truthful propagation target is an Obsidian review packet under:

```text
_System/review/proposals/pdf-transition/<doc_id>/
```

not a canonical `Wiki/` or `Atlas/` note and not a permanent generated-program runtime stored in the vault.
