---
summary: "Design packet for a task-gated v10 DSPx empirical-quality evaluation successor to the reviewed zero-process v9 Oracle semantic-analysis candidate."
read_when:
  - "When deciding whether or how AK-4591 v9 may become an executable empirical evaluation contract."
  - "Before creating a task that could invoke the Oracle semantic-analysis provider path."
type: "design"
status: "assessed"
---

# Oracle semantic-analysis v10 empirical evaluation design

## Status and authority

This packet designs the next lawful **DSPx empirical-quality** successor to the reviewed AK-4591 v9 candidate. It does not create the v10 contract, authorize an evaluation process, invoke a provider, or issue a verdict.

The canonical verdict and owner split remains [DSPx verdict classification and source-owner contract](dspx-verdict-classification-and-source-owner-contract.md). This packet applies that contract to one exact experiment instead of repeating its general owner matrix.

The implementation sequence is in [the v10 implementation plan](oracle-semantic-analysis-v10-implementation-plan.md). Active task, packet, direction, and evidence state remain in AK.

## Exact question

| Classification field | Bound value |
|---|---|
| Proposition | Under one exact source commit, one fresh task-fixed attempt ledger, the production DSPx adapter, and the reviewed v9 provider-visible request semantics, do all four frozen cases return typed analyses that satisfy every frozen exact-code, evidence-reference, confidence, and aggregate threshold? |
| Consumer | The DSPx Oracle semantic-analysis empirical gate under `IW-CPR-04-ORACLE-SEMANTIC-TRUTH`. |
| Source owner | DSPx owns this benchmark contract, its reviewed hidden empirical labels, and the direct behavior it mediates. The labels are benchmark expectations, not domain ontology policy. |
| Subjects and access | The four candidate-local v9 cases, complete provider-visible code-semantics object, exact source files, exact request bytes, and bounded structured responses. No external semantic-owner corpus or protected subject is introduced. |
| Evaluator | DSPx runs the exact production adapter path and independently re-derives the retained result without another provider invocation. |
| Maximum claim | The exact four-case, one-process empirical contract passed or failed under the retained route and source identities. |
| Next transition | Retain local empirical evidence. Any shared Oracle publication, ROCS conformance, package release, or generated-program activation remains a separately governed owner transition. |

This proposition is not generic semantic correctness and cannot resolve or replace rejected ROCS Decisions 106 or 107.

## Frozen predecessor

V10 must treat these AK-4591 facts as immutable inputs:

- independently reviewed candidate commit: `6089521a5a3d216f7a83e6342de92197bf4e82c9` with candidate SHA-256 `0fa68440c482030ed6deb76b1d12feca8ebad36c2ebf53e1bca2766c434cf461`;
- accepted final artifact commit: `d188328c6eb226baf596a8949774056bb86ff895`;
- v9 contract SHA-256 at that final commit: `d346c4703df46348478ca4d272b766c23eabe6b72ba1ff168bbe911fd3387944`;
- code-semantics SHA-256: `42ad952318adcde35605c468fc043ae161faf310159203a3c2980a7c51177c41`;
- reviewed case order: `authority-boundary`, `causal-calibration`, `review-only-transition`, `provenance-drift`;
- v9 authorizes zero provider, fixture, or test-double evaluation processes.

V10 is a new contract and ledger identity. It must not edit v9, reuse an earlier ledger, reinterpret the v8 terminal failure, or treat a future result as retroactive v9 execution.

## V10 contract shape

### Byte-preserved inherited subtrees

The v10 preflight must prove the following logical JSON subtrees are equal to v9 before any backend resolution:

- all four case IDs, objectives, evidence records, hidden expected/forbidden labels, and confidence bounds;
- field, evidence-reference, and confidence rubrics;
- thresholds and falsifiers;
- complete code-semantics binding and materialization rule;
- privacy/effect limits, claim scope, and nonclaims;
- fixed case order and stop-after-first-failed-or-indeterminate behavior.

Provider-visible requests receive the complete hash-verified code-semantics object. They must not receive hidden labels, case-specific answers, or an unresolved file reference.

### Deliberately new v10 fields

Only the execution-bearing identity may change:

- v10 contract-schema/status and fresh AK execution-task identity;
- hashes of every evaluation source that is outside the v10 contract preimage;
- exact dependency and production-adapter preflight;
- task-fixed owner-local ledger namespace/key;
- a conditional one-process gate supplied by a later fresh task, not by this packet;
- retained artifact-root and result/verification identities.

The v10 file must not embed the Git commit or tree that contains itself. An external no-replace pre-live review receipt binds the already-fixed v10 contract hash and bound source-file hashes to one exact clean commit/tree. The terminal result binds both the contract hash and that receipt. This keeps the identity graph acyclic.

Any label, threshold, rubric, case, semantics, privacy, or authority change requires a new reviewed design rather than being smuggled into v10 materialization.

## Route and identity

The proposed route remains:

- provider: `dspy-lm-auth`;
- requested model: `codex/gpt-5.6-sol`;
- requested reasoning effort: `max`;
- adapter: exact production `DspyLmAuthLM` path with call-history evidence;
- source: a no-replace pre-live review receipt whose fixed preimage binds the v10 contract hash and external source-file hashes to an exact clean Git commit/tree matching `HEAD`.

Requested, configured, and observed identities remain separate. A successful case requires a non-empty observed model identity. The result must not claim provider transport-call cardinality or provider-internal retry absence from DSPx invocation counts.

