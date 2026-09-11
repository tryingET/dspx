---
summary: "Target-state contract for DSPx as a behavior-first runtime for empirical evolution of DSPy systems."
read_when:
  - "When deciding whether new synthesis behavior belongs in module_service, program_service, or a deeper runtime object model"
  - "When integrating GEPA-backed search and Oracle empirical analysis without collapsing authority boundaries"
---

# Behavior-First Runtime Boundary

## Status

This document replaces the narrower ladder-style framing for richer program synthesis with a target-state contract.

It is intentionally **contract-first, not execution-first**:
- it does **not** materialize AK implementation tasks by itself,
- it does **not** authorize widening live behavior just because the target shape is clearer,
- it exists so later implementation slices can bind against the right ontology instead of inheriting a cramped one.

## Target definition

DSPx should become a **local-first behavior-first runtime for empirical evolution of DSPy systems**.

It should not be understood primarily as:
- a module generator with extra features,
- a prompt optimizer with receipts,
- or a single service that merely turns modules into programs.

Its deeper role is to:
- evolve candidate DSPy systems,
- execute them under explicit conditions,
- emit replayable evidence by default,
- let Oracle interpret their observed behavior,
- and use that empirical field to shape later synthesis and search without collapsing governance or promotion authority.

## Why this boundary exists

The product north star is larger than module artifact generation and larger than a single "program synthesis service":

`candidate surfaces -> candidate assembly -> execution episodes -> receipts/traces -> Oracle empirical interpretation -> later search shaping -> bounded promotion`

Without an explicit boundary, DSPx risks repeatedly collapsing richer runtime concerns into whatever existing service is nearby:
- `module_service` becomes overloaded with program concerns,
- `optimize_service` looks like the semantic owner of synthesis,
- Oracle looks like downstream analytics instead of an empirical interpreter,
- and promotion semantics get muddied between optimizer success and explicit authority.

This boundary exists to stop that collapse.

## The core architectural claim

The center of gravity should not be a service name.
The center of gravity should be a small set of first-class runtime objects.

Service boundaries still matter, but they should be derived from the runtime ontology rather than used as a substitute for it.

## First-class runtime objects

### 1) Candidate Surface

A **candidate surface** is any editable/evolvable part of a DSPy system.

Examples:
- signature
- module
- program
- prompt
- configuration
- orchestration structure

Why it matters:
- this is the true mutation/search substrate,
- "program" is a major case, but not the only one,
- the runtime should not overfit its ontology to a single editable surface.

Primary owner:
- DSPx runtime contract

### 2) Candidate Assembly

A **candidate assembly** is a concrete materialized candidate built from one or more candidate surfaces.

Examples:
- a runnable DSPy program directory,
- a composed module + signature + config bundle,
- a replayable module-surface contract that declares module IO/effects/provenance without importing or executing arbitrary custom code,
- a prompt/config/control-flow combination ready for execution.

Why it matters:
- it is the executable unit,
- it gives synthesis something stable to run, replay, compare, withhold, or promote,
- it is the first place where `program_service` becomes a truthful major boundary.

Primary owner:
- DSPx runtime contract

### 3) Execution Episode

An **execution episode** is one bounded run of a candidate assembly under an explicit setup/evaluation context.

Includes:
- provider/runtime conditions,
- dataset or input slice,
- evaluation harness,
- policy/constraint envelope,
- bounded execution metadata.

Why it matters:
- behavior only becomes real when a candidate assembly is run,
- episodes are where design intent meets runtime reality.

Primary owner:
- DSPx runtime contract

### 4) Receipt Bundle

A **receipt bundle** is the canonical replay/evidence artifact for an execution episode.

Includes:
- candidate assembly identity,
- execution inputs/outputs,
- evaluation results,
- runtime/environment metadata,
- trace references,
- replayable evidence sufficient for later analysis.

Why it matters:
- receipts are the spinal cord of the system,
- Oracle should consume replayable evidence rather than anecdotes,
- promotion semantics should be grounded in explicit episode evidence.

Primary owner:
- DSPx runtime contract

### 5) Behavioral Phenotype

A **behavioral phenotype** is the empirically observed behavioral character of a candidate or candidate lineage across execution episodes.

Examples:
- recurring failure modes,
- convergence tendencies,
- drift signatures,
- robustness patterns,
- task-family strengths or weaknesses.

Why it matters:
- this is where "behavior-first" becomes real,
- the system should know not just what a candidate is, but how it behaves.

Primary owner:
- Oracle empirical analysis layer

### 6) Territory / Frontier Map

A **territory / frontier map** is Oracle's higher-order topology of the behavioral field.

Examples:
- saturated regions,
- unstable regions,
- promising unexplored regions,
- attractors,
- anti-pattern basins,
- frontier candidates or families worth exploration.

Why it matters:
- this is how isolated evaluations become navigable empirical structure,
- later synthesis/search can use this map to shape exploration versus exploitation.

Primary owner:
- Oracle empirical analysis layer

### 7) Promotion State

A **promotion state** is the explicit status of a candidate assembly after evaluation.

Examples:
- exploratory,
- evaluated,
- withheld,
- selected,
- promoted,
- superseded.

Why it matters:
- optimizer success must not silently become authority,
- empirical promise must not silently become promotion,
- runtime selection and later governance/promotion boundaries must remain explicit.

Primary owner:
- DSPx locally for synthesis/runtime state,
- AK/governance where canonical authority leaves DSPx-local engineering scope.

## What this means for service boundaries

## `module_service`

`module_service` remains truthfully scoped to module artifact generation.

It should continue to own:
- `signatures -> modules`,
- module materialization,
- module-scoped validation and smoke checks,
- module-scoped synthesis runtime integration when the selected artifact is still a module,
- module-scoped receipts/diagnostics/promotion shell behavior.

It should not become the semantic owner of:
- multi-artifact candidate assembly,
- execution-episode orchestration at program scope,
- Oracle-coupled empirical search shaping,
- jury/program optimization entrypoints when the assembly under evaluation is larger than a module.

## `program_service`

`program_service` is still useful, but it is **not** the final ontology of the system.

It should be understood as the first strong owner of **program-shaped candidate assembly**.

It should eventually own:
- `modules -> programs` when the resulting unit is a program-shaped candidate assembly,
- program-scoped materialization,
- program-scoped execution setup,
- program-scoped receipt emission,
- program-scoped promotion semantics.

It should not be mistaken for:
- the whole empirical phenotype layer,
- the territory/frontier layer,
- the search engine itself,
- governance authority.

## `optimize_service`

`optimize_service` remains a bounded optimization/search mechanism surface.

