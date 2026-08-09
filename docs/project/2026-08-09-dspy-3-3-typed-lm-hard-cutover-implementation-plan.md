---
summary: "Implementation, validation, rollout, and rollback plan for the DSPy 3.3 typed-LM hard cutover."
read_when:
  - "Executing Decision 118 or reviewing its implementation tasks."
type: "implementation-plan"
---

# DSPy 3.3 typed-LM hard-cutover implementation plan

## Authority

Decision 118 and `../adr/20260809-dspy-3-3-typed-lm-hard-cutover.md` authorize this plan. AK owns executable task scope and lifecycle. This document does not authorize release, publication, activation, providers, tools, or external effects.

## Fixed target

- Python 3.13
- DSPy `3.3.0`
- DSPy-AI `3.3.0`
- retained target GEPA `0.1.1`
- retained target lock SHA-256 `3c1a67002a7b2a42afda6ff5bba6e2cb10e164badab5e81620504b05772034a9`
- retained rollback: exact DSPy/DSPy-AI `3.1.3`, GEPA `0.0.26`

Every implementation task uses exact scoped files, no ambient AK, no live credentials/providers/network/external tools, and no `.ontology/**` or `governance/release-signing/**` mutation.

## Wave T1 — typed provider kernel and offline canary

Build in the retained exact-target environment before canonical dependency movement.

Required behavior:

- define DSPx-owned provider request/result/effect types;
- define a synchronous DSPx provider protocol;
- implement a deterministic stub provider with no DSPy inheritance;
- implement the sole `DSPyTypedLMAdapter(dspy.BaseLM)` with `forward_contract = "typed_lm"` and `forward(request: dspy.LMRequest) -> dspy.LMResponse`;
- initialize `BaseLM` with an exact model, `model_type="text"`, empty secret-free kwargs, and DSPy-owned callbacks/history;
- accept only `LMRequest.model` matching the adapter model, empty `tools`, empty request metadata, roles `system|user|assistant`, and messages whose parts are exclusively `dspy.core.types.LMTextPart`;
- accept only default `LMConfig` plus the exact cache configuration that DSPy `BaseLM` derives from the adapter's own `cache` flag with no rollout ID; non-default temperature, max tokens, top-p, stop, n, logprobs, response format, reasoning, tool choice, prompt cache, extensions, or divergent cache controls require a later explicit mapping;
- construct output with `dspy.LMResponse.from_text`, exact observed model, zero-token `dspy.core.types.LMUsage`, and bounded non-secret provider data containing the terminal effect disposition;
- override `aforward` to raise `dspy.LMUnsupportedFeatureError(features=["async"])` before provider invocation; do not inherit or synthesize async execution;
- reject tools, non-text parts, unknown metadata/extensions, unsupported response schemas/reasoning, cancellation, and streaming before effects;
- keep DSPx and DSPy DTO identities distinct;
- keep adapter state secret-free and reconstructible for trusted local saved programs.

Acceptance:

- explicit typed request returns typed response;
- ordinary DSPy module call retains DSPy's documented legacy list return only at the DSPy public call boundary, not inside DSPx providers;
- adapter history and provider events are distinct: DSPy owns `history`/callbacks while the provider owns a separately named bounded event record;
- `dump_state`/`load_state` use an exact versioned provider descriptor, exclude provider objects and secrets, and reconstruct the trusted stub through DSPy `BaseLM.load_state(..., allow_custom_lm_class=True)`;
- `copy()` resets DSPy history, copies callback/kwargs containers, and neither aliases mutable provider events nor fabricates a new provider effect;
- callback tests prove one start/end around success and one start/error around pre-effect rejection without treating callbacks as effect receipts;
- no legacy provider response envelope is involved;
- independent API-boundary and safety review accepts the slice.

## Wave T2 — canonical exact-3.3 transaction and support cut

Apply source, dependency declarations, and lock atomically.

Required behavior:

- pin exact direct `dspy==3.3.0` and `dspy-ai==3.3.0` unless package metadata proves one identity is redundant and the decision is amended;
- move the typed kernel and stub into canonical source;
- default offline/local paths to explicit stub where lawful;
- make live paths require an explicit migrated provider;
- registry lists only supported providers and reports deterministic unsupported errors for removed names;
- delete every importable legacy DSPy provider subclass, legacy response facsimile/parser, related export/registration path, and `MultiProviderLM` before the canonical dependency move; Git history is the migration source for later provider restoration;
- remove or rewrite tests and examples that advertise the deleted provider objects; no dormant shipped module may retain the bridge;
- preserve S1/S2 generated-program safety repairs;
- keep ReActV2, Flex, external tools, and GEPA pickle materialization unavailable.

