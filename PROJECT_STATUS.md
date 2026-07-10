---
summary: "DSPx shipped product posture and current evidence frontier."
read_when:
  - "You need the current project status summary."
  - "You are checking high-level completion or remaining work."
type: "reference"
---

# Project Status

DSPx is a local-first behavioral-intelligence toolkit for generated DSPy programs. Active task, decision, direction, and evidence authority lives in AK; this file is a maintained runtime projection, not a task log.

## Shipped truth

- The Python 3.13 `uv` monorepo enforces `apps/* -> packages/dspx-core` dependency direction.
- Signature/module generation, provider runtimes, receipts, replay, Oracle indexing/interpretation, and generated-program evidence surfaces are implemented.
- `program-gen` materializes bounded candidate assemblies with distinct materialization, binding, behavior, receipt, and non-authority evidence.
- `program-loop` composes generation, receipt replay, candidate-local Oracle evidence/reporting, and candidate-state output. Its product status is behavior-first: failed/error/degraded behavior cannot report `ok` or exit zero, while successful materialization and replay remain separately visible and all evidence remains inspectable.
- Generated-program review, jury, refinement, comparison, planning, and activation-packet surfaces remain local evidence/advisory seams. They do not activate production, mutate AK/governance, or acquire promotion authority.
- Default smoke and program-loop paths are offline/stub-capable and service-free. Shared Oracle publication is explicit opt-in.

## Current frontier

The central gap is no longer basic artifact materialization. It is broader, provider-backed semantic proof: richer executable topology and adapter coverage, stronger benchmark slices, iterative optimization grounded in observed behavior, and clearer operator comparison/review flows. Unsafe tools, external retrievers, custom imports, and authority apply remain blocked until their own bounded contracts exist.

## Validation posture

Use the repo `Justfile`: `just check` for landing readiness, `just verify-impact` for bounded changed-file validation, and `just verify-full` when impact is wide or before release. `just smoke-base` is the offline deterministic semantic-control proof for workflow/status plumbing; it does not claim live-model quality. Generated/server artifact roots are non-authoritative local storage; inspect retention candidates with `just artifact-cleanup`, then apply only with the unchanged dry-run plan id and exact-root confirmation.

## Canonical orientation

- `docs/system4d/compass.md`
- `docs/ARCHITECTURE.md`
- `docs/project/product-posture.md`
- `docs/project/developer_workflow.md`
- AK direction/task/decision/evidence runtime
