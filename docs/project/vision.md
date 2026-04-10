---
summary: "Long-horizon product and architecture vision for DSPx."
read_when:
  - "When aligning long-term direction"
  - "When choosing which architecture wave to invest in next"
---

# Vision

This is the canonical product-vision document for DSPx.

DSPx should become a **local-first runtime for empirical development of DSPy systems**.

It should be able to:
- assemble candidate systems from explicit surfaces,
- execute them under explicit conditions,
- emit replayable evidence by default,
- let Oracle interpret observed behavior from that evidence,
- and keep selection, withholding, review, and promotion under explicit governance instead of hidden drift.

## What success looks like

A DSPx user can:
- describe a signature, module, program, or other candidate surface,
- materialize a runnable candidate assembly from a structured request,
- execute and evaluate that candidate under explicit runtime conditions,
- inspect replayable receipts and traces for what happened,
- compare behavioral outcomes across candidates and runs,
- and trust that every important decision remains inspectable, reproducible, and governable.

## Scope boundaries

DSPx is:
- a local-first DSPy runtime,
- a provider-aware execution and evidence system,
- a receipts-first environment for empirical iteration on DSPy systems,
- a place where runtime behavior and governance boundaries stay explicit.

DSPx is not:
- a hosted SaaS control plane,
- an app-first monolith where core depends on Forge or other apps,
- an uncontrolled self-modifying agent runtime,
- a system where interesting evidence silently becomes live authority.

## Durable product principles

1. **Core-first architecture** — `packages/dspx-core` is the product; apps remain optional consumers.
2. **Runtime objects before service sprawl** — candidate surfaces, candidate assemblies, execution episodes, receipt bundles, and promotion state should be the primary architectural language.
3. **Receipts before anecdotes** — execution, evaluation, and review decisions must leave durable evidence.
4. **Behavior before shape** — the system should care not only what a candidate is, but how it behaves under real execution conditions.
5. **Oracle interprets behavior, not authority** — Oracle may derive patterns and territory from evidence, but it does not silently approve policy.
6. **Governance stays explicit** — review, approval, activation, and promotion must remain separate and named.
7. **Search engines are internal tools, not the architecture** — optimization/search mechanisms are replaceable; evidence and authority boundaries are not.

## Architecture direction

DSPx should be described through a small set of first-class runtime objects:

- **candidate surface** — any editable/evolvable part of a DSPy system
- **candidate assembly** — a concrete runnable candidate built from one or more surfaces
- **execution episode** — one bounded run of a candidate assembly under explicit conditions
- **receipt bundle** — the replayable evidence emitted by an execution episode
- **behavioral interpretation** — Oracle’s reading of recurring patterns, drift, strengths, weaknesses, and topology
- **promotion state** — the explicit status of a candidate after evaluation and review

The architecture should be framed directly in terms of these objects and their authority boundaries.

## What this implies right now

Near-term work should favor:
- candidate-assembly contracts,
- execution-episode contracts,
- replayable receipt bundles,
- Oracle-readable evidence surfaces,
- explicit review and promotion boundaries,
- clear separation between runtime evidence, empirical interpretation, and governance authority.

It should defer, until explicitly justified:
- silent live-policy mutation,
- evidence-backed behavior that jumps directly into live authority,
- uncontrolled self-improvement loops,
- broad surface-area expansion without evidence needs,
- any wording that treats historical architecture scaffolding as the thing being built.

## Language discipline

The current product direction should be described in direct runtime language.

Prefer:
- candidate surface
- candidate assembly
- execution episode
- receipt bundle
- behavioral interpretation
- governance review
- promotion state
- runtime boundary
- authority boundary

Avoid:
- ladder/stage framing,
- "advance to the next version" language,
- proxy labels that obscure the real runtime objects,
- wording that makes the team think it is building a stage instead of the actual runtime.
