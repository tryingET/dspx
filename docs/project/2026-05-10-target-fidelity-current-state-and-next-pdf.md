---
summary: "Current-state readout for target-fidelity gates and the next-PDF dogfood run."
read_when:
  - "You need to know what is working after the target-fidelity gate waves."
  - "You are deciding whether to run or review another Obsidian/PDF DSPy output."
type: "evidence"
---

# Target-fidelity current state and next-PDF dogfood

Date: 2026-05-10
Task: AK-2730

## Why this readout exists

The implementation moved quickly across DSPx and the Obsidian adapter. This readout separates:

- what is architecturally accepted;
- what is implemented and verified;
- what a new PDF run proves;
- what is still not proven.

## Current architecture state

Accepted architecture:

- ADR: `docs/adr/20260510-target-protocol-fidelity-gates.md`
- Decision: AK decision `#34`
- Scope: shared target-fidelity invariant plus `program-gen` first implementation path.

Implemented in DSPx:

| Wave | Status | Proof |
| --- | --- | --- |
| RFC/ADR | done | `2962ea5`, `32efc6f`, `ec16f56`, `d6340d0` |
| Wave 1 validators | done | `b6e353e` |
| Wave 2 preflight/gated generation | done | `b28ef12` |
| Wave 3 traceability/fitness results | done | `077c606` |

Implemented in Obsidian adapter:

| Concern | Status | Proof |
| --- | --- | --- |
| old invalid DSPy outputs removed from active proposal path | done | Obsidian commit `e9c13c81c` |
| review-page hover/focus artifact UX retained | done | Obsidian commit `1f7585a5a` |
| deterministic Wiki-draft layer removed | done | Obsidian commit `1f7585a5a` |
| adapter requires `generation_fitness_results.json` | done | Obsidian commit `1f7585a5a` |

## Current command meaning

```text
program-gen target-contract
```

Builds a declared target contract from structured intent. It does not prove semantic target truth.

```text
program-gen fitness-suite
```

Builds a mechanical adversarial/checkable suite skeleton. It does not execute domain acceptance.

```text
program-gen verify-generation-gate
```

Allows or blocks candidate creation based on declared contract/suite sufficiency.

```text
program-gen traceability
program-gen fitness-results
```

Writes post-generation sidecars. `fitness_passed` means only:

```text
eligible_for_downstream_evidence_review
```

It does not mean approved, promoted, activated, canonical, or domain-accepted.

## Next-PDF dogfood run

Purpose: prove the new full local path can process another PDF package through gated generation, runtime execution, target-fitness sidecars, and adapter materialization into a temporary vault.

Source package:

```text
/home/tryinget/Documents/Obsidian/_System/pdf-pipeline/packages/doc:cd25bf38
```

Dogfood root:

```text
/tmp/dspx-target-fidelity-next-pdf.ZCg2c0
```

Temporary adapter vault:

```text
/tmp/obsidian-next-pdf-vault.fgwF4I
```

Summary:

```json
{
  "doc_id": "doc:cd25bf38",
  "preflight_status": "generation_allowed",
  "fitness_status": "fitness_passed",
  "fitness_rendered_state": "eligible_for_downstream_evidence_review",
  "program_run_exit_code": 0,
  "program_run_status": "ok",
  "adapter_status": "materialized",
  "proposal_file_count": 7,
  "html_has_hover_artifacts": true,
  "html_has_drafted_wiki_entry": false,
  "wiki_exists": false,
  "atlas_exists": false
}
```

Observed generated proposal posture:

- 12 section units were emitted.
- 7 merge/create proposals were emitted.
- proposals target `Wiki/...` paths but carry `canonical_mutation_allowed=false` and `review_required=true`.
- adapter materialization happened only in a temporary vault, not the real active Obsidian review queue.

## What this proves

The local pipeline can now run:

```text
source PDF package
-> runtime inputs
-> target contract
-> fitness suite
-> generation gate
-> generated candidate
-> traceability
-> fitness results
-> runtime episode on new PDF input
-> adapter materialization in temp vault
```

without mutating canonical `Wiki/` or `Atlas/` paths.

## What this still does not prove

It does not prove:

- the output is semantically good enough for Obsidian acceptance;
- every proposed Wiki concept should be created;
- source extraction is complete;
- source-language and terminology are fully correct;
- the generated-program adjudicator has accepted the result;
- governance/domain owner has accepted activation;
- GEPA training labels are available.

## Product posture consequence

DSPx is now past “can generate and run a candidate” for this path. It can require target-fidelity sidecars before the Obsidian adapter sees a candidate.

The next gap is no longer basic plumbing. The next gap is judgment quality:

```text
mechanical target-fidelity sidecars
-> adjudication integration
-> semantic failure fixtures
-> owner review/acceptance boundary
```

Recommended next slice:

1. Add the target-fidelity sidecars to DSPx meta-adjudication evidence packets.
2. Treat the quarantined old Obsidian outputs as negative/failure fixtures.
3. Only then consider materializing a new real PDF output into the real Obsidian active review path.
