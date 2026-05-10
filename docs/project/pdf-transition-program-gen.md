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

The scenario turns raw PDF/Marker-derived source text plus source-package context into **reviewable transition/proposal artifacts and note-draft previews**, not canonical notes. The refined target contract requires source-language fidelity, Zotero/source footnotes, wikilinked durable key concepts, and Zotero review-link derivation from real source-package keys when explicit URI fields are absent.

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
| `wiki_note_drafts_json` | draft | Review-only Wiki note draft previews with source-language text, wikilinked key concepts, and footnote-only Zotero/source provenance. |
| `review_packet_json` | review | Review packet with confidence, uncertainty, provenance, draft quality, and review needs. |
| `artifact_contract_manifest_json` | review / contract | Declares source/transition/proposal/draft/review/canonical boundaries and forbidden effects. |

The fixture includes one tiny PDF-like Marker markdown excerpt about close reading and expected transition/proposal/review outputs.

## Authority model

| Artifact family | Authority posture |
| --- | --- |
| source | Raw extraction/source package artifact. Zotero/source package identity remains authoritative outside DSPx. |
| transition | Regenerable section units, distillation frames, and evidence cards. |
| proposal | Merge/create candidates only; not accepted notes. |
| draft | Wiki note draft previews for review; source-language, wikilink, and footnote rules are target-fidelity constraints, not acceptance. |
| review | Human/operator review packets only. |
| canonical | Wiki/Atlas notes only after explicit review/apply outside `program-gen`. |

## Generated-program jury and adjudicator layer

This scenario declares a generated-program-level jury contract in `intent.yaml`:

```text
source_grounding
authority_boundaries
transition_artifact_quality
language_fidelity
zotero_footnote_linkage
zotero_identity_derivation
wiki_link_key_concepts
```

`program-gen` materializes those explicit perspectives into `jury.json`, `jury_selection.json`, and `jury_rubric.json` even when the intent does not bind concrete juror models. They are candidate-local evaluation contracts for the generated DSPy program. The generated-program-level promotion adjudicator is the declared DSPx AI agent (`dspx_program_adjudicator_v1`) and starts pending.

To see both adjudicator layers without making the operator the judge, run the meta-adjudication sidecar chain through `program_adjudicator_verification.json`, let the DSPx/meta adjudicator delegate local decision scope to the generated-program adjudicator, then let that generated-program adjudicator decide:

```bash
uv run --package dspx-core -q python -m dspx.cli.dspx program-promote adjudicator-delegation \
  --manifest "$TD/pdf-transition-program/manifest.json" \
  --adjudicator-verification "$TD/pdf-transition-program/program_adjudicator_verification.json" \
  --out "$TD/pdf-transition-program/program_adjudicator_delegation.json" \
  --json

uv run --package dspx-core -q python -m dspx.cli.dspx program-promote generated-adjudicator-decision \
  --evidence-adjudication "$TD/pdf-transition-program/program_evidence_adjudication.json" \
  --adjudicator-delegation "$TD/pdf-transition-program/program_adjudicator_delegation.json" \
  --out "$TD/pdf-transition-program/promotion_decision_record.json" \
  --json
```

The first command is the DSPx/meta adjudicator deciding that the generated-program adjudicator is fit to decide. The second command is the generated-program adjudicator's local decision. Both remain non-authoritative: they do not activate production, mutate the Obsidian vault, update AK/governance, or grant Oracle promotion authority.

This is separate from other DSPx/meta-adjudication sidecars such as `target_profile.json`, `meta_jury_selection.json`, `program_adjudicator_verification.json`, and `adjudication_behavior_trace.json`.

## Running an existing candidate on real PDF source-package input

After a candidate exists, use `program-run` to run that generated program against explicit runtime inputs without mutating the candidate manifest or canonical notes:

```bash
uv run --package dspx-core -q python -m dspx.cli.dspx program-run \
  --manifest "$CANDIDATE/manifest.json" \
  --inputs "$RUN_ROOT/real_pdf_input.json" \
  --outdir "$RUN_ROOT/runtime-episode" \
  --contract-mode pdf_transition_review \
  --publication-preflight-out "$RUN_ROOT/runtime-episode/program_oracle_publication_preflight.real_pdf.json" \
  --publication-target shared-postgres \
  --publication-label retained \
  --publisher-id pi-session \
  --publisher-role operator \
  --publisher-assertion 'share checked real-PDF runtime episode behavior for future Oracle retrieval and GEPA analysis; no activation or canonical note authority is granted' \
  --redaction-status checked \
  --retention-class retained_behavior_memory \
  --json
```

`real_pdf_input.json` may be either a direct input-field object or `{ "inputs": { ... } }` with the generated program's declared fields:

```json
{
  "inputs": {
    "source_package_manifest_json": "{...}\n",
    "marker_markdown": "# Extracted Marker markdown...",
    "existing_wiki_index_json": "{\"schema_version\":1,\"canonical_artifacts\":[]}",
    "declared_output_root": "transition/doc:example"
  }
}
```

The runtime episode writes:

```text
manifest.json                                # runtime manifest copy; source candidate manifest is not mutated
runtime_episode.json
runtime_inputs.json
behavior_results.json
oracle_evidence.json
oracle/coordinates.db
program_oracle_report.json
program_oracle_publication_preflight.real_pdf.json  # optional, preflight only
section_units_json
...
artifact_contract_manifest_json
```

With `--contract-mode pdf_transition_review`, the runtime fails closed unless the generated outputs preserve review-only boundaries: `canonical_mutation_performed=false`, proposal `canonical_mutation_allowed=false`, and `review_required=true`.

For Zotero-bound source packages, the program contract treats the package path and Zotero identity as separate facts:

