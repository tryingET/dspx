---
summary: "Dogfood proof that How to Read a Paragraph now has a real Zotero-bound source package and the refined PDF DSPy program can emit Zotero-linked English note drafts from it."
created: 2026-05-10
system4d_domain: dspx
read_when:
  - "You need the current Zotero/source-package binding state for How to Read a Paragraph."
  - "You are checking whether the refined Obsidian PDF generated program can use real Zotero source identity in footnotes."
tags:
  - dspx
  - obsidian
  - zotero
  - pdf-transition
  - generated-program
  - dogfood
---

# Dogfood: How to Read Zotero-bound source package

AK task: `AK-2795` completed.

## Question answered

The package folder is **not** the Zotero key. Per Obsidian PDF architecture, the durable extraction package is keyed by the verified attachment hash:

```text
_System/pdf-pipeline/packages/doc:a6112bfb/
```

The Zotero identity lives in the source package manifest and source registry manifest:

```yaml
source_id: zotero:user:11645215/RBPICNTS
item_key: RBPICNTS
citekey: paulElderHowReadParagraph
attachment_record_id: zotero-attachment:user:11645215/92FBZPLS
```

## Real Zotero bind

A real live Zotero item now exists for `How to Read a Paragraph`:

- Zotero item key: `RBPICNTS`
- Zotero source id: `zotero:user:11645215/RBPICNTS`
- Zotero attachment key: `92FBZPLS`
- attachment id/hash: `sha256:a6112bfb80ed1aff51f5b108ca349300dedc116de645785fe377595e1e7bcbaf`
- doc id: `doc:a6112bfb`
- citekey: `paulElderHowReadParagraph`

The first live-create attempt created the Zotero parent but returned `deferred_review` due an `extra` field drift. A reviewed retry aligned the stable extra field surface and succeeded as `reused` with one verified attachment.

Committed Obsidian evidence:

```text
/home/tryinget/Documents/Obsidian/_System/pdf-pipeline/runs/2026-04-21-gpu-queue-batch/008-how-to-read-a-paragraph/provider/pdf-intake.jsonl
/home/tryinget/Documents/Obsidian/_System/pdf-pipeline/runs/2026-04-21-gpu-queue-batch/008-how-to-read-a-paragraph/provider/candidate-overrides.reviewed-extra.json
/home/tryinget/Documents/Obsidian/_System/pdf-pipeline/runs/2026-04-21-gpu-queue-batch/008-how-to-read-a-paragraph/provider/source-zotero-transport.live.reviewed-extra.json
/home/tryinget/Documents/Obsidian/_System/pdf-pipeline/runs/2026-04-21-gpu-queue-batch/008-how-to-read-a-paragraph/provider/zotero-bind.live.reviewed-extra.json
/home/tryinget/Documents/Obsidian/_System/pdf-pipeline/runs/2026-04-21-gpu-queue-batch/008-how-to-read-a-paragraph/provider/source-package-runtime.live.reviewed-extra.stdout.json
```

Obsidian commit:

```text
56e2eff1b feat: bind How to Read PDF source package to Zotero
```

## Externalized source package authority

Materialized source package manifest:

```text
/home/tryinget/Documents/Obsidian-externalized/_System/pdf-pipeline/packages/doc:a6112bfb/manifest.yaml
```

Materialized source registry manifest:

```text
/home/tryinget/Documents/Obsidian-externalized/_System/source-registry/zotero/manifests/user_11645215/RBPICNTS.yaml
```

Key manifest facts:

```yaml
doc_id: doc:a6112bfb
source_id: zotero:user:11645215/RBPICNTS
library_scope: user:11645215
item_key: RBPICNTS
title: 'How to Read a Paragraph: The Art of Close Reading'
citekey: paulElderHowReadParagraph
attachment_record_id: zotero-attachment:user:11645215/92FBZPLS
package_root: _System/pdf-pipeline/packages/doc:a6112bfb
source_pdf_path: _System/pdf-pipeline/packages/doc:a6112bfb/source.pdf
```