It is useful when:
- running GEPA-backed optimization,
- executing a particular search workflow,
- evaluating bounded candidate-improvement procedures.

It is not the semantic owner of:
- what a candidate assembly is,
- what an execution episode is,
- what a receipt bundle is,
- what Oracle means by phenotype or frontier,
- what promotion state means.

## How GEPA fits

GEPA should be treated as a **search/reflection engine inside DSPx**, not as the architecture itself.

GEPA may own:
- mutation/reflection strategy,
- bounded candidate proposal/evolution,
- search over prompts/programs/configurations under declared metrics.

GEPA does not replace:
- candidate assembly boundaries,
- execution-episode boundaries,
- receipt bundles,
- Oracle's empirical interpretation layer,
- explicit promotion state.

This keeps GEPA powerful but replaceable.

## How Oracle fits

Oracle is **not** auxiliary analytics.
Oracle is the empirical interpreter of the runtime's own behavioral world.

Oracle should own:
- behavioral phenotype derivation,
- territory/frontier/topology over observed behavior,
- recurrence, drift, attractor, and failure-pattern interpretation,
- later advisory search-shaping signals grounded in receipts and traces.

Oracle should **not** own:
- direct promotion authority,
- canonical governance authority,
- silent policy mutation,
- replacement of receipt-based replay truth.

A good test:
- if the concern is "what happened, what patterns recur, and where should bounded exploration go next?" it belongs with Oracle,
- if the concern is "what was executed, materialized, replayed, selected, or promoted?" it belongs with DSPx runtime contracts,
- if the concern is "what is legally canonical beyond DSPx-local engineering scope?" it belongs with AK/governance surfaces.

## Receipt and evidence stance

DSPx remains a receipts-first system.

That means:
- execution episodes should emit replayable receipt bundles by default,
- Oracle should consume those receipts/traces as empirical evidence,
- search shaping should be evidence-backed rather than intuition-only,
- promotion state should remain explicit and inspectable,
- external search success should not self-authorize promotion.

## Canonical authority by surface

Verdict vocabulary and owner routing are defined once in the [DSPx verdict classification and source-owner contract](dspx-verdict-classification-and-source-owner-contract.md). This target-state boundary does not turn local evaluation, Oracle interpretation, promotion state, or documentation into ROCS conformance or external activation authority.

### Canonical in docs

Docs are canonical for:
- the target runtime ontology,
- service-boundary interpretation,
- scope/non-goals,
- authority separation before implementation tasks exist.

This document is therefore the canonical target-state boundary note for this concern until superseded by a dated ADR or narrower implementation contract.

### Canonical in DSPx runtime artifacts

DSPx runtime artifacts are canonical for:
- candidate assemblies,
- execution episodes,
- receipt bundles,
- local synthesis/promotion state inside DSPx.

### Canonical in Oracle

Oracle is canonical for:
- empirical phenotype interpretation,
- territory/frontier/topology over accumulated episode evidence,
- advisory empirical signals derived from receipts and traces.

### Canonical in AK

AK is canonical for:
- execution materialization outside this docs-only contract stage,
- repo-local task/decision runtime truth where that workflow is active,
- later governance/promotion/runtime authority once the concern leaves DSPx-local engineering scope.

### Canonical in Prompt Vault

Prompt Vault is canonical for:
- reusable procedures/templates/routers,
- controlled prompt-body assets intended for reuse.

Prompt Vault is not canonical for:
- runtime state,
- execution truth,
- promotion state,
- Oracle empirical interpretation,
- repo direction truth.

## Scope

This boundary covers:
- the target-state ontology for a behavior-first DSPx runtime,
- the first-class runtime objects that should anchor that ontology,
- the truthful placement of `module_service`, `program_service`, `optimize_service`, GEPA, Oracle, and promotion state,
- authority separation across docs, DSPx runtime artifacts, Oracle, AK, and Prompt Vault.

## Non-goals

This document does **not**:
- define the final code/API surface for every runtime object,
- authorize implementation work by itself,
- define live promotion policy,
- replace AK direction/task/decision authority,
- collapse Oracle into governance authority,
- require immediate changes to `module_service`, `program_service`, or `optimize_service`.

## Relationship to current repo direction

AK direction/task/decision runtime is the active direction and execution authority where landed. Checked-in docs such as [[vision]] and [[product-posture]] are projections/orientation unless imported or reconciled through AK.

This document clarifies the target-state runtime ontology.
It does not by itself change active execution truth.

## Immediate consequence

After this doc lands, the repo has a stronger and less misleading contract for saying:
- DSPx's future should be framed as a behavior-first runtime for empirical evolution of DSPy systems,
- `program_service` is a key boundary but not the whole architecture,
- Oracle is a first-class empirical interpreter rather than a downstream analytics afterthought,
- GEPA is one engine inside the runtime rather than the architecture itself,
- future implementation slices should bind to runtime objects and authority boundaries that can compound cleanly.

## First implementation foothold

`AK-1827` / `docs/adr/20260423-intent-to-program-candidate-assembly-mvp.md` materialized the first bounded foothold for this boundary: `program-gen` can now read one structured JSON/YAML intent and write a deterministic program-shaped candidate assembly with `plan.json`, standalone `intent_normalization.json`, standalone `module_surfaces.json` (`program-module-surfaces-v1` / `program-module-surface-v1`), standalone `jury.json`, deterministic `jury_selection.json`, deterministic `jury_rubric.json`, `promotion_review.json` with optional opaque non-exporting `external_authority` refs, `promotion_adjudication_request.json`, `promotion_decision_template.json`, standalone `execution_episode.json`, explicit or per-program inferred planned `program-jury-v1` contracts, optional explicit topology preserved as declared input and materialized for the bounded supported `pipeline`, `router`, `retrieve_then_answer`, `extract_transform_validate`, and `generate_critique_revise` subsets, `signature.py`, `module.py`, `program.py`, `eval_smoke.py`, `eval_jury.py`, `eval_promotion.py`, typed/described signature fields when provided, optional `examples.json` / `eval_examples.py` from inline `examples` or `examples_path`, optional deterministic dataset split artifacts (`dataset_manifest.json`, `splits/{train,validation,test}.jsonl`, `eval_{train,validation,test}.py`, `behavior_results.{train,validation,test}.json`) from declared `dataset` / `datasets`, normalized `intent.json`, `manifest.json`, and a standard `program-gen` run receipt.

