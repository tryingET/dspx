---
summary: "Implementation, validation, execution-gate, and rollback plan for the proposed v10 DSPx Oracle semantic-analysis empirical evaluation."
read_when:
  - "When creating or executing the fresh AK task that follows the v10 empirical evaluation design."
  - "When reviewing whether a fresh task and its later gates permit a v10 provider process."
type: "implementation_plan"
status: "proposed"
---

# Oracle semantic-analysis v10 implementation plan

## Purpose and authority

Implement the [v10 empirical evaluation design](oracle-semantic-analysis-v10-empirical-evaluation-design.md) as a new DSPx-local one-shot empirical contract derived from the reviewed zero-process v9 candidate.

This plan is sequencing guidance. It does **not** create the v10 artifact, authorize a provider/fixture/test-double process, consume a ledger, or approve a result. Execution requires a fresh claimed AK task whose done contract and guardrails explicitly permit at most one process after exact pre-live review.

The [verdict classification and source-owner contract](dspx-verdict-classification-and-source-owner-contract.md) remains canonical for owner routing. This plan does not repeat or widen it.

## Entry conditions

Before implementation begins:

1. AK-4591 remains `done`, and its v9 contract and code-semantics hashes match the design packet.
2. Decisions 106 and 107 remain rejected; neither is reopened or used as v10 authority.
3. A fresh DSPx task is created with exact repo-relative scope, done contract, guardrails, and a task-fixed ledger identity.
4. The task explicitly distinguishes zero-process implementation/preflight work from the later one-process gate.
5. The worktree is clean except for declared task files; `.ontology/` remains out of scope.
6. No provider, fixture, or test-double evaluation process occurs before the committed candidate receives independent pre-live acceptance.

## Recommended task scope

The future execution task should normally allow only:

- new `benchmarks/semantic/oracle-semantic-analysis-evaluation-v10.json`;
- the existing code-semantics artifact only as a read-only bound input;
- minimal Oracle semantic evaluation/materialization/verifier modules needed to consume v10;
- focused tests for contract equality, prompt isolation, ledger behavior, scoring, retention, and verification;
- narrow updates to [Semantic benchmarks](semantic-benchmarks.md) and [Product posture](product-posture.md) after terminal evidence exists;
- a task-scope snapshot when the repo workflow emits one.

The code-semantics v1 file, v9 contract, v8 contract/result/ledger, and prior evidence roots are forbidden mutation targets. Shared Oracle, release-signing, ontology, package publication, and activation paths remain out of scope.

If implementation requires broader adapter behavior or a new public runtime surface, stop and reopen design/decision classification instead of widening the task.

## Phase 1 — materialize v10 without effects

Create v10 as a new contract. Do not copy v9 and edit it informally.

A deterministic materializer or validator must:

1. load exact v9 bytes and verify SHA-256 `d346c4703df46348478ca4d272b766c23eabe6b72ba1ff168bbe911fd3387944`;
2. load exact code-semantics bytes and verify SHA-256 `42ad952318adcde35605c468fc043ae161faf310159203a3c2980a7c51177c41`;
3. preserve every inherited case, hidden label, rubric, threshold, falsifier, privacy field, claim scope, and nonclaim required by the design;
4. bind the fresh task ID, exact external source-file hashes, dependency requirements, route, ledger key, and artifact-root contract; do not embed the commit/tree containing the v10 file itself;
5. materialize the complete semantics object into each future provider-visible request while excluding hidden labels;
6. write no artifact root or ledger during contract-check-only tests unless a disposable task fixture explicitly requires it;
7. reject unknown or widened fields fail-closed.

The v10 contract must remain non-executable until an external no-replace review receipt binds its fixed contract hash and external source-file hashes to one exact clean commit/tree. The receipt—not the v10 file—carries the self-containing Git identity.

## Phase 2 — implement bounded execution and verification

Prefer adapting the existing production evaluation and verification paths over adding another runner family.

Required behavior:

- keep offline candidate validation effect-free and ledger-free before execution entry;
- once execution entry is requested, create a no-replace mode-`0700` artifact directory and initial task-fixed ledger marker before any execution-path source, dependency, contract, request, route, or backend preflight;
- retain regular files under that directory with mode `0600`;
- terminalize the same ledger if any post-entry preflight fails;
- atomically mark the process/case boundary before each possible provider effect;
- invoke only the exact production adapter and requested route;
- run cases only in the frozen order;
- stop after the first failed, error, or effect-indeterminate case;
- retain bounded typed analysis and hashes, never raw unbounded output or credentials;
- derive terminal disposition without overwriting prior markers;
- make equal deterministic verification idempotent;
- reject any verifier path that would invoke a provider, modify terminal evidence, or infer missing identity.

A process crash or timeout after the effect boundary is `effect_indeterminate` unless retained evidence proves a narrower result. Absence of an output file is not proof that no provider effect occurred.

## Phase 3 — deterministic tests

Before independent pre-live review, add tests for at least:

### Contract and request isolation

- v10 inherited subtrees equal v9;
- v9 and code-semantics files remain unchanged;
- complete 26-code semantics materializes into every request;
- hidden-label mutation cannot change provider-visible bytes;
- response enums derive only from visible code/evidence values;
- wrong predecessor/source/semantics hash fails during offline candidate validation without entering execution;
- the same drift after execution entry creates terminal `error` evidence in the already-created ledger before backend work.

### Attempt and route membrane

- one task-fixed ledger and one no-replace artifact root;
- zero health probes and no fallback route;
- at most one process and one DSPx generate invocation per reached case;
- no case selector, retry, or selective rerun;
- stop-after-first-terminal-case;
- requested/configured/observed identity separation;
- source, adapter-method, package-version, or commit drift fails before effect.

