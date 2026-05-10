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

> DSPx already has mature local-first signature/module generation, receipts, replay, Oracle behavioral primitives, and a first `program-gen` composition path over signature/module/program surfaces plus standalone `program-module-surfaces-v1` / `program-module-surface-v1` contracts, deterministic plan/jury/promotion artifacts, typed/described field specs, explicit declared topology preservation/validation without topology inference, narrow explicit `pipeline` topology rendering for `Predict`/`ChainOfThought` modules with simple equality routing, deterministic inline/example-file binding, optional deterministic local dataset split materialization (`dataset_manifest.json`, split JSONL files, split eval harnesses, split behavior results), bounded `eval_behavior.py` orchestration with `behavior_episode.json`, a standalone execution-episode contract artifact with source-indexed evaluation evidence summaries, local behavior-result evidence over inline examples / `examples_path` / dataset splits, source-aware Oracle-readable evidence over those local behavior sources, explicit non-authoritative Oracle evidence indexing into a local CoordinateIndex, explicit non-authoritative Oracle program-evidence reporting over those indexed records, explicit bounded source-aware local refinement proposals over a manifest plus behavior evidence plus Oracle report, explicit local promotion-review refinement packets over behavior/report/proposal evidence, explicit local deterministic jury-results sidecars over planned jury artifacts plus already-generated behavior results or behavior episodes, explicit local adjudicator decision-record sidecars against refined review packets, explicit request-more-evidence second-candidate materialization from bounded refinement proposals, explicit local source-vs-second-candidate behavior comparison sidecars over existing candidate manifests, explicit local candidate truth-state summaries (`program-candidate-state-v1`) over manifests plus sidecars including optional local jury-results evidence, an explicit local `program-refine optimize-gepa` sidecar seam over existing candidate manifests, opaque external-authority refs, and a local Agent Kernel export-preflight packet seam that binds manifest/decision/comparison evidence to an opaque external ref without calling or mutating AK; it is converging toward one-intent generation of full runnable DSPy program assemblies, but the main maturity gap is that `program-gen` still performs narrow deterministic materialization and bounded example/dataset behavior capture rather than broad topology inference/execution, arbitrary custom module import/execution, full evaluation episodes, automatic optimization, automatic closed-loop Oracle interpretation feedback, broader accepted-proposal regeneration policy, external authority apply, or a complete promotion-governance product loop.

## Target-fidelity gate posture — 2026-05-10

The target-protocol fidelity gate is now partly shipped for `program-gen` and the Obsidian/PDF review adapter.

Shipped in DSPx:

- `program-gen target-contract` writes `gen-target-contract-v1`.
- `program-gen fitness-suite` writes `gen-fitness-suite-v1`.
- `program-gen verify-generation-gate` writes `gen-generation-gate-preflight-v1` and can block candidate creation.
- `program-gen --generation-gate-preflight` requires a successful gate before materializing a candidate when supplied.
- `program-gen traceability` writes `gen-traceability-v1` after generation.
- `program-gen fitness-results` writes `gen-fitness-results-v1` after generation.
- `fitness_passed` is rendered only as `eligible_for_downstream_evidence_review`.
- DSPx/meta adjudication consumes generation target-fidelity sidecars and adds a `target_protocol_fidelity` judgment.
- `program-promote status` can summarize generation gate, fitness result, target-protocol adjudication, and Obsidian review-adapter admission readiness in `target_fidelity_state`.
- `program-promote activation-packet` can consume target-aware candidate status plus the Obsidian review-adapter receipt, prove review-only admission, and list remaining generated-program runtime activation blockers without applying activation.
- quarantined pre-target-fidelity Obsidian/PDF DSPy outputs are codified as negative fixtures and must fail/ask for more evidence.

Shipped in the Obsidian/PDF adapter:

- pre-target-fidelity DSPy review outputs are quarantined, not active review evidence;
- active DSPy PDF review materialization requires `generation_fitness_results.json`;
- missing, failed, or unsafe target-fitness results are rejected;
- the review page keeps hover/focus artifact previews but does not synthesize deterministic Wiki note text;
- canonical `Wiki/` / `Atlas/` mutation remains out of scope.

