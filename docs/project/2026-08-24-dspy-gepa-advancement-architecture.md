---
summary: "Target admission architecture and dependency order for DSPy 3.3.x, RLM, GEPA, Oracle, and resumable local evolution."
read_when:
  - "Selecting or sequencing DSPy 3.3.x, GEPA, RLM, ReActV2, Oracle, or autonomous-foundry work."
  - "Checking whether an upstream capability or local artifact may be characterized, supported, admitted, or activated."
type: "architecture-projection"
---

# DSPy and GEPA advancement architecture

## Authority and present truth

AK owns direction, task, decision, and execution state. This document projects a target architecture over exact AK keys. It neither activates pending work nor authorizes provider, Soomfon, release, publication, or production effects.

As observed on 2026-08-24:

- `IW-CPR-06-DSPY33-TRUSTED-LOCAL-CORE` is pending. DSPy 3.3.1 and transitive GEPA 0.1.4 compatibility are implemented; the six-button Soomfon evaluation has not run.
- tasks `#4809` and `#4929` are completed. Decision 118 governs the typed-LM architecture. Decision 115 remains review-pending context.
- Oracle semantic v10 remains terminal `effect_indeterminate`. Task `#4708` rejected the materialized v11 candidate at provider-free Gate 3 with 11 blockers; remediation task `#4713` is pending. No Gate 4, Gate 5, or empirical pass exists.
- GEPA whole-program output is pickle-backed and production-excluded. Checkpoint resume and truthful reflection-cost accounting remain unavailable.
- `SF-AUTONOMOUS-PROGRAM-FOUNDRY` is paused. Its child waves remain pending even where partial implementation exists.

`ak direction check` passed with 31 nodes, 68 task links, 2 decision links, and zero issues. Query AK again before execution; these counts and states are a dated projection.

## The architecture law

**Nothing advances because upstream exposes it. It advances only when DSPx can name the exact subject, hold its effects, interpret its evidence, admit its artifacts, resume it without duplication, and reverse its transition.**

Every capability, runtime, artifact, and candidate therefore carries an immutable identity and append-only transition evidence. Its current claim must be exactly one of:

| State | What it proves |
|---|---|
| `available` | The exact dependency or API exists. DSPx support is not implied. |
| `characterized` | Bounded behavior and falsifiers were observed under a named local contract. |
| `supported` | DSPx maintains a declared scope, tests, failure semantics, and replay/effect custody. |
| `production-admitted` | The exact subject passed its applicable safety, provenance, adjudication, and rollback gates. |
| `activated` | The governing owner authorized and observed the exact deployment or route. |

A later rollback adds a transition; it never rewrites history. Release, publication, external authority, and activation remain separate claims even when local admission succeeds.

## Six owner-bound gates

Upstream feature names are discovery inputs, not architecture boundaries. RLM, ReActV2, managed interpreters, GEPA artifacts, and checkpoints enter through the same six gates.

### 1. Execution and product truth

**Question:** What exact candidate ran, where, through which runtime and provider route, with what terminal effect and receipt?

DSPx may compare or improve behavior only after candidate, dependency, route, effect, and receipt identities are bound. The Soomfon matrix belongs here. Semantic v11 remediation also belongs here because a rejected candidate is not a live-evaluation input.

### 2. Runtime and effect custody

**Question:** Can DSPx bound execution, tools, concurrency, failure, replay, and indeterminate effects?

ProgramOfThought succession, RLM, ReActV2, and managed interpreters share this gate. A stronger upstream sandbox may reduce risk but cannot establish DSPx custody or OS isolation by implication. `unsupported` is a valid result.

### 3. Semantic and temporal intelligence

**Question:** Can observed behavior become evidence without becoming authority?

Oracle owns empirical interpretation: phenotype, drift, recurrence, frontier, uncertainty, and transfer evidence. It does not own ROCS semantics, task truth, ranking authority, promotion, or activation. Cross-program transfer requires compatible target, runtime, metric, provenance, privacy, and negative-transfer evidence.

### 4. Safe artifact admission

**Question:** Can the exact candidate be loaded, replayed, inspected, and rejected without hidden code or ambiguous effects?

GEPA candidate admission binds code/data separation, provenance, loader effects, identity, failure custody, and rollback. Hash-binding a pickle detects drift; it does not make executable deserialization safe. Until this gate passes, GEPA output may be characterized locally but remains production-excluded.

### 5. Resumable optimization

**Question:** Can improvement stop and continue without changing identity, losing cost truth, or duplicating effects?

A continuation binds candidate lineage, admitted inputs, objective and budget, checkpoint identity, completed effects, interruption disposition, and the next lawful action. Oracle-guided GEPA may choose bounded experiments only from state-qualified evidence and artifacts admitted for that use.