Acceptance:

- exact focused and full credential-free matrix passes;
- generated-code guard and receipt failures remain fail-closed;
- Core wheel metadata, clean consumer resolution, installed versions, and lock agree;
- CLI/import/program execution works with `PYTHONPATH` empty and no checkout leakage;
- rollback reconstruction is demonstrated without mixing source generations.

## Wave T3 — provider extraction and restoration

For each provider, first split transport behavior from DSPy inheritance, then add it to the supported allowlist only after contract proof.

Recommended order:

1. local/openai-compatible with injected fake client;
2. `dspy-lm-auth` if its exact typed dependency contract is available;
3. OpenRouter;
4. Pi RPC;
5. Gemini CLI;
6. Claude headless;
7. Codex exec.

Per-provider acceptance:

- no DSPy inheritance;
- one DSPx provider request produces one DSPx result and effect disposition;
- unsupported typed content rejects before dispatch;
- failures cannot become answer text;
- no broad `TypeError` signature retry;
- no secret in state, history, callbacks, diagnostics, receipts, or provider data;
- prompts are not placed in process argv;
- environment is allowlisted for subprocess routes;
- timeout/cancellation disposition is proven or explicitly unsupported;
- provider/model identity and bounded usage are preserved.

## Wave T4 — aggregation replacement

`MultiProviderLM` was deleted in T2. A future aggregate is a new DSPx provider combinator, not a restored DSPy subclass.

Initial supported strategy: sequential-first only.

Rules:

- route only to capability-compatible children;
- pass immutable domain requests;
- preserve complete results rather than reducing to text;
- retry only confirmed-no-effect failures under explicit policy;
- stop on `effect_indeterminate`;
- no parallel-first until acknowledged cancellation and terminal receipts exist for every child;
- collection reducers explicitly reject non-text results until typed reduction semantics are designed.

## Wave T5 — trusted-local Core proof

Prove the exact installed artifact for:

- local, single operator;
- owner-built/reviewed hash-bound programs;
- supported typed provider matrix;
- durable receipts/traces/replay integrity;
- local evidence stores;
- explicit supported/unsupported capability matrix.

Continue to exclude arbitrary Python, generated `ProgramOfThought`, pickle-backed GEPA whole programs, hosted/multi-tenant service, shared Oracle production, external tools, automatic promotion/publication/activation, ReActV2, and Flex.

## Optional GEPA compatibility lane

A separate nonblocking task may run the exact real-output journey:

```text
real GEPA 0.1.1 optimize
-> hash-bound output classification
-> candidate copy/materialization
-> fresh subprocess load
-> behavior refresh
-> receipt integrity
-> comparison
```

Passing proves compatibility only. It does not admit pickle artifacts to the trusted-local production matrix and is not a prerequisite for T1-T5.

## Validation plan

Every wave runs:

- exact focused tests first;
- ruff format/check;
- `ty` typecheck;
- `uv lock --check` where applicable;
- `git diff --check`;
- isolated task-scope validation;
- independent review;
- exact staged-file inspection.

T2 and T5 additionally require build, clean installed-wheel consumer proof, complete resolved-environment hashes, and the repo's lawful full gate with runtime-bearing AK hooks still disabled.

## Rollout

This is a flag day at the package boundary, delivered internally as ordered commits/tasks:

1. T1 proves the spine in isolation.
2. T2 moves canonical source and exact dependencies and intentionally contracts provider support.
3. T3 restores providers additively.
4. T4 restores only safe aggregation semantics.
5. T5 produces technical evidence for separate release operations.

No compatibility aliases or deprecation shims preserve legacy provider objects.

## Rollback

- Before T2: discard the isolated target implementation and retain evidence.
- During T2: revert source/dependency/lock together.
- The immutable pre-T2 commit identifies the only full 3.1.3 rollback source generation. A full rollback after T2, T3, or T4 reverts every typed-cutover and later provider/aggregate commit to that exact source generation, restores its exact wheel/lock/environment, and quarantines all 3.3 provider state, receipts, caches, and version-bound artifacts.
- A bounded T3/T4 slice rollback reverts only that post-T2 provider/aggregate addition and removes it from the support allowlist while retaining the accepted T2 typed runtime; it never mixes 3.1.3 dependencies with typed source or restores legacy inheritance.
- Never retry an indeterminate provider effect.
