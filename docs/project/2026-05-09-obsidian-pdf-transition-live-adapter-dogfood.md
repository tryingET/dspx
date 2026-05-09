---
summary: "Dogfood receipt for the Obsidian PDF transition generated program using dspy-lm-auth/codex/gpt-5.5 and the review-only Obsidian adapter."
read_when:
  - "You need the latest Obsidian PDF transition generated-program dogfood evidence."
  - "You are checking whether the Obsidian adapter mutated canonical Wiki/Atlas surfaces."
type: "evidence"
---

# 2026-05-09 Obsidian PDF Transition Live Adapter Dogfood

## Result

Status: **review-queue adapter dogfooded, canonical activation still not applied**.

The PDF transition generated program was rerun with the auth-backed provider route:

```text
DSPX_PROVIDER=dspy-lm-auth
DSPX_LM_AUTH_MODEL=codex/gpt-5.5
resolved model: openai/gpt-5.5
```

The generated behavior evidence passed for the fixture:

```text
candidate_root=/tmp/dspx-obsidian-pdf-transition-live.9QA9Nv/pdf-transition-program
program_loop_status=ok
behavior_status=passed
oracle_report_status=ok
activation_status=ready_for_domain_adjudication
activation_next=record_domain_decision
```

The Obsidian review-only runtime adapter was then run against that candidate root:

```bash
python /home/tryinget/Documents/Obsidian/_System/pdf-pipeline/scripts/materialize_dspy_transition_review.py \
  --input-dir /tmp/dspx-obsidian-pdf-transition-live.9QA9Nv/pdf-transition-program \
  --json
```

Adapter receipt:

```text
receipt=/home/tryinget/Documents/Obsidian/_System/review/proposals/pdf-transition/doc:pdf-transition-demo/adapter-receipt.json
output_dir=_System/review/proposals/pdf-transition/doc:pdf-transition-demo
status=materialized
source_id=zotero:user:demo/DEMO2026
```

Written review-only artifacts:

```text
_System/review/proposals/pdf-transition/doc:pdf-transition-demo/dspy-transition-artifacts.json
_System/review/proposals/pdf-transition/doc:pdf-transition-demo/prop-dspy-merge-doc-pdf-transition-demo-0001.md
_System/review/proposals/pdf-transition/doc:pdf-transition-demo/dspy-review-packet.md
_System/review/proposals/pdf-transition/doc:pdf-transition-demo/adapter-receipt.json
```

## Boundary proof

The adapter receipt declares all canonical/external mutation flags as false:

```text
canonical_mutation_performed=false
external_mutation_performed=false
wiki_mutation_performed=false
atlas_mutation_performed=false
zotero_mutation_performed=false
source_package_mutation_performed=false
puzzle_register_mutation_performed=false
```

A local receipt assertion verified that every adapter-written path is under:

```text
_System/review/proposals/
```

The adapter does not apply accepted notes and does not mutate canonical `Wiki/` or `Atlas/` surfaces.

## Important remaining distinction

This proves the generated program can produce reviewable transition artifacts with `dspy-lm-auth/codex/gpt-5.5` and that the Obsidian adapter can materialize them into the approved review/proposal surface.

It does **not** mean the generated program is canonically production-activated. Activation still requires the owning domain/governance path to record a domain decision, canonical binding, rollout owner, and rollback plan. The local jury evidence from this run remained deterministic/non-provider-backed and withheld approval; it is not a production approval.
