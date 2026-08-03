---
summary: "Canonical DSPx-local classification of empirical quality, semantic conformance, publication, activation, and AK lifecycle facts after Decisions 105–107."
read_when:
  - "You are interpreting a DSPx semantic benchmark, Oracle result, jury result, or candidate status."
  - "You are deciding whether work belongs in DSPx, ROCS/ontology, a publication owner, a governing domain, or AK."
  - "You are proposing a successor after rejected ROCS Decisions 106 or 107."
type: "reference"
status: "current"
---

# DSPx verdict classification and source-owner contract

## Scope

This document is canonical for **DSPx-local verdict vocabulary and owner routing**. It prevents the word `semantic` from collapsing empirical model quality, ontology-backed semantic conformance, publication, production activation, and AK lifecycle state into one result.

It is not:

- semantic policy or ontology authority;
- a ROCS evaluator or Decision 53 adapter;
- an activation or publication decision;
- a replacement for AK task, decision, artifact, or evidence truth;
- authorization to execute the DSPx AK-4591 semantic-analysis v9 candidate.

Query AK for current lifecycle truth. Treat this file as a repo documentation contract, not a second status database.

## Typed fact and verdict owners

| Fact or verdict | Source owner | Maximum truthful claim | Must not imply |
|---|---|---|---|
| Execution, output, custody, and replay facts | DSPx for effects it directly mediates or observes | A named attempt produced or retained the bound observations and bytes under the stated contract | Semantic correctness, provider-side behavior, publication, or activation |
| Empirical benchmark or quality gate | DSPx under the exact evaluation contract; Oracle may interpret retained behavior | The exact bounded corpus, scorer, runtime, and attempt satisfied or missed their declared empirical threshold | ROCS semantic conformance, broad correctness, domain acceptance, or activation |
| Semantic policy, labels, predicate meaning, subject selection, and precedence | Named domain semantic/ontology owner | The owner has supplied an exact, current meaning and subject contract | DSPx file location, benchmark labels, or AK lifecycle state creating semantic authority |
| Deterministic semantic conformance | ROCS under an accepted owner policy, authorized subjects, typed joins, and conformance vectors | The named subjects conform or do not conform to the exact accepted semantic contract | Schema/identity checking becoming semantics, or conformance authorizing publication/activation |
| Shared Oracle empirical-memory publication | DSPx/Oracle publication contract and named storage owner | The named empirical record was published into the declared Oracle memory with bound provenance | The record is semantically correct, approved, canonical society state, or activation authority |
| Semantic-release publication and currentness | Decision 53 semantic-release owners under their accepted protocol | A named semantic release is published/current for its declared scope | Consumer adoption, production activation, or a missing upstream semantic result |
| Package publication or release | DSPx release/package owner under a separate accepted release contract | The named package artifact was published or released under that contract | Semantic conformance, program activation, or owner quorum that was not proven |
| Generated-program production activation | Affected domain or delegated governing body | The identified program may be activated under explicit constraints, rollout, monitoring, and rollback | DSPx, Oracle, MLflow, jury, or local sidecar evidence deciding activation by itself |
| Task, decision, artifact, evidence, and lineage state | AK / active society DB | A governed lifecycle transition or evidence attachment occurred | AK `accepted`, `rejected`, or `unblocked` becoming a domain or semantic verdict |

The terms **semantic benchmark**, **semantic-analysis LM gate**, and **production-semantic embedding gate** in DSPx are historical/product vocabulary for bounded **empirical-quality evidence**. They do not name ROCS semantic-conformance results.

## Current closure boundary

As of 2026-08-03:

- **Decision 105** is `unblocked/accepted`. It established bounded DSPx execution-attempt custody and one immutable digest-only, explicitly non-semantic projection. It did not establish semantic meaning or a ROCS verdict.
- **Decision 106** is `unblocked/rejected`, with no ADR. Its controlling review found no semantic-owner policy, selected subject preimages, typed joins, acquisition authority, currentness, verdict vocabulary, or conformance vectors. It exposes no accepted semantic-result interface.
- **Decision 107** is `unblocked/rejected`, with no ADR. An adapter cannot manufacture the absent Decision 106 source fact or translate AK rejection into a domain result.
- **DSPx AK-4591 semantic-analysis v9** is a reviewed metadata-only remediation candidate. It adds provider-visible code semantics while preserving accepted hidden labels and distractors. It authorizes zero provider, fixture, or test-double evaluation processes and grants no empirical-quality pass, ROCS conformance, release, publication, or activation claim.

