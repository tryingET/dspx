---
summary: "Adjustment record for separating review artifact, proposed note, and source/work frontmatter in the Obsidian PDF generated DSPy program."
created: 2026-05-10
system4d_domain: dspx
read_when:
  - "You need the current frontmatter contract for generated Obsidian PDF Wiki draft previews."
  - "You are checking why source material type is separate from proposed note kind."
tags:
  - dspx
  - obsidian
  - pdf-transition
  - generated-program
  - frontmatter
  - ontology
---

# Adjustment: frontmatter roles for PDF generated program

AK task: `AK-2807`.

## Problem

The previous refined generated program emitted useful English, Zotero-linked, wikilinked draft Markdown, but the draft frontmatter still collapsed multiple roles into one small block:

```yaml
artifact_type: wiki_note
state: operator_review_seed
review_seed: true
source_language: en
```

That is useful as a temporary review seed, but it is not the vault frontmatter architecture. It also blurs three different things:

1. the generated review artifact;
2. the proposed canonical Wiki/Atlas note;
3. the Zotero/source-work identity.

## Decision

The generated program target now requires role-separated frontmatter planning.

New output:

```text
frontmatter_plans_json
```

The program must separate:

| Role | Structure | Meaning |
| --- | --- | --- |
| Review artifact | `review_artifacts[]` / per-draft `review_artifact_frontmatter` | Generated review object, pending review, no canonical mutation. |
| Proposed note | `proposed_notes[]` / per-draft `proposed_note_frontmatter` | The Wiki/Atlas note frontmatter that would be used if accepted. |
| Source/work | `source_work_candidates[]` | Source/work note identity using Zotero/source metadata. |

## Source material type vs note kind

The user's wording was right in spirit: different source kinds matter. The sharper contract is:

- preserve `source_material_type` / `work_type` separately (`guide`, `book`, `paper`, `article`, `report`, `chapter`, `transcript`, `webpage`, `unknown`);
- choose proposed note `kind` from the role of the content (`concept`, `framework`, `method`, `source`, `person`, `board`, etc.);
- a PDF source can yield one source/work note plus many concept/method/framework Wiki notes.

For `How to Read a Paragraph`, the source is a guide, but `Purpose-Driven Reading` is a `concept`, while `Five Levels of Close Reading` and `Structural Reading` are better as `method` candidates.

## Implementation changes

Updated:

```text
tests/fixtures/program_gen/pdf_transition/intent.yaml
tests/fixtures/program_gen/pdf_transition/examples.yaml
packages/dspx-core/src/dspx/services/program_jury.py
tests/test_program_gen_pdf_transition.py
docs/project/pdf-transition-program-gen.md
```

Added generated-program jury perspective:

```text
ontological_role_separation
```

Rubric criteria:

```text
review_note_source_roles_separated
source_material_type_not_confused_with_note_kind
```

## Regenerated candidate

Auth-backed candidate:

```text
/tmp/dspx-pdf-transition-frontmatter-roles.xvzVkb/pdf-transition-program
```

Candidate id:

```text
prog-cand-14746cb9b56c
```

Declared outputs now include:

```text
frontmatter_plans_json
```

Declared jury perspectives:

```text
source_grounding
authority_boundaries
transition_artifact_quality
language_fidelity
zotero_footnote_linkage
zotero_identity_derivation
ontological_role_separation
wiki_link_key_concepts
```

## Dogfood run

Reran `How to Read a Paragraph` through the adjusted candidate using the real Zotero-bound source package input with explicit Zotero URI fields omitted.

Runtime root:

```text
/tmp/dspx-how-to-read-frontmatter-roles-run.2GCuZW
```

Observed summary:

```json
{
  "status": "ok",
  "draft_count": 5,
  "has_frontmatter_plans": true,
  "has_review_artifact_frontmatter": true,
  "has_proposed_note_frontmatter": true,
  "has_source_work_frontmatter": true,
  "has_zotero_item_uri": true,
  "has_citekey": true,
  "has_doc_package": true,
  "has_source_heading": false
}
```

Example proposed note frontmatter in draft Markdown:

```yaml
space: wiki
domain: reading
kind: concept
state: seed
title: Purpose-Driven Reading
source_language: en
source_ids:
  - zotero:user:11645215/RBPICNTS
citekeys:
  - paulElderHowReadParagraph
doc_ids:
  - doc:a6112bfb
confidence: 0.88
needs_review: true
```

The review artifact frontmatter remains outside the proposed note frontmatter:

```json
{
  "artifact_type": "wiki_note_draft_preview",
  "state": "proposed",
  "review_status": "pending",
  "canonical_mutation_performed": false,
  "generated_by": "dspx-pdf-transition-program-gen",
  "draft_id": "draft:doc-a6112bfb:purpose-driven-reading",
  "doc_id": "doc:a6112bfb",
  "source_id": "zotero:user:11645215/RBPICNTS"
}
```

## Verification

Passed:

```bash
uv run --no-sync -m pytest -q tests/test_program_gen_pdf_transition.py
uv run --no-sync ruff check packages/dspx-core/src/dspx/services/program_jury.py tests/test_program_gen_pdf_transition.py
node ~/ai-society/core/agent-scripts/scripts/docs-list.mjs --docs . --strict
just task-scope-check task_id=2807 mode=working-tree
just verify-fast
```

## Boundary

This is a generated-program target-contract and candidate-dogfood adjustment. It does not production-activate the candidate, mutate Obsidian Wiki/Atlas, create source/work notes, or apply canonical frontmatter to the vault.
