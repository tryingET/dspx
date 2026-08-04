---
summary: "AK-4681 provider-free admission decision selecting a separate unique Oracle semantic-analysis v11 contract proposal, without creating v11 or live authority."
read_when:
  - "Deciding whether the accepted provider outcome receipt prerequisite permits a v11 proposal."
  - "Scoping any Oracle semantic-analysis successor after v10."
type: "decision"
status: "repo_recorded_candidate_ak_lifecycle_authoritative"
task_id: 4681
---

# Oracle semantic-analysis v11 admission decision

## Decision

Select **`propose_unique_v11_contract`**.

The provider-owner receipt implementation and the DSPx fixture-only consumer create a material observation and custody delta from v10. A fresh provider-free task may therefore propose a uniquely identified v11 contract and its task-fixed ledger and artifact root.

This decision does **not** create that contract, ledger, root, runner, candidate, review gate, live gate, verifier, or empirical process. It grants no provider, model, backend, health-probe, network, authentication, shared-store, release, publication, or activation authority. AK task evidence and result remain lifecycle authority; until AK-4681 records them, this document is a candidate.

No new AK architecture decision is opened here. Decisions 105, 106, and 107 retain their existing lifecycle outcomes and proposition boundaries.

## Bound inputs and immutable history

| Input | Bound fact | Consequence |
|---|---|---|
| AK-4643 / v10 | The one v10 corpus process is consumed, non-retryable, and terminal `effect_indeterminate`. Its receipts, events, ledger, result, verification, and retained artifact root are immutable. | V11 cannot reuse, repair, retry, relabel, or append to v10. |
| Preserved semantic bytes | V8 SHA-256 `6318df90f8dbfe187386433fe3dbc95424a409f19aed0a656dba76ef67e6cb28`; v9 SHA-256 `d346c4703df46348478ca4d272b766c23eabe6b72ba1ff168bbe911fd3387944`; code-semantics SHA-256 `42ad952318adcde35605c468fc043ae161faf310159203a3c2980a7c51177c41`. | A proposal may bind these exact reviewed semantics but may not silently revise them. |
| Provider owner | AK-4672 accepted commit `40dd8c0be1bdd48d1b296297c89613931c033239`, tree `5d980c2849685d24166d5f6924f82b9defaf1393`, with `ACCEPT_PROVIDER_OUTCOME_RECEIPT_IMPLEMENTATION`. The interface is not released or installed and its reviewed identity is not assumed to be on owner main. | A proposal may bind the exact reviewed source bytes. Any integration, rebase, cherry-pick, release, or identity change needs separate owner work and fresh exact review. |
| DSPx consumer | AK-4678 accepted commit `0f7a3efde290c66a3cf810cb436d3652e21431b3`, tree `593854ef76baed50b976547505dd07b153b301f0`, with `ACCEPT_PROVIDER_OUTCOME_RECEIPT_CONSUMER`. | The accepted private sink, journal, exact source/dependency verifier, and fail-closed reducer may be required by a proposal; they are not empirical evidence. |
| Validation limitation | AK-4678 focused fixtures, Ruff, typechecks, hooks, docs, and task-scope checks passed. Its wide gate did not pass because of recorded generated-code/module-synthesis environment failures outside the task files. | This decision does not claim a green repo-wide gate. Exact candidate review must require its own current provider-free gate evidence before any live authorization. |
| Decision 105 | Accepted DSPx execution-custody boundary only. | It does not supply semantic correctness or provider attribution. |
| Decisions 106 and 107 | Rejected; no accepted ROCS semantic-evaluation machine or compatibility adapter exists. | A v11 proposal remains DSPx empirical evaluation only and cannot claim ROCS conformance or semantic-owner authority. |

## Admission test

A successor proposal is admitted only when every row below is satisfied. A qualification narrows the next task; it is not permission to ignore the condition.

