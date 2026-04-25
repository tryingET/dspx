---
summary: "First bounded intent-to-program candidate-assembly MVP for DSPx."
read_when:
  - "You are changing program-gen, program synthesis, or one-intent DSPy program materialization."
  - "You need the authority boundary between module-gen and program-shaped candidate assemblies."
---

# Intent-to-program candidate assembly MVP

## Status

Accepted.

## Context

DSPx already has a mature `module-gen` path and SG2 evidence/governance receipts around module-shaped synthesis runs.

The product direction is now larger: a user should be able to provide one intent and receive a runnable DSPy program-shaped candidate assembly. The boundary note in `docs/project/program-synthesis-boundary.md` says this should be anchored in first-class runtime objects rather than by overloading `module_service`.

The first implementation therefore needs to be small but ontology-preserving:

`intent -> program-shaped candidate assembly -> execution episode -> receipt bundle`

It must not widen live ranking, pruning, promotion, governance-policy activation, or Oracle authority.

## Decision

Introduce a bounded deterministic `program-gen` MVP that materializes a program-shaped candidate assembly from a structured JSON/YAML intent.

The structured intent contract is now backward-compatible with the original V1 fields while normalizing as `program-intent-v2` for plan-aware materialization. It includes:

- `schema_version`
- `name`
- `objective`
- `inputs`
- `outputs`
- `input_fields` / `output_fields` for optional typed/described field specs
- `task_type`, defaulting to `single_module`
- `topology`, defaulting through the plan to one module
- `constraints`
- `examples`
- `examples_path`
- `metric`
- `runtime`
- `jury`, including optional future multi-model/perspective jury-selection hints
- `options`, retained for service/template options and backward-compatible jury hints

The first materialized bundle writes:

- `plan.json` — deterministic `program-plan-v1` intermediate contract generated from the intent, including normalized field specs, task type, default topology, surfaces, metric/runtime/constraints, examples metadata, non-authority defaults, and explicit planned `program-jury-v1` multi-model/perspective evaluation shape
- `jury.json` — standalone planned `program-jury-v1` contract copied from the plan so later jury execution can bind to an exact per-program juror/perspective pool artifact; when the intent does not supply an explicit pool, DSPx infers one deterministically from task type, objective, metric, examples, fields, and constraints
- `jury_selection.json` — deterministic `program-jury-selection-v1` artifact that selects jurors from the per-program pool by preferring diverse perspectives, remains non-authoritative, and does not call any model
- `jury_rubric.json` — deterministic `program-jury-rubric-v1` artifact that binds selected jurors/perspectives to criteria and adversarial questions for a later jury execution episode, remains non-authoritative, and does not call any model
- `signature.py` — deterministic DSPy `Signature` surface generated through the signature service, including typed/described field specs when provided
- `module.py` — deterministic DSPy `Module` surface generated through the module service and wired to the signature surface
- `program.py` — deterministic program assembly wrapper with `build_program()`, `build_student()`, intent summary, and IO helper re-exports
- `eval_smoke.py` — deterministic local smoke harness scaffold
- `eval_jury.py` — deterministic jury artifact binding harness that validates `jury.json`, `jury_selection.json`, and `jury_rubric.json` without calling models
- `examples.json` / `eval_examples.py` — emitted when inline `examples` or `examples_path` examples are present, validating example binding without calling an LM
- `intent.json` — normalized intent payload
- `manifest.json` — candidate-assembly, execution-episode, receipt-bundle, plan/jury/selection/rubric-provenance, surface-provenance, example-binding, and per-surface hash metadata
- `manifest.json.meta.json` — standard DSPx run receipt with `run_kind=program-gen`

Before marking the materialization episode as `passed`, DSPx compiles the generated files and runs `eval_smoke.py` in the candidate assembly directory. The receipt hash is computed from the exact written `manifest.json` bytes, and replay validation can recompute the `program-gen` cache key from `replay_inputs.intent`.

The CLI entrypoint is root-level:

```bash
uv run python -m dspx.cli.dspx program-gen --intent intent.yaml --outdir generated/programs/demo
```

The implementation belongs in `dspx.services.program_service`, not `module_service`.

## Consequences

Positive:

- DSPx now has a concrete foothold for one-intent program synthesis.
- Program synthesis begins at the candidate-assembly boundary instead of being squeezed into module generation.
- `program-gen` now composes signature and module generation as candidate-surface providers instead of permanently duplicating them inline.
- Receipts and manifests already expose assembly, episode, receipt-bundle IDs, plan/jury/selection/rubric provenance, surface provenance, optional example-binding evidence, and per-surface hashes for later replay, Oracle interpretation, and bounded promotion work.
- The first path is deterministic and testable, so it can compound before model-backed synthesis or GEPA-backed search is introduced.

Tradeoffs:

- V1 is scaffold-first and does not yet infer complex multi-step control flow from natural language alone.
- V1 can carry a planned jury contract but does not yet run model-backed program evaluation, multi-model jury evaluation, or optimization.
- V1 does not promote generated programs to live authority.

Non-authority defaults:

- `program-gen` receipts are evidence, not approval.
- Candidate assemblies are materialized, not promoted.
- Oracle may later interpret receipt evidence, but this ADR does not grant Oracle promotion or governance authority.
- The existing module governance chain remains closed unless a later task explicitly widens it.

## Validation surface

The first implementation is covered by:

- service-level materialization tests for generated files, `plan.json` / `jury.json` / `jury_selection.json` / `jury_rubric.json` shape, manifest plan/jury/selection/rubric provenance, receipt fields, exact manifest hash, and replay validation
- CLI tests for YAML intent input and invalid-field rejection
- validation tests for empty IO, input/output overlap, and docstring-hostile objectives
- targeted compile / lint / pytest checks

## Follow-on shape

The next truthful follow-ons are:

1. richer intent normalization and examples/dataset binding,
2. real execution episodes that run the generated program and selected jury under declared runtime conditions,
3. Oracle-readable behavioral phenotype extraction from program receipts,
4. later search/reflection engines that propose candidate assemblies without owning promotion authority.