Still not shipped:

- automatic semantic proof that the generated program truly implements the target workflow;
- GEPA curation from target-fidelity outcomes;
- production activation, owner acceptance, canonical binding, or rollout preflight for Obsidian PDF transition outputs;
- one-command `program-loop` execution of the entire generation/adjudication/review-admission chain.

Current interpretation:

```text
generation_allowed -> candidate may be created
fitness_passed / eligible_for_downstream_evidence_review -> candidate may be inspected downstream
target_protocol_fidelity supports_domain_review -> DSPx adjudication does not block review-adapter admission
program-promote status target_fidelity_state.obsidian_review_adapter_materialization_allowed -> review packet may be materialized, not canonicalized
program-promote activation-packet target_review_admission=review_admitted -> review admission is evidenced, not runtime activation
owner/domain acceptance -> not claimed by DSPx or the adapter
canonical binding / rollout preflight -> still required before generated-program runtime activation
canonical mutation -> still forbidden without a separate owner acceptance path
```

## Product maturity map

| Area | Current posture | Target posture | Main gap | Proof of closure |
|---|---|---|---|---|
| One-intent program generation | `program-gen` can materialize a deterministic program-shaped candidate assembly from structured JSON/YAML intent with `plan.json`, standalone `jury.json`, deterministic `jury_selection.json`, deterministic `jury_rubric.json`, `promotion_review.json` with opaque `external_authority` refs when supplied, `promotion_adjudication_request.json`, `promotion_decision_template.json`, standalone `execution_episode.json`, separate `signature.py`, `module.py`, `program.py`, `eval_smoke.py`, `eval_jury.py`, `eval_promotion.py`, optional `examples.json` / `eval_examples.py` from inline `examples` or `examples_path`, `intent.json`, `manifest.json`, and a run receipt. `program-intent-v2` can carry explicit declared topology; the current renderer materializes the narrow `pipeline` subset (`Predict`/`ChainOfThought`, `signature.name`/`inputs`/`outputs`, simple equality `when`) and preserves unsupported valid topology as declared-only. | A user can state one intent and receive a full-featured DSPy program assembly with explicit typed signatures, modules, topology, examples/datasets, metrics, runtime constraints, jury-backed evaluation harness, receipts, and replay path. | `program-gen` is still scaffold-first: it composes signature/module surfaces, emits deterministic intermediate plan/jury/selection/rubric/promotion-review/external-ref/adjudication-request/decision-template/execution-episode artifacts with normalized field specs/default or declared/materialized topology/surface list/per-program inferred or explicit `program-jury-v1` evaluation intent, and validates inline/example-file plus jury/promotion artifact binding, but does not yet infer topology, support broad graph execution, run behavioral evaluations beyond the current examples harness, or export to external authority adapters. | Program receipts include richer evaluation episodes over examples/datasets with result summaries, failures, traces, and replayable inputs. |
| Signature and module surfaces | Native signature generation/refinement and `module-gen` are now service-level building blocks for `program-gen`; the program assembly records separate signature/module/program/eval surfaces plus standalone `module_surfaces.json` contracts, per-surface hashes, and generator provenance. | Signature and module generation are reusable candidate-surface providers inside larger program assemblies, with generated and future local custom module references represented through the same replayable IO-declared module-surface shape. | Module-scoped governance/ranking semantics must remain bounded when module generation is called as a program-surface provider, and future custom module refs must not become arbitrary import/execution authority. | Program assembly code calls service-level signature/module surface APIs, records module-surface contracts and nested provenance, and keeps module-specific ranking/promotion/custom-execution semantics bounded. |
| Execution episodes | Program generation currently writes `execution_episode.json`, runs compile/smoke validation, records examples/jury/promotion binding separately, generates bounded `eval_behavior.py`, writes `behavior_episode.json`, and records source-indexed `evaluation_sources` plus aggregate `behavior_evidence_summary` over inline examples, `examples_path`, and/or dataset split behavior results. Example runs still use `eval_examples.py` / `behavior_results.json`; dataset runs use split-specific harnesses and `behavior_results.<split>.json`; `eval_behavior.py` orchestrates only those generated harnesses and each source records result paths/hashes, counts/status summaries, metric, and provider facts already available. | Generated programs run declared evaluations under explicit provider/runtime/dataset/metric conditions. | The behavior episode now has bounded local orchestration across examples and dataset splits, but remains narrow/local and does not yet provide traces, model-jury execution, broad graph execution, or quality claims. | Program receipts include richer evaluation episodes over examples/datasets with result summaries, failures, traces, and replayable inputs. |
| Oracle behavioral intelligence | Oracle CLI and coordinate/territory/frontier/attractor/contract surfaces exist; module synthesis evidence can use constrained Oracle neighbors as contextual hints; program-gen now writes `oracle_evidence.json` readability-only evidence from source-indexed local behavior results across inline examples, `examples_path`, and dataset splits, and records its hash/summary/facets in manifests and receipts; `oracle index --from-program-evidence` explicitly ingests those artifacts into a local CoordinateIndex as searchable `program-oracle-evidence` records; `oracle program-evidence report` explicitly reads those indexed records and summarizes behavior statuses, source kinds, task/metric/IO facets, source artifacts, and failure signals as non-authoritative interpretation. | Oracle interprets program execution evidence as behavioral phenotypes, drift, recurrence, attractors, and frontiers that shape later bounded exploration. | Program-gen receipt bundles are now source-aware, Oracle-readable, explicitly indexable, and explicitly reportable, but interpretation remains consumer-side and must not rank, prune, promote, block, or mutate authority. | Oracle program-evidence reporting consumes indexed program evidence and reports behavioral patterns without ranking, pruning, or promoting by itself. |
| Bounded refinement proposal | `program-refine propose` explicitly consumes a `program-gen` manifest, declared `behavior_results.json` when inline/example-file behavior exists, source-indexed execution/oracle evidence when dataset-only behavior exists, and a non-authoritative Oracle program-evidence report, then writes a local `program-refinement-proposal-v1` artifact. | A user can inspect behavior plus Oracle interpretation and choose a bounded next candidate refinement while preserving authority boundaries. | The proposal is advisory only: it does not apply changes, create a new candidate assembly, call Oracle/indexing automatically, rank, prune, promote, block, export authority, or mutate governance. | A proposal artifact binds to the manifest identity, summarizes behavior/report evidence source kinds/counts, preserves non-authority flags, and leaves generated program files unchanged. |
| Promotion-review refinement | `program-promote review` explicitly consumes a `program-gen` manifest, original generated promotion shell artifacts, declared behavior evidence (`behavior_results.json` when present, otherwise bounded `behavior_episode.json`), a non-authoritative Oracle report, and a `program-refinement-proposal-v1` artifact, then writes a local `program-promotion-review-refined-v1` sidecar. | A user can bring behavior, Oracle interpretation, and refinement proposal evidence into one adjudication packet without treating any of it as approval. | The refined packet is local review evidence only: it does not overwrite `promotion_review.json`, invoke an adjudicator, promote, rank, prune, block via Oracle, mutate governance, run new behavior, or generate a new candidate. | A refined packet keeps `promotion_state: not_promoted`, preserves explicit missing model-jury/adjudicator requirements, records behavior evidence kind/presence and non-authority flags, and leaves generated program files unchanged. |
| Local jury execution | `program-promote jury` explicitly consumes a `program-gen` manifest, planned `jury.json` / `jury_selection.json` / `jury_rubric.json`, and already-generated behavior evidence: example-backed `behavior_results.json` when present, otherwise bounded `behavior_episode.json` from generated harness orchestration. It then writes a `program-jury-results-v1` sidecar. | A user can inspect per-juror deterministic local judgments and agreement/disagreement without treating jury evidence as authority. | This slice is offline and deterministic: it preserves planned provider/model fields but does not call external models, does not run new example/dataset/model-jury/topology/custom-module behavior, does not mutate the candidate or promotion review, does not create Oracle indexes, does not introduce or broaden `eval_behavior.py`, and does not rank, select winners, approve, promote, export authority, mutate AK, or mutate governance. | A jury sidecar preserves candidate identity, jury schemas/counts/perspectives, behavior evidence kind/presence, per-juror criteria results, aggregate counts/disagreement, effect flags, and non-authority flags. |
| Promotion decision recording | `program-promote decide` explicitly consumes a `program-promotion-review-refined-v1` packet plus operator/adjudicator input and writes a `program-promotion-decision-record-v1` sidecar. | A user can record an inspectable local decision outcome without confusing it with activation or external governance. | The decision record is local evidence only: it does not mutate generated program artifacts, the refined review packet, Oracle, AK, governance, or external authority. `promote` fails closed unless `review_readiness.ready_for_adjudicator_review` is true; top-level `review_packet_ready` is not sufficient. | A decision record preserves identity from the refined packet, records rationale/decider/outcome, keeps non-promote outcomes unpromoted, and carries local-only/no-mutation flags. |
| Second-candidate generation | `program-refine generate-candidate` explicitly consumes a source manifest, a proposed refinement, and a local `request_more_evidence` decision record, then materializes one local second candidate at `--outdir`. | A user can turn an explicit request for more evidence into a bounded follow-up candidate without making the proposal or decision record authoritative. | The first slice applies only bounded `constraints` patches, writes only the new candidate directory, and does not mutate the source candidate, proposal, decision record, Oracle, AK, governance, or external authority. | A second candidate manifest records refinement lineage in intent options, remains `not_promoted`, and carries local-only/no-external-mutation posture. |
| Candidate comparison | `program-refine compare-candidates` explicitly consumes two already-materialized `program-candidate-assembly-v1` manifests and writes a `program-refinement-candidate-comparison-v1` local sidecar; `program-refine generate-and-compare` is an explicit ergonomic workflow over one second-candidate generation plus that same comparison sidecar. | A user can inspect whether the request-more-evidence path changed generated local behavior evidence before any future promotion/export work. | The comparison is limited to already-generated `behavior_episode.json` plus example-backed `behavior_results.json` when present; it reports deltas only and does not run new behavior, Oracle, jury, topology, or custom-module execution. The workflow generates exactly one second candidate when explicitly invoked. Neither path ranks, selects winners, promotes, mutates Oracle authority, AK, governance, external authority, or source candidate artifacts. | A comparison sidecar records source/candidate identities, optional refinement lineage, behavior evidence kind/presence, behavior status/count/source deltas, failure signals added/removed/persisted, and local-only/non-authority flags; the workflow result points at the generated candidate plus comparison sidecar without making either authoritative. |
| Local adjudication plan | `program-promote plan` explicitly consumes an existing candidate manifest, local decision record, and comparison sidecar, plus a declared local target and authority owner, and writes a `program-promotion-plan-v1` sidecar. | A user can capture what local promotion/adjudication planning evidence exists without applying promotion or exporting authority. | The plan is `planned_not_applied` and `promotion_state: not_promoted`; it records target, authority owner, eligibility, evidence hashes, audit trail, and reversibility posture, but `allowed_for_apply` remains false and missing required evidence includes future authority/apply requirements. | A promotion plan sidecar leaves candidate artifacts, decision records, comparison sidecars, Oracle indexes, AK, governance, and external authority unchanged; it does not rank, select winners, approve, promote, deploy, or make Oracle authoritative. |
| Optimization / search | GEPA and optimization surfaces exist as bounded mechanisms for programs exporting expected hooks; `program-refine optimize-gepa` now adds an explicit local sidecar over an existing `program-candidate-assembly-v1` manifest, using explicit JSONL train/validation files, manifest dataset splits, or limited inline examples. | Search/reflection engines propose or improve candidate assemblies while runtime objects and governance boundaries remain explicit. | The current GEPA sidecar can truthfully record an attempt and local DSPy optimizer output, but it does not yet materialize a new `program-candidate-assembly-v1`; degraded results keep `candidate: null`. | A generated program assembly can enter an explicit optimization attempt whose outputs are local sidecars/evidence, not ranking, winner selection, promotion, or authority. |
| Governance / authority | SG2 has extensive governance-only receipt and review-decision contracts; current program-gen MVP explicitly does not widen ranking, pruning, promotion, Oracle, external adapter apply, or governance authority; generated assemblies carry `promotion_review.json` with an explicit pending adjudicator that may be human, one AI agent, an AI council, a hybrid, or a policy gate plus opaque external authority refs when supplied. A separately invoked Agent Kernel authority adapter can emit a `planned_not_exported` sidecar export plan from manifests/receipts, a stronger `agent-kernel-export-preflight` command can emit a `program-external-authority-export-preflight-v1` packet from a manifest, explicit external ref, and optional decision/comparison sidecars, and `program-promote status` can emit a `program-candidate-state-v1` truth-state summary over the manifest plus local sidecars. | Candidate assemblies can be evaluated, compared, withheld, reviewed, summarized, and promoted through explicit local/runtime/governance boundaries. | The program-shaped promotion/review shell, candidate-state summary, and export preflight are local and non-authoritative; the state summary explains current local truth across sidecars including local jury-results evidence, and the preflight records hashes, idempotency, planned evidence attachment payload, no-mutation effect flags, and apply blockers, but neither can call AK, check external duplicates, emit apply receipts, rollback, or mutate external authority. | Program assemblies have explicit local promotion-state metadata and any governance transition is backed by a dated contract/ADR and external authority truth when a future optional apply adapter is explicitly implemented and invoked. |
| Operator / user experience | Power users can run separate CLI surfaces for signature, module, optimize, replay, Oracle, and program-gen; `program-loop` now provides a first coherent local command that composes one intent through program generation, replay check, candidate-local Oracle indexing/reporting, and candidate-state summary without authority effects. | A user can start with one intent, inspect the generated plan/surfaces, run/evaluate, replay, ask Oracle what happened, and choose the next bounded refinement. | The product has a first integrated intent-to-evidence loop, but refinement/search/review/activation still require explicit follow-on commands rather than one guided product flow. | A documented walkthrough and `program-loop` smoke prove one intent flowing through assembly, execution, receipt replay, Oracle interpretation, and state summarization. |