### 6. Adjudication and rollback

**Question:** Who may decide, transition, observe, and reverse the exact candidate?

Jury evidence and adjudication remain distinct from decision authority. A local transition preserves immutable predecessors and rollback. External deployment or canonical activation requires its governing owner; DSPx evidence cannot grant it.

## Dependency order

```text
execution identity ───────┐
runtime/effect custody ───┼──> safe artifact admission ──> resumable optimization
semantic/temporal truth ──┘                                      │
                                                                 v
                                                       adjudication + rollback
                                                                 │
                                                                 v
                                                    owner-governed activation
```

This is an evidence order for the same production-bound subject, not a global work serialization:

- provider-free runtime characterization may proceed before Soomfon observation;
- local GEPA characterization may remain below production admission;
- no production-bound optimization may consume an unidentified execution, an unheld effect, unqualified semantic evidence, or an unadmitted artifact;
- release/security/publication under `IW-CPR-05-RELEASE-OPERATIONS` remains a separate branch.

Receipts and manifests are replay truth. DSPy cache is not. Prompt Vault owns reusable procedures, ROCS owns controlled semantics, AK owns direction and execution authority, and DSPx owns local empirical artifacts.

## Task-ready gates

“Eligible” means an exact task may be selected or authored under AK authority. It does not activate a wave.

| Order | AK surface | Current disposition | Proof required to move |
|---|---|---|---|
| 1 | task `#4713`; `IW-CPR-04-ORACLE-SEMANTIC-TRUTH` | pending remediation | Renewed provider-free exact review resolves all v11 blockers. Acceptance would authorize neither live execution nor empirical success. |
| 1, independent | `IW-CPR-06-DSPY33-TRUSTED-LOCAL-CORE` | pending; executor task `#4809` completed, evaluation not run | A separate effect-authorized task binds the deployed Soomfon environment, one-shot ledger, and current reviewed contract SHA-256 `07ba8c3559d1e527bd9fe5376a7accac2f48f617e5ba1288329a9cf4362e69eb`; the task must read this anchor from the current reviewed module/contract rather than reuse task #4809's historical pre-release SHA. |
| Decision gate | Decision 115; task `#4694` | review-pending; task deferred | Decision 115 reaches a terminal outcome, then AK reconciles the deferred ReActV2 task. |
| 2 | `IW-CPR-07-RLM-PRIMITIVE-SUCCESSION` | pending | An exact task compares RLM and managed-interpreter behavior with current sandbox, trace, receipt, replay, concurrency, tool, and failure contracts. |
| 4 | `IW-CPR-08-GEPA-SAFE-ARTIFACT` | pending; pickle excluded | An exact artifact contract passes provenance, code/data, loading-effect, replay, failure-custody, and rollback review—or records continued exclusion. |
| 3 | `IW-APF-03-ORACLE-SEMANTICS-TIME`, then `IW-APF-04-CROSS-PROGRAM-LEARNING` | pending under paused parent | Separate parent/wave authorization after accepted Core truth gates; semantic evidence precedes temporal or cross-program generalization. |
| 5 | `IW-APF-05-ORACLE-GEPA-LOOP` and `IW-APF-08-RESUMABLE-CLI` | pending under paused parent | Core-admitted artifact, state-qualified Oracle evidence, checkpoint/effect identity, cost truth, and duplicate-effect prevention. |
| 6 | `IW-APF-06-JURY-ADJUDICATOR`, `IW-APF-07-LOCAL-TRANSITION`, then `IW-APF-09-PRODUCTION-PROOF` | pending under paused parent | Admitted candidates, resumable attempts, explicit adjudication authority, observed transition, and rollback proof. |

The v11 remediation and an authorized Soomfon evaluation are independent truth gates; neither can stand in for the other.

## Adjudication behind this shape

The recorded many-of-the-greats review exposed four valid pressures:

- upstream maximalism sees migration debt and ecosystem velocity;
- custody-first minimalism sees effect, artifact, and authority failure modes;
- learning-loop architecture sees compounding value in Oracle-guided improvement;
- product-proof sequencing sees the danger of optimizing an unobserved deployment.

The decision is contextual, not a compromise: product proof determines the first move; custody determines admission; the learning loop determines the target; upstream capabilities are useful only inside bounded characterization. This faces three lawful outcomes the feature roadmap avoided: an RLM successor may be unsupported, Decision 115 may reject executable ReActV2, and GEPA artifacts may remain production-excluded.

## Closure condition

This architecture slice is complete when the projection and AK agree on current claims, dependencies, owners, and reopen triggers. It does not close the execution debt above. Each debt closes only on the exact evidence named by its owner surface; absence of authorization or a failed gate is a result, not evidence to invent.
