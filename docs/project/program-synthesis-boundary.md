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
- replace current active SG/TG repo truth,
- collapse Oracle into governance authority,
- require immediate changes to `module_service`, `program_service`, or `optimize_service`.

## Relationship to current repo direction

Current repo direction remains truthful as-is unless explicitly refreshed:
- active strategic goal remains `SG2`,
- active tactical goal remains `TG25`,
- `docs/project/operational_goals.md` currently says no repo-scoped implementation slice is pinned.

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

`AK-1827` / `docs/adr/20260423-intent-to-program-candidate-assembly-mvp.md` materialized the first bounded foothold for this boundary: `program-gen` can now read one structured JSON/YAML intent and write a deterministic program-shaped candidate assembly with `plan.json`, standalone `module_surfaces.json` (`program-module-surfaces-v1` / `program-module-surface-v1`), standalone `jury.json`, deterministic `jury_selection.json`, deterministic `jury_rubric.json`, `promotion_review.json` with optional opaque non-exporting `external_authority` refs, `promotion_adjudication_request.json`, `promotion_decision_template.json`, standalone `execution_episode.json`, explicit or per-program inferred planned `program-jury-v1` contracts, optional explicit topology preserved as declared input and materialized for the narrow supported `pipeline` subset, `signature.py`, `module.py`, `program.py`, `eval_smoke.py`, `eval_jury.py`, `eval_promotion.py`, typed/described signature fields when provided, optional `examples.json` / `eval_examples.py` from inline `examples` or `examples_path`, optional deterministic dataset split artifacts (`dataset_manifest.json`, `splits/{train,validation,test}.jsonl`, `eval_{train,validation,test}.py`, `behavior_results.{train,validation,test}.json`) from declared `dataset` / `datasets`, normalized `intent.json`, `manifest.json`, and a standard `program-gen` run receipt.

