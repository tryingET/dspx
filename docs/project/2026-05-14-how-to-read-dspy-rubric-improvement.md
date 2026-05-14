---
summary: "Receipt for using How to Read a Paragraph as a close-reading rubric to improve the PDF-transition DSPy program fixture and jury contract."
read_when:
  - "You are checking the 2026-05-14 How-to-Read DSPy program-improvement dogfood slice."
  - "You need the evidence path for the purpose/authorial-structure/metacognitive PDF-transition jury additions."
type: "evidence"
---

# How-to-Read DSPy rubric improvement receipt

Date: 2026-05-14

## Purpose

Use the accepted/reviewed *How to Read a Paragraph* dogfood bundle as a rubric for improving the `pdf-transition-program-gen` scenario, rather than treating the generated notes only as vault content.

## Change made

The PDF-transition program intent now asks generated artifacts to expose:

- reading purpose;
- authorial purpose;
- document / argument structure role;
- elements of thought where inferable;
- paragraph-scale evidence linkage;
- source-grounding uncertainty;
- puzzle-fit / merge-before-create rationale.

The generated-program jury contract now includes these additional perspectives:

```text
purpose_framing
authorial_purpose_and_structure
metacognitive_uncertainty
```

The fixture expected outputs carry the rubric through distillation frames, evidence cards, merge/create proposals, Wiki drafts, review packets, and artifact-contract requirements.

## Validation

Targeted tests:

```bash
uv run pytest tests/test_program_gen_pdf_transition.py -q
uv run pytest tests/test_program_generation_contract.py tests/test_program_service.py::test_program_gen_cli_materializes_explicit_perspectives_without_bound_jurors -q
uv run ruff check packages/dspx-core/src/dspx/services/program_jury.py tests/test_program_gen_pdf_transition.py
uv run ruff format --check packages/dspx-core/src/dspx/services/program_jury.py tests/test_program_gen_pdf_transition.py
```

Observed:

```text
3 passed
16 passed
ruff check: passed
ruff format --check: passed
```

## Dogfood generation evidence

Local temp root:

```text
/tmp/dspx-how-to-read-rubric.b5V17N
```

Commands performed the target-fidelity sequence:

```text
intent.yaml
-> generation_target_contract.json
-> generation_fitness_suite.json
-> generation_gate_preflight.json
-> gated program-gen candidate
-> generation_traceability.json
-> generation_fitness_results.json
```

Observed summary:

```json
{
  "candidate": "/tmp/dspx-how-to-read-rubric.b5V17N/program",
  "assembly_id": "prog-asm-4bb4ec921c4c",
  "preflight_status": "generation_allowed",
  "fitness_status": "fitness_passed",
  "fitness_rendered_state": "eligible_for_downstream_evidence_review",
  "jury_minimum": 11,
  "new_perspectives": [
    "purpose_framing",
    "authorial_purpose_and_structure",
    "metacognitive_uncertainty"
  ]
}
```

A stub-provider runtime replay against the previous real `doc:a6112bfb` inputs was intentionally non-authoritative and degraded because the stub provider emitted non-JSON output for JSON-string fields. This is useful feedback: the fixture/rubric contract improved, but a real model-backed replay is still required before claiming the generated program became a better close reader.

Runtime evidence:

```text
/tmp/dspx-how-to-read-rubric.b5V17N/runtime
/tmp/dspx-how-to-read-rubric.b5V17N/program_run.stdout.json
```

Observed runtime status:

```text
status: degraded
runtime_execution.status: failed_boundary
reason: stub/echo output was not valid JSON for the PDF-transition JSON-string outputs
```

## Authority boundary

This slice does not:

- promote or activate a generated program;
- mutate Obsidian Wiki/Atlas/Zotero/source packages;
- claim production readiness;
- rank, select, or deploy a candidate.

It improves the fixture/intent/jury contract and records that the next real experiment step is a model-backed rerun/comparison.
