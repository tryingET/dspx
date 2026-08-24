---
summary: "RFC to replace DSPx's DSPy legacy BaseLM bridges with one typed DSPy 3.3 adapter over DSPx-owned provider ports."
read_when:
  - "Reviewing the DSPy 3.3 provider architecture or dependency cutover."
  - "Implementing or removing DSPx provider integrations."
type: "rfc"
---

# RFC: DSPy 3.3 typed-LM hard cutover

## Status

Proposed for Decision 118 through AK-4728. This RFC supersedes the proposed legacy-bridge repair direction; it does not rewrite the historical `unsupported_legacy_bridge` result of AK-4722 or the `unsupported_real_materialization` result of AK-4725.

## Trigger and evidence

The DSPy 3.3 compatibility wave proved that repairing the inherited legacy bridge would preserve the wrong architecture:

- nine provider classes combine DSPx transport behavior, DSPx DTO behavior, and DSPy `BaseLM` lifecycle behavior;
- DSPy 3.3's typed contract is explicit: `forward_contract = "typed_lm"` and `forward(dspy.LMRequest) -> dspy.LMResponse`;
- DSPx and DSPy have distinct request/response types with different semantics;
- inherited async, state, copy, history, callback, and response-normalization behavior is not truthful for current provider objects;
- `MultiProviderLM` reduces responses to text and cannot preserve typed outputs or reliable effect disposition;
- the trusted-local Core target already excludes pickle-backed GEPA whole-program artifacts, so real GEPA materialization is compatibility evidence rather than a production prerequisite.

Evidence:

- `docs/project/dspy-3-3-custom-lm-legacy-bridge-proof.md`
- `docs/project/dspy-3-3-gepa-0-1-1-materialization-disposition.md`
- exact retained DSPy/DSPy-AI 3.3.0 and GEPA 0.1.1 target lock SHA-256 `3c1a67002a7b2a42afda6ff5bba6e2cb10e164badab5e81620504b05772034a9`
- many-of-the-greats review dispatches `dispatch-1786314254545` through `dispatch-1786314254549`

## Problem

Repairing each legacy `BaseLM.forward(prompt, messages, **kwargs)` implementation would stabilize an upstream compatibility layer that DSPx no longer wants. Converting all nine provider classes in place to typed DSPy subclasses would still couple transport ownership, DSPx domain ownership, and upstream DSPy lifecycle ownership in one object.

The migration needs a hard break that removes the bridge instead of renaming it.

## Goals

1. Use DSPy 3.3's typed custom-LM contract exactly.
2. Keep DSPx provider/effect/receipt semantics DSPx-owned.
3. Remove DSPy inheritance from transport providers.
4. Introduce exactly one audited DSPy anti-corruption adapter.
5. Reject unsupported typed content before provider effects rather than flattening it.
6. Preserve effect-indeterminate as terminal and non-retryable across aggregation.
7. Make the supported provider matrix explicit; unavailable providers must not appear through best-effort registration.
8. Move the canonical dependency only as one reviewed source/dependency/lock transaction with exact rollback evidence.

## Non-goals

- preserving source or runtime compatibility for the legacy provider classes;
- maintaining `forward(prompt=..., messages=..., **kwargs)` provider entrypoints;
- replacing DSPx DTO authority with upstream DSPy DTO authority;
- fabricating async, cancellation, or incremental streaming from synchronous transports;
- enabling ReActV2, Flex, external tools, hosted service, publication, release, or activation;
- admitting pickle-backed GEPA artifacts to the trusted-local production matrix.

## Options considered

### A. Repair all nine legacy bridges

Rejected. It spends migration effort extending an upstream compatibility seam and retains lifecycle ambiguity.

### B. Convert all nine providers directly into typed DSPy subclasses

Rejected. It removes the old method shape but preserves the deeper conflation: each transport continues to own DSPy callbacks, history, copying, serialization, and normalized response construction.

### C. DSPx provider ports plus one typed DSPy adapter

Selected. Transport providers implement a DSPx-owned request/response/effect contract and do not inherit from DSPy. One `DSPyTypedLMAdapter` subclasses `dspy.BaseLM`, declares `forward_contract = "typed_lm"`, translates supported requests, and creates typed responses.