These are lifecycle and architecture facts. Future owner inputs require new decisions/tasks; they do not retroactively revise Decisions 106 or 107.

Current readback surfaces:

```bash
ak decision passport 105 -F json
ak decision passport 106 -F json
ak decision passport 107 -F json
ak task show 4591 -F json
```

## Classification procedure

Before naming or implementing a verdict, record:

1. **Proposition** — the exact question being answered.
2. **Consumer** — the named component or governing domain that needs the answer.
3. **Source owner** — who owns the meaning and source facts.
4. **Subjects and access** — exact bytes, canonicalization, typed joins, and read/currentness authority.
5. **Evaluator** — which owner may execute the derivation or empirical measurement.
6. **Maximum claim** — the strongest result the evidence can support.
7. **Next transition** — whether the result remains local evidence or feeds a separately governed publication or activation decision.

If any of these is absent, stop rather than publishing a generic verdict interface.

## Lawful continuation routes

### DSPx empirical-quality work

Use a fresh, explicitly scoped DSPx task and evaluation contract. A successor may materialize or evaluate AK-4591 v9 only after separately binding the exact candidate, attempt budget, route, privacy, failure, retention, and verification rules. A result remains bounded empirical evidence.

This route does not resolve or replace Decision 106.

### Semantic-conformance work

First obtain a fresh domain semantic-owner proposal containing:

- owner identity and current approval;
- exact canonical policy bytes, predicates, verdict/abstention vocabulary, scope, and precedence;
- policy-selected subject preimages or an explicit owner-local evaluation model;
- capability/read receipts for non-public subjects;
- typed digest/preimage joins and canonicalization;
- positive, negative, malformed, stale, revoked, and abstention vectors.

Only after acceptance may a fresh ROCS decision propose deterministic evaluation. Do not reopen Decision 106.

### Publication or activation work

Route publication to its typed owner: Oracle empirical-memory publication, Decision 53 semantic-release publication/currentness, or DSPx package publication are distinct concerns.

Route generated-program activation to the accountable domain or delegated governing body. DSPx/Oracle artifacts are inputs; AK records canonical lifecycle and evidence where landed. Do not reopen Decision 107 or use an adapter to manufacture owner conclusions.

## Non-implications

```text
custody or digest equality
  != semantic meaning

schema conformance
  != semantic conformance

empirical benchmark pass
  != broad correctness or ROCS verdict

ROCS semantic conformance
  != publication, adoption, or activation

Oracle publication
  != canonical society state or activation

AK lifecycle outcome
  != domain verdict

jury or review evidence
  != governing-domain authorization
```

An adapter may preserve or reduce an accepted typed source claim. It may not create a missing source value, strengthen authority, or translate lifecycle state into semantic meaning.

## DRY source map

Use the owning document instead of copying its detail:

- DSPx benchmark mechanics and v1–v9 empirical history: [Semantic benchmarks](semantic-benchmarks.md).
- DSPx generated-program activation evidence boundary: [Generated program activation boundary](generated-program-activation-boundary.md).
- DSPx target runtime ontology: [Behavior-First Runtime Boundary](program-synthesis-boundary.md).
- Current shipped-vs-target projection: [Product posture](product-posture.md).
- Decision 105 accepted custody boundary: [`../adr/20260803-bounded-semantic-evaluation-execution-custody-v1.md`](../adr/20260803-bounded-semantic-evaluation-execution-custody-v1.md).
- Decision 106 controlling closure: `~/ai-society/core/rocs-cli/docs/project/semantic-evaluation-machine-v1-review-synthesis-r2.md`.
- Decision 107 controlling closure: `~/ai-society/core/rocs-cli/docs/project/semantic-evaluation-decision53-compatibility-v1-review-synthesis-r2.md`.
- Current cross-system owner tie-break: `~/ai-society/holdingco/governance-kernel/docs/core/definitions/runtime-authority-matrix.md`.
- 10,000-foot system placement: `~/ai-society/softwareco/owned/agent-kernel/docs/project/ai-society-convergence-architecture.md`.
- Society-wide generated-program activation boundary: `~/ai-society/holdingco/governance-kernel/docs/core/definitions/generated-dspy-program-promotion-governance.md`.

The convergence architecture is system context, not Decision 106 evidence. Candidate KES learnings and proposal documents remain advisory until their owner accepts them.