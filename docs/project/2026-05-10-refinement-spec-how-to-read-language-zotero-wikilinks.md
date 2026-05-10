---
summary: "Refinement spec derived from the How to Read a Paragraph dogfood run: source-language fidelity, Zotero footnotes, wikilinked key concepts, and no source heading blocks."
created: 2026-05-10
system4d_domain: dspx
read_when:
  - "You need the refinement target for the Obsidian PDF generated DSPy program after the How to Read a Paragraph run."
  - "You are checking why pdf-transition-program-gen now emits Wiki note draft previews with language fidelity, Zotero footnotes, and wikilinks."
tags:
  - dspx
  - obsidian
  - generated-program
  - pdf-transition
  - refinement
---

# Refinement spec: How to Read language/Zotero/wikilink target

AK task: `AK-2792` completed.

## Problem observed in the dogfood run

The `How to Read a Paragraph` run proved that the generated Obsidian/PDF DSPy program can produce useful section units, evidence cards, merge/create proposals, and review packets. The all-12 operator-review seed materialization also exposed product-fit gaps in the note shape:

1. English source text produced mixed-language note scaffolding in the downstream materialization.
2. Source evidence was too visible as a note section instead of living in footnotes.
3. Zotero/source-package links were not first-class in note-draft provenance.
4. Durable key concepts were not systematically emitted as Obsidian `[[wikilinks]]`.
5. The generated program did not produce a note-draft preview output field; downstream scripts had to infer the note shape from proposals and evidence cards.

## Refinement target

For Obsidian/PDF transition, the generated DSPy program target contract now includes a new review-only draft artifact:

```text
wiki_note_drafts_json
```

The draft artifact must obey these rules:

- **Language fidelity:** detect and preserve source language. If the source is English, draft note headings, labels, body prose, warning text, and review questions should be English unless quoting non-English source text.
- **Footnote-only provenance:** source evidence belongs in footnotes / `footnotes` records, not in a separate `Source`, `Quelle`, `Provenance`, or `Quelle und Beleg` heading block.
- **Zotero-first linkage:** when source package metadata carries Zotero item or attachment refs, footnotes should prefer those links/refs and also keep page/section/Marker references.
- **Wikilink key concepts:** durable concepts, methods, frameworks, and sibling candidate notes should be emitted as `[[...]]`; ordinary words should not be overlinked.
- **Review-only status:** drafts may preview target Wiki note content, but they must not claim accepted canonical status or mutate files.

## Implementation changes

Updated target intent:

```text
tests/fixtures/program_gen/pdf_transition/intent.yaml
```

Key additions:

- output field: `wiki_note_drafts_json`
- constraints for source-language fidelity, footnote-only provenance, Zotero-first linkage, and wikilinked key concepts
- authority model includes `draft`
- forbidden effects include source-language translation without request and separate source/provenance heading blocks
- jury perspectives now include:
  - `language_fidelity`
  - `zotero_footnote_linkage`
  - `wiki_link_key_concepts`

Updated fixture example:

```text
tests/fixtures/program_gen/pdf_transition/examples.yaml
```

The example now includes Zotero item/attachment metadata and an expected English draft note preview containing:

- English headings (`Core Idea`, `Review Questions`)
- `[[Close Reading]]`, `[[Paraphrase]]`, `[[Thesis Extraction]]`, `[[Logic Analysis]]`
- a footnote with Zotero item and attachment links
- no source/provenance heading block

Updated jury rubrics:

```text
packages/dspx-core/src/dspx/services/program_jury.py
```

Added explicit criteria for:

- source-language preservation;
- review text language consistency;
- Zotero refs preferred;
- source provenance in footnotes only;
- durable concepts wikilinked;
- ordinary words not overlinked.

## Regeneration / dogfood command

Regenerate a candidate from the refined target contract:

```bash
TD="$(mktemp -d /tmp/dspx-pdf-transition-refined.XXXXXX)"
export DSPX_PROVIDER=dspy-lm-auth
export DSPX_LM_AUTH_MODEL=codex/gpt-5.5
export MLFLOW_ENABLE=0
export DSPX_CACHE_DIR="$TD/cache"
export DSPX_CACHE_ENABLE=1

uv run -q python -m dspx.cli.dspx program-gen \
  --intent tests/fixtures/program_gen/pdf_transition/intent.yaml \
  --outdir "$TD/pdf-transition-program" \
  --print-manifest
```

The refined candidate must declare `wiki_note_drafts_json` in `manifest.json`, materialize `jury.json` with six perspectives, and treat note drafts as review-only artifacts.

## Dogfood result

A regenerated auth-backed candidate was materialized at:

```text
/tmp/dspx-pdf-transition-refined.2CN0wD/pdf-transition-program
```

Candidate id:

```text
prog-cand-4a967f43298d
```

It declared outputs:

```text
section_units_json
distillation_frames_json
evidence_cards_json
merge_create_proposals_json
wiki_note_drafts_json
review_packet_json
artifact_contract_manifest_json
```

It declared jury perspectives:

```text
source_grounding
authority_boundaries
transition_artifact_quality
language_fidelity
zotero_footnote_linkage
wiki_link_key_concepts
```

The refined candidate was then run on `How to Read a Paragraph` at:

```text
/tmp/dspx-how-to-read-refined-run.DC8lR1/runtime
```

Observed result:

- runtime status: `ok`
- `wiki_note_drafts_json` exists
- draft count: `2`
- draft language: `en`
- draft prose/headings are English
- key concepts include Obsidian wikilinks such as `[[How to Read a Paragraph]]`, `[[Close Reading]]`, `[[Purposeful Reading]]`, `[[Structural Reading]]`, and `[[Reflective Reading]]`
- provenance appears in footnotes, with source-package fallback because this bounded source manifest had no Zotero item/attachment URI
- no canonical Wiki/Atlas mutation occurred

One expected limitation remains: because the `How to Read a Paragraph` source was not bound to a real Zotero item in this bounded run, the refined program used source package / PDF path / attachment hash / Marker path fallback in footnotes. Zotero linkage is ready in the target contract when those refs are present.

## Verification

Required local checks:

```bash
uv run --no-sync -m pytest -q tests/test_program_gen_pdf_transition.py
node ~/ai-society/core/agent-scripts/scripts/docs-list.mjs --docs . --strict
just task-scope-check task_id=2792 mode=working-tree
just verify-fast
```

## Boundary

This refinement improves the generated program target and fixture contract. It does not itself promote any generated program, mutate Obsidian Wiki/Atlas, publish to Oracle/Postgres, change Zotero, or activate production runtime routing.

Next product slice after this refinement:

1. regenerate with the auth-backed provider;
2. rerun `How to Read a Paragraph`;
3. compare old all-12 notes against new `wiki_note_drafts_json` previews;
4. only then update Obsidian materialization/apply surfaces to consume the draft field directly.
