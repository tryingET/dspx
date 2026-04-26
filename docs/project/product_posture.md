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

> DSPx already has mature local-first signature/module generation, receipts, replay, Oracle behavioral primitives, and a first `program-gen` composition path over signature/module surfaces plus deterministic plan/jury/promotion artifacts, typed/described field specs, deterministic inline/example-file binding, a standalone execution-episode contract artifact, minimal local behavior-result evidence over examples, compact Oracle-readable evidence, explicit non-authoritative Oracle evidence indexing into a local CoordinateIndex, explicit non-authoritative Oracle program-evidence reporting over those indexed records, explicit bounded local refinement proposals over a manifest plus behavior evidence plus Oracle report, explicit local promotion-review refinement packets over behavior/report/proposal evidence, explicit local adjudicator decision-record sidecars against refined review packets, explicit request-more-evidence second-candidate materialization from bounded refinement proposals, explicit local source-vs-second-candidate behavior comparison sidecars over existing candidate manifests, and opaque external-authority refs; it is converging toward one-intent generation of full runnable DSPy program assemblies, but the main maturity gap is that `program-gen` still performs narrow deterministic materialization and example-backed behavior capture/readability rather than rich intent normalization, full evaluation episodes, optimization, automatic closed-loop Oracle interpretation feedback, broader accepted-proposal regeneration policy, external authority export, or a complete promotion-governance product loop.

## Product maturity map