## Validation

The real run bundle validator passed:

```bash
cd /home/tryinget/Documents/Obsidian
uv run _System/pdf-pipeline/scripts/validate_pdf_run_bundle.py \
  --provider-jsonl _System/pdf-pipeline/runs/2026-04-21-gpu-queue-batch/008-how-to-read-a-paragraph/provider/pdf-intake.jsonl \
  --package-manifest /home/tryinget/Documents/Obsidian-externalized/_System/pdf-pipeline/packages/doc:a6112bfb/manifest.yaml \
  --source-manifest /home/tryinget/Documents/Obsidian-externalized/_System/source-registry/zotero/manifests/user_11645215/RBPICNTS.yaml \
  --review-queue /home/tryinget/Documents/Obsidian-externalized/_System/pdf-pipeline/review/pdf-transition-review-queue.jsonl \
  --replay-cache /home/tryinget/Documents/Obsidian-externalized/_System/pdf-pipeline/indexes/source-package-replay.jsonl \
  --bind-payload _System/pdf-pipeline/runs/2026-04-21-gpu-queue-batch/008-how-to-read-a-paragraph/provider/zotero-bind.live.reviewed-extra.json \
  --transport-result _System/pdf-pipeline/runs/2026-04-21-gpu-queue-batch/008-how-to-read-a-paragraph/provider/source-zotero-transport.live.reviewed-extra.json \
  --expected-transport-status succeeded \
  --expected-transport-action reused \
  --receipt-jsonl /home/tryinget/Documents/Obsidian-externalized/_System/source-inbox/receipts/2026-05-10/pdf-intake.adapter-receipts.jsonl \
  --receipt-id rcp:pdf-intake:e7de91d45e8f83de4ae8a109:2 \
  --expected-outcome accepted_updated
```

Observed summary:

```json
{
  "status": "ok",
  "doc_id": "doc:a6112bfb",
  "source_id": "zotero:user:11645215/RBPICNTS",
  "bind_summary": {
    "item_key": "RBPICNTS",
    "attachment_count": 1
  },
  "transport_summary": {
    "status": "succeeded",
    "action": "reused"
  }
}
```

## Refined program dogfood with real source identity

The refined generated candidate from `AK-2792` was rerun against the Zotero-bound source package.

Runtime root:

```text
/tmp/dspx-how-to-read-zotero-bound-refined-run.VbJkhj/runtime
```

The runtime input used the real source package manifest plus derived Zotero URIs:

```text
zotero://select/items/RBPICNTS
zotero://open-pdf/library/items/92FBZPLS
```

Observed `wiki_note_drafts_json` improvement:

- source language: `en`
- draft text/headings: English
- wikilinks include `[[How to Read a Paragraph]]`, `[[Purpose-Driven Reading]]`, `[[Reflective Reading]]`, `[[Five Levels of Close Reading]]`, `[[Structural Reading]]`, `[[Map of Knowledge]]`
- footnote includes Zotero item and attachment links
- no source/provenance heading block
- no canonical Wiki/Atlas mutation

Representative footnote output:

```markdown
[^paul-elder-guide]: Zotero item: [RBPICNTS](zotero://select/items/RBPICNTS); attachment: [PDF](zotero://open-pdf/library/items/92FBZPLS); section: `The Theory`; Marker path: `_System/pdf-pipeline/packages/doc:a6112bfb/marker/document.md`; quote: "Reading is a form of intellectual work."
```

## Current truth

- The Zotero/source-package side is now real for this PDF.
- The package folder remains `doc:a6112bfb`, not the Zotero key.
- The Zotero key and attachment key are now available for generated-program footnotes.
- The refined generated program can use them in note-draft previews.
- This is still not production activation; it is verified source binding plus generated-program dogfood evidence.
