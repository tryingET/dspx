---
summary: "Claimed-task design for fail-closed MultiProviderLM response classification, fallback legality, and finite registered-provider timeout defaults."
read_when:
  - "Changing MultiProviderLM failure, fallback, reduction, or timeout behavior."
  - "Reviewing AK task 4032 or IW-CPR-01 provider-truth completion."
type: "design"
---

# Multi-provider failure and timeout truth design

## Status and scope

- AK task: `4032` — **claimed** before this design was authored.
- Strategic frame: `SF-CORE-PRODUCTION-READINESS`.
- Implementation wave: `IW-CPR-01-PROVIDER-TRUTH`.
- Design packet key: `DSPX-MULTI-PROVIDER-TRUTH-DESIGN-V1`.
- Scope: `MultiProviderLM`, the registered `multi` factory, focused tests, and provider-runtime documentation.
- Decision membrane: not required. This tightens an existing fail-closed runtime contract without moving source ownership, external authority, or architecture ownership.

This packet freezes the bounded implementation shape before code implementation. It does not itself execute a provider, approve a model result, mutate external authority, or authorize production activation.

## Design question

How can the aggregate provider route guarantee that child-provider failures and timeouts never become success-shaped output, while preserving exact marker semantics, useful fallback, request-option forwarding, redaction, and a finite production timeout default?

## Current surface summary

`MultiProviderLM` currently records an error only when a child raises. A child response carrying `_dspx_error: true`, a non-empty explicit `error`, or a declared failure `status` can therefore be reduced as successful text. The async collection path trusts `.text`, does not normalize DSPy/internal response shapes, and can accept empty output as the first parallel success.

Sequential and collection strategies continue after every exception. That is unsafe for a timeout because an invoked provider may have produced an effect even though the caller did not receive a determinate result. Async readiness has a finite fallback timeout, but the registered `multi` route does not impose a finite default on child providers whose timeout configuration is unset or non-finite.

## Operator needs

1. A marked or declared child failure must never appear as aggregate model output.
2. Failure classification must be identical through outer `forward()` and `generate()` entrypoints.
3. Error-looking model prose must remain valid when the provider reports success.
4. A conclusive child failure may permit the selected strategy to use another child.
5. A timeout is indeterminate and must stop sequential/collection fallback rather than replaying work through another provider.
6. The registered production `multi` route must configure a finite child-provider timeout by default.
7. Diagnostics and aggregate raw metadata must be sanitized and attributed to the provider that actually produced the result.

## Design decision

### 1. One response-classification membrane

All synchronous `forward`, internal `generate`, and async `collect` response envelopes pass through one helper before text is accepted.

The helper:

- applies `raise_for_explicit_provider_error()` to the response and its `raw` payload;
- recognizes internal `outputs`, DSPy/dictionary `choices`, and explicit `.text` response shapes;
- rejects missing, malformed, empty, or whitespace-only completions as conclusive provider-response failures;
- never inspects model prose for error meaning;
- preserves the exact marker rule: only typed boolean `_dspx_error is True` activates that marker; false/non-boolean markers and empty optional error fields do not;
- treats a provider-declared timeout error type as indeterminate rather than conclusive.

### 2. Explicit outcome disposition

`ProviderResult` records whether an error is indeterminate. The runtime has three effective outcomes:

- **success** — a recognized, non-empty completion with no provider-owned failure signal;
- **conclusive failure** — explicit failure payload/status, ordinary non-timeout exception, missing response contract, or empty completion;
- **indeterminate** — `TimeoutError`, a timeout exception type such as `TimeoutExpired`, a provider-declared timeout error type, or async readiness expiry after invocation started.

Classification uses typed payload fields and exception types, never exception/model message prose.

### 3. Fallback legality

- `sequential_first`: continue only after conclusive failure. Stop on the first indeterminate result.
- `collect_concat` / `collect_longest`: omit conclusive failures when at least one child succeeds. Stop before invoking remaining children on an indeterminate result; never return partial output from that request.
- `parallel_first`: a conclusive failure cannot beat a slower success. A timeout observed before a successful winner poisons the request, triggers best-effort termination of pending async runs, and fails closed. Already launched work is never replayed.
- Reducers and built-in reduction receive only successful results.
- No providers, no successful results, or any indeterminate result is an outer invocation failure.

The runtime makes no claim that a timed-out synchronous Python thread can be killed. The safety property is narrower and truthful: provider transport owns its timeout/cancellation, and the aggregate route performs no fallback replay after an indeterminate timeout.

### 4. Finite registered-provider timeout default

