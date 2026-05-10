---
summary: "Dogfood receipt for codifying quarantined Obsidian/PDF DSPy outputs as target-fidelity negative fixtures."
read_when:
  - "You are checking whether old PDF transition DSPy outputs can enter review."
  - "You are continuing target-fidelity fixture/adjudication hardening."
type: "evidence"
---

# Target-fidelity negative fixtures for quarantined PDF outputs

Date: 2026-05-10
Task: AK-2743

## Scope

This slice turns the old quarantined Obsidian/PDF DSPy review outputs into explicit DSPx negative fixtures.

It does not re-activate those outputs, copy their full content into DSPx, mutate Obsidian `Wiki/` or `Atlas/`, publish Oracle evidence, or assign GEPA labels.

## Fixture added

```text
tests/fixtures/program_gen/pdf_transition/quarantined_invalid_outputs.json
```

The fixture records the four quarantined pre-target-fidelity outputs by doc id and quarantine-hash evidence:

```text
doc:46c8f2bb
doc:deddff66
doc:f7cf59ed
doc:pdf-transition-demo
```

Each fixture record declares:

- `classification = quarantined_invalid_or_untrusted`;
- missing Wave 3 target-fidelity sidecars;
- expected generation-fitness state `target_fidelity_unknown`;
- expected meta-adjudication judgment `needs_more_evidence`;
- non-authority status for canonical acceptance, production activation, domain approval, and GEPA training.

## Tests added

Generation target-fidelity tests now prove:

- the quarantine fixture shape is explicit and non-authoritative;
- missing traceability keeps generation fitness at `target_fidelity_unknown` rather than review-eligible;
- uncovered traceability yields `fitness_failed` / `withheld_for_target_protocol_failure`.

Meta-adjudication tests now prove:

- pre-target-fidelity quarantined outputs need more evidence;
- `target_protocol_fidelity` blocks domain decision when `generation_fitness_results.json` is missing;
- missing target fitness is not silently converted into runnable success.

## Dogfood interpretation

This is the desired failure path:

```text
quarantined old DSPy review output
-> no generation_fitness_results.json
-> generation target-fidelity is unknown
-> DSPx target_protocol_fidelity judgment = needs_more_evidence
-> not ready for domain decision or active Obsidian materialization
```

This keeps `fitness_passed` narrow: it can only mean `eligible_for_downstream_evidence_review`, and only when the target-fidelity sidecars exist and pass their checks.

## Validation

Executed for this slice:

```bash
uv run ruff format packages/dspx-core/src/dspx/services/program_generation_contract.py packages/dspx-core/src/dspx/services/program_meta_adjudication.py tests/test_program_generation_contract.py tests/test_program_meta_adjudication.py
uv run ruff check packages/dspx-core/src/dspx/services/program_generation_contract.py packages/dspx-core/src/dspx/services/program_meta_adjudication.py tests/test_program_generation_contract.py tests/test_program_meta_adjudication.py
uv run ty check packages/dspx-core/src/dspx/services/program_generation_contract.py packages/dspx-core/src/dspx/services/program_meta_adjudication.py
uv run pytest tests/test_program_generation_contract.py tests/test_program_meta_adjudication.py -q
node ~/ai-society/core/agent-scripts/scripts/docs-list.mjs --docs . --strict --full-list
just task-scope-check task_id=2743 mode=working-tree
just verify-fast
```

## Remaining decision

After this slice, a new real PDF output can be considered for the active Obsidian review path only if it carries passing Wave 3 target-fidelity results and the DSPx adjudication path does not block on target-protocol evidence.