```text
package_root: _System/pdf-pipeline/packages/doc:<hash-prefix>
source_id: zotero:user:<library>/<item_key>
item_key: <Zotero parent item key>
attachment_record_id: zotero-attachment:user:<library>/<attachment_key>
citekey: <Better BibTeX citekey when present>
```

If `zotero_item_uri` / `zotero_attachment_uri` are absent, draft footnotes should derive review links from manifest keys, for example `zotero://select/items/RBPICNTS` and `zotero://open-pdf/library/items/92FBZPLS`. This derivation does not rename the package folder and does not create source identity; it only formats already-bound Zotero identity for review.

## What this scenario does not do

It does **not**:

- mutate canonical `Wiki/` notes
- create accepted notes
- make Atlas/Wiki authority decisions
- mutate Zotero/source identity
- claim Marker extraction authority
- write external filesystem artifacts beyond the declared DSPx `program-gen` output directory
- promote a proposal to an accepted note
- translate source-language note drafts unless explicitly requested
- rename doc-id/hash-keyed source package folders to Zotero item keys or citekeys
- put source/provenance material into a separate note-draft source heading instead of footnotes
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
jury.json
jury_selection.json
jury_rubric.json
promotion_review.json
promotion_adjudication_request.json
promotion_decision_template.json
```

The fixture's expected transition artifacts are embedded as `expected_outputs` in `behavior_results.json`. With the stub provider, the behavior check may report mismatches; that is acceptable for this scenario because the test proves the generated program shape, artifact contracts, replay metadata, and authority boundaries rather than model quality.

To exercise the generated DSPy program with the default auth-backed provider/model instead of the stub, run:

```bash
export TD="$(mktemp -d)"
export DSPX_PROVIDER=dspy-lm-auth
export DSPX_LM_AUTH_MODEL=codex/gpt-5.5
export MLFLOW_ENABLE=0
export DSPX_CACHE_DIR="$TD/cache"
export DSPX_CACHE_ENABLE=1

uv run -q python -m dspx.cli.dspx program-gen \
  --intent tests/fixtures/program_gen/pdf_transition/intent.yaml \
  --outdir "$TD/pdf-transition-program" \
  --print-manifest

python3 - <<'PY'
import json, os
from pathlib import Path
out = Path(os.environ["TD"]) / "pdf-transition-program"
behavior = json.loads((out / "behavior_results.json").read_text())
print(json.dumps(behavior["summary"], indent=2, sort_keys=True))
print(json.dumps(behavior["examples"][0].get("observed_outputs"), indent=2, sort_keys=True))
PY
```

`dspy-lm-auth` defaults to `codex/gpt-5.5` when `DSPX_LM_AUTH_MODEL` is unset. The explicit export above keeps the provider-backed run auditable.

## Test coverage

The executable scenario test is:

```bash
uv run --no-sync -m pytest -q tests/test_program_gen_pdf_transition.py
```

It proves:

- `program-gen` materializes the PDF transition intent with the stub/offline provider
- the scenario preserves source/transition/proposal/review/canonical artifact-family distinctions
- expected outputs include section-unit candidates, distillation frames, evidence cards, merge/create proposals, a review packet, and an artifact contract manifest
- generated-program jury selection honors the explicit PDF-transition perspectives: `source_grounding`, `authority_boundaries`, and `transition_artifact_quality`
- no fake canonical Wiki note is mutated
- no transition files are written outside the DSPx output directory during `program-gen`
- replay metadata is inspectable and `dspx run replay --check-only` passes
- no default Oracle index is created

## Obsidian review-only adapter

The production review/proposal materialization surface is the Obsidian adapter:

```text
/home/tryinget/Documents/Obsidian/_System/pdf-pipeline/scripts/materialize_dspy_transition_review.py
```

It consumes either:

- direct generated output files named after the DSPx output fields; or
- a DSPx generated-program candidate root containing `behavior_results.json` with `observed_outputs`.

Example live-provider flow:

```bash
export TD="$(mktemp -d)"
export DSPX_PROVIDER=dspy-lm-auth
export DSPX_LM_AUTH_MODEL=codex/gpt-5.5
export MLFLOW_ENABLE=0
export DSPX_CACHE_DIR="$TD/cache"
export DSPX_CACHE_ENABLE=1
export DSPX_ORACLE_EMBEDDING_BACKEND=mock

uv run --package dspx-core -q python -m dspx.cli.dspx program-loop \
  --intent tests/fixtures/program_gen/pdf_transition/intent.yaml \
  --outdir "$TD/pdf-transition-program" \
  --json

python /home/tryinget/Documents/Obsidian/_System/pdf-pipeline/scripts/materialize_dspy_transition_review.py \
  --input-dir "$TD/pdf-transition-program" \
  --json
```

The adapter writes only to the approved review/proposal surface:

```text
_System/review/proposals/pdf-transition/<doc-id>/
```

It refuses generated bundles that do not declare `canonical_mutation_performed=false`, `canonical_mutation_allowed=false`, and `review_required=true`. Its receipt records `wiki_mutation_performed=false`, `atlas_mutation_performed=false`, `zotero_mutation_performed=false`, `source_package_mutation_performed=false`, and `puzzle_register_mutation_performed=false`.

Latest dogfood evidence: `docs/project/2026-05-09-obsidian-pdf-transition-live-adapter-dogfood.md`.

## Current limitation

This is now a generated-program scenario plus a review-only Obsidian materialization adapter, not a canonical Wiki/Atlas activation path.

The adapter can materialize provider-backed generated transition/proposal artifacts for review. It still does **not** accept proposals, write canonical notes, bind production authority, or replace the owning domain/governance decision path.