The current implementation keeps that foothold narrow while making the surface boundary more truthful:
- it proves the intent -> candidate assembly -> execution episode -> receipt bundle spine at program shape,
- it keeps orchestration in `dspx.services.program_service` rather than overloading `module_service`,
- it composes the existing signature/module generation services as candidate-surface providers,
- it records plan/module-surface/jury/selection/rubric/promotion-review/external-ref/adjudication-request/decision-template/execution-episode provenance, declared-vs-materialized topology status, generator provenance, optional example-binding evidence, minimal behavior-result evidence over examples, compact Oracle-readable evidence, and per-surface hashes in the manifest/receipt evidence,
- a separately invoked Agent Kernel authority adapter can consume those manifests/receipts and produce a receipted sidecar export plan without mutating external authority,
- a separately invoked Oracle indexing command can consume `program-oracle-evidence-v1` artifacts into a local CoordinateIndex as searchable evidence,
- a separately invoked Oracle program-evidence report command can read those indexed records and summarize example-backed behavior evidence without ranking, pruning, promotion, governance, external mutation, or program-gen automation,
- a separately invoked `program-refine propose` command can consume the manifest, declared `behavior_results.json` when present, and an explicit non-authoritative Oracle report to write a local `program-refinement-proposal-v1` artifact only,
- a separately invoked `program-promote review` command can consume the manifest, original generated promotion shell artifacts, declared behavior evidence when present, the explicit Oracle report, and the explicit refinement proposal to write a local `program-promotion-review-refined-v1` sidecar packet,
- a separately invoked `program-promote jury` command can consume an existing manifest, planned jury artifacts, and current `eval_examples.py` / `behavior_results.json` evidence to write a local deterministic `program-jury-results-v1` sidecar without model calls, candidate mutation, Oracle indexing, ranking, winner selection, promotion, AK, or governance effects,
- a separately invoked `program-promote decide` command can consume that refined review packet plus explicit operator/adjudicator input to write a local `program-promotion-decision-record-v1` sidecar,
- a separately invoked `program-refine generate-candidate` command can consume a proposed refinement plus a local `request_more_evidence` decision record to materialize one explicit local second candidate at a requested output directory,
- a separately invoked `program-refine compare-candidates` command can consume already-materialized source and refinement candidate manifests, read current `eval_examples.py` / `behavior_results.json` evidence, and write a local `program-refinement-candidate-comparison-v1` sidecar with behavior status/count/failure-signal deltas,
- a separately invoked `program-refine generate-and-compare` command can serve as an explicit local operator workflow over exactly one second-candidate generation followed by the same comparison sidecar,
- a separately invoked `program-promote plan` command can consume an existing candidate manifest, a local decision record, and a comparison sidecar plus explicit target and authority-owner inputs, then write a local `program-promotion-plan-v1` sidecar with `planned_not_applied` / `not_promoted` posture, evidence hashes, eligibility, audit trail, and reversibility posture,
- a separately invoked `program-refine optimize-gepa` command can consume an existing `program-candidate-assembly-v1` manifest, explicit JSONL train/validation files or manifest dataset splits or limited inline examples, and write a `program-refinement-gepa-result-v1` sidecar; the current GEPA optimizer may only produce local DSPy optimizer output, not a new candidate assembly, so the sidecar degrades truthfully with `candidate: null` unless a real candidate materializer exists,
- the refinement proposal, refined promotion-review packet, jury-results sidecar, decision record, comparison sidecar, local promotion/adjudication plan, generate-and-compare workflow result, and GEPA refinement result do not mutate generated source program files, do not overwrite `promotion_review.json` / adjudication request / decision template artifacts, do not mutate `promotion_review_refined.json`, and cannot rank, select winners, prune, promote, deploy, block via Oracle, export authority, mutate AK, mutate governance, or make Oracle authoritative,
- second-candidate generation is explicit and local: it applies only the bounded constraints patch in this first slice, writes only the requested new candidate directory, records refinement lineage in the new candidate intent, and does not mutate the source candidate, proposal, decision record, Oracle, AK, governance, or external authority,
- candidate comparison is explicit and local: it writes only the requested sidecar, does not generate a third candidate, does not mutate either candidate, and does not treat Oracle as authority,
- promotion/adjudication planning is explicit and local: it writes only the requested `program-promotion-plan-v1` sidecar, keeps `allowed_for_apply: false`, records missing apply/external-authority evidence, and does not mutate candidate artifacts, decision records, comparison sidecars, Oracle indexes, AK, governance, or external authority,
- non-promote decision outcomes keep the candidate unpromoted, while `promote` fails closed unless `review_readiness.ready_for_adjudicator_review` is explicitly true and remains local-only even when recordable,
- explicit topology is validated and preserved as declared input; the narrow `pipeline` subset is rendered into multiple `Predict`/`ChainOfThought` signature/module classes plus composed `program.py` with simple `when.field`/`when.equals` routing, and `module_surfaces.json` records one generated module surface per materialized topology module, while unsupported topology kinds remain declared-only,
- no LM/provider topology inference is performed and no broad graph engine, arbitrary expressions, arbitrary custom Python module imports/execution, tools, retrievers, ReAct, or ProgramOfThought execution is claimed,
- inline examples remain `eval_examples.py` / `behavior_results.json`; declared datasets add split-specific `eval_train.py`, `eval_validation.py`, `eval_test.py`, and split-specific behavior result artifacts rather than introducing `eval_behavior.py`,
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
- deepen execution episodes toward richer behavior sources when that justifies a future `eval_behavior.py` orchestration layer,
- deepen local promotion/adjudication plans from decision records and comparison evidence while keeping apply/export as a separate future authority surface.

Current dataset split support is deliberately evidence-only: it accepts JSONL or JSON/YAML list-of-object records shaped like inline examples, materializes deterministic local train/validation/test splits by ratio seed or explicit split files, and records hashes in manifest/receipt/replay. It does not run Oracle indexing, GEPA/search, jury execution, ranking, promotion, authority export, AK/governance mutation, custom module execution, or topology inference during `program-gen`; `program-promote jury` can later consume current example-backed behavior explicitly as local non-authoritative jury evidence, and `program-refine optimize-gepa` can consume split artifacts explicitly as local non-authoritative refinement input.

Do not start by stuffing richer synthesis behavior directly into `module_service`.
Do not mistake `program_service` for the final ontology of the runtime.