| Criterion | Finding | Status |
|---|---|---|
| Material observation delta | V10 had only a local effect-possible boundary. The accepted receipt family can distinguish proven pre-transport failure, an observed bound HTTP response, a validated local provider-protocol terminal, and an unresolved possible external effect. | satisfied |
| Acknowledgement discipline | Wrapper entry, gate entry, `transport_effect_pending`, and transport entry remain non-acknowledgement. Attribution requires `http_response_observed` or a stronger fully validated local protocol terminal. | satisfied |
| Effect-before-custody closure | The DSPx sink durably acknowledges the effect-pending marker before the owner gate may delegate; missing or invalid terminals retain `effect_indeterminate` precedence. | satisfied by fixture-only implementation proof |
| Exact identity | The accepted owner and DSPx source trees plus locked dependency payload identities are mechanically verifiable before a usable receipt reservation is created. | satisfied for exact reviewed source; no release/install claim |
| Retry and bypass closure | The owner gate admits at most one effect-capable client-visible delegation and closes stock sync/async retry, callback, alternate-client, and stream-terminal hazards under receipt mode. | satisfied by fake-transport review only |
| Bounded retention | The producer and consumer admit only closed typed facts and reject raw prompts, outputs, bodies, headers, credentials, URLs, paths, exception text, tracebacks, and arbitrary diagnostics. | satisfied by fixture-only implementation proof |
| Unique successor identity | No v11 identity, ledger, or artifact root exists yet, so a future proposal can define fresh non-colliding values without touching v10. | proposal task required |
| Gate separation | Contract proposal, candidate materialization/review, operator-authorized live execution, and independent provider-free verification can be separate tasks with fail-closed transitions. | admitted by this decision; none created |

The exact accepted receipt seam is a stronger fact boundary than the v10 local call counter and effect reservation. The successor therefore does not merely rename v10. The remaining qualifications are deliberately placed in future gates rather than converted into live authority now.

## Why the pause disposition is not selected

`pause_empirical_line` would be required if the receipt were wrapper-local only, if request acknowledgement still depended on call counters or exception text, if effect-pending durability could not precede delegation, if retries or alternate clients could bypass the gate, if a missing terminal could become failure rather than indeterminate, or if basic feasibility required a provider probe.

The accepted owner and DSPx fixture evidence falsifies those prerequisite failures for the exact reviewed source identities. It does not prove live provider behavior, but live proof is not needed to decide that a contract proposal is technically meaningful. The lawful result is therefore permission to **propose**, not permission to execute.

## Mandatory future gate graph

Every transition below requires a fresh AK task. Completion of one gate does not create, approve, or execute the next.

### Gate 1 — provider-free unique contract proposal

A fresh task may draft, but not execute, a v11 contract. It must:

- define a unique contract/schema/version, a fresh task-fixed ledger identity, and a fresh no-reuse artifact root;
- bind the exact reviewed provider-owner and DSPx source identities, concrete module hashes, dependency payload identities, and accepted receipt schemas;
- re-derive the exact reviewed non-secret semantic-request projection and preserve the v8, v9, and code-semantics hashes above unless an owning decision separately changes them;
- freeze declared corpus order, thresholds, terminal precedence, one corpus-process budget, zero health probes, zero DSPx-managed retries, no selective quality rerun, and stop-on-`effect_indeterminate` behavior;
- keep artifact-integrity review, provider-outcome receipt acceptance, empirical disposition, ROCS conformance, publication, release, and activation as separate coordinates;
- specify provider-free positive and adversarial validation, current repo-wide gate expectations, rollback, privacy, and bounded retention;
- end as either `v11_candidate_designable` or `pause_empirical_line`.

This gate may name proposed identities but must not initialize or consume a ledger, create the live artifact root, invoke a provider, or claim operator/live approval.

### Gate 2 — provider-free candidate materialization

Only an accepted Gate 1 contract may authorize a fresh task to implement its candidate runner, ledger initializer, receipt binding, and verifier surfaces. The task must create fresh v11-only code and fixture artifacts without touching v10, and it must perform no provider or network operation.