The current implementation keeps that foothold narrow while making the surface boundary more truthful:
- it proves the intent -> candidate assembly -> execution episode -> receipt bundle spine at program shape,
- it keeps orchestration in `dspx.services.program_service` rather than overloading `module_service`,
- it composes the existing signature/module generation services as candidate-surface providers,
- it records intent-normalization/plan/module-surface/jury/selection/rubric/promotion-review/external-ref/adjudication-request/decision-template/execution-episode provenance, declared-vs-materialized topology status, generator provenance, optional example-binding evidence, source-indexed behavior-result evidence over inline examples / `examples_path` / dataset splits, source-aware Oracle-readable evidence over those behavior sources, and per-surface hashes in the manifest/receipt evidence,
- a separately invoked Agent Kernel authority adapter can consume those manifests/receipts and produce a receipted sidecar export plan without mutating external authority,
- a stronger separately invoked `adapters authority agent-kernel-export-preflight` command can consume a manifest, explicit opaque AK ref, and optional decision/comparison sidecars to write a local `program-external-authority-export-preflight-v1` packet with input schemas/hashes, manifest identity, deterministic `export_id`/idempotency fingerprint, an `ak_task_evidence_attachment` planned payload, no-mutation effect flags, local preflight blockers, and separate future external-apply blockers,
- a separately invoked Oracle indexing command can consume `program-oracle-evidence-v1` artifacts into a local CoordinateIndex as searchable evidence,
- a separately invoked Oracle program-evidence report command can read those indexed records and summarize source-aware behavior evidence without ranking, pruning, promotion, governance, external mutation, or program-gen automation,
- a separately invoked `program-refine propose` command can consume the manifest, declared `behavior_results.json` when inline/example-file behavior exists, source-indexed execution/oracle evidence when dataset-only behavior exists, and an explicit non-authoritative Oracle report to write a local `program-refinement-proposal-v1` artifact only,
- a separately invoked `program-promote review` command can consume the manifest, original generated promotion shell artifacts, declared behavior evidence (`behavior_results.json` when present, otherwise bounded `behavior_episode.json`), the explicit Oracle report, and the explicit refinement proposal to write a local `program-promotion-review-refined-v1` sidecar packet,
- a separately invoked `program-promote jury` command can consume an existing manifest, planned jury artifacts, and already-generated behavior evidence (`behavior_results.json` when present, otherwise bounded `behavior_episode.json`) to write a local deterministic `program-jury-results-v2` sidecar without model calls, new behavior execution, candidate mutation, Oracle indexing, ranking, winner selection, promotion, AK, or governance effects,
- a separately invoked `program-promote decide` command can consume that refined review packet plus explicit operator/adjudicator input to write a local `program-promotion-decision-record-v1` sidecar,
- a separately invoked `program-refine generate-candidate` command can consume a proposed refinement plus a local `request_more_evidence` decision record to materialize one explicit local second candidate at a requested output directory,
- a separately invoked `program-refine compare-candidates` command can consume already-materialized source and refinement candidate manifests, read already-generated `behavior_episode.json` plus example-backed `behavior_results.json` when present, and write a local `program-refinement-candidate-comparison-v1` sidecar with behavior evidence kind, status/count/source, and failure-signal deltas,
- a separately invoked `program-refine generate-and-compare` command can serve as an explicit local operator workflow over exactly one second-candidate generation followed by the same comparison sidecar,
- a separately invoked `program-promote plan` command can consume an existing candidate manifest, a local decision record, and a comparison sidecar plus explicit target and authority-owner inputs, then write a local `program-promotion-plan-v1` sidecar with `planned_not_applied` / `not_promoted` posture, behavior-results and behavior-episode evidence hashes, eligibility, audit trail, and reversibility posture,
- a separately invoked `program-refine optimize-gepa` command can consume an existing `program-candidate-assembly-v1` manifest, explicit JSONL train/validation files or manifest dataset splits or limited inline examples, and write a `program-refinement-gepa-result-v1` sidecar; the current GEPA optimizer may only produce local DSPy optimizer output, not a new candidate assembly, so the sidecar degrades truthfully with `candidate: null` unless a real candidate materializer exists,
- the refinement proposal, refined promotion-review packet, jury-results sidecar, decision record, comparison sidecar, local promotion/adjudication plan, external-authority export preflight packet, generate-and-compare workflow result, and GEPA refinement result do not mutate generated source program files, do not overwrite `promotion_review.json` / adjudication request / decision template artifacts, do not mutate `promotion_review_refined.json`, and cannot rank, select winners, prune, promote, deploy, block via Oracle, apply authority, mutate AK, mutate governance, or make Oracle authoritative,
- second-candidate generation is explicit and local: it applies only the bounded constraints patch in this first slice, writes only the requested new candidate directory, records refinement lineage in the new candidate intent, and does not mutate the source candidate, proposal, decision record, Oracle, AK, governance, or external authority,
- candidate comparison is explicit and local: it writes only the requested sidecar, does not generate a third candidate, does not run new behavior/Oracle/jury/topology/custom-module execution, does not mutate either candidate, and does not treat Oracle as authority,
- promotion/adjudication planning is explicit and local: it writes only the requested `program-promotion-plan-v1` sidecar, keeps `allowed_for_apply: false`, records missing apply/external-authority evidence, and does not mutate candidate artifacts, decision records, comparison sidecars, Oracle indexes, AK, governance, or external authority,
- external-authority export preflight is explicit and local: it writes only the requested `program-external-authority-export-preflight-v1` packet, preserves `planned_not_exported` / `ready_not_applied` or `incomplete_preflight` posture, keeps local `blocking_reasons` empty when `ready_not_applied`, keeps `ready_for_future_apply: false`, reports `external_apply_not_implemented` and `target_contract_not_bound_to_ak_runtime` as separate `external_apply_blocking_reasons`, degrades when optional decision/comparison sidecars are absent, fails closed on explicit identity mismatch, and does not call AK or mutate governance/external authority,
- candidate-state summarization is explicit and local: `program-promote status` writes only the requested `program-candidate-state-v1` sidecar, summarizes manifest/behavior-results/behavior-episode/Oracle/proposal/review/decision/jury-results/comparison/plan/export-preflight truth plus artifact hashes, local preflight blockers, and future external-apply blockers, reports missing optional sidecars instead of inventing readiness, treats local jury results as evidence only, fails closed on authority-widened or mismatched inputs, and does not call AK, mutate sidecars, mutate Oracle indexes, select winners, promote, or apply authority,
- non-promote decision outcomes keep the candidate unpromoted, while `promote` fails closed unless `review_readiness.ready_for_adjudicator_review` is explicitly true and remains local-only even when recordable,
- explicit topology is validated and preserved as declared input; bounded `pipeline`, `router`, `retrieve_then_answer`, `extract_transform_validate`, and `generate_critique_revise` subsets are rendered into multiple `Predict`/`ChainOfThought`/bounded no-tool `ReAct`, explicit opt-in no-tool `ReActV2` when public `dspy.ReActV2` is installed, and sandboxed `ProgramOfThought` signature/module classes plus composed `program.py` with simple `when.field`/`when.equals` routing, `retrieve_then_answer` additionally requires every bounded inline or materialization-time local-corpus snapshot Retriever output to feed a downstream answer module that reaches `output`, `module_surfaces.json` records one generated module surface per materialized topology module, `program_runtime_outcomes.json` records the normalized final-output/trajectory outcome contract for those surfaces, `program_runtime_traces.json` records hash-bound local generated-harness module-call/final-output trace evidence when behavior examples or dataset splits execute, and `program_tool_contracts.json` records descriptor-only future tool id/name, schema, effect, allowlist, timeout, redaction, dry-run/mutation, non-authority, and absent-adapter provenance while unsupported topology kinds remain declared-only,
- no LM/provider topology inference is performed and no broad graph engine, arbitrary expressions, arbitrary custom Python module imports/execution, live external tools/retrievers, ReAct/ReActV2 tool binding, `dspy.Tool` execution, or ProgramOfThought filesystem/network/env/tool sandbox access is claimed,
- inline examples remain `eval_examples.py` / `behavior_results.json`; declared datasets add split-specific `eval_train.py`, `eval_validation.py`, `eval_test.py`, and split-specific behavior result artifacts; bounded `eval_behavior.py` orchestrates only those generated harnesses and writes `behavior_episode.json` instead of becoming broad execution authority,
- it remains scaffold-first and deterministic,
- and it does not widen live ranking, pruning, promotion, Oracle, external adapter apply/export mutation, or governance-policy authority.

