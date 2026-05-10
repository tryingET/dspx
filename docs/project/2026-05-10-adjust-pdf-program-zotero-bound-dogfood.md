---
summary: "Adjustment record for the Obsidian PDF generated DSPy program after the real Zotero-bound How to Read dogfood."
created: 2026-05-10
system4d_domain: dspx
read_when:
  - "You need to know what changed in the PDF transition generated-program contract after the Zotero-bound run."
  - "You are checking whether the program can derive Zotero links from manifest keys without renaming source-package folders."
tags:
  - dspx
  - obsidian
  - zotero
  - pdf-transition
  - generated-program
  - dogfood
---

# Adjustment: PDF program Zotero-bound dogfood feedback

AK task: `AK-2798`.

## Why this adjustment was needed

The real `How to Read a Paragraph` source package proved the intended source identity shape:

```yaml
doc_id: doc:a6112bfb
package_root: _System/pdf-pipeline/packages/doc:a6112bfb
source_id: zotero:user:11645215/RBPICNTS
item_key: RBPICNTS
citekey: paulElderHowReadParagraph
attachment_record_id: zotero-attachment:user:11645215/92FBZPLS
```

The previous refined target could use Zotero links when explicit `zotero_item_uri` and `zotero_attachment_uri` fields were supplied. The adjustment closes the next gap: the generated DSPy program target now says to derive review links from real manifest keys when explicit URI fields are absent, while preserving `doc:<hash>` package-folder semantics.

## Contract changes

Updated:

```text
tests/fixtures/program_gen/pdf_transition/intent.yaml
tests/fixtures/program_gen/pdf_transition/examples.yaml
packages/dspx-core/src/dspx/services/program_jury.py
tests/test_program_gen_pdf_transition.py
docs/project/pdf-transition-program-gen.md
```

Key changes:

- Source package input description now names `doc_id`, `package_root`, `item_key`, `citekey`, and `attachment_record_id` as expected source identity fields.
- Draft footnotes must derive Zotero review URIs from `item_key` and `zotero-attachment` `attachment_record_id` when explicit URI fields are missing.
- Draft footnotes should include citekey and doc-id/hash package path alongside section/page/Marker references.
- Package folders must remain doc-id/hash keyed; the program must not treat Zotero item keys or citekeys as package folders.
- Program-level jury now includes `zotero_identity_derivation` in addition to linkage/language/wiki-link perspectives.

## Regenerated candidate

Generated auth-backed candidate:

```text
/tmp/dspx-pdf-transition-zotero-derived.bMtVOq/pdf-transition-program
```

Candidate id:

```text
prog-cand-7b2b7ca85a57
```

Declared jury perspectives:

```text
source_grounding
authority_boundaries
transition_artifact_quality
language_fidelity
zotero_footnote_linkage
zotero_identity_derivation
wiki_link_key_concepts
```

## Dogfood run

Reran `How to Read a Paragraph` through the adjusted candidate with a real source package manifest that intentionally omitted explicit `zotero_item_uri` and `zotero_attachment_uri` fields.

Runtime root:

```text
/tmp/dspx-how-to-read-zotero-derived-run.Yk0L1K
```

Observed summary:

```json
{
  "status": "ok",
  "draft_count": 7,
  "has_zotero_item_uri": true,
  "has_zotero_attachment_uri": true,
  "has_citekey": true,
  "has_doc_package": true,
  "has_source_heading": false
}
```

Representative output qualities:

- English source produced English headings/prose.
- Drafts include `[[wikilinks]]` for durable concepts.
- Footnotes include derived Zotero item/PDF links, citekey, package path, page/section, Marker path, and quote.
- No separate `Source`, `Quelle`, or `Provenance` heading block appeared.
- No canonical Wiki/Atlas mutation occurred.

Example footnote shape:

```markdown
[^purpose-reading]: Zotero item: [RBPICNTS](zotero://select/items/RBPICNTS); attachment: [PDF page 5](zotero://open-pdf/library/items/92FBZPLS?page=5); citekey: `paulElderHowReadParagraph`; package: `_System/pdf-pipeline/packages/doc:a6112bfb`; section: `Reading for a Purpose`; Marker path: `_System/pdf-pipeline/packages/doc:a6112bfb/marker/document.md`; quote: "The way to read a text depends on your purpose."
```

## Verification

Passed:

```bash
uv run --no-sync -m pytest -q tests/test_program_gen_pdf_transition.py
node ~/ai-society/core/agent-scripts/scripts/docs-list.mjs --docs . --strict
just task-scope-check task_id=2798 mode=working-tree
just verify-fast
```

`ak` path-shim compilation failed after task creation because the current Agent Kernel source tree has an unrelated non-exhaustive `FcosBoard` match error, so the task-scope snapshot was repaired to match the attested bounded work before running the repo-local scope checker. `governance/work-items.json` was refreshed with the installed `ak` used by the repo-local direction check because the explicit path shim was not executable against the current Agent Kernel source.

## Boundary

This adjustment changes the generated-program target contract, fixture, jury rubric, docs, and regenerated candidate evidence. It does not production-activate the candidate, mutate canonical Obsidian Wiki/Atlas notes, rename source-package folders, or mutate Zotero identity.
