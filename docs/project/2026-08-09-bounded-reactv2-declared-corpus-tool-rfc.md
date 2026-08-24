---
summary: "RFC for one fixed generated ReActV2 tool over a hash-bound declared local corpus snapshot."
read_when:
  - "Reviewing generated ReActV2 retrieval, generated tool policy, runtime traces, or replay contracts."
type: "proposal"
---

# RFC: bounded generated ReActV2 declared-corpus search

## Status

Proposal only. AK decision runtime is authoritative. This RFC does not authorize implementation, generated-program activation, promotion, or external effects.

## Inputs

- Trigger: [bounded declared-corpus search trigger](2026-08-09-bounded-reactv2-declared-corpus-tool-trigger.md)
- Evidence: [current ReActV2 and corpus boundary](2026-08-09-bounded-reactv2-declared-corpus-tool-evidence.md)
- Existing frame: [program-gen broadening strategic frame](program-gen-broadening-strategic-frame.md)
- Runtime boundary: [behavior-first runtime boundary](program-synthesis-boundary.md)

## Problem statement

Generated ReActV2 can currently reason only with `tools=[]`. The existing `local_corpus_snapshot` retriever is executable and deterministic, but it is a scheduled topology module rather than an iterative ReActV2 callable. A deep-research voice brain therefore cannot truthfully claim ReActV2 retrieval-tool execution.

## Goals

1. Permit exactly one generated callable named `search_declared_corpus` for an explicitly opted-in ReActV2 module.
2. Reuse the materialization-time `local_corpus_snapshot` capture and deterministic lexical-selection semantics.
3. Make executable binding true only when generated code contains and passes the real callable to ReActV2.
4. Bind corpus identity, limits, policy, traces, outcomes, tool contracts, manifest, receipt, and replay checks.
5. Preserve support for existing descriptor-only and no-tool programs.
6. Fail closed on unknown refs, unknown citations, policy drift, corpus drift, or budget exhaustion.

## Non-goals

- generic tool registration or arbitrary callable binding;
- live web, network, subprocess, environment, shell, mutation, or external-authority access;
- runtime rereading of the declared corpus source;
- arbitrary filesystem reads or paths controlled by runtime inputs;
- tool chaining, dynamic import, custom Python refs, or non-empty ProgramOfThought sandbox;
- program promotion, selection, deployment, or authority export;
- changes to GEPA itself.

## Proposed contract

### Declaration and materialization

An explicitly opted-in ReActV2 topology module may reference only `search_declared_corpus`. Its declaration must reference one `local_corpus_snapshot` configuration with JSONL path, ID/text fields, `k`, and fixed safety limits. Materialization resolves and validates that source exactly once, embeds normalized records into generated candidate code, and records SHA-256 identity/provenance sidecars. Runtime never opens the source path.

Arbitrary tool refs and declared tools remain descriptor-only and blocked.

### Generated callable

Generated code contains one private immutable corpus value and one callable with the fixed public name:

```text
search_declared_corpus(query: str, k: int | None = None) -> list[passage]
```

The callable:

- rejects non-string, empty, or over-limit queries;
- clamps or rejects `k` above the declared maximum;
- applies the existing deterministic lexical score and stable tie-break by score then corpus ID;
- returns only bounded `{id, text, score}` passage objects from the embedded snapshot;
- tracks a fixed per-turn total-call budget in generated local process memory;
- has no imports or capabilities for network, subprocess, environment, external filesystem, mutation, or tool chaining.

The generated `dspy.Tool` or directly accepted public callable is passed as the sole ReActV2 tool. ReActV2 `max_iters`, query length, per-call `k`, total calls, result text size, and aggregate returned bytes are statically bounded.

### Evidence agreement

The following must agree on callable name, corpus hash, declaration hash, limits, and executable status:

- normalized intent and generation preview;
- plan and module surfaces;
- capability registry and tool contracts;
- generated module policy;
- manifest and receipt bundle;
- runtime outcomes and module-call traces;
- replay verification.

A runtime trace must distinguish attempted, executed, rejected, and budget-exhausted calls without adding a second authority surface. Sensitive input query and passage text remain local behavior evidence and must not enter sanitized downstream receipts.

### Citation posture

Research program outputs include structured response text plus source IDs. A consumer must verify every emitted source ID is present in the actual retrieved-ID union for that turn. Unknown or fabricated IDs fail closed before speech. DSPx runtime evidence retains the retrieved-ID set; LACP persists only hashes/counts.

### Replay and generated policy

Replay verifies exact generated source/policy/contract hashes and rejects any mismatch between claimed binding and actual constructor/callable. The static generated-policy validator allows only the fixed generated pattern and continues rejecting aliases, arbitrary tool lists, dynamic calls/imports, and widened budgets.

Old no-tool ReActV2 candidates remain valid under their original false-binding contract. Descriptor-only refs never become executable by implication.

## Options considered

### A. Keep `tools=[]`

Safest current posture, but cannot satisfy genuine iterative deep-research retrieval. Truthful outcome would be to stop the voice-turn objective as unsupported.

### B. Use only scheduled `Retriever`

Reuses existing implementation and supports researched answers, but does not satisfy the required ReActV2 tool-call proof.

### C. Add the fixed hash-bound callable (proposed)

Adds the narrow capability needed while preserving local determinism and fail-closed replay. It does increase generated-code and policy complexity and therefore requires explicit architecture review.

### D. Build a generic tool framework

Rejected. It widens authority/effect/security scope far beyond the use case.

## Validation obligations if accepted

- intent/topology validation for one valid ref and adversarial unknown/widened refs;
- generated-code compile and actual callable-execution tests with a fake ReActV2 harness;
- lexical selection/tie-break/query/result/call/iteration budget tests;
- generated-policy positive test for only the canonical pattern and negative import/effect/alias tests;
- runtime outcome/trace proof of executed and rejected calls;
- replay success plus corpus/source/policy/constructor/trace drift rejection;
- compatibility tests for old descriptor-only/no-tool candidates;
- six separate voice-brain intents/manifests and live provider runs;
- researched citation validation and deep-research real tool-call evidence;
- repo `just check` and `just verify-full`.

## Rollout and rollback posture

Rollout is source-only and opt-in at intent materialization. No existing candidate is rewritten. Before any downstream operator use, regenerate only the deep-research candidate, run focused replay and live evidence, and keep promotion state `not_promoted`.

Rollback removes the opt-in source path and regenerates the affected local candidate; existing no-tool candidates continue to work. Any indeterminate live run is retained as evidence and not mechanically retried.

## Open questions for review

1. Should return passage text be capped per passage and in aggregate, and at what exact byte limits?
2. Should call-budget state live in the callable closure or a generated immutable helper object?
3. Does DSPy 3.3 public ReActV2 require `dspy.Tool`, or is a typed callable the narrower stable surface?
4. Which exact trace fields prove execution without retaining more conversational text than needed?
5. Is one review track sufficient, or should generated-policy and replay safety receive independent tracks plus synthesis?

## Decision requested

Accept, revise, or reject Option C: one fixed, pure, hash-bound `search_declared_corpus` generated binding for explicitly opted-in ReActV2, under the limits and evidence obligations above.

The next legal move is structured review. Source implementation is blocked until the latest review closure is `ready_for_adr`, an ADR is accepted, and post-ADR implementation/validation/rollback planning is linked.