## Recommended next execution shape

When the repo is ready to materialize this concern, the best first slice should remain small but ontology-preserving.

Prefer a contract-grounding implementation step such as:
- deepen the deterministic ProgramPlan contract into richer candidate-assembly planning,
- deepen the first minimal local behavior-results contract into richer execution episode + receipt bundle semantics,
- integrate territory/frontier views over the indexed program-evidence run kind,
- broaden second-candidate generation beyond request-more-evidence constraints patches once a clearer accepted-proposal policy exists,
- integrate territory/frontier views over the indexed program-evidence run kind,
- deepen execution episodes toward selected jury behavior or richer trace consumers only behind explicit contracts; the current `eval_behavior.py` remains bounded to generated example/split harness orchestration and `program_runtime_traces.json` remains local evidence only,
- deepen local promotion/adjudication plans, candidate-state summaries, and external-authority export preflights from decision records and comparison evidence while keeping apply as a separate future authority surface that must bind an exact AK target contract, perform duplicate checks, emit an apply receipt, and define rollback/failure semantics.

Current dataset split support is deliberately evidence-only: it accepts JSONL or JSON/YAML list-of-object records shaped like inline examples, materializes deterministic local train/validation/test splits by ratio seed or explicit split files, records hashes in manifest/receipt/replay, adds each split's behavior result to `execution_episode.evaluation_sources` plus the aggregate `behavior_evidence_summary`, and includes split sources in readability-only `oracle_evidence.json`. It does not run Oracle indexing, GEPA/search, jury execution, ranking, promotion, authority export, AK/governance mutation, custom module execution, or topology inference during `program-gen`; `program-promote jury` can later consume already-generated `behavior_episode.json` explicitly as local non-authoritative jury evidence without running new dataset/model behavior, and `program-refine optimize-gepa` can consume split artifacts explicitly as local non-authoritative refinement input.

Do not start by stuffing richer synthesis behavior directly into `module_service`.
Do not mistake `program_service` for the final ontology of the runtime.

## Statechart-to-program-suite contract — AK5419 design

**Status: proposed design, not implemented or activated.** AK5419 contract v3,
guardrails v2 and operator-route evidence **8364** authorize only reconciliation
in four existing documents. Core production readiness remains the priority;
`SF-AUTONOMOUS-PROGRAM-FOUNDRY` remains paused. Existing bounded jury work does not
reactivate its parent by implication. AK SF14/Decision140/task5210 and G7/task5281
retain their own scope. No new strategic frame, direction transition or runtime
owner is created here. Route approval is not acceptance of this design.

### Operating boundary and portable binding

Keep the entire behavioral machine above candidate-local computation. A versioned
statechart may invoke several independently versioned DSPy programs, with shared
review/cancellation/recovery protocols and separate receipt lineages. Existing
program-topology DAGs can be invoked leaves; they cannot represent the parent
machine's hierarchy, orthogonal regions or event-driven cycles.

Proposed portable binding records contain: machine ID/version/content hash;
state/region IDs; typed event schemas; named pure guard/assignment definitions;
ordered named effect descriptors; named actor/program registry entries; exact
candidate manifest and input/output schema hashes; input projections; budgets;
timeout/cancellation/retry policies; and requirement/test IDs. The owner reviews
this binding before a host may execute it. Neither a diagram nor a registry name
is executable authority. Inline JavaScript, Python imports and serializable
strings that name arbitrary code are not portable bindings.

The visual editor owns presentation and explicit edit proposals. A future
reviewed transition host owns event serialization, checkpoint/outbox and effect
custody. DSPx owns candidate assemblies, bounded episodes and receipts; the
source/knowledge owners own corpus disclosure and acceptance. AK owns canonical
work, direction, decision and evidence. A browser snapshot, Forge manifest or
Oracle verdict cannot replace any of those authorities. No host is selected or
implemented by this task.

### Semantic mapping and fail-closed support profile

This table defines the **proposed admissible profile**, not current DSPx or
installed XState support. An admission validator must reject an unsupported
construct with its exact state/path, reason and owner action; it must never
silently approximate it as a sequence.