`MultiProviderLM` gains `provider_timeout_s`, a strictly positive finite value with a default of 60 seconds. Construction applies this value to a child provider's existing `timeout` or `timeout_s` attribute only when that attribute is unset, non-positive, NaN, or infinite. An explicitly configured positive finite child timeout is preserved.

The registered `multi` factory reads `DSPX_MULTI_TIMEOUT` with a strict positive-finite default of `60` and passes it as `provider_timeout_s`. Invalid values fail factory construction instead of silently selecting an unbounded route.

Async readiness remains separately bounded but is capped by the finite multi-provider timeout. Direct custom providers that expose no timeout contract remain responsible for their own transport deadline; DSPx does not claim that arbitrary Python callables can be safely cancelled.

### 5. Forwarding and observability

- `forward` kwargs remain unchanged when the child accepts them.
- `generate` merges `request.options` followed by explicit kwargs, preserving the current override order and the merged child `LMRequest`.
- No broad `TypeError` retry is introduced.
- Aggregate raw metadata uses each returned `ProviderResult.name` and `model`, not the result-list index.
- Child raw payloads and errors are sanitized before they enter aggregate metadata.

## Authority boundary

- Provider transports and authentication remain owned by their provider implementations and `dspy-lm-auth` where applicable.
- DSPx owns aggregate role selection, failure disposition, fallback policy, timeout defaults, redaction, receipts, and local runtime behavior.
- This design grants no Layer-12, foundry, jury, adjudicator, review, decision, successor, AK mutation, external apply, publication, or activation authority.
- Pi remains a protocol/conformance provider, not a production dependency.

## Acceptance scenarios

### Scenario A — marked failure falls through

Given a sequential child returns text plus `_dspx_error: true`,
when a later child returns a valid completion,
then the marked text is never exposed and the valid child may win.

### Scenario B — exact marker semantics

Given a child returns error-looking prose with `_dspx_error` equal to `false`, `"false"`, or `1` and an empty `error` field,
when the aggregate classifies the response,
then the prose remains a successful completion.

### Scenario C — timeout blocks replay

Given the first sequential child raises a timeout after invocation begins,
when another child is configured,
then the aggregate fails as indeterminate and never invokes the second child.

### Scenario D — parallel failure does not win

Given a fast parallel child returns a conclusive explicit failure and a slower child returns valid output before any timeout,
when `parallel_first` resolves,
then the valid child wins.

### Scenario E — parallel timeout poisons the request

Given a parallel child reaches its readiness timeout before any valid winner,
when other work remains pending,
then pending async work is terminated best-effort and no success-shaped aggregate result is returned.

### Scenario F — collection is not partial after timeout

Given one collection child succeeds and the next times out,
when the collection strategy executes,
then later children are not invoked and the earlier partial output is not returned.

### Scenario G — finite production default

Given `DSPX_MULTI_TIMEOUT` is absent,
when the registered `multi` provider resolves children with unset timeouts,
then each supported child receives a 60-second timeout default; an invalid environment value fails closed.

## Validation plan

- Focused tests:
  - `tests/test_multi_provider_parallel_semantics.py`
  - `tests/test_provider_failure_semantics.py`
- Adversarial cases: forward-only, generate-only, async collect, exact marker controls, conclusive fallback, timeout no-fallback, empty response, provider attribution, and registered timeout configuration.
- Static gates: Ruff format/check and Ty for changed Python paths.
- Repo gates: task-scope check, impact-aware validation, strict docs, `ak direction check`, `ak packet check`, and the repo landing gate.
- Independent review asks whether any explicit child failure or indeterminate timeout can still become successful aggregate output or trigger replay.

## Rollback and non-goals

Rollback is the single bounded AK-4032 implementation commit; AK task/direction/packet history remains auditable.

Non-goals:

- generic cancellation of arbitrary Python callables;
- reducer architecture or `reduce_timeout_ms` redesign;
- provider-client transport changes;
- health/benchmark CLI expansion;
- new jury, adjudicator, executor, foundry, Oracle, transition, or learning-loop behavior;
- Layer-12 fixed-token publication or conformance work.

## Next implementation slice

Implement this packet in the task-scoped runtime, factory, tests, and provider-runtime documentation. Do not widen to installed-wheel proof; that remains `IW-CPR-02-INSTALLED-GOLDEN-PATH`.

## Stop rule

Stop implementation if finite timeout behavior would require claiming cancellation or effect rollback that the child transport cannot prove, or if the slice requires changing a provider transport owner outside DSPx. Route that gap to a separate owner-authorized task instead of weakening the fail-closed contract.