| Area | Current posture | Target posture | Main gap | Proof of closure |
|---|---|---|---|---|
| One-intent program generation | `program-gen` can materialize a deterministic program-shaped candidate assembly from structured JSON/YAML intent with `plan.json`, standalone `jury.json`, deterministic `jury_selection.json`, deterministic `jury_rubric.json`, `promotion_review.json` with opaque `external_authority` refs when supplied, `promotion_adjudication_request.json`, `promotion_decision_template.json`, standalone `execution_episode.json`, separate `signature.py`, `module.py`, `program.py`, `eval_smoke.py`, `eval_jury.py`, `eval_promotion.py`, optional `examples.json` / `eval_examples.py` from inline `examples` or `examples_path`, `intent.json`, `manifest.json`, and a run receipt. | A user can state one intent and receive a full-featured DSPy program assembly with explicit typed signatures, modules, topology, examples/datasets, metrics, runtime constraints, jury-backed evaluation harness, receipts, and replay path. | `program-gen` is still scaffold-first: it composes signature/module surfaces, emits deterministic intermediate plan/jury/selection/rubric/promotion-review/external-ref/adjudication-request/decision-template/execution-episode artifacts with normalized field specs/default topology/surface list/per-program inferred or explicit `program-jury-v1` evaluation intent, and validates inline/example-file plus jury/promotion artifact binding, but does not yet infer rich topology, run behavioral evaluations beyond the current examples harness, or export to external authority adapters. | Program receipts include richer evaluation episodes over examples/datasets with result summaries, failures, traces, and replayable inputs. |
| Signature and module surfaces | Native signature generation/refinement and `module-gen` are now service-level building blocks for `program-gen`; the program assembly records separate signature/module/program/eval surfaces plus per-surface hashes and generator provenance. | Signature and module generation are reusable candidate-surface providers inside larger program assemblies. | Module-scoped governance/ranking semantics must remain bounded when module generation is called as a program-surface provider. | Program assembly code calls service-level signature/module surface APIs, records nested provenance, and keeps module-specific ranking/promotion semantics bounded. |
| Execution episodes | Program generation currently writes `execution_episode.json`, runs compile/smoke validation, records examples/jury/promotion binding separately, and, when examples are present, invokes the generated program locally through `eval_examples.py` and writes `behavior_results.json` with per-example status, observed outputs when available, errors/degraded notes, summary counts, and manifest/receipt hashes. | Generated programs run declared evaluations under explicit provider/runtime/dataset/metric conditions. | The first behavior episode is intentionally minimal and example-local; it now has a standalone contract artifact but does not yet provide rich evaluation datasets, traces, model-jury execution, or quality claims. | Program receipts include richer evaluation episodes over examples/datasets with result summaries, failures, traces, and replayable inputs. |
| Oracle behavioral intelligence | Oracle CLI and coordinate/territory/frontier/attractor/contract surfaces exist; module synthesis evidence can use constrained Oracle neighbors as contextual hints; program-gen now writes `oracle_evidence.json` readability-only evidence from example-backed behavior results and records its hash/summary/facets in manifests and receipts; `oracle index --from-program-evidence` explicitly ingests those artifacts into a local CoordinateIndex as searchable `program-oracle-evidence` records; `oracle program-evidence report` explicitly reads those indexed records and summarizes example-backed behavior statuses, task/metric/IO facets, source artifacts, and failure signals as non-authoritative interpretation. | Oracle interprets program execution evidence as behavioral phenotypes, drift, recurrence, attractors, and frontiers that shape later bounded exploration. | Program-gen receipt bundles are now Oracle-readable, explicitly indexable, and explicitly reportable for the first compact slice, but interpretation remains consumer-side and must not rank, prune, promote, block, or mutate authority. | Oracle program-evidence reporting consumes indexed program evidence and reports behavioral patterns without ranking, pruning, or promoting by itself. |
| Bounded refinement proposal | `program-refine propose` explicitly consumes a `program-gen` manifest, declared example-backed `behavior_results.json` when present, and a non-authoritative Oracle program-evidence report, then writes a local `program-refinement-proposal-v1` artifact. | A user can inspect behavior plus Oracle interpretation and choose a bounded next candidate refinement while preserving authority boundaries. | The proposal is advisory only: it does not apply changes, create a new candidate assembly, call Oracle/indexing automatically, rank, prune, promote, block, export authority, or mutate governance. | A proposal artifact binds to the manifest identity, summarizes behavior/report evidence, preserves non-authority flags, and leaves generated program files unchanged. |
| Promotion-review refinement | `program-promote review` explicitly consumes a `program-gen` manifest, original generated promotion shell artifacts, declared example-backed behavior evidence when present, a non-authoritative Oracle report, and a `program-refinement-proposal-v1` artifact, then writes a local `program-promotion-review-refined-v1` sidecar. | A user can bring behavior, Oracle interpretation, and refinement proposal evidence into one adjudication packet without treating any of it as approval. | The refined packet is local review evidence only: it does not overwrite `promotion_review.json`, invoke an adjudicator, promote, rank, prune, block via Oracle, mutate governance, or generate a new candidate. | A refined packet keeps `promotion_state: not_promoted`, preserves explicit missing model-jury/adjudicator requirements, records non-authority flags, and leaves generated program files unchanged. |
| Promotion decision recording | `program-promote decide` explicitly consumes a `program-promotion-review-refined-v1` packet plus operator/adjudicator input and writes a `program-promotion-decision-record-v1` sidecar. | A user can record an inspectable local decision outcome without confusing it with activation or external governance. | The decision record is local evidence only: it does not mutate generated program artifacts, the refined review packet, Oracle, AK, governance, or external authority. `promote` fails closed unless `review_readiness.ready_for_adjudicator_review` is true; top-level `review_packet_ready` is not sufficient. | A decision record preserves identity from the refined packet, records rationale/decider/outcome, keeps non-promote outcomes unpromoted, and carries local-only/no-mutation flags. |
| Second-candidate generation | `program-refine generate-candidate` explicitly consumes a source manifest, a proposed refinement, and a local `request_more_evidence` decision record, then materializes one local second candidate at `--outdir`. | A user can turn an explicit request for more evidence into a bounded follow-up candidate without making the proposal or decision record authoritative. | The first slice applies only bounded `constraints` patches, writes only the new candidate directory, and does not mutate the source candidate, proposal, decision record, Oracle, AK, governance, or external authority. | A second candidate manifest records refinement lineage in intent options, remains `not_promoted`, and carries local-only/no-external-mutation posture. |
| Candidate comparison | `program-refine compare-candidates` explicitly consumes two already-materialized `program-candidate-assembly-v1` manifests and writes a `program-refinement-candidate-comparison-v1` local sidecar. | A user can inspect whether the request-more-evidence path changed example-backed behavior before any future promotion/export work. | The comparison is limited to current `eval_examples.py` / `behavior_results.json` evidence and reports deltas only; it does not generate candidates, rank, select winners, promote, mutate Oracle, AK, governance, external authority, or candidate artifacts. | A comparison sidecar records source/candidate identities, optional refinement lineage, behavior status/count deltas, failure signals added/removed/persisted, and local-only/non-authority flags. |
| Optimization / search | GEPA and optimization surfaces exist as bounded mechanisms for programs exporting expected hooks. | Search/reflection engines propose or improve candidate assemblies while runtime objects and governance boundaries remain explicit. | Optimization is not yet integrated into the one-intent program assembly loop as a bounded refinement phase. | A generated program assembly can enter an explicit optimization episode whose outputs are receipts/evidence, not automatic authority. |
| Governance / authority | SG2 has extensive governance-only receipt and review-decision contracts; current program-gen MVP explicitly does not widen ranking, pruning, promotion, Oracle, external adapter export, or governance authority; generated assemblies carry `promotion_review.json` with an explicit pending adjudicator that may be human, one AI agent, an AI council, a hybrid, or a policy gate plus opaque external authority refs when supplied, and a separately invoked Agent Kernel authority adapter can emit a `planned_not_exported` sidecar export plan from manifests/receipts. | Candidate assemblies can be evaluated, compared, withheld, reviewed, and promoted through explicit local/runtime/governance boundaries. | The program-shaped promotion/review shell is local and non-authoritative; it does not yet consume real behavioral episodes, model-jury execution, adjudicator decisions, or external adapter apply/export mutations. | Program assemblies have explicit local promotion-state metadata and any governance transition is backed by a dated contract/ADR and external authority truth when that optional adapter is explicitly applied. |
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