| Construct | Required mapping | Rejection / acceptance probe |
|---|---|---|
| Atomic/final states | Stable IDs, explicit initial/final states and typed completion output; no program call merely because a node is displayed | Unresolved target/final output rejects; final state cannot accept another work request |
| Hierarchy | Preserve parent/child configuration, initial descent, ancestor event handling, entry/exit ordering and re-entry semantics | Test child-vs-parent priority, internal transition vs re-entry, and ancestor exit cascade; flattening rejects |
| Parallel regions | Simultaneous active configuration, independent child lifetimes, deterministic shared-event ordering, explicit join/cancellation policy | One region finishing cannot finish all; late result from a cancelled sibling cannot satisfy join; conflicting context writes reject absent declared merge rule |
| Events and cycles | Typed, identity-bound queued events with event ID, expected state revision and correlation; bounded eventless transitions and loop budgets | Duplicate key/body returns prior result; same key/different body conflicts; runaway eventless cycles reject rather than hang |
| Guards/context | Named pure predicates and typed immutable assignments from supplied snapshot/event; data projection preserves null/absent and enum distinctions | Reject clock, random, I/O, arbitrary expressions or unknown guard names; compare transition trace for the same journal |
| Entry/exit/named effects | Transition emits ordered descriptors; effect registry separately binds implementation, permissions and compensation policy | No external call during pure transition or display; unknown action/effect rejects before dispatch |
| Invoked DSPy programs | Named actor source binds exact candidate, input contract, output contract, source snapshot and working-intent identity; completion carries episode/receipt and actor incarnation | Stale identity, missing required output, provider error or unknown incarnation cannot become success; assemblies remain interconnected, not inlined into one opaque program |
| Timers | Stable timer ID and source address; host records accepted absolute deadline, handles cancellation and journals firing event | Restart cannot reset an accepted deadline; exited-state timer cannot advance new state; sleeping inline is not an interruptible timer |
| Cancellation | Stop admission of new work, issue typed cancel request, distinguish requested/acknowledged/unconfirmed; retain completed outputs as historical evidence | UI close/timeout is not proof a provider stopped; unknown external effect enters reconciliation, never automatic retry |
| Retry | Explicit bounded policy, immutable predecessor and new attempt identity; confirmed no-effect or reviewed idempotent replay only | HTTP status, missing receipt or XState batch rejection alone cannot authorize retry of effect-indeterminate work |
| Persistence/recovery | Bind machine/runtime/binding versions, intent/source hashes, active configuration, child identities, next transition index, event journal, pending effects and timer deadlines | Restore mismatched code/schema/intent rejects unless separately reviewed migration preserves lineage; snapshot alone cannot prove an effect did not happen |
| History/dynamic actors/remote placement | Preserve in the design vocabulary but initially unsupported unless separately specified and tested | Reject history pseudostates, unbounded spawning, executable closures, cross-host actor reconstruction and unsupported observation semantics; no silent downgrade |

Proposed host commit protocol separates **pre-dispatch intent custody** from a
**settled resumable checkpoint**:
1. Serialize one entity and validate its event/expected revision. Durably bind
   the event ID/body, predecessor checkpoint and computed effect intents before
   dispatch. This transition/event/effect-intent ledger records requested work;
   any computed next state there is provisional, **not a resumable snapshot**.
2. Hand off effects in order through the reviewed adapter. With v6, do not call
   `getPersistedSnapshot` until `executeEffects` resolves after all transitively
   initiated operations are accepted. Persist that settled checkpoint with
   `nextTransitionIndex`, machine ID/version and binding identity, consistently
   retaining pending root-event, child/incarnation and timer/deadline custody.
   Events arriving between acceptance and checkpoint must remain durably queued
   for exactly correlated later consumption, never lost at suspension.
3. Acceptance means the host took custody of an operation, not that its external
   business effect completed. Record **requested / accepted / completed /
   uncertain** separately from machine state and effect-owner acknowledgements.
   A settled checkpoint may still reference accepted, incomplete work. It cannot
   turn a missing response, timeout or cancellation request into completion.
4. A custom host driving pure transitions instead of `executeEffects` must supply
   transitive settlement, root-event capture/replay, ordered handoff and
   batch-failure handling itself. Without those guarantees it cannot checkpoint.
   Do not checkpoint a rejected/unsettled batch or blindly replay the batch:
   already accepted operations may have executed or delivered child events.
   Recover from the last settled checkpoint plus the durable intent/acceptance
   ledger and owner receipts; unresolved effects require owner reconciliation.

Crash before dispatch, after dispatch, during transitive acceptance and before
checkpoint/acknowledgement remain distinct dispositions. Deterministic IDs do not
prove exactly-once effects. A reused event key with another body is always a
conflict. Rejected/malformed events leave an inspectable rejection, not a
success-shaped empty transition. Queue limits, per-episode cost/time budgets,
scope and privacy checks precede every newly admitted effect. This is a proposed
host contract requiring future proof, not an implemented v6 adapter.

### XState comparison: exact candidates, no dependency selection

Source inspection on 2026-09-05 compared registry metadata for **6.0.0-alpha.52**
and **5.32.6**, v5 tagged source, and v6 upstream commit
`2c4eeb4881c7fab607ef2dd410e547c17f1bff87`. Both registry records have null
`gitHead`: reviewed source and published package are separate evidence, not
source-to-package equivalence proof. Nothing was installed or executed.

| Requirement | Stable 5.32.6 source/metadata | v6 alpha.52 candidate source/metadata | Design consequence |
|---|---|---|---|
| Pure transition boundary | `transition.ts` exposes pure snapshot + executable-action results; v5 is not merely an imperative runtime | `createDurable` wraps pure initial/next transitions with ordered stable-ID effects | Compare actual semantics, not presence of a new export |
| Actor/program boundary | `StateMachine.restoreSnapshot` reconstructs children from registered sources and persisted child state | Named `src`, serializable input and deterministic addresses support host-owned `runLogic`; named action descriptors carry type/args | Require typed registry/receipt bindings in either version; do not ship closures to Python |
| Persistence/effect custody | `getPersistedSnapshot`/`restoreSnapshot` exist; no `xstate/durable` export in the exact registry metadata | Experimental durable adapter contract includes effects, timers, waits, child routing, machine version and `nextTransitionIndex` | Host transaction, effect reconciliation, remote deduplication and storage are still our integration obligations |
| Retry/cancellation | Persistence API alone is not an external-effect journal | Rejected effect batches may redeliver all operations; `run()` is fresh-only, checkpoint resume uses explicit loop | Upstream retry ability does not override the no-indeterminate-retry rule |
| Local visualization | No local renderer/editor compatibility run performed | `createDurable(..., {inspect})` documents actor/transition observations, not a verified editor | Both need a separately authorized offline local renderer/round-trip test with hierarchy, parallelism and resumed traces |
| Adoption risk | Stable comparison baseline, not automatically safe or selected | Experimental API and source/package identity gap add migration and custody risk | Prefer v6 only as the next **evaluation candidate** for durable seams; retain v5 baseline and allow neither to pass |

A dependency selection requires owner-reviewed proof of the semantic matrix,
source/package/runtime identity, local-only visualization, cross-language JSON
fidelity, failure recovery and maintenance cost. This task selects **neither**.
A design can be accepted while the dependency remains unresolved. Do not bridge
arbitrary XState JavaScript to arbitrary DSPy/Python execution.