## Current strengths

- DSPx has a local-first CLI/product identity centered on DSPy development rather than hosted SaaS.
- Native signature generation and refinement already exist with deterministic and provider-backed paths.
- `module-gen` has a mature module synthesis/evidence stack, including quality events, receipt metadata, replay integration, and SG2 governance-only evidence surfaces.
- Program-shaped candidate assemblies now exist through `program-gen`, including separate signature/module/program/eval surfaces, manifest metadata, receipt-bundle IDs, and per-surface provenance.
- Receipt/replay infrastructure gives the product a durable evidence spine.
- `program-loop` now dogfoods that spine as a single local command: materialize candidate, replay-check receipt, index/report Oracle-readable behavior evidence in a candidate-local index, and write a candidate-state summary without authority effects.
- Oracle already has behavioral coordinate, search, neighbor, drift, territory, frontier, attractor, and contract concepts in the product surface.
- The docs already separate runtime evidence, Oracle interpretation, and governance authority.

## Current gaps

- `program-gen` composes deterministic signature/module surfaces, emits `program-plan-v1` plus standalone `module_surfaces.json` / `jury.json` / `jury_selection.json` / `jury_rubric.json` / `promotion_review.json` with opaque non-exporting `external_authority` refs / `promotion_adjudication_request.json` / `promotion_decision_template.json`, preserves typed/described field specs, can validate inline examples and relative `examples_path` files, can materialize deterministic local dataset splits from JSONL/JSON/YAML example-shaped records or explicit split files, can carry explicit or per-program inferred planned `program-jury-v1` multi-model/perspective contracts, and now preserves explicit user/Pi-declared topology while rendering the narrow supported `pipeline` subset, but it does not infer topology, support broad graph execution, execute arbitrary custom Python module imports, support tools/retrievers/ReAct/ProgramOfThought, execute selected jury behavior, run GEPA/search automatically, or export/apply to external authority. External authority export preflight is a separately invoked adapter seam and remains local-only; whole-candidate truth-state summarization is also separately invoked and local-only.
- The current program execution episode now includes bounded `eval_behavior.py` orchestration over inline/example-file sources and declared dataset splits, source-indexed `evaluation_sources`, aggregate `behavior_evidence_summary`, metric/runtime/provider facts already known, and source-aware Oracle-readable evidence over those behavior sources, but it is not yet a rich declared evaluation episode over traces, model-jury execution, broad topology behavior, or explicit quality criteria.
- Program receipts now expose a source-aware Oracle-readable evidence view, an explicit local indexing path, an explicit local report path for non-authoritative behavioral interpretation, an explicit source-aware local refinement-proposal path, an explicit local promotion-review refinement packet path, an explicit local adjudicator decision-record path, an explicit request-more-evidence second-candidate path, an explicit local source-vs-candidate comparison path, an explicit local promotion/adjudication plan path, and an explicit local candidate-state summary path, but DSPx still does not invoke Oracle indexing, interpretation, refinement, promotion review, decision recording, second-candidate generation, candidate comparison, promotion planning, or state summarization during `program-gen`.
- GEPA/search is now present as an explicit local sidecar seam over program candidate manifests, but it is not automatic and does not yet turn optimizer output into a new `program-candidate-assembly-v1`; proposal acceptance remains separate from this GEPA path.
- The operator experience now has a first `program-loop` command for the core one-intent to evidence/state path, but still requires knowing separate CLI surfaces for refinement, GEPA/search, review, decision recording, second-candidate generation, comparison, promotion planning, external preflight, and activation packets.
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