- `program-gen` composes deterministic signature/module surfaces, emits `program-plan-v1` plus standalone `jury.json` / `jury_selection.json` / `jury_rubric.json` / `promotion_review.json` with opaque non-exporting `external_authority` refs / `promotion_adjudication_request.json` / `promotion_decision_template.json`, preserves typed/described field specs, can validate inline examples and relative `examples_path` files, and can carry explicit or per-program inferred planned `program-jury-v1` multi-model/perspective contracts, but the current one-intent contract is not yet rich enough for inferred full program topology, dataset splits, executing selected jury behavior, routing, multi-step orchestration, or external authority export.
- The current program execution episode now includes minimal local behavior-result capture when examples are present plus a compact Oracle-readable evidence artifact, but it is not yet a rich declared evaluation episode over datasets, traces, model-jury execution, or explicit quality criteria.
- Program receipts now expose a first Oracle-readable evidence view, an explicit local indexing path, an explicit local report path for example-backed behavioral interpretation, an explicit local refinement-proposal path, an explicit local promotion-review refinement packet path, an explicit local adjudicator decision-record path, an explicit request-more-evidence second-candidate path, and an explicit local source-vs-candidate comparison path, but DSPx still does not invoke Oracle indexing, interpretation, refinement, promotion review, decision recording, second-candidate generation, or candidate comparison during `program-gen`.
- GEPA/search is not yet part of a bounded one-intent refinement loop over program candidate assemblies, and proposal acceptance does not yet generate a second candidate.
- The operator experience still requires knowing multiple CLI surfaces rather than following one coherent intent-to-behavior workflow.
- Current docs can make the target architecture legible, but without this posture file the shipped-vs-target gap is easy to blur.

## Target product experience

A DSPx user should be able to:

1. State one intent for a desired DSPy behavior.
2. Receive a normalized structured intent that makes assumptions inspectable.
3. See the candidate surfaces DSPx plans to generate: signatures, modules, program topology, prompts/configuration, examples/datasets, metrics, jury-shaped evaluation contracts, and evaluation harnesses.
4. Materialize a runnable candidate assembly, not just a loose code snippet.
5. Execute the assembly under explicit runtime/provider/dataset/metric conditions.
6. Inspect receipt bundles, traces, replay checks, and evaluation summaries.
7. Ask Oracle what behavioral phenotype, drift, recurring failures, attractors, or frontiers appear.
8. Run bounded refinement/search when useful, with each improvement attempt leaving evidence.
9. Decide whether to keep, compare, withhold, review, or promote a candidate through explicit authority boundaries.

## Near-term convergence path

1. **Deepen the structured intent and plan contract.** `program-plan-v1` now captures task type, default topology, normalized fields, surfaces, metrics, runtime, constraints, examples metadata, non-authority defaults, and explicit planned `program-jury-v1` juror/perspective contracts; the remaining work is richer normalization, dataset splits, executable jury episodes, desired DSPy strategy, and multi-step topology.
2. **Upgrade materialization into real execution episodes.** Generate evaluation harnesses that execute the generated program over declared examples/datasets and record behavioral results, not only smoke/example-binding success.
3. **Use program receipt bundles as Oracle inputs.** `program-gen` now emits the first readability-only evidence contract, `oracle index --from-program-evidence` ingests it into a local CoordinateIndex, and `oracle program-evidence report` summarizes those indexed records as deterministic example-backed behavioral interpretation without authority widening.
4. **Add bounded refinement/search.** `program-refine propose` now provides the first proposal-only seam over manifest + example-backed behavior evidence + Oracle report; later work can accept a proposal into a second-candidate generation or optimization episode whose results remain evidence until reviewed.
5. **Document one end-to-end walkthrough.** `docs/project/program-gen-walkthrough.md` now shows one intent moving through assembly, execution-episode evidence, receipt/replay, Oracle-readable evidence, explicit temp-dir indexing, explicit non-authoritative program-evidence reporting, and bounded next-step interpretation; a later walkthrough can extend this once refinement episodes are implemented.

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
