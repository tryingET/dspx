---
summary: "Current DSPx product maturity, active Core-readiness frontier, owner gates, and proof required to advance it."
read_when:
  - "When choosing the next DSPx product slice."
  - "Before implementation, to identify the current shipped-vs-target gap."
  - "Before loop completion, to refresh the product frontier against observed evidence."
type: "reference"
---

# Product Posture

## Purpose and use

This file is the status-bearing bridge between the durable [vision](vision.md) and current execution.

Use it as an **active work artifact**:

1. read it before selecting a slice;
2. test its apparent frontier against AK, code, tests, and current artifacts during discovery;
3. update it before completion when the shipped baseline, gaps, proof, or lawful next move changed.

This file is a dated projection, not live authority, a task list, or a changelog. Active direction, tasks, decisions, and evidence live in Agent Kernel (AK). Shipped behavior lives in code and its current executable proof. Historical posture snapshots remain available in Git history; do not append implementation diaries here.

## Current snapshot — 2026-07-25

### Posture in one sentence

DSPx has a substantial local-first, behavior-first Core with one-intent candidate generation, bounded execution, receipts/replay, Oracle inspection, refinement, and review evidence; the active product gap is truthful production readiness, not further autonomous-foundry expansion.

### Active frontier: Core production readiness

Current AK direction prioritizes making Core DSPx installable, operationally safe, and empirically proven before expanding autonomous foundry behavior.

The latest bounded proof establishes:

- a Core-only wheel installation outside the source checkout with `PYTHONPATH` unset;
- a stub-provider journey through candidate materialization, passing local behavior, receipt checking, candidate-local Oracle indexing/reporting, and candidate-state generation;
- exact installed-wheel payload verification against wheel `RECORD` plus rejection of undeclared importable package files;
- a hash-bound release-evidence v3 envelope over the wheel, sdist, installed proof, exact-wheel CycloneDX SBOM, and point-in-time resolved-environment CycloneDX SBOM;
- an optional mode-0600, no-replace local release bundle retaining those subjects, SBOMs, proof, envelope, manifest, and an unauthenticated local provenance statement;
- machine-readable replay claims that distinguish receipt integrity, deterministic regeneration, runtime reproduction, semantic reproduction, and quality-evaluation reproduction;
- explicit Oracle embedding-backend identity, with mock vectors labeled plumbing-only and unavailable production backends failing closed;
- bounded, paged local Oracle reads that tolerate malformed legacy rows without turning them into trusted evidence.

These observations are implemented and exercised by the package and focused test lanes. They are not release approval.

### Validation gate status

Both type lanes are now green, but the full gate still has one observed failure:

- `just typecheck` passes after module-quality rank-key normalization removed the unsafe `int(object)` boundary.
- `just typecheck-tests` passes after test fixtures gained typed mutable boundaries, frozen-capability mutation was checked through Pydantic's `ValidationError`, and marker-environment values were narrowed without casts or filtering.
- `just verify-full` now reaches the complete offline suite but fails one deterministic refined-review contract test: `test_meta_adjudication_plan_revalidates_refined_review_contract` receives `contract_invalid` for its nominal fixture. AK-4148 owns that separate contract-drift/full-gate blocker. Until it passes, focused and typecheck evidence do not establish full release confidence.

### Deferred and contingent next moves

The following Core moves are blocked on owner decisions or explicit trigger events. This repo must not invent owner policy or treat every contingent move as a current release requirement:

1. **Signer policy and verification** — AK-4125 is deferred pending an owner decision covering the signature scheme, trusted signer identity, key custody, signed subject set, revocation, and threshold policy.
2. **CI evidence custody** — AK-4126 is deferred pending an owner decision covering CI provider, visibility, retention/deletion, access controls, and secret/publication posture.
3. **Exact-sdist install proof** — AK-4137 is contingent on an owner declaring sdist support/signer-subject inclusion or on an observed sdist defect.

Until those triggers occur, use `ak task ready` to find lawful work. Inspect these records with `ak task show 4125`, `ak task show 4126`, and `ak task show 4137`; this AK CLI accepts numeric task IDs. Do not substitute richer foundry features, prose-only signer policy, local evidence retention, or static sdist inspection for blocked owner decisions.

### Explicit nonclaims

Current evidence does **not** prove:

- live-provider correctness or production-semantic program quality;
- production-semantic Oracle embeddings or comparison quality;
- OS-level network isolation or exclusion of absolute-path/external API effects;
- hash-locked dependency resolution, retained dependency artifacts, reproducible builds, or future resolver stability;
- vulnerability, license, VEX, or supply-chain policy acceptance;
- attested provenance, trusted signer identity, signature verification, or CI custody;
- exact-sdist PEP 517 build/install behavior or source-to-wheel equivalence;
- registry publication, technical release completeness, release readiness, promotion, activation, or external authority.

## Current product baseline

