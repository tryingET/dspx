---
summary: "Session note for AK-5366: the concept_coverage GEPA wrapper is now hash-bound to its source candidate through a closed metric_honesty block, the consume contract verifies it, and the honest lineage was rerun on the loopback vLLM up to (not including) consume."
read_when:
  - "Consuming a foundry GEPA receipt whose optimizer manifest program is the concept_coverage wrapper, or debugging 'optimizer manifest source program hash does not match source candidate'."
---

# 2026-09-04 — AK-5366 metric_honesty wrapper binding

Scope: `program_refinement_gepa*.py`, `program_foundry_gepa_execution.py`, tests, this note.
No commit, no AK mutation, loopback-only network, `DSPX_ALLOW_UNSAFE_GEPA_PICKLE_SHA256` never set,
consume step not run.

## Defect

With `--gepa-metric concept_coverage` (c617826c) `program_refinement_gepa` hands GEPA a generated
wrapper (`_gepa_inputs/concept_coverage_program.py`), so `optimize_service` records the wrapper's hash
as `manifest.program.sha256`. The consume contract compared that hash with the source candidate's
`program.py` and failed closed (`program_refinement_gepa_candidate_contracts.py`, "GEPA optimizer
manifest source program hash does not match source candidate", exit 3), burning lineage
`misegraph-foundry-honest-5365.uMYFWr` through its consumption-attempt marker. Verified before the fix:
the optimizer manifest carried no honesty data at all (`gepa.metric` = `exact`, no wrapper/source
binding); the execution receipt mirrored nothing; only the result sidecar's
`gepa.concept_coverage_binding` and `gepa.metric_honesty` (intent/optimizer alignment) existed, and no
consumer read them.

## Fix

- `program_refinement_gepa_metric_honesty.py` (new): wrapper template moved here; the wrapper now
  embeds `CANDIDATE_PROGRAM_SHA256 = '<source hash>'` and refuses to load a drifted source program.
  `metric_honesty_block` builds the closed block
  `{metric: concept_coverage, wrapper_program_sha256, source_program_sha256, criteria_sha256}`;
  `verify_concept_coverage_metric_honesty` checks the block shape, `wrapper == manifest.program.sha256`,
  `source == current source program hash`, `criteria == intent criteria hash`, and (when source context
  is supplied) re-derives the wrapper byte-for-byte from the source program + criteria and compares it
  with `source/concept_coverage_program.py` in the optimizer output.
- `program_refinement_gepa.py`: after `run_gepa_optimize`, `_stamp_metric_honesty` writes the block into
  the optimizer `manifest.json` (before `_classify_gepa_output` hashes it) and mirrors it under
  `gepa.concept_coverage_binding.metric_honesty`; failure to bind degrades the result to
  `gepa_output_unverified`.
- `program_foundry_gepa_execution.py`: `_validate_metric_honesty` cross-checks manifest block vs result
  binding (required for concept_coverage, forbidden otherwise) and the execution receipt mirrors the
  block; the receipt rebuild/compare makes any drift of the mirror fail closed. Exact-path receipts are
  byte-identical to before (no key added when no block).
- `program_refinement_gepa_candidate_contracts.py`: `_verify_manifest_program_binding` replaces the bare
  hash equality. No block: unchanged exact behaviour (plus a concept_coverage intent without a block is
  refused). Block present: hash-level verification always; byte re-derivation when the caller supplies
  `source_manifest` + `source_program_path` (materialization does). The candidate-result contract requires
  the materialized lineage block to equal the copied manifest block and the candidate `program.py` hash to
  differ from the wrapper hash.
- `program_refinement_gepa_candidate.py`: materialization passes the source context, refuses a candidate
  whose program is the wrapper, and records the block in `gepa_candidate_lineage.json`,
  `manifest.gepa_refinement`, and the result's `gepa_output`. The candidate program remains the source
  program render plus the hash-guarded optimizer-output loader (GEPA-optimized instructions come from the
  bound `program.pkl`), never the wrapper.

Tests (`tests/test_program_foundry_metric_honesty.py`, `tests/test_program_foundry_gepa_execution.py`,
`tests/test_program_refinement_gepa.py::_fake_gepa(hash_program=True)`): closed block stamped; consume
contract accepts and materializes a concept_coverage lineage; tampered wrapper hash, tampered source
hash, tampered criteria hash, dropped block, opened block, and a foreign wrapper with consistent hashes
are rejected; exact-metric manifests carry no block and keep the old hash check; retained
`docs/project/*-evidence.json` execution receipts keep their pre-block shape; receipt mirror drift is
rejected.

## Lineage rerun (ak-5366-honest-live-lineage)

ROOT `/home/tryinget/.local/state/pi-quests/tmp/misegraph-foundry-honest-5366.RZzphH` (scripts copied and adapted from `misegraph-foundry-honest-5365.uMYFWr`;
same env: `DSPX_PROVIDER=openai-compatible`, base `http://127.0.0.1:2456/v1`, model
`local/Qwen3.8-27B-AEON-NVFP4-FP8`, live Oracle backend, unsafe-pickle opt-in never set).
Steps export → import (no `--answers`, `answers.origin=package_derived`) → program-gen → program-run →
quality proposal derivation (AK-5346 injected test-double `model_execution`, still the hollow link) →
foundry `--gepa-metric concept_coverage --gepa-max-metric-calls 4` → execute-foundry-gepa
(`--operator-label ak-5366-honest-live-lineage`). Stopped before consume; no consumption marker exists.

- proposal_id `721e404015b1a2721caa8b773514f4d6b602e26a7c0d38ce8cf040fbfc77e2d6`
- optimizer_manifest_sha256 `8d5701c2c6fb452aaec9c9712a6fe6f02bb76966062c82a4d0ac148668ec1acc`
- manifest `metric_honesty` (byte-equal mirror in `execution-receipt.json`):
  metric `concept_coverage`, wrapper_program_sha256 `2454e90137360a17790fb117d9bd17a2ea166f6e288ba39811d1bef3b68d6cbc`
  (= `manifest.program.sha256`), source_program_sha256 `ecbb8c7cdbf9c641526304b31a9448c5c16c038c1bc7c98009f3c67e1e637981`
  (= sha256 of `foundry/candidate/program.py`), criteria_sha256 `57e44042144cbb3f174afb172dde9d32bf3652a717dd9c92c4963479da4d0486`
  (= proposal `gepa_plan.metric.concept_coverage_binding.criteria_sha256`)
- Oracle sidecar: execution_status `succeeded`, executed_model `local/Qwen3.8-27B-AEON-NVFP4-FP8`,
  executed_provider `openai-compatible`, backend_kind `live`, provider_evidence_kind `live`,
  1 recommended experiment ("A next experiment would compare the answer text against each required Misegraph concept group").
- GEPA: status completed, provider_evidence_kind live, candidate_count 1, candidates_accepted
  0, proposal_starts 0, total_metric_calls 4, best_validation_score
  1.0 — no new candidate was proposed; the 4-call budget is consumed by the base validation
  eval plus subsample evals before any reflection round.
- Read-only dry check: `validate_program_refinement_gepa_result_contract(..., source_manifest, source_program_path)`
  over this lineage returns ready with the block verified (wrapper re-derived byte-for-byte). The consume
  step itself was not run (task scope); it is the operator's call.

Open follow-ups (not in this task's scope): the quality proposal envelope still carries the injected
test-double `model_execution`; `--gepa-max-metric-calls 4` cannot reach a reflection round, so a
concept_coverage GEPA run that can actually propose a candidate needs a larger bounded budget.