### Gate 3 — exact candidate review

A separate independent review task must bind the exact candidate commit, tree, contract hash, source-module hashes, dependency identities, and task-fixed ledger/root declarations. It must rerun the contract's provider-free positive/adversarial lanes and current repo-declared gates. Any source drift, unresolved wide-gate failure material to the candidate, receipt bypass, ambiguous terminal, secret retention, ledger collision, or v10 mutation yields rejection.

Acceptance may produce only an exact candidate-review token. It cannot authorize provider execution.

### Gate 4 — explicit operator/live gate

A fresh live task may exist only after the exact candidate review is accepted and the operator explicitly authorizes the named provider operation. Its preflight must re-bind the reviewed bytes and prove the fresh ledger/root are absent and available. The task may then consume at most its contract-fixed one corpus process, with no health probe, mechanical retry, selective rerun, or fallback path.

An open or invalid effect-capable receipt immediately terminalizes the corpus as `effect_indeterminate`; it does not permit retry. Provider transport-call cardinality, provider-internal retries, executed-model identity, and process-wide network isolation remain unproved unless separately and directly observed under an owning contract.

### Gate 5 — independent provider-free verification

After Gate 4 terminalizes, a separate task must verify retained bytes without invoking a provider, filling missing events, changing terminal artifacts, or consuming another ledger. It may accept or reject artifact integrity and receipt validity, but it may not relabel the empirical disposition or synthesize transport facts.

## Mandatory pause and rejection conditions

Any future gate must stop rather than weaken the contract when:

- the exact reviewed owner source cannot be bound or changes without fresh owner review;
- the DSPx consumer or dependency envelope drifts without exact acceptance;
- any supported path can bypass the one receipt gate or delegate a repeated effect-capable attempt;
- acknowledgement is inferred from wrapper/gate/transport entry, counters, elapsed time, exceptions, or missing output;
- effect-pending durability is not acknowledged before delegation;
- raw, secret, unbounded, or tainted diagnostic data would be retained;
- the ledger or artifact root collides with v10 or any consumed attempt;
- contract, candidate review, live authorization, execution, and verification are collapsed into one task;
- provider-free candidate validation is not green or exact review is not accepted;
- operator authority for the exact live operation is absent;
- the proposal changes semantic meanings or claims ROCS conformance without an accepted semantic owner;
- v10 would need to be retried, rewritten, repaired, or reinterpreted.

## Maximum claim and nonclaims

The maximum claim is:

> The exact accepted provider-owner receipt and DSPx consumer make a separately reviewed v11 contract proposal technically meaningful because they add a direct, fail-closed outcome-observation boundary unavailable to v10.

This decision does not prove or authorize:

- a v11 contract, candidate, runner, ledger, artifact root, live gate, verifier, or empirical result;
- provider connectivity, request completion, semantic quality, transport-call cardinality, provider-internal retry count, exact wire bytes, executed-model identity, or network isolation;
- owner-main integration, package release, installation, publication, promotion, or activation;
- shared-store durability, ROCS conformance, semantic-owner acceptance, or reversal of Decisions 106/107;
- a passing repo-wide gate at the AK-4678 commit.

## Legal next transition

After AK-4681 records `propose_unique_v11_contract`, the only admitted next leaf is **Gate 1: a fresh provider-free task to propose the unique v11 contract**. Gates 2–5 remain uncreated and unauthorized. If Gate 1 cannot satisfy every bound identity, uniqueness, privacy, custody, validation, and separation requirement, it must return `pause_empirical_line` and create no candidate or live task.

Use [Oracle semantic provider outcome receipt design](oracle-semantic-provider-outcome-receipt-design.md) for the accepted prerequisite contract, [Oracle semantic truth next move](oracle-semantic-truth-next-move.md) for the v10 route selection, [Product posture](product-posture.md) for the current frontier, and [Semantic benchmarks](semantic-benchmarks.md) for immutable empirical history.
