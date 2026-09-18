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

For dependency-intelligence work, this means DSPx may generate and evaluate rerunnable DSPy review programs that consume owner-supplied dependency evidence packets, target contracts, and fitness suites, then emit replayable review evidence. DSPx does not own dependency semantics, dependency-removal authority, exploitability claims, or remediation decisions.

DSPx should be able to:
- normalize a user intent into explicit candidate surfaces,
- generate domain-bounded review programs, including dependency-intelligence review programs, from explicit target contracts and owner-supplied evidence schemas,
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

## Visual statecharts and interconnected DSPy suites — design target

AK5419 is **owner-accepted DESIGN only** (evidence8373), reconciled into existing
runtime objects, not a new strategic frame. **Core production readiness remains
first and Autonomous Program Foundry paused**. AK5455 host/XState selection is
pending and deferred; neither XState is selected. Historically evaluated v6
alpha.52 and v5 5.32.6 are not current-version claims. AK5735 aligns documentation
only; no implementation or downstream-review detail is selected today.

A user should be able to inspect and revise a complete visual behavioral machine:
hierarchical states, parallel regions, event-driven re-entry, typed program
invocations, review waits, cancellation, recovery, and bounded refinement. One
machine may coordinate several interconnected DSPy candidate assemblies; each
assembly retains its own input contract, runtime conditions, evaluation and
receipt lineage. A deterministic event-based durable host should coordinate these
workers through typed source/coverage/intent/program/schema/runtime/budget bindings,
persistent effect custody and uncertain reconciliation, never blind model-call
retries. A linear diagram or one generated Python program is not the whole product.
Statechart semantics must not be flattened into a program-topology DAG. Mermaid
is orientation, not a faithful compiler; no Three.js explorer is verified.

The design segment is part of that machine: operating concept → needs and
requirements → candidate bindings → verification and semantic acceptance design
→ owner review. Revision can return to earlier decisions without erasing history.
The machine explains which transition is available; only the owning runtime and
accepted authority can execute it. Core remains independent of Forge and any
visual editor. See the [statechart contract](program-synthesis-boundary.md#statechart-to-program-suite-contract--ak5419-design).

### Reading as the concrete operating concept

Given an explicitly supplied source package and puzzle context, propose a working
puzzle and reader purpose with evidence, uncertainty and alternatives. The first
review can correct either, choose Wiki/Atlas-direct preservation, defer, or retain
source-only. Working intent is noncanonical: it is neither the author's purpose
nor a merged canonical puzzle assignment.

Reading moves whole-source orientation → declared chapter/passage L1–L5 →
cross-chapter synthesis → grounded L6, retaining counterevidence and explicit
coverage gaps. Paul/Elder's five levels remain distinct: paraphrase; full explication
(main point, elaboration, example, analogy); analysis of eight elements; evaluation
by nine standards; source-supported, labeled author-perspective simulation.
Our added sixth level proposes application/transfer with limits, counterexample
and observable test. Each unit/level declares applicability or insufficiency;
valid JSON does not prove semantic success. Program-candidate and per-run
jury/adjudication are separate required loops, not presumed implemented behavior.
Purpose controls relevance, not source meaning. Purpose correction supersedes
intent and stales dependent/in-flight outputs; a route-only change is distinct.
Applications remain proposals, not filesystem operations or accepted knowledge.

The coded two-stage swipe flow stays unchanged: Stage1 RIGHT=puzzle review,
UP=Atlas/Wiki, LEFT=source-only, DOWN=defer; Stage2 RIGHT=approve next step,
UP=revise, LEFT=cancel, DOWN=defer, currently gated on Stage1 RIGHT. It does not
run a producer or accept/apply knowledge. Wiki, Atlas and puzzle/project refinement
may coexist downstream. A proposed final exact-change acceptance may itself be a
swipe without another ceremonial approval; deterministic apply remains separate,
with distinct accepted/applied states. Do not reinterpret `approve_campaign` or
old receipts as that future acceptance.

Owner references: [canonical method](../../../../../../Documents/Obsidian/_System/architecture/distillation-method-architecture.md),
[Mermaid doc-only lifecycle chart](../../../../../../Documents/Obsidian/_System/docs/project/flow-views.md#reading-lifecycle-statechart),
and [tomorrow's review alternatives](../../../../../../Documents/Obsidian/_System/architecture/next-session-roadmap.md#reading-review-directions-for-next-session).
A destination-specific decks, B grouped review packet (recommended initial bounded
slice), and C puzzle/project-first workspace are proposals; **none selected**.

Success requires both faithful source interpretation and a demonstrable response
to changed reader purpose. Showing a purpose label, recording revision text,
copying a binding, or passing a fake-producer regression does not prove this
behavior. The [reading contract and acceptance matrix](program-synthesis-boundary.md#reading-intent-and-six-level-contract)
keep structural checks, semantic evaluation, review and canonical acceptance separate.

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
10. **Domain semantics stay with their owners** — generated programs may operationalize owner-supplied contracts and evidence schemas, but DSPx must not redefine dependency classifications, visualization meaning, vulnerability applicability states, removal authority, or remediation policy.

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
- dependency-intelligence review programs should consume dep-diet, dep-viz, dep-redteam, and runtime-trace-insights evidence contracts as inputs, while leaving dependency semantics and state transitions with those source-owner repos.

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
