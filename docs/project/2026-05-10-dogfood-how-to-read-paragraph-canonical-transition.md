---
summary: "Dogfood run of the Obsidian/PDF generated DSPy program on How to Read a Paragraph, followed by bounded canonical Wiki seed apply."
created: 2026-05-10
system4d_domain: dspx
read_when:
  - "You need the current dogfood result for running the generated Obsidian/PDF DSPy program on How to Read a Paragraph."
  - "You need to know whether the How to Read a Paragraph run created canonical Wiki/Atlas notes or production activation."
tags:
  - dspx
  - obsidian
  - generated-program
  - pdf-transition
  - dogfood
---

# Dogfood: How to Read a Paragraph canonical transition

AK task: `AK-2785`.

## Intent

Use the real Obsidian source `How to Read a Paragraph.pdf` as the first exemplar for the generated DSPy PDF-transition program, then cross the smallest lawful canonical boundary: one reviewed Wiki seed note, not a broad production activation claim.

## Source

- PDF: `/home/tryinget/Documents/Obsidian/20-29_Input/23_Schriftliches/23.06_PDFs/How to Read a Paragraph.pdf`
- Existing Marker/postprocess run: `/home/tryinget/Documents/Obsidian/_System/pdf-pipeline/runs/2026-04-21-gpu-queue-batch/008-how-to-read-a-paragraph/`
- Source document id used for this bounded run: `doc:a6112bfb`
- PDF sha256: `a6112bfb80ed1aff51f5b108ca349300dedc116de645785fe377595e1e7bcbaf`

## Runtime evidence

Generated-program runtime root:

```text
/tmp/dspx-how-to-read-run.DTXiRz/runtime
```

Command class:

```bash
uv run dspx program-run \
  --manifest /tmp/dspx-target-fidelity-next-pdf.ZCg2c0/program/manifest.json \
  --inputs /tmp/dspx-how-to-read-run.DTXiRz/runtime_inputs.json \
  --outdir /tmp/dspx-how-to-read-run.DTXiRz/runtime \
  --contract-mode pdf_transition_review \
  --json
```

Observed effect summary:

- status: `ok`
- canonical notes mutated by DSPx runtime: `false`
- governance / AK mutated by DSPx runtime: `false`
- local runtime Oracle sidecars written: `true`
- shared Oracle mutated: `false`

The run produced:

- 13 section-unit candidates
- 12 evidence cards
- 12 merge/create proposals
- review packet state: `needs_review`
- all generated proposals initially targeted `Wiki/*.md` with `canonical_mutation_allowed=false`

## Obsidian review materialization

Review packet:

```text
/home/tryinget/Documents/Obsidian/_System/review/proposals/pdf-transition/doc:a6112bfb/dspy-review-packet.md
```

Review page:

```text
/home/tryinget/Documents/Obsidian/_System/review/proposals/pdf-transition/doc:a6112bfb/review.html
```

Adapter receipt:

```text
/home/tryinget/Documents/Obsidian/_System/review/proposals/pdf-transition/doc:a6112bfb/adapter-receipt.json
```

Adapter validation passed:

```bash
cd /home/tryinget/Documents/Obsidian
uv run python _System/pdf-pipeline/scripts/validate_dspy_transition_review_adapter.py
```

## Adjudication result

DSPx/generated-program adjudication was run against the new `How to Read a Paragraph` runtime evidence.

Artifacts:

```text
/tmp/dspx-how-to-read-run.DTXiRz/adjudication/program_evidence_adjudication.json
/tmp/dspx-how-to-read-run.DTXiRz/adjudication/generated_adjudicator_decision.json
```

Outcome:

- generated-program adjudicator outcome: `request_more_evidence`
- activation approved: `false`
- production activation claim: `false`

This means the generated program is useful for domain review, but it did not become a production-activated canonical mutation runtime.

## Merge-before-create review

The generated program proposed 12 `create` actions because the supplied canonical index was empty. That is not sufficient for production canonical creation.

A bounded duplicate/merge check found existing reading-strategy context, especially:

- `/home/tryinget/Documents/Obsidian/00-09_meta/08_Wissen-allg.Wissenschaft,Didaktik,KI,Mathematik,Naturwissenschaften/Lesestrategien.md`
- `/home/tryinget/Documents/Obsidian/60-69_UmweltUndKontext/63_BeruflicheEntwicklung/63.05_Lehrer/Schule/Lesen/Übersicht diverser Lesestrategien als MarkdownTabelle.md`

Source-grounding quote check against the Marker postprocess markdown found:

- 9 exact/normalized quote hits used in the accepted seed note
- 3 generated quote strings requiring tighter source checking before separate canonical concept notes

## Canonical apply performed

A separate bounded owner-side apply step created one conservative Wiki seed note:

```text
/home/tryinget/Documents/Obsidian/Wiki/How to Read a Paragraph.md
```

Apply receipt:

```text
/home/tryinget/Documents/Obsidian/_System/review/proposals/pdf-transition/doc:a6112bfb/canonical-apply-receipt.json
```

The receipt records:

- `wiki_mutation_performed=true`
- `canonical_mutation_performed=true`
- `atlas_mutation_performed=false`
- `zotero_mutation_performed=false`
- `source_package_mutation_performed=false`
- `puzzle_register_mutation_performed=false`
- production activation claim: `false`

Why only one note:

- `merge-before-create` says create is last resort.
- The 12 generated concept proposals were generated from an empty canonical index.
- One source seed note preserves reusable understanding without note explosion.
- Separate concept notes and Atlas board work remain deferred until merge/review is stronger.

## Verification

```bash
cd /home/tryinget/Documents/Obsidian
python -m json.tool _System/review/proposals/pdf-transition/doc:a6112bfb/canonical-apply-receipt.json
uv run python _System/pdf-pipeline/scripts/validate_dspy_transition_review_adapter.py
python - <<'PY'
from pathlib import Path
note = Path('Wiki/How to Read a Paragraph.md')
text = note.read_text(encoding='utf-8')
required = [
    '[^purpose-driven-reading]', '[^author-purpose]', '[^map-of-knowledge]',
    '[^reflective-reading]', '[^elements-of-thought]', '[^five-levels-close-reading]',
    '[^structural-reading]', '[^paragraph-reading]', '[^logic-analysis-template]',
]
missing = [ref for ref in required if text.count(ref) < 2]
if missing:
    raise SystemExit(f'missing footnote refs/defs: {missing}')
print('note_ok')
PY
```

Observed:

```text
note_ok
adapter validation status: ok
```

## Current truth

This dogfood **did** create a real bounded canonical Wiki note from the generated-program review path.

It **did not** production-activate the generated program as an autonomous canonical Wiki/Atlas mutation runtime.

Next useful slice:

1. build a fuller existing-canonical index for Obsidian reading/learning notes;
2. rerun the generated program with that index;
3. convert some proposals from `create` to `enrich` or `board-only`;
4. add a real apply/preflight surface if we want repeatable canonical Wiki/Atlas promotion instead of one bounded manual apply.