### D. Stub-only permanent product cut

Rejected as the durable architecture. Stub-first is the migration canary, not the final provider posture. Providers return one at a time only after satisfying the new contract.

## Decision requested

Adopt option C as a hard cutover.

### Canonical boundary

```text
DSPy module/runtime
  -> dspy.LMRequest
  -> DSPyTypedLMAdapter (only DSPy subclass)
  -> validated DSPx ProviderRequest
  -> DSPx provider port
  -> DSPx ProviderResult + effect disposition
  -> DSPyTypedLMAdapter
  -> dspy.LMResponse
```

### Domain rules

- DSPx types remain nominally distinct from DSPy types.
- The adapter translates only explicitly supported text/message/config fields in the first slice.
- Tools, typed non-text parts, reasoning, response schemas, and unknown extensions fail before effects until separately implemented.
- Provider results carry observed model identity, bounded usage, safe metadata, and an effect disposition.
- Raw credential-bearing responses, environment contents, clients, locks, subprocesses, and provider history are not serialized into DSPy state or history.

### Runtime rules

- Synchronous typed execution is the first supported contract.
- `aforward` exists only for a natively asynchronous, cancellation-accountable provider; otherwise it rejects before effects.
- Thread wrapping is not async support.
- Completed output is not incremental streaming.
- `effect_indeterminate` prohibits retry, fallback, or starting another aggregate child.
- Parallel-first aggregation remains unsupported until every participating effectful child has acknowledged cancellation and terminal receipts.

### Provider rules

- Registry factories return DSPx providers, not dual-interface DSPy/provider objects.
- Composition explicitly wraps a provider with `DSPyTypedLMAdapter` before `dspy.configure`.
- Default registration is an allowlist, not best-effort exception swallowing.
- Stub is the first canary. Every other provider is unavailable until migrated and proven.
- Before the canonical dependency move, every importable legacy provider subclass, response facsimile/parser, registration/export path, and `MultiProviderLM` is deleted from the shipped source; any future provider or aggregate is rebuilt as a DSPx port that preserves domain results and effect disposition.

### Dependency and GEPA rules

- The canonical transaction pins exact reviewed DSPy and DSPy-AI 3.3.0 identities and retains the exact lock/environment proof.
- S0's exact 3.1.3 environment remains rollback evidence, not a supported parallel bridge after cutover.
- AK-4725 remains truthful historical compatibility evidence.
- Real GEPA 0.1.1 materialization may be proved later in a credential-free compatibility lane, but it no longer blocks the typed trusted-local Core because pickle-backed GEPA artifacts remain excluded from that production matrix.

## Consequences

### Positive

- one upstream coupling point instead of nine;
- explicit typed request rejection and response construction;
- DSPx retains effect, receipt, provider, and redaction authority;
- provider support becomes truthful and additive;
- legacy response facsimiles and mixed history ownership disappear.

### Negative

- this is a public breaking change;
- provider availability shrinks during migration;
- downstream users of provider classes, `LMBase.generate`, DSPx `LMRequest`/`LMResponse`, or `MultiProviderLM` must migrate;
- the canonical 3.3 transaction is necessarily broad and must be tested as one atomic cutover.

## Falsifiers

Reject or roll back the cutover if:

- transport providers still subclass DSPy after their migration slice;
- a second adapter or legacy response parser survives as a required path;
- unsupported typed fields are flattened or silently ignored;
- an indeterminate effect can be retried or hidden as completion text;
- the exact installed dependency graph differs from the retained lock;
- the installed-wheel proof needs source-checkout leakage;
- generated-code guard policy must weaken.

## Rollback

Revert the canonical typed source/dependency/lock transaction as a unit, restore the retained exact 3.1.3 wheel and environment, and quarantine 3.3-created caches and version-bound artifacts. Do not restore half-migrated dual-interface provider objects.

## Decision

Accept the hard cutover and authorize the implementation plan in `2026-08-09-dspy-3-3-typed-lm-hard-cutover-implementation-plan.md` after a `ready_for_adr` review and accepted ADR.