A route preflight failure after execution entry is requested is terminal setup evidence for that task. It does not permit fallback, fixture substitution, or a second route.

## Attempt membrane

A fresh implementation task must create one owner-only artifact directory and freeze one owner-local ledger before any execution-entry preflight or backend resolution:

- at most one evaluation process;
- at most one DSPx `generate` invocation per reached case;
- zero separate health probes;
- zero DSPx-managed retries;
- no case selector or selective rerun;
- immediate stop after the first failed, error, or effect-indeterminate case;
- a started or terminal marker permanently forbids another artifact root under that task.

One process may still contain multiple provider transport operations. Provider-managed retry behavior remains `not_proven`.

Offline candidate validation and review happen before execution entry and create no live ledger. Once execution entry is requested, the mode-`0700` artifact directory and initial ledger marker are created first; every later source, dependency, contract, code-semantics, hidden-label, request, route, or backend preflight terminalizes that same ledger on failure. The task stops before any provider effect, and the terminal marker forbids another v10 entry under that task.

## Result vocabulary

The retained terminal disposition is exactly one of, using this precedence:

1. `effect_indeterminate` — execution may have crossed the provider-effect boundary without a complete attributable terminal observation;
2. `error` — no indeterminate interval exists, but setup, backend, transport, parsing, response-schema, or retention failed, including malformed/partial output or source/request/procedural drift that prevents a valid scored case;
3. `failed` — every reached response needed for classification is attributable and well formed, but a scored empirical threshold or content falsifier failed;
4. `passed` — all four cases ran in order and every frozen threshold/falsifier passed.

The first applicable class wins. A malformed response is therefore `error`, not also `failed`; a well-formed response with a forbidden code is `failed`.

Independent verification is separately `accepted` or `rejected`. Verification never invokes the provider and cannot promote `failed`, `error`, or `effect_indeterminate` into `passed`.

## Evidence and privacy

The owner-only artifact root must retain enough bounded material to re-derive the result:

- v10 contract and SHA-256;
- predecessor and code-semantics bindings;
- source commit/tree and bound file hashes;
- ledger and process/case transition facts;
- requested/configured/observed route identities per reached case;
- request hashes and bounded typed analysis for each reached case;
- independently derived per-case and aggregate scoring;
- sanitized error classification and terminal disposition;
- deterministic verification packet and hashes.

It must not retain raw unbounded provider output, credentials, tokens, headers, auth-store paths/content, or unrelated local state. The owner-only artifact directory is mode `0700`; regular retained files are mode `0600`. Possible provider-owned authentication refresh is disclosed rather than denied.

The execution requests zero shared-store connections, shared Oracle publications, embedding calls, package/release effects, governance mutations, and activation effects.

## Decision membrane

No new architecture decision is required **for this design** because it preserves the existing DSPx-local empirical evaluator, adapter, corpus, authority ceiling, and one-shot failure semantics. It adds no AK/shared-runtime schema, shared service, publication path, owner transfer, or lifecycle vocabulary; a versioned v10 benchmark-contract schema remains an ordinary task-scoped artifact.

Implementation and execution are still distinct gates:

1. this assessed design and plan;
2. a fresh scoped AK task whose contract conditionally permits at most one process after the later gates;
3. v10 materialization and zero-process validation;
4. independent pre-live review of exact committed bytes and an acyclic review receipt;
5. conditional one-process entry, only if the task and every preflight permit it;
6. deterministic verification and independent terminal review.

A material change to authority, shared publication, semantic-owner facts, subject access, adapter behavior, or runtime lifecycle requires a fresh decision/design membrane.

## Acceptance and falsification

A v10 pass requires the unchanged v9 threshold object, including exact code/evidence matches and zero forbidden hits. The complete threshold and falsifier definitions stay canonical in `benchmarks/semantic/oracle-semantic-analysis-evaluation-v9.json` until the separately tasked v10 artifact freezes its own equal copy.

The design is falsified before execution if equality with v9 cannot be proven, the complete provider-visible semantics object is not materialized, hidden labels affect request bytes, source identity is dirty or ambiguous, the ledger is reusable, or any claim/effect boundary widens.

It is falsified after execution by any missing or extra code, missing or distractor evidence reference, confidence-bound violation, malformed/partial output, source/request drift, route-identity collapse, second process, retry, selective rerun, cross-case leakage, or overwritten failure history.

## Failure, continuation, and rollback

Every terminal failure is retained. There is no v10 retry.

If v10 does not pass, a later successor requires a fresh task, contract, ledger, diagnosis grounded in retained evidence, and review. A later result does not erase or relabel v10.

Before provider execution, rollback is a normal revert of candidate contract/code. After a process starts, rollback means stopping further effects and retaining the terminal evidence; it never deletes a consumed ledger or rewrites a result.

## DRY references

- General verdict ownership: [DSPx verdict classification and source-owner contract](dspx-verdict-classification-and-source-owner-contract.md).
- V1–v9 mechanics and history: [Semantic benchmarks](semantic-benchmarks.md).
- Current shipped-vs-target posture: [Product posture](product-posture.md).
- Generated-program activation boundary: [Generated program activation boundary](generated-program-activation-boundary.md).
- Execution/custody precedent only: [Decision 105 ADR](../adr/20260803-bounded-semantic-evaluation-execution-custody-v1.md).

Decision 105 custody evidence is not a v10 quality result. Decisions 106 and 107 remain rejected and expose no accepted semantic-result interface or adapter.