1. **Deepen the structured intent and plan contract.** `program-plan-v1` now captures task type, default or explicit declared topology, normalized fields, declared-vs-materialized topology status, surfaces, metrics, runtime, constraints, examples metadata, non-authority defaults, and explicit planned `program-jury-v1` juror/perspective contracts; the remaining work is richer normalization, dataset splits, executable jury episodes, desired DSPy strategy, and actual multi-step topology rendering/execution.
2. **Upgrade materialization into real execution episodes.** The current execution episode records source-indexed behavior evidence over examples and deterministic dataset splits through bounded `eval_behavior.py` orchestration; the remaining target is richer traces, quality criteria, selected jury execution, and broader topology behavior behind explicit contracts.
3. **Use program receipt bundles as Oracle inputs.** `program-gen` now emits a source-aware readability-only evidence contract, `oracle index --from-program-evidence` ingests it into a local CoordinateIndex, and `oracle program-evidence report` summarizes those indexed records as deterministic behavioral interpretation without authority widening.
4. **Add bounded refinement/search.** `program-refine propose` provides the proposal-only seam over manifest + source-aware behavior evidence + Oracle report, `program-refine generate-candidate` covers the request-more-evidence second-candidate path, and `program-refine optimize-gepa` records an explicit local GEPA attempt sidecar over existing manifests; later work can turn safe optimizer output into a candidate assembly only behind a real non-authoritative materializer.
5. **Document and ship one end-to-end loop.** `docs/project/program-gen-walkthrough.md` now shows one intent moving through assembly, execution-episode evidence, receipt/replay, Oracle-readable evidence, explicit temp-dir indexing, explicit non-authoritative program-evidence reporting, candidate-state summary, and the new `program-loop` command; later work can extend the guided loop into refinement episodes once those remain safe and non-authoritative.

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