Source references (inspection, not runtime proof):
- [v6 durable execution](https://github.com/statelyai/xstate/blob/2c4eeb4881c7fab607ef2dd410e547c17f1bff87/docs/durable-execution.md): Identity, effect contract, journaling rules, checkpoints and host adapters.
- [v6 data/effects](https://github.com/statelyai/xstate/blob/2c4eeb4881c7fab607ef2dd410e547c17f1bff87/docs/data-and-effects.md) and [backend workflow](https://github.com/statelyai/xstate/blob/2c4eeb4881c7fab607ef2dd410e547c17f1bff87/docs/backend-workflows.md).
- [v5 pure transitions](https://github.com/statelyai/xstate/blob/xstate%405.32.6/packages/core/src/transition.ts) and [persist/restore implementation](https://github.com/statelyai/xstate/blob/xstate%405.32.6/packages/core/src/StateMachine.ts).
- Exact registry records: [v6 alpha.52](https://registry.npmjs.org/xstate/6.0.0-alpha.52), [v5 5.32.6](https://registry.npmjs.org/xstate/5.32.6).

## Reading intent and six-level contract

Method attribution: Richard Paul and Linda Elder, *How to Read a Paragraph*,
original five levels of close reading. The task's source-qualified method is
preserved below; **level 6 is our explicit application/transfer extension**, not
a claim about the authors' original numbering. No private PDF/note was reopened
for AK5419. Public article pages retrieved during design did not expose the full
five-level text, so this is task-contract attribution, not a new primary-text
verification claim.

| Level | Required operation and output | Anti-collapse rule |
|---|---|---|
| 1 — Paraphrase | Restate sentences/paragraph meaning in one's own words, preserving qualifiers and source location | Not free association or a purpose-shaped rewrite of what the author says |
| 2 — Explicate | State the main point, elaborate it, give an example and an analogy/illustration, separating supplied from generated examples | A headline alone is not explication |
| 3 — Analyze | Reconstruct purpose, question, information, concepts, assumptions, inferences, implications and point of view | Reader purpose cannot replace author `purpose_in_source` |
| 4 — Evaluate | Assess clarity, accuracy, precision, relevance, depth, breadth, logic, significance and fairness against cited evidence | Agreement with the selected puzzle is not evidence of truth |
| 5 — Author-perspective examination | Answer questions by role-playing the author's reasoned position, with source support, uncertainty and clear simulation label | Not invented author testimony; not omitted or relabeled as application |
| 6 — Added application/transfer | Propose a context-specific use, limits, counterexample and observable test, with uncertainty and a separate recipient/review boundary | Transfer is not filesystem apply, canonical acceptance or attribution to Paul/Elder |

First map the whole source and its argumentative structure. A purpose-guided plan
selects parts plus contrary evidence and explains exclusions. Paragraph outputs
retain source ID/hash, page/section/paragraph locator, excerpt hash and exact vs
approximate quotation status. Integrate the parts back into the whole; record
contradictions and changed interpretation. Missing source support means
`insufficient_evidence`, not an invented quotation or a completed level. Source
meaning, reader intent, critique, application proposal, review and accepted
knowledge stay separate objects even if shown on one screen.

### Proposed intent propagation

Reuse the Obsidian-owned provisional `working-reading-intent-v1` boundary:
`intent_id`, integer `revision`, `hash`, `supersedes`, source/decision refs,
candidate IDs/provenance, selected puzzle, `reader_purpose`, mode and explicit
exception reason. `purpose_in_source` and canonical `primary_puzzle_id` are never
aliases. Candidate provenance should bind the supplied puzzle-set snapshot,
source evidence, producer identity/version, rationale, uncertainty and alternatives;
no candidate is forced. A new manually suggested puzzle needs reviewed provenance
before becoming selectable, not an invented canonical register entry.

The current `reading_intent.producer_input` returns `source_input`, the complete
`working_reading_intent`, and `reading_intent_binding = {intent_id, revision, hash}`.
Its hash is SHA-256 over UTF-8, sorted-key compact JSON, non-ASCII preserved,
non-finite numbers rejected, excluding the `hash` field itself. Preserve that
exact producer convention; cross-language canonicalization requires golden-byte
vectors before another implementation is admitted. Do not invent a different
hash under the same schema name.

Proposed sequence:
1. An explicitly supplied source/puzzle snapshot feeds an automatic **proposal**
   producer; first-review acceptance or correction creates immutable intent vN.
   This proposal stage may inspect source structure but must not masquerade as
   the already purpose-sensitive whole/part/whole reading result.
2. The Obsidian intent owner supplies the full intent and independent binding.
   A DSPx input adapter validates source, schema and content/hash before mapping
   the envelope to **declared** DSPy signature fields; nested metadata alone is
   insufficient. `program-intent-v2` describes a program, not a reading session.
3. A future producer/run receipt binds the exact input hash, candidate manifest,
   intent identity and observed output hashes. Machine-generated output may echo
   intent for inspection, but the model is not trusted to certify which input ran.
4. Every dependent reading plan, paragraph result, synthesis, draft/campaign,
   review packet and downstream proposal carries that identity and producer
   provenance. Source-only extraction can be reused only if separately
   source-hash-bound and genuinely purpose-independent.
5. Correction appends vN+1, preserves vN/history and invalidates all descendants
   including in-flight completions. A completion for vN stays historical; it must
   not be rebound to vN+1. New work requires new input/receipt identity and lawful
   effect admission. Old approvals do not transfer to regenerated output.
6. `defer` and `source_only` block purpose-sensitive production; Wiki/Atlas-direct
   requires null puzzle plus explicit preservation purpose/reason. Direct is not
   forced puzzle selection and never permission for canonical apply.

The materializer must validate the independent producer receipt and the current
intent-owner identity before publishing a new review bundle. Bindings must agree
at bundle, campaign packet and dependent rows; copying the current UI identity
onto old outputs is forbidden. The review consumer independently checks current
intent, exact packet hash/revision and active prior RIGHT route. `/intent` and
`revise_campaign` remain recorded requests until a separately authorized consumer
exists. GET/render/gesture confirmation cannot invoke a producer.

### Current producer evidence and bounded owner handoff

Source baseline for this inspection: DSPx `ae60ad90860006a145bab04fb0c2cb12afe9f7cf`.
Obsidian safety implementation is `6930feec0d08b6e67d390132808a465855c1e6c5`, with
closeout documentation `c37c019691942558e97ce8d2436df81f161f623f`, evidence8355/8356
and transferred obligation8357. These are bounded safety/proposal evidence only.

| Current source locator | Observed contract | Design consequence |
|---|---|---|
| `tests/fixtures/program_gen/pdf_transition/intent.yaml:11–24,87–94,121–123` | Four inputs: `source_package_manifest_json`, `marker_markdown`, `existing_wiki_index_json`, `declared_output_root`; eight output names, purpose rubric and focused-bundle option | A tracked producer **scenario/fixture exists**; purpose rubric is not a versioned working-intent or automatic-suggestion input contract |
| `packages/dspx-core/src/dspx/services/program_intent.py:473–497` (`ProgramIntent`) | Structured program contract; `extra="forbid"`, declared IO/quality/runtime/options | A new top-level reading field cannot be assumed accepted; program and per-reading identity must remain distinct |
| `packages/dspx-core/src/dspx/templates/module_templates.py:18–48` (`render_module_skeleton`) and `packages/dspx-core/src/dspx/services/program_surfaces.py:29–88` (`render_signature_surface`, `render_module_surface`) | Focused bundle renderer derives declared inputs and outputs from generation contracts | Enhance the declared signature and focused-bundle path together; metadata propagation alone cannot prove provider-visible purpose |
| `packages/dspx-core/src/dspx/services/program_runtime_episode.py:272–276,1025–1080` (`_load_inputs`, `_validate_pdf_transition_review_outputs`) | Generic direct/nested input mapping; six required PDF JSON families and noncanonical flags | No checked versioned intent admission or semantic steering in this validator |
| Obsidian `_System/pdf-pipeline/scripts/materialize_dspy_transition_review.py:20–29,55–84,493–545` (`OUTPUT_FILES`, `_load_observed_outputs_from_behavior`, `_load_generated_bundle`, `materialize`) | Requires eight families; fallback chooses a passed example; bundle uses `**parsed`, no independent top-level intent binding | Future adapter must select the exact reviewed run/example, validate provenance and propagate binding; passing example is not current-intent authority |
| Obsidian `_System/review/mobile-routing-prototype/reading_intent.py` (`producer_input`, `freshness`, `campaign_approvable`) | Explicit noncanonical input helper and structural freshness gate; no executor | Reuse helper contract, not a claim of current live producer integration |

The **six** runtime-required families are `section_units_json`,
`distillation_frames_json`, `evidence_cards_json`, `merge_create_proposals_json`,
`review_packet_json`, `artifact_contract_manifest_json`. The materializer also
requires **`frontmatter_plans_json` and `wiki_note_drafts_json`**. Thus a runtime
validation pass can still lack role-separated frontmatter or reviewable note
content required by the adapter. Neither check proves the original fifth reading
level, a substantive v2 mobile campaign, or actual purpose-sensitive behavior.
The future contract must enumerate all required families and explicitly reject
missing content; it cannot hide the mismatch by filling empty arrays.

Bounded negative: inspection of current Core/Forge Python, the tracked PDF fixture,
renderer/runtime and named Obsidian adapter found **no end-to-end contract for
automatic puzzle/purpose suggestion plus version-bound purpose-sensitive reading**.
This is not proof that no producer or historical experiment exists anywhere.
The [May10 dogfood](2026-05-10-dogfood-how-to-read-paragraph-canonical-transition.md)
and [May14 replay](2026-05-14-purpose-driven-codex-gpt55-replay.md) describe historical
candidates, inputs and outcomes; their scratch/private source paths were not
opened, replayed or accepted as current producer identity. The May14 timeout and
later run remain historical facts, not precedent for retrying uncertain effects.

Proposed separately reviewed implementation scopes, **not tasks launched here**:
- **DSPx owner:** extend the PDF scenario's declared input/output contract,
  focused renderer and runtime validation/receipt seam; add synthetic intent
  propagation and six-level traceability tests. Design an automatic proposal
  producer against supplied source/puzzle snapshots before introducing any live
  model. Candidate paths are the fixture, `program_intent.py` only if a genuine
  program-level field is needed, `program_surfaces.py`, `module_templates.py`,
  `program_runtime_episode.py` and their focused tests. No generic foundry rewrite.
- **Obsidian owner:** review changes to the named materializer and its validator
  plus the prototype input/campaign consumer. Retain independent receipt and
  current-intent verification, immutable packet generations, eight-family
  completeness, explicit exact-example selection and stale admission rejection.
  This design grants no write to those paths or to real review stores.
- **Source/knowledge and runtime owners:** separately approve corpus disclosure,
  provider/effect budgets, any installed host/PWA work and canonical acceptance.
  Neither DSPx nor the adapter manufactures these permissions.

### Synthetic producer implementation — AK5456

The separately admitted additive implementation now lives in Core services
`program_reading_contracts.py`, `program_reading_runtime.py` and
`program_reading_receipts.py`. The existing PDF fixture, generic runtime/readback,
renderers and AK5511 historical closure remain unchanged. This implements only
synthetic contract/integration proof; it does not implement the statechart host,
semantic-quality acceptance or an installed review/knowledge workflow.

Public Python entrypoints:
- `materialize_reading_candidate(intent_path=..., candidate_root=..., stage=...)`
  generates a proposal or reading candidate from the new `reading_*_intent.yaml`
  fixtures under `tests/fixtures/program_gen/pdf_transition/`.
- `run_reading_producer(manifest_path=..., requests_root=..., expected=...,
  inputs=..., synthetic_transport=..., current_intent=...)` invokes the actual
  generated DSPy program and native runtime in a spawned worker. The explicitly
  supplied transport is trusted synthetic test code, not a plugin sandbox.
- `consume_reading_receipt(root=..., trusted_receipt_sha256=..., manifest_path=...,
  expected=..., inputs=..., expected_native_episode_id=...,
  expected_native_index=0, current_intent=...)` verifies and returns captured
  synthetic outputs. The trusted receipt hash and expected identities must arrive
  through independent caller custody, never a submitted bundle's own trust claims.

Both fixtures disable focused-bundle rendering **and module inference**; otherwise
inferred topology can discard rich field descriptors despite disabling the focused
renderer. The proposal stage emits reviewable supplied-puzzle alternatives/no-fit,
not an approved working intent. The reading stage receives the full owner-reviewed
intent as declared input; defer/source-only cause zero reading dispatches. Direct
preservation requires a null puzzle and explicit purpose/reason.

Admission requires exact `DSPX_PROVIDER=stub`, `MLFLOW_ENABLE=0`,
`DSPX_POLICY_ALLOW_NETWORK_MUTATE=0` and
`DSPX_POLICY_DISALLOWED_CAPS=network.read,network.mutate`; other DSPx/MLflow activation
or custody configuration rejects before generation or runtime construction.
Optional allowed variables are the private `DSPX_CACHE_DIR` and
`DSPX_POLICY_ALLOWED_PROVIDERS=stub`. The caller establishes this posture before
invocation; the wrapper does not switch shared process environment. Existing local
Oracle readability files remain, but indexing/semantic/publication are disabled.

`dspx-program-reading-receipt-v1` retains the independent expected request,
source/puzzle/candidate/input/intent identities, exact native episode/index,
`raw_file_sha256`, `output_parsed_sha256` and readback byte/parsed hashes. Raw
native inputs use their existing pretty-printed envelope serialization; raw outputs
use native string `rstrip()` plus newline. Working-intent hashes preserve Obsidian's
`sha256:`-prefixed compact sorted UTF-8 convention. These domains are deliberately
not interchangeable. Captured generated source and confined stable artifact reads
prevent unchecked candidate bytecode and path-selected evidence from replacing
those subjects; these checks do not authenticate a provider or establish OS isolation.

All eight families and the nested v2 campaign must pass closed structural/reference
schemas, including original L1–L5 and explicit added L6. Missing content, forged
exact quotations, foreign descendants and contradictory authority flags reject.
This is structural/reference integrity, not an assertion that the reasoning is good.
The outer receipt always retains the synthetic ceiling, unknown quality,
unestablished provider-output authentication, false review eligibility and false
canonical-apply permission.

Every request uses exclusive creation; failed/stale generations are retained and
never rebound. Start/end intent callbacks detect observed supersession but are not
an atomic owner publication lock. AK5457's landed Obsidian consumer independently
retains receipt hashes and serializes current-intent verification/publication into
an isolated **synthetic inspection** destination. Existing materializer fitness/
active-review admission remains unchanged; synthetic evidence is not review-ready.

Independent final review `dispatch-1789080583190` passed 118 tests with one optional
external probe skipped, plus four independently selected bundles/61 raw-file hashes.
Prior bytecode/schema/test-environment HOLDs remain in the task evidence. This proof
does not close AK5511's full gate, implement AK5525 quality provenance, or satisfy
AK5458 empirical reading acceptance. Example use and adversarial cases are the new
`tests/test_program_reading_*.py`; they require only synthetic source snapshots.


### Separate passage pilot — AK5681

The [passage A/B API](../../examples/reading_pilot/README.md) is separately implemented
and independently approved with 91 isolated native-runtime baseline tests, nine probes,
and a 14-case test-only follow-up. One immutable two-request batch uses generic-provider code, not
AK5456 synthetic receipt relabeling. Worker-to-parent digest custody rejects forged
observations while preserving genuine effects across unrelated readback damage.
This is provider-free implementation proof, not empirical quality, full eight-family
integration, whole-source coverage or installed behavior. Human source/rubric review,
local-only deployment/output-bound evidence, explicit live admission and independent
local result review remain open. The timed-out budget form grants no consent; AK5458
remains deferred. The historical acceptance matrix below is not a new live result.

### Requirements-to-binding and acceptance traceability

All tests below are **required future acceptance probes**, except the explicitly
observed prototype regression. A design review pass does not execute them.

| Requirement / operating need | State/program binding | Falsifiable acceptance |
|---|---|---|
| R1: inspect the entire machine | Hierarchical `design` / `reading` / `review` regions, invoked assemblies and bounded revision cycles | T1: model/renderer round-trip retains IDs, nested/parallel configuration, guards, loops and input hashes; unknown construct rejects rather than flattens |
| R2: first-review purpose correction | `proposal → intent_review → planning`; explicit correction from campaign to same intent owner | T2: two puzzles A/B, revise purposeA to purposeB; input to fake producer has v2/B/purposeB, old packets are stale and history/RIGHT remain unchanged |
| R3: source-qualified five-plus-one reading | Whole map → per-paragraph L1–L5 → whole synthesis → added L6 proposal | T3: source rubric evaluates each level separately; omission of author-roleplay fails, unsupported author claims and fabricated quotes fail |
| R4: purpose changes relevance, not truth | Version-bound planner, paragraph readers and synthesizer | T4: on the same declared public/synthetic source, two contrasting purposes change relevant questions/plans/outputs while preserving source claims and counterevidence; independent domain review rejects mere label copying |
| R5: stale/forged outputs cannot become review | Receipt-bound completion → eight-family materializer → current-intent campaign gate | T5: reject forged echo binding, old in-flight completion, missing two adapter families, wrong example/run, malformed dependent row or missing substantive campaign |
| R6: uncertain effects stay uncertain | Pre-dispatch intent ledger, ordered/transitive acceptance, independent effect acknowledgement and reconciliation | T6: crash at intent-write/dispatch/transitive-acceptance/checkpoint/ack boundaries; inject a child operation and root-event between acceptance and checkpoint. Recover without event loss, duplicate authorization or false business-effect completion; rejected batches and uncertain effects are not blindly replayed |
| R7: resumes preserve semantics | Post-settlement checkpoint plus transition index, machine/binding identity and pending root-event/child/timer custody | T7: reject pre-settlement snapshots; restore hierarchy/parallel regions, queued root events and absolute deadlines consistently across a crash after acceptance. Preserve accepted-but-incomplete operations without reauthorization; changed machine/program/intent/schema rejects and old incarnation cannot finish a new run |
| R8: no forced puzzle or canonical apply | `wiki_atlas_direct`, `defer`, `source_only`; separate owner acceptance boundary | T8: direct retains null puzzle/reason; defer/source-only cause zero producer calls; review/level6 never mutates canonical-note sentinels |
| R9: independent assembly evolution | Suite registry plus per-candidate manifests, episodes and evaluation lineage | T9: changing one candidate invalidates its dependent bindings without silently rewriting siblings; budgets, jury independence and rollback are evaluated separately from semantic quality |
| R10: preserve owners and the selected route | Core-first binding registry; no Forge dependency or Foundry activation | T10: source/dependency and direction checks retain owner boundaries, existing frames and no external apply; package selection remains separately owner-gated |

**Observed T2 regression only:** reran existing
`test_review_safety.ReviewSafety.test_two_puzzles_fake_producer_and_stale_approval`
from the committed Obsidian prototype: **1 test passed**. It binds changed intent
to a fake producer, rejects old approval and preserves historical receipts and
canonical sentinels. It does not validate the proposed DSPx adapter, execute an
XState machine, prove automatic suggestion, or satisfy empirical T4.

Design closure requires owner review of this mapping and explicit disposition of
the remaining dependency/host, producer implementation and empirical acceptance
gates. No green document check can substitute for those future runtime proofs.