| Runtime area | Shipped baseline | Main bounded gap |
|---|---|---|
| One-intent candidate assembly | `program-gen` normalizes structured intent and materializes separate signatures, modules, topology, harnesses, manifests, execution evidence, and receipts. Bounded pipeline/router/retriever/review topologies are supported; unsupported valid capabilities remain declared-only. | No arbitrary graph/effect engine, custom-import execution, live external tool/retriever binding, or provider-backed arbitrary topology inference. |
| Execution and replay | Generated examples/datasets can run through bounded behavior harnesses and explicit runtime episodes. Replay claims are machine-readable and receipt-bound. | No general semantic-reproduction claim, broad provider/runtime coverage, or receipt-bound multi-episode product contract. |
| Oracle behavioral evidence | Candidate-local evidence can be indexed and reported with explicit backend identity; Oracle exposes search, drift, territory, frontier, attractor, and program-evidence concepts. | Production-semantic embedding quality and shared-backend readiness remain separate empirical/operational gates. Oracle remains interpretation, not authority. |
| Refinement and review | Local proposals, GEPA attempts, second candidates, comparisons, jury/model-jury evidence, adjudication records, plans, status, and activation-preflight packets exist as inspectable sidecars and guided workflows. | Further autonomous orchestration is paused. External apply, activation, and owner acceptance remain unavailable without their own authority contracts. |
| Packaging and release evidence | Core-only installed-wheel behavior, exact-wheel payload identity, two SBOM scopes, release claim separation, and local evidence retention are proven in the bounded package lane. | Owner-authorized signer verification and CI custody are the immediate gates; publication/readiness remain false. |
| Operator experience | `program-loop` provides a coherent local intent-to-candidate/evidence/state path; `just smoke-base` dogfoods an offline no-AK loop. | The product still needs owner-gated release operations and later live empirical proof before a production-ready claim. |

## Durable boundaries

- `packages/dspx-core` is the product kernel; apps such as Forge consume Core and must not become Core dependencies.
- DSPx owns local generation, execution, evaluation, replay, receipts, and Oracle-backed empirical interpretation.
- Oracle interprets observed behavior; it does not rank, promote, activate, or become governance authority by implication.
- Receipts, bundles, reports, sidecars, and candidate-state packets are evidence or projections. They do not approve release or mutate external authority.
- Prompt/procedure truth remains in Prompt Vault, semantic ontology remains with ROCS/owner repos, and task/direction/decision/evidence authority remains in AK.
- Domain-specific generated review programs consume owner-supplied contracts and evidence; DSPx does not redefine domain truth, remediation policy, or acceptance authority.

## Observable exit signals for the active frontier

The Core frontier advances only when current evidence shows all applicable conditions, without widening claims:

- an accepted owner decision defines signer policy and custody;
- the exact required release subjects are verified against that policy and the result is machine-checkable;
- an accepted owner decision defines CI artifact custody and the workflow implements it without leaking secrets or implying publication;
- retained evidence is bound to the exact built subjects, source state, SBOM scopes, installed proof, and verification result;
- failure, revocation, stale evidence, wrong signer, missing subject, permission, partial-write, and retention/deletion cases fail closed or report effect-indeterminate truthfully;
- `just typecheck`, `just typecheck-tests`, `just verify-full`, package, focused adversarial, docs, workflow, direction, and scoped landing checks pass;
- product posture and AK state are reconciled before any completion or readiness statement.

Passing these signals would establish a stronger technical release-evidence posture. Release approval, registry publication, rollout, and production activation would still require their owning decisions and evidence.

## Target product experience

A user should be able to state one intent and receive a runnable, evaluated, replayable DSPy candidate assembly whose behavior can be inspected, compared, improved, and governed.

The direct product loop is:

1. normalize intent and expose assumptions;
2. materialize explicit candidate surfaces;
3. execute under declared runtime/provider/data/metric conditions;
4. emit and verify receipts, traces, and evaluation evidence;
5. let Oracle interpret observed behavior without granting it authority;
6. refine or compare candidates through explicit bounded attempts;
7. keep review, signing, release, promotion, and activation as separate owner-governed transitions.

See [vision.md](vision.md) for the durable architecture and [program-gen-walkthrough.md](program-gen-walkthrough.md) for the current local product path.

## Status language rules

- Say **observed**, **implemented**, or **verified by `<command/artifact>`** only when current evidence supports it.
- Say **target**, **planned**, **deferred**, **contingent**, or **owner-gated** when behavior or authorization has not landed.
- Keep a positive proof adjacent to its limitations; do not preserve “closes X” while dropping “does not prove Y.”
- Do not use “production ready,” “approved,” “attested,” “signed,” “published,” “activated,” or “authoritative” for local evidence unless the owning contract and current proof establish that exact claim.
- Do not infer current task state from this file. Query AK.

## Authority and orientation map

- Durable product ambition: [vision.md](vision.md)
- Current product projection: this file
- Architecture and package boundaries: [../ARCHITECTURE.md](../ARCHITECTURE.md)
- Local workflow and validation: [developer_workflow.md](developer_workflow.md)
- Current generated-program walkthrough: [program-gen-walkthrough.md](program-gen-walkthrough.md)
- Runtime/source evidence: code, tests, built artifacts, and current validated receipts owned by this repo
- Active direction, execution, decisions, and canonical evidence: AK runtime
- Raw session history: `diary/`
- Crystallized reusable learning: `docs/learnings/`