### Scoring and verification

- exact pass vector;
- every missing/extra/forbidden code mutation;
- missing, extra, distractor, and cross-case evidence references;
- confidence above reviewed bounds;
- malformed, duplicate, unknown, prose, or partial output;
- cross-case response leakage;
- deterministic re-derivation of per-case and aggregate scores;
- immutable failed/error/indeterminate history;
- verifier rejection of tampered contract, request, ledger, result, or artifact hashes.

### Privacy and authority

- mode-`0700` artifact directory, mode-`0600` regular files, and no-replace behavior;
- sanitized bounded failure retention;
- zero shared store/publication/embedding/release/activation mutations;
- explicit nonclaims in every terminal result;
- no AK subprocess or PATH-based authority call from evaluated code.

Fixtures may test plumbing but never contribute to a live empirical result.

## Phase 4 — candidate commit and pre-live review

Run the repo-selected focused and full offline gates before any process:

```bash
just hooks-run files="<exact task files>"
just typecheck
just typecheck-tests
just task-scope-check task_id=<fresh-task-id> mode=working-tree
just check
```

Run any task-specific v10 contract/verifier commands added by the implementation. The pre-live review receives exact:

- task scope, done contract, and guardrails;
- clean commit and tree supplied outside the v10 contract preimage;
- v10/v9/code-semantics hashes;
- source/dependency/adapter bindings;
- a proposed no-replace review receipt whose preimage binds the v10 contract hash and external source-file hashes to that commit/tree;
- attempt/ledger/artifact-root policy;
- focused test commands and outputs;
- provider-visible request hashes plus proof that hidden labels are absent;
- explicit maximum claim and nonclaims.

Review outcome is either `ACCEPT_CANDIDATE_FOR_TASK_GATE` or `REJECT`. Candidate acceptance is review evidence only; it does not invoke or independently permit a process. Silence, partial review, or a material unresolved question is `REJECT`.

After review, contract, source, or commit/tree drift invalidates the receipt. Amend/rebase/fixup requires a new exact review and receipt; it does not inherit acceptance.

## Phase 5 — conditional one-process task gate

This plan and candidate review do not permit process entry. A fresh task may conditionally permit at most one process only after its explicit gate is satisfied. Before invoking the execution entrypoint:

1. re-read the task, done contract, and guardrails;
2. prove the exact review receipt, reviewed commit/tree, and clean status;
3. prove the v10 ledger and artifact directory are absent;
4. prove no other v10 process is active or terminal for the task;
5. select the exact requested provider/model/effort without fallback;
6. record the operator/task gate reference required by that task.

A failed check in this list means **do not invoke execution**; it is not a consumed attempt. Once invoked, the entrypoint first creates the mode-`0700` directory and initial ledger marker. It then reruns all source, dependency, contract, semantics, hidden-label, request, route, and backend preflights. Any failure terminalizes that ledger as `error` and forbids another v10 entry under the task.

If all post-entry preflights pass, run exactly one corpus process. Do not run a health probe, fixture wiring process, test-double process, preliminary one-case call, mechanical retry, or selective rerun.

## Phase 6 — verification and terminal review

Without a provider call, deterministic verification must re-derive:

- source, predecessor, contract, semantics, request, route, ledger, and artifact identities;
- the exact reached-case sequence and invocation counts;
- every expected/forbidden code and evidence-reference comparison;
- confidence bounds, per-case scores, aggregate score, falsifiers, and exactly one terminal disposition under the design precedence `effect_indeterminate` → `error` → `failed` → `passed`;
- privacy/effect and non-authority claims.

Retain verifier output no-replace and hash-bind it to the result. Independent terminal review asks only whether the packet is internally complete and the maximum empirical claim follows.

A review may accept a truthful failure packet without accepting the empirical gate. Record these separately:

```text
artifact_integrity_review = accepted | rejected
empirical_gate = passed | failed | error | effect_indeterminate
```

## Phase 7 — closeout and documentation

After terminal evidence:

1. record exact command/evidence references in AK;
2. update [Semantic benchmarks](semantic-benchmarks.md) with one concise terminal-history entry;
3. update [Product posture](product-posture.md) only if the shipped-vs-target frontier changed;
4. link the implementation task to `IW-CPR-04-ORACLE-SEMANTIC-TRUTH` using the lifecycle-correct role;
5. run task close-check and complete or fail truthfully;
6. leave publication, release, shared Oracle, ROCS, and activation state unchanged.

Do not copy the full design contract into status docs.

## Stop conditions

Stop before execution on:

- predecessor/semantics/source/dependency/request drift;
- missing exact independent review;
- dirty or unreviewed source;
- absent, reused, or ambiguous ledger identity;
- hidden-label leakage;
- route fallback or fixture/test-double substitution;
- widened corpus, thresholds, effects, claims, storage, publication, or authority;
- inability to prove one-process/no-retry behavior.

Stop during execution after the first failed/error/indeterminate case. Stop after execution on any artifact mutation, missing terminal binding, verifier disagreement, or independent-review rejection.

## Rollback and successor policy

Before a process starts, revert candidate implementation normally and leave v9 untouched.

After a process starts:

- retain ledger, artifacts, result, verification, and failures;
- disable further process entry for that task;
- make no destructive cleanup or history rewrite;
- use a forward code fix only under a fresh task/contract;
- call a later attempt v11 or another explicit successor, never a v10 retry.

A future semantic-owner/ROCS route remains independent and still requires the source contract described in the canonical verdict-classification document. A v10 pass cannot supply that missing authority by implication.
