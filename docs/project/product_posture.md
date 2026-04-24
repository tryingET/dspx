---
summary: "Product posture snapshot for DSPx: current maturity, target product experience, major gaps, and proof signals."
read_when:
  - "When deciding where DSPx stands relative to its durable vision"
  - "When selecting or reviewing strategic goals from product maturity rather than task history"
  - "When checking whether active work converges on one-intent full DSPy program generation"
type: "reference"
---

# Product Posture

## Purpose

This file is the status-bearing bridge between durable vision and active direction.

It captures where DSPx stands, what target product experience it is converging toward, which gaps matter most, and what proof would close those gaps.

It does **not** replace:

- shipped runtime/source truth in code, tests, READMEs, architecture docs, or generated artifacts
- AK task or decision authority
- `docs/project/strategic_goals.md`
- `docs/project/tactical_goals.md`
- `docs/project/operational_goals.md`

Use this file only when a product-wide maturity snapshot helps strategy. Do not turn it into a task log, release log, changelog, or second operating plan.

## Posture in one sentence

> DSPx already has mature local-first signature/module generation, receipts, replay, Oracle behavioral primitives, and a first `program-gen` composition path over signature/module surfaces plus typed/described field specs and deterministic inline/example-file binding; it is converging toward one-intent generation of full runnable DSPy program assemblies, but the main maturity gap is that `program-gen` still performs scaffold materialization and validation rather than rich intent normalization, behavioral evaluation episodes, optimization, and Oracle feedback in one complete product loop.

## Product maturity map

| Area | Current posture | Target posture | Main gap | Proof of closure |
|---|---|---|---|---|
| One-intent program generation | `program-gen` can materialize a deterministic program-shaped candidate assembly from structured JSON/YAML intent with separate `signature.py`, `module.py`, `program.py`, `eval_smoke.py`, optional `examples.json` / `eval_examples.py` from inline `examples` or `examples_path`, `intent.json`, `manifest.json`, and a run receipt. | A user can state one intent and receive a full-featured DSPy program assembly with explicit typed signatures, modules, topology, examples/datasets, metrics, runtime constraints, evaluation harness, receipts, and replay path. | `program-gen` is still scaffold-first: it composes signature/module surfaces, preserves typed/described field specs, and validates inline/example-file binding, but does not yet infer rich topology or run behavioral evaluations. | Program receipts include real evaluation episodes over examples/datasets with result summaries, failures, traces, and replayable inputs. |
| Signature and module surfaces | Native signature generation/refinement and `module-gen` are now service-level building blocks for `program-gen`; the program assembly records separate signature/module/program/eval surfaces plus per-surface hashes and generator provenance. | Signature and module generation are reusable candidate-surface providers inside larger program assemblies. | Module-scoped governance/ranking semantics must remain bounded when module generation is called as a program-surface provider. | Program assembly code calls service-level signature/module surface APIs, records nested provenance, and keeps module-specific ranking/promotion semantics bounded. |
| Execution episodes | Program generation currently runs compile/smoke validation and records a materialization episode. | Generated programs run declared evaluations under explicit provider/runtime/dataset/metric conditions. | Smoke validation proves bundle shape, not behavioral performance. | Program receipts include real evaluation episodes over examples/datasets with result summaries, failures, traces, and replayable inputs. |
| Oracle behavioral intelligence | Oracle CLI and coordinate/territory/frontier/attractor/contract surfaces exist; module synthesis evidence can use constrained Oracle neighbors as contextual hints. | Oracle interprets program execution evidence as behavioral phenotypes, drift, recurrence, attractors, and frontiers that shape later bounded exploration. | Program-gen receipt bundles are not yet first-class Oracle behavioral evidence for phenotype/territory loops. | Oracle indexing and interpretation can consume program receipt bundles and report behavioral patterns without ranking, pruning, or promoting by itself. |
| Optimization / search | GEPA and optimization surfaces exist as bounded mechanisms for programs exporting expected hooks. | Search/reflection engines propose or improve candidate assemblies while runtime objects and governance boundaries remain explicit. | Optimization is not yet integrated into the one-intent program assembly loop as a bounded refinement phase. | A generated program assembly can enter an explicit optimization episode whose outputs are receipts/evidence, not automatic authority. |
| Governance / authority | SG2 has extensive governance-only receipt and review-decision contracts; current program-gen MVP explicitly does not widen ranking, pruning, promotion, Oracle, or governance authority. | Candidate assemblies can be evaluated, compared, withheld, reviewed, and promoted through explicit local/runtime/governance boundaries. | The program-shaped promotion/review shell is not yet defined beyond non-authority defaults. | Program assemblies have explicit local promotion-state metadata and any governance transition is backed by a dated contract/ADR and AK task truth. |
| Operator / user experience | Power users can run separate CLI surfaces for signature, module, optimize, replay, Oracle, and program-gen. | A user can start with one intent, inspect the generated plan/surfaces, run/evaluate, replay, ask Oracle what happened, and choose the next bounded refinement. | The product still feels like a toolbox plus a new program scaffold rather than one coherent intent-to-behavior loop. | A documented walkthrough demonstrates one intent flowing through assembly, execution, receipt, replay, Oracle interpretation, and bounded refinement. |

