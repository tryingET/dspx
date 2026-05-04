---
summary: "Program-gen scenario for Obsidian PDF transition artifacts: source package to section units, distillation frames, evidence cards, proposals, and review packets without canonical Wiki mutation."
read_when:
  - "You want to run or modify the PDF Transition Program-Gen scenario."
  - "You are checking DSPx against Obsidian PDF transition architecture boundaries."
type: "guide"
---

# PDF Transition Program-Gen

## Purpose

This scenario uses DSPx `program-gen` to generate a DSPy program-shaped candidate assembly for the Obsidian PDF transition pipeline.

It is grounded in the Obsidian architecture:

- `/home/tryinget/Documents/Obsidian/_System/architecture/pdf-transition-architecture.md`
- `/home/tryinget/Documents/Obsidian/_System/architecture/distillation-method-architecture.md`
- `/home/tryinget/Documents/Obsidian/_System/architecture/source-semantic-scaffold-architecture.md`
- `/home/tryinget/Documents/Obsidian/_System/pdf-pipeline/workflow-profiles.md`

The scenario turns raw PDF/Marker-derived source text plus source-package context into **reviewable transition/proposal artifacts**, not canonical notes.

Canonical flow:

```text
PDF
-> source package
-> section units
-> evidence cards
-> merge/create
-> review
-> canonical notes
```

## Scenario name

```text
pdf-transition-program-gen
```

Fixture paths:

```text
tests/fixtures/program_gen/pdf_transition/intent.yaml
tests/fixtures/program_gen/pdf_transition/examples.yaml
```

## What the generated program is intended to produce

The intent asks the generated DSPy program to produce JSON-string outputs for this artifact family:

| Output field | Artifact family | Meaning |
| --- | --- | --- |
| `section_units_json` | transition | Section-unit candidates derived from source package / Marker markdown. |
| `distillation_frames_json` | transition | Close-reading frames with `paraphrase`, `thesis`, `logic`, `evaluation`, and `application`. |
| `evidence_cards_json` | transition | Source-grounded evidence cards for later Wiki/Atlas decisions. |
| `merge_create_proposals_json` | proposal | Merge/create candidates such as `enrich`, `create`, `board-only`, `ignore`, or `review`. |
| `review_packet_json` | review | Review packet with confidence, uncertainty, provenance, and review needs. |
| `artifact_contract_manifest_json` | review / contract | Declares source/transition/proposal/review/canonical boundaries and forbidden effects. |

The fixture includes one tiny PDF-like Marker markdown excerpt about close reading and expected transition/proposal/review outputs.

## Authority model

| Artifact family | Authority posture |
| --- | --- |
| source | Raw extraction/source package artifact. Zotero/source package identity remains authoritative outside DSPx. |
| transition | Regenerable section units, distillation frames, and evidence cards. |
| proposal | Merge/create candidates only; not accepted notes. |
| review | Human/operator review packets only. |
| canonical | Wiki/Atlas notes only after explicit review outside `program-gen`. |

## What this scenario does not do

It does **not**:

- mutate canonical `Wiki/` notes
- create accepted notes
- make Atlas/Wiki authority decisions
- mutate Zotero/source identity
- claim Marker extraction authority
- write external filesystem artifacts beyond the declared DSPx `program-gen` output directory
- promote a proposal to an accepted note
- call AK
- invoke Oracle indexing automatically
- rank, select winners, approve, or deploy

`program-gen` materializes a local candidate assembly and evidence/receipt artifacts only.

## Example command

From the DSPx repo root:

```bash
TD="$(mktemp -d)"
export DSPX_PROVIDER=stub
export MLFLOW_ENABLE=0
export DSPX_CACHE_DIR="$TD/cache"
export DSPX_CACHE_ENABLE=1

uv run -q python -m dspx.cli.dspx program-gen \
  --intent tests/fixtures/program_gen/pdf_transition/intent.yaml \
  --outdir "$TD/pdf-transition-program" \
  --print-manifest

uv run -q python -m dspx.cli.dspx run replay \
  --from "$TD/pdf-transition-program/manifest.json.meta.json" \
  --check-only \
  --json
```

High-signal generated files:

```text
manifest.json
manifest.json.meta.json
intent.json
program.py
module.py
signature.py
eval_examples.py
behavior_results.json
eval_behavior.py
behavior_episode.json
oracle_evidence.json
execution_episode.json
promotion_review.json
promotion_adjudication_request.json
promotion_decision_template.json
```

The fixture's expected transition artifacts are embedded as `expected_outputs` in `behavior_results.json`. With the stub provider, the behavior check may report mismatches; that is acceptable for this scenario because the test proves the generated program shape, artifact contracts, replay metadata, and authority boundaries rather than model quality.

## Test coverage

The executable scenario test is:

```bash
uv run --no-sync -m pytest -q tests/test_program_gen_pdf_transition.py
```

It proves:

- `program-gen` materializes the PDF transition intent with the stub/offline provider
- the scenario preserves source/transition/proposal/review/canonical artifact-family distinctions
- expected outputs include section-unit candidates, distillation frames, evidence cards, merge/create proposals, a review packet, and an artifact contract manifest
- no fake canonical Wiki note is mutated
- no transition files are written outside the DSPx output directory during `program-gen`
- replay metadata is inspectable and `dspx run replay --check-only` passes
- no default Oracle index is created

## Current limitation

This is a **program-gen scenario and fixture**, not a full Obsidian runtime adapter.

The generated program currently exposes transition artifacts as declared JSON output fields and behavior evidence, not as a filesystem writer for Obsidian transition queues. A future explicit adapter could write these JSON outputs into an Obsidian review queue, but that must remain separate from canonical Wiki mutation and must carry its own review/authority contract.
