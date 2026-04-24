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

The V1 intent contract includes:

- `name`
- `objective`
- `inputs`
- `outputs`
- `constraints`
- `examples`
- `metric`
- `runtime`
- `options`

The first materialized bundle writes:

- `signature.py` — deterministic DSPy `Signature` surface generated through the signature service
- `module.py` — deterministic DSPy `Module` surface generated through the module service and wired to the signature surface
- `program.py` — deterministic program assembly wrapper with `build_program()`, `build_student()`, intent summary, and IO helper re-exports
- `eval_smoke.py` — deterministic local smoke harness scaffold
- `intent.json` — normalized intent payload
- `manifest.json` — candidate-assembly, execution-episode, receipt-bundle, surface-provenance, and per-surface hash metadata
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
- Receipts and manifests already expose assembly, episode, receipt-bundle IDs, surface provenance, and per-surface hashes for later replay, Oracle interpretation, and bounded promotion work.
- The first path is deterministic and testable, so it can compound before model-backed synthesis or GEPA-backed search is introduced.

Tradeoffs:

- V1 is scaffold-first and does not yet infer complex multi-step control flow from natural language alone.
- V1 does not yet run model-backed program evaluation or optimization.
- V1 does not promote generated programs to live authority.

Non-authority defaults:

- `program-gen` receipts are evidence, not approval.
- Candidate assemblies are materialized, not promoted.
- Oracle may later interpret receipt evidence, but this ADR does not grant Oracle promotion or governance authority.
- The existing module governance chain remains closed unless a later task explicitly widens it.

## Validation surface

The first implementation is covered by:

- service-level materialization tests for generated files, manifest shape, receipt fields, exact manifest hash, and replay validation
- CLI tests for YAML intent input and invalid-field rejection
- validation tests for empty IO, input/output overlap, and docstring-hostile objectives
- targeted compile / lint / pytest checks

## Follow-on shape

The next truthful follow-ons are:

1. richer intent schema and examples/dataset binding,
2. real execution episodes that run the generated program under declared runtime conditions,
3. Oracle-readable behavioral phenotype extraction from program receipts,
4. later search/reflection engines that propose candidate assemblies without owning promotion authority.
