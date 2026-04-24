---
summary: "Long-horizon product and architecture vision for DSPx."
read_when:
  - "When aligning long-term direction"
  - "When choosing which architecture wave to invest in next"
---

# Vision

This is the canonical product-vision document for DSPx.

DSPx should become a **local-first behavior-first runtime for empirical development of DSPy systems**.

Its long-horizon product promise is simple:

> A user should be able to state one intent and receive a runnable, evaluated, replayable DSPy program assembly whose behavior can be inspected, compared, improved, and governed.

DSPx should be able to:
- normalize a user intent into explicit candidate surfaces,
- assemble signatures, modules, programs, prompts, configuration, and evaluation harnesses into runnable candidate assemblies,
- execute those assemblies under explicit runtime and dataset conditions,
- emit replayable receipts and traces by default,
- let Oracle interpret observed behavior from that evidence,
- use empirical interpretation to shape later bounded search and refinement,
- and keep selection, withholding, review, activation, and promotion under explicit governance instead of hidden drift.

## What success looks like

A DSPx user can:
- describe a desired DSPy behavior in one intent,
- see the structured candidate surfaces derived from that intent,
- materialize a runnable candidate assembly rather than a loose code snippet,
- execute and evaluate that assembly under declared runtime, provider, metric, and dataset/example conditions,
- inspect replayable receipts and traces for what happened,
- ask Oracle what behavioral patterns, drift, strengths, weaknesses, attractors, and frontiers appear across runs,
- compare candidate assemblies and execution episodes without confusing empirical promise with approval,
- and trust that every important decision remains inspectable, reproducible, and governable.

## Scope boundaries

DSPx is:
- a local-first DSPy runtime,
- a one-intent-to-candidate-assembly workbench,
- a provider-aware execution and evidence system,
- a receipts-first environment for empirical iteration on DSPy systems,
- an Oracle-backed behavioral interpretation environment,
- and a place where runtime behavior and governance boundaries stay explicit.

DSPx is not:
- a hosted SaaS control plane,
- an app-first monolith where core depends on Forge or other apps,
- a prompt-only generator that emits unowned code snippets,
- an uncontrolled self-modifying agent runtime,
- a system where Oracle silently becomes policy authority,
- or a system where interesting evidence silently becomes live authority.

## Durable product principles

1. **Core-first architecture** — `packages/dspx-core` is the product; apps remain optional consumers.
2. **One intent, explicit surfaces** — a user-facing intent should be normalized into named candidate surfaces rather than hidden prompt magic.
3. **Runtime objects before service sprawl** — candidate surfaces, candidate assemblies, execution episodes, receipt bundles, behavioral interpretation, and promotion state should be the primary architectural language.
4. **Programs are assemblies, not just files** — a useful DSPy program includes signatures, modules, orchestration, configuration, examples/datasets, evaluation harnesses, runtime conditions, and receipts.
5. **Receipts before anecdotes** — execution, evaluation, and review decisions must leave durable evidence.
6. **Behavior before shape** — the system should care not only what a candidate is, but how it behaves under real execution conditions.
7. **Oracle interprets behavior, not authority** — Oracle may derive phenotypes, patterns, drift, territory, attractors, and frontiers from evidence, but it does not silently approve policy or promotion.
8. **Governance stays explicit** — review, approval, activation, and promotion must remain separate and named.
9. **Search engines are internal tools, not the architecture** — optimization/search mechanisms such as GEPA are replaceable; evidence and authority boundaries are not.

## Architecture direction

DSPx should be described through a small set of first-class runtime objects:

- **structured intent** — the explicit normalized request derived from a user's goal
- **candidate surface** — any editable/evolvable part of a DSPy system
- **candidate assembly** — a concrete runnable candidate built from one or more surfaces
- **execution episode** — one bounded run of a candidate assembly under explicit conditions
- **receipt bundle** — the replayable evidence emitted by an execution episode
- **behavioral phenotype / interpretation** — Oracle's reading of recurring patterns, drift, strengths, weaknesses, and topology
- **territory / frontier map** — Oracle's higher-order map of explored, stable, unstable, saturated, and promising behavioral regions
- **promotion state** — the explicit status of a candidate after evaluation and review

The architecture should be framed directly in terms of these objects and their authority boundaries.

Service boundaries should follow from those objects:
- `signature` surfaces should reuse the mature native signature pipeline,
- `module` surfaces should reuse the module synthesis/generation pipeline where its module-scoped semantics fit,
- `program-gen` should become the candidate-assembly orchestrator for program-shaped systems rather than a permanent duplicate mini-generator,
- `optimize`/GEPA should act as bounded search and reflection engines inside the runtime,
- Oracle should interpret accumulated behavioral evidence without becoming governance authority.

## What this implies right now

Near-term work should favor:
- the one-intent-to-program product loop,
- structured intent contracts that can derive signatures, modules, program topology, examples/datasets, metrics, and runtime constraints,
- candidate-assembly contracts that preserve separate generated surfaces instead of hiding everything in one file,
- execution-episode contracts that run real evaluations, not only smoke checks,
- replayable receipt bundles that Oracle can read as behavioral evidence,
- Oracle-readable phenotype / territory / frontier surfaces for generated programs,
- explicit review and promotion boundaries,
- clear separation between runtime evidence, empirical interpretation, and governance authority.

It should defer, until explicitly justified:
- silent live-policy mutation,
- evidence-backed behavior that jumps directly into live authority,
- uncontrolled self-improvement loops,
- broad surface-area expansion without evidence needs,
- Oracle-derived signals that directly rank, prune, promote, or block without an explicit contract,
- and any wording that treats historical architecture scaffolding as the thing being built.

## Language discipline

The current product direction should be described in direct runtime language.

Prefer:
- one intent
- structured intent
- candidate surface
- candidate assembly
- execution episode
- receipt bundle
- behavioral phenotype
- behavioral interpretation
- territory / frontier map
- governance review
- promotion state
- runtime boundary
- authority boundary

Avoid:
- ladder/stage framing,
- "advance to the next version" language,
- proxy labels that obscure the real runtime objects,
- wording that makes the team think it is building a stage instead of the actual runtime,
- wording that implies Oracle, GEPA, or any search engine owns promotion authority.