## Current strengths

- DSPx has a local-first CLI/product identity centered on DSPy development rather than hosted SaaS.
- Native signature generation and refinement already exist with deterministic and provider-backed paths.
- `module-gen` has a mature module synthesis/evidence stack, including quality events, receipt metadata, replay integration, and SG2 governance-only evidence surfaces.
- Program-shaped candidate assemblies now exist through `program-gen`, including separate signature/module/program/eval surfaces, manifest metadata, receipt-bundle IDs, and per-surface provenance.
- Receipt/replay infrastructure gives the product a durable evidence spine.
- Oracle already has behavioral coordinate, search, neighbor, drift, territory, frontier, attractor, and contract concepts in the product surface.
- The docs already separate runtime evidence, Oracle interpretation, and governance authority.

## Current gaps

- `program-gen` composes deterministic signature/module surfaces, preserves typed/described field specs, and can validate inline examples and relative `examples_path` files, but the current one-intent contract is not yet rich enough for full program topology, task type, dataset splits, judge behavior, routing, or multi-step orchestration.
- The current program execution episode is a compile/smoke/example-binding materialization check, not a behavioral evaluation episode.
- Program receipts are not yet first-class Oracle inputs for phenotype, territory, frontier, or attractor analysis.
- GEPA/search is not yet part of a bounded one-intent refinement loop over program candidate assemblies.
- The operator experience still requires knowing multiple CLI surfaces rather than following one coherent intent-to-behavior workflow.
- Current docs can make the target architecture legible, but without this posture file the shipped-vs-target gap is easy to blur.

## Target product experience

A DSPx user should be able to:

1. State one intent for a desired DSPy behavior.
2. Receive a normalized structured intent that makes assumptions inspectable.
3. See the candidate surfaces DSPx plans to generate: signatures, modules, program topology, prompts/configuration, examples/datasets, metrics, and evaluation harnesses.
4. Materialize a runnable candidate assembly, not just a loose code snippet.
5. Execute the assembly under explicit runtime/provider/dataset/metric conditions.
6. Inspect receipt bundles, traces, replay checks, and evaluation summaries.
7. Ask Oracle what behavioral phenotype, drift, recurring failures, attractors, or frontiers appear.
8. Run bounded refinement/search when useful, with each improvement attempt leaving evidence.
9. Decide whether to keep, compare, withhold, review, or promote a candidate through explicit authority boundaries.

## Near-term convergence path

1. **Define a richer structured intent contract.** Include task type, dataset splits, metrics, runtime conditions, desired DSPy strategy, constraints, and expected artifact surfaces.
2. **Upgrade materialization into real execution episodes.** Generate evaluation harnesses that execute the generated program over declared examples/datasets and record behavioral results, not only smoke/example-binding success.
3. **Make program receipt bundles Oracle-readable.** Ensure Oracle can index and interpret program execution evidence as behavioral phenotypes and territory/frontier signals without authority widening.
4. **Add bounded refinement/search.** Let GEPA or other engines propose candidate improvements as explicit episodes whose results remain evidence until reviewed.
5. **Document one end-to-end walkthrough.** Prove the product posture changed by showing one intent move through assembly, execution, receipt, replay, Oracle interpretation, and bounded next-step selection.

## Oracle posture

Oracle is central to DSPx, but its authority must stay bounded.

Oracle should be treated as the empirical interpreter of observed DSPy behavior:

- It can identify similar executions, behavioral drift, recurrence, attractors, frontiers, unstable regions, and likely failure patterns.
- It can provide advisory search-shaping signals grounded in receipts and traces.
- It can help a user understand what happened and where bounded exploration might go next.

Oracle should not be treated as:

- direct promotion authority,
- canonical governance authority,
- an automatic ranking/pruning/blocking engine,
- or a substitute for replayable receipt truth.

The near-term Oracle product gap is not conceptual presence; Oracle is already in the vision and code surface. The gap is integration: program-shaped receipt bundles need to become first-class Oracle behavioral evidence.

## Hard rules for status language

- Say what is shipped, observable, or otherwise authoritative today; do not describe target-state ambition as current fact.
- Say “target posture” or “intended experience” when proof has not landed yet.
- Say “proof of closure” only when the cited code, artifact, test, runtime evidence, or owner decision exists.
- Keep product-wide posture here; task-level current truth belongs in AK and the repo's active execution surface.
- Use current-vs-target language inside this file when useful, but reserve separate current-vs-target boundary docs for seam-specific transitions.

## Authority map

- Durable ambition: `docs/project/vision.md`
- Product posture: this file
- Target-state runtime boundary for program/Oracle/search concerns: `docs/project/program-synthesis-boundary.md`
- Shipped runtime/source truth: README, architecture/configuration docs, source code, tests, and generated artifacts owned by the repo
- Active direction: `docs/project/strategic_goals.md`, `docs/project/tactical_goals.md`, and `docs/project/operational_goals.md`
- Live execution truth: repo-local AK tasks and decisions
- Raw session evidence: `diary/`
- Crystallized learning: `docs/learnings/`
