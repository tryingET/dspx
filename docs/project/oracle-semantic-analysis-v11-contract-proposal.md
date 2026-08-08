---
summary: "AK-4689 provider-free proposal for a unique receipt-bound Oracle semantic-analysis v11 contract and separated candidate, review, live, and verification gates."
read_when:
  - "Materializing or reviewing an Oracle semantic-analysis v11 candidate."
  - "Authoring any task that could eventually request a v11 provider operation."
type: "design"
status: "repo_recorded_candidate_ak_lifecycle_authoritative"
task_id: 4689
---

# Oracle semantic-analysis v11 contract proposal

## Proposed disposition

Select **`v11_candidate_designable`**.

The v11 proposal is materially different from v10 because every reached semantic request must use the exact accepted provider-owner outcome receipt and DSPx private consumer. V11 may classify a valid bound HTTP response or stronger validated local protocol terminal as attributable, while an open, missing, malformed, drifted, or contradictory effect-capable chain remains `effect_indeterminate`. Wrapper entry, receipt-gate entry, `transport_effect_pending`, and transport entry remain non-acknowledgement.

This document is **Gate 1 only**. It proposes contract identities and deterministic construction rules. It does not materialize a contract JSON file, implement source, initialize or consume a ledger, create an artifact root, create later gate tasks, invoke a provider, inspect authentication state, or authorize live execution. Only AK-4689 evidence and result can select this disposition as lifecycle truth.

## Proposition and maximum claim

| Field | Proposed bound value |
|---|---|
| Proposition | Under one exact candidate commit, one fresh live-task-bound ledger/root, the unchanged four-case semantic corpus, the exact accepted receipt producer/consumer, and at most one corpus process, do all reached requests end in attributable typed outcomes and do all four cases satisfy every frozen exact-code, evidence-reference, confidence, and aggregate threshold? |
| Evaluator owner | DSPx owns the benchmark, hidden empirical labels, local custody, parsing, and scoring. The labels are benchmark expectations, not ontology policy. |
| Receipt fact owners | `tryinget-dspy-lm-auth` owns its closed wrapper/transport/protocol event meanings. DSPx owns reservation identity, private persistence, journal verification, and empirical reduction. |
| Maximum positive claim | The exact four-case v11 empirical contract passed under the retained requested/configured/observed route and accepted receipt identities. |
| Authority ceiling | No generic semantic correctness, ROCS conformance, executed-model proof, provider attestation, release, publication, or activation claim. |

Decision 105 remains custody-only. Decisions 106 and 107 remain rejected and supply no semantic-result interface. This proposal changes no decision outcome.

## Immutable predecessor bindings

V11 must reject before candidate acceptance if any of these bytes or lifecycle facts drift.

| Binding | Exact value |
|---|---|
| V8 contract SHA-256 | `6318df90f8dbfe187386433fe3dbc95424a409f19aed0a656dba76ef67e6cb28` |
| V9 contract SHA-256 | `d346c4703df46348478ca4d272b766c23eabe6b72ba1ff168bbe911fd3387944` |
| Code-semantics-v1 SHA-256 | `42ad952318adcde35605c468fc043ae161faf310159203a3c2980a7c51177c41` |
| V10 contract SHA-256 | `fb90f0c266e984489110fc3ae945c3bd37bf71b6ec8f725f56d6167241ab4128` |
| V10 implementation candidate | commit `486352e540d6f4c425419ce6145ca598b826b63e`, tree `668ddde4193502a936c346896374920b13ecbcdc` |
| V10 terminal result | SHA-256 `e8f4de5a8d5ddc25281d294dcad60f5201f21cf94d597c04004edd66014ab49d`, `effect_indeterminate`, first case `authority-boundary`, classification `effect_outcome_unresolved` |
| V10 accepted verification | SHA-256 `bd09f20b1379fd5e54ae66d0b0e335e42fc47f4494dc64d5cbb27ebb8a7da93e`, artifact integrity accepted, empirical gate unchanged |
| Admission decision | AK-4681 commit `87d68dbaa5d20a3e3a6c1c405b865b27fa8f9e49`, tree `88ec5ff21c12a181bbf15d3c303523b232f64c64`, artifact SHA-256 `73365d6829ad72cc71f83d452fdb2a2c4a9cb2a4f35c7a0ccb29b0c5ac05ca00` |

AK-4643's task-fixed ledger, event chain, result, artifact root, and one consumed process remain immutable and non-retryable. V11 must not read them as writable state, append to them, repair them, use them as a fallback root, or reinterpret their terminal disposition.

The proposal was authored from base commit `87d68dbaa5d20a3e3a6c1c405b865b27fa8f9e49` / tree `88ec5ff21c12a181bbf15d3c303523b232f64c64`. The proposal cannot embed the Git identity containing itself. AK-4689's no-replace evidence/result must bind the final proposal SHA-256 and commit/tree externally; Gate 2 must consume those exact identities.

## Exact accepted receipt identities

### Provider-owner source

The only accepted producer source is `tryinget-dspy-lm-auth` version `0.1.5`, commit `40dd8c0be1bdd48d1b296297c89613931c033239`, tree `5d980c2849685d24166d5f6924f82b9defaf1393`, lock SHA-256 `0d6c79b4b5d70f7a11a879b0bb26dc61dce064fe8dd2ca7e694a9099b43e90e1`.

| Producer module | SHA-256 |
|---|---|
| `src/dspy_lm_auth/__init__.py` | `5fce1f73b46996390379ca7a4bf86a3b73fa47809aaf68ee6822ee39c4702a38` |
| `src/dspy_lm_auth/lm.py` | `85f7c5a5b72c2062ba628827b609671299867b9ff5f1ee7ff96410c6e70e77a1` |
| `src/dspy_lm_auth/codex_stream.py` | `edb153d6f6e4615624c9688716f4b2bd02e32ac1d9794b1355190e62af1be3c4` |
| `src/dspy_lm_auth/codex_stream_support.py` | `a8804500abbf481346e833da727679472b477fcc8a6c39c3ba299c51e2f632cd` |
| `src/dspy_lm_auth/outcome_receipt.py` | `cd46faf242a2696fe4322aaee961e2b383d944f663a08959dbcb7a143e282899` |
| `src/dspy_lm_auth/outcome_receipt_state.py` | `79d9262a3f40690a3fa4fe49721bc49d984f842fd1681039b92e6629a9adc1fa` |
| `src/dspy_lm_auth/outcome_receipt_runtime.py` | `950745532b1481c850e8144c9c7c56c622ca3ce275bda8167a6a93a33fc55a5c` |
| `src/dspy_lm_auth/outcome_receipt_transport.py` | `846fd6a7e0c368e9a2a5ce72f6354d324fb61ea06663d4c04cdb7595cf022e49` |

The owner interface is not assumed released, installed, merged, or present on owner main. Gate 2 may use the exact reviewed source for provider-free fixtures. Gate 3 must reject any changed owner identity unless a separate owner task produces new exact acceptance.

### DSPx consumer source

AK-4678 accepted commit `0f7a3efde290c66a3cf810cb436d3652e21431b3` / tree `593854ef76baed50b976547505dd07b153b301f0` with these committed module hashes:

| Consumer module | SHA-256 |
|---|---|
| `provider_outcome_receipt_contract.py` | `08310ff976c47bb2a5a3003131ab4ce4b45787f1380418a96b109de6f1664d30` |
| `provider_outcome_receipt_identity.py` | `9f8a40b1b22f5fc377fb44ceb21919d2c37b48e23c04802bf340cd3fa35fc5a2` |
| `provider_outcome_receipt_journal.py` | `6e2df68d71f081192ac460ecab9acbc0c44445cc5014409279595a87a0a340a5` |
| `provider_outcome_receipt_reducer.py` | `33efcd28db0443c30069bdcb2a77ae6c9772dde25c34b2b411892302d5e48a4c` |

Gate 2 may add v11-only integration modules, but these accepted consumer bytes must remain unchanged unless a fresh fixture-only consumer task and exact review accept new identities.

### Locked runtime dependency envelope

| Distribution | Version | Locked wheel SHA-256 | Payload count | Payload SHA-256 | `RECORD` SHA-256 |
|---|---:|---|---:|---|---|
| DSPy | `3.1.3` | `26f983372ebb284324cc2162458f7bce509ef5ef7b48be4c9f490fa06ea73e37` | 139 | `e0d6a2a7cf2363b3c581a74bae5ea0f391cef631bda00e4b5fcc77e39b80270b` | `96d7152d6535f744dba11cec3cdb1c037f6539570043173ac521e0893a1948d5` |
| LiteLLM | `1.82.1` | `a9ec3fe42eccb1611883caaf8b1bf33c9f4e12163f94c7d1004095b14c379eb2` | 2532 | `b7b99502fcf3b3a78271d973233b8f25d3b812b92a060b58eb68964f8fa3a025` | `459b41009766c4fbbe8dc89f7c670acf8ab4d78f22adc57d2cbbafde5ffa579c` |
| HTTPX | `0.28.1` | `d909fcccc110f8c7faf814ca82a9a4d816bc5a6dbfea25d6591d6985b8ba59ad` | 24 | `07414d29fb1941459875ce8779ba8b64ffb35df39b38cccbb81db96aceb23ed3` | `2bf47a837bca4b5497bf86d9b2d2c15db8af63581511d70b3450c21e42ae0234` |
| httpcore | `1.0.9` | `2d400746a40668fc9dec9810239072b40b4484b640a8c38fd654a024c7a1bf55` | 32 | `bb0e6120792945054384bc9e1fa7721211f903245c79c029a648cbf6ff2b0829` | `67cb4644d84fef1df8c5a0862c57c3380eff058a153bac7a4ba2722779982554` |

The Gate 2 verifier must bind source imports and these payload identities before creating any usable receipt reservation. A version string alone is insufficient.

## Proposed closed identity vocabulary

Gate 2 must materialize these exact proposed names unless exact review rejects the proposal:

| Surface | Proposed identity |
|---|---|
| Contract schema | `dspx-oracle-semantic-analysis-evaluation-v11` |
| Contract status | `candidate_requires_receipt_review_and_separate_live_gate` |
| Contract template | `dspx-oracle-semantic-analysis-v11-contract-template-v1` |
| Ledger schema | `dspx-oracle-semantic-v11-ledger-v1` |
| Candidate-review schema | `dspx-oracle-semantic-v11-candidate-review-v1` |
| Live-gate schema | `dspx-oracle-semantic-v11-live-gate-v1` |
| Result schema | `dspx-oracle-semantic-v11-result-v1` |
| Verification schema | `dspx-oracle-semantic-v11-verification-v1` |
| Producer event family | `dspy-lm-provider-outcome-receipt-v1` |
| DSPx reservation schema | `dspx-provider-outcome-reservation-v1` |
| DSPx consumption journal | `dspx-provider-outcome-consumption-v1` |
| DSPx consumption event | `dspx-provider-outcome-consumption-event-v1` |
| DSPx inflight marker | `dspx-provider-outcome-inflight-v1` |
| DSPx poison marker | `dspx-provider-outcome-poison-v1` |
| DSPx projection | `dspx-provider-outcome-projection-v1` |

This table includes every schema emitted or consumed by the unchanged accepted consumer modules. Unknown names, versions, fields, aliases, migration fallback, or automatic compatibility normalization are contract errors.

## Fresh live-task-bound ledger and artifact root

Let `T` be the positive AK task ID of the future Gate 4 live task. Gate 2 reviews the construction function; Gate 4 supplies the concrete `T` in its no-replace live-gate receipt. No live task or concrete value is created by this proposal.

The exact construction is:

```text
ledger_namespace = dspx/oracle-semantic-analysis-evaluations/AK-<T>/v11
ledger_key       = AK-<T>:oracle-semantic-analysis-v11:one-process
artifact_key     = oracle-semantic-analysis-evaluations/AK-<T>/v11/attempt
```

The owner-private state root is selected by the Gate 4 host contract; only the relative `artifact_key` is retained. Raw absolute paths are not retained in the contract, receipt, result, or verification. The candidate must reject `T <= 0`, `T == 4643`, any task whose done contract is not the exact Gate 4 live completion kind, any alternate spelling, and any existing ledger namespace, artifact key, started marker, terminal marker, or symlink.

Before execution entry, checking absence creates nothing. On the one Gate 4 entry, the implementation must create the mode-`0700` task directory, v11 directory, and attempt directory no-replace, then write and parent-sync the mode-`0600` consumed ledger before backend imports, route resolution, request construction, or receipt creation. A started or terminal marker permanently forbids another v11 attempt for `T`.

This task-bound construction breaks the identity cycle without creating Gate 4 early:

1. Gate 2 materializes code that accepts only the construction above.
2. Gate 3 reviews the exact construction and source bytes, not a concrete task ID.
3. After acceptance, a fresh Gate 4 task receives `T` and a no-replace live-gate receipt binds `T`, the reviewed candidate receipt, and the derived namespace/key.
4. Execution checks the concrete derivation before creating state.

## Byte-preserved semantic contract

V11 must prove that all semantic-bearing v10 logical subtrees are byte-equivalent after canonical JSON normalization. The only allowed changes are the v11 schema/status, predecessor/receipt/source/dependency bindings, task-binding construction, and gate/result identities.

The preserved keys include cases, objectives, evidence, hidden expected/forbidden labels, field/evidence/confidence rubrics, complete code semantics and materialization rule, thresholds, falsifiers, privacy/effects, claim scope, nonclaims, remediation, fixed order, and stop policy.

Exact case order:

1. `authority-boundary`
2. `causal-calibration`
3. `review-only-transition`
4. `provenance-drift`

Exact thresholds:

| Threshold | Value |
|---|---:|
| Minimum case score | `1.0` |
| Minimum macro score | `1.0` |
| Minimum evidence-reference precision | `1.0` |
| Minimum evidence-reference recall | `1.0` |
| Minimum expected-code exactness | `1.0` |
| Maximum forbidden hits | `0` |
| Maximum failed or error cases | `0` |

The complete code-semantics object is provider-visible. Hidden labels, case answers, prior outputs, receipt events, and empirical dispositions are not provider-visible. Hidden-label mutation must not change provider-visible request bytes.

## Route and request contract

The requested route remains exactly:

```text
provider = dspy-lm-auth
model = codex/gpt-5.6-sol
reasoning_effort = max
mode = sync
cache = false
num_retries = 0
stream = true
store = false
```

Requested, resolved, configured, owner-observed, and provider-reported identities remain separate. A provider-reported model label is bounded metadata, not executed-model proof.

For each reached case, Gate 2 must build the exact normalized Responses request before effect. The accepted owner source permits a subset of the semantic keys `input`, `instructions`, `model`, `reasoning`, `store`, `stream`, and `text`, but the v11 integration narrows that surface and requires all seven exactly. The owner re-derives `semantic_request_sha256` as SHA-256 over `b"dspx-oracle-semantic-request-v1\0"` followed by canonical JSON of the present semantic keys. Optional generation keys `max_output_tokens`, `temperature`, `top_p`, and `truncation` may be absent or explicitly null only and are excluded from the projection; any non-null value is rejected before effect. Operational keys such as endpoint, credential, headers, client, timeout, cache, and retry posture are excluded rather than retained.

DSPx must independently derive the same digest over exactly the required seven-key reviewed non-secret projection. Missing semantic keys, a non-null optional generation key, or any digest mismatch stops before effect. The receipt is passed only through the owner public call surface as `outcome_receipt=` with `cache=False` and `num_retries=0`. DSPx must not call the owner's internal receipt-session methods, mutate LiteLLM callbacks, or let the persistence-only sink invoke an LM.

The existing v10 evaluation call path does not supply an outcome receipt. Although `DspyLMAuthLM` forwards arbitrary call kwargs to the owner LM, its generic history/error path can retain generated text and stringify exceptions. Gate 2 must make receipt use explicit through a narrowly reviewed opt-in v11 integration while preserving the same semantic request bytes and production backend proposition. Receipt mode must pass only the public receipt capability, must not stringify or persist tainted provider exceptions, and must not persist raw output through adapter history; default behavior when receipt mode is absent remains unchanged. Call counters, generic history, sanitized exception text, and post-return transport metadata remain non-authoritative and cannot substitute for the receipt.

## Per-case reservation and journal binding

Each reached case receives exactly one single-use reservation and one private journal. Proposed opaque identities are lowercase SHA-256 over domain-separated canonical data:

```text
logical_request_id = sha256("dspx-oracle-semantic-v11-logical-request-v1\0" ||
                            {T, contract_sha256, ledger_sha256, case_id, case_ordinal})
transport_gate_id  = sha256("dspx-oracle-semantic-v11-transport-gate-v1\0" ||
                            {logical_request_id, gate_ordinal: 1})
process_id         = sha256("dspx-oracle-semantic-v11-process-v1\0" ||
                            {T, ledger_sha256, retained_process_identity})
```

Every `ReceiptReservation` binds `consumer_task_id=T`, initial consumed-ledger SHA-256, process ID, case ID, logical-request ID, transport-gate ID, semantic-request SHA-256, v11 contract SHA-256, sync mode, requested and resolved route, endpoint-origin SHA-256, exact producer source identity, and exact dependency identity.

Journal root construction is `<artifact_key>/provider-outcomes/<case-ordinal>-<case-id>`. It is mode `0700`; reservation, inflight, poison, and event files are mode `0600`, no-replace, and parent-directory synced as required by the accepted consumer. The semantic output is never stored in this journal.

A reservation and journal are single-use. Missing, repeated, cross-case, cross-task, cross-ledger, wrong-contract, wrong-request, wrong-source, wrong-dependency, mixed-mode, sequence-gap, broken-chain, contradictory-terminal, or event-after-terminal data is rejected. Fixture-created owner artifacts or journals cannot support an accepted live reduction.

## Attempt and provider-effect membrane

One Gate 4 task may consume at most:

- one corpus process;
- four reached logical requests in the fixed order;
- one DSPx semantic-analysis invocation per reached case;
- one owner receipt per reached case;
- one client-visible effect-capable underlying transport delegation per reached request;
- zero separate health probes;
- zero DSPx-managed or mechanical retries;
- zero fallback routes, selectors, selective reruns, fixtures, or test-double processes.

The corpus stops after the first `effect_indeterminate`, `error`, or `failed` case. A valid `pre_transport_failed` still terminalizes that case as `error`; it does not authorize a retry. Provider-internal retry behavior, socket writes, and total provider transport cardinality remain `not_proven`.

The receipt sink must durably acknowledge `transport_effect_pending` before the owner gate delegates. A sink failure before that acknowledgement aborts the case. A failure after effect becomes possible is `effect_indeterminate` unless a stronger immutable terminal is already durable. `BaseException`, cancellation, timeout, crash, or late callback cannot rewrite a durable terminal.

## Closed terminal reduction

The v11 result applies this precedence across receipt validity and semantic scoring:

1. **`effect_indeterminate`** — any open, missing, invalid, bypassed, drifted, callback-mutated, contradictory, or unresolved effect-capable chain; receipt persistence ambiguity after effect; or inability to prove whether effect became possible.
2. **`error`** — valid `pre_transport_failed`, `remote_http_error_final`, `provider_response_failed`, or `provider_response_incomplete`; or a valid attributable `provider_response_completed` followed by bounded response parse/schema/retention failure.
3. **`failed`** — every reached request is attributable and well formed, but an exact case threshold or falsifier misses.
4. **`passed`** — all four cases run in order, every receipt chain terminalizes as valid `provider_response_completed`, every typed response is attributable and well formed, and every frozen threshold/falsifier passes.

`request_acknowledged=true` derives only from valid `http_response_observed` or a stronger bound terminal. It never derives from wrapper/gate/effect-pending/transport entry, invocation counts, history, elapsed time, exception text, missing output, or receipt absence.

Three coordinates remain independent:

```text
provider_outcome_receipt = accepted | rejected
artifact_integrity_review = accepted | rejected
empirical_gate = effect_indeterminate | error | failed | passed
```

Artifact-integrity acceptance cannot relabel the empirical gate. A valid provider terminal cannot be reopened by later DSPx parse failure; the case becomes `error`, not indeterminate. A verifier cannot synthesize or fill a missing producer event.

The accepted consumer's generic `ReceiptProjection.payload()` remains an authority-false prerequisite projection and must be retained verbatim when serialized: `fixture_only=true`, `v11_authorized=false`, and `live_execution_authorized=false`. Gate 2 must not flip, omit, or reinterpret those fields. A v11 result may consume the projection's closed receipt facts only after exact source verification, while separate AK task and Gate 4 receipts supply lifecycle/live authority. The generic consumer projection itself never authorizes v11 or proves that an empirical operation was live.

## Bounded retention and prohibited data

V11 may retain closed enums, booleans, bounded integers, task/case ordinals, bounded opaque identifiers, exact source/dependency/contract/request/response hashes, status class, protocol-event kind, and a bounded provider-reported model label. The semantic result remains separately bounded under the unchanged v10 privacy contract.

It must not retain raw or unbounded prompts, generated output, response bodies, stream deltas, owner events, headers, cookies, credentials, tokens, account identifiers, auth-store identity/content, URLs, endpoint paths, proxy values, exception text, tracebacks, arbitrary mappings, or arbitrary diagnostics. Receipt code must not stringify tainted exception or response objects. Absolute filesystem paths are not retained.

Owner-private directories are mode `0700`; regular files are mode `0600`, one link, non-symlink, no-replace. Maximum receipt event size remains 16 KiB and maximum events per logical request remains 64. Broader retention requires a new reviewed contract and cannot be introduced as debugging.

## Gate 2 — provider-free candidate materialization

A fresh scoped task may implement only after AK-4689 records `v11_candidate_designable`. It must create new v11 contract, artifact, identity, evaluation, and verification surfaces plus focused provider-free tests. It may minimally adapt the DSPx provider path to pass the public receipt capability, but it must not alter the accepted consumer modules or v10 files.

Gate 2 must:

- materialize one canonical v11 contract JSON from the exact predecessor bindings;
- implement the task-bound ledger/root construction without creating live state during validation;
- implement exact owner source/dependency verification and public receipt creation before a usable request;
- use hostile fake transports and exact accepted owner classes only;
- prove request-digest equality, hidden-label isolation, sync receipt wiring, durability ordering, retry blocking, callback rejection, all terminal mappings, crash/cancellation/BaseException custody, no tainted exception stringification or raw-output history retention in receipt mode, privacy, and tamper rejection;
- keep default non-v11 provider behavior unchanged;
- run focused tests, Ruff, both typechecks, hooks, task scope, docs checks, and the current repo-wide provider-free gate;
- end with a committed exact candidate or `pause_empirical_line`.

A current repo-wide gate failure is not silently waived. Gate 2 may preserve unrelated failures as observations, but Gate 3 cannot accept a live candidate until the contract-required current provider-free gate passes.

## Gate 3 — exact candidate review

A separate read-only task must bind:

- Gate 2 task scope, contract, guardrails, commit, tree, and clean status;
- v11 contract SHA-256 and canonical equality with the inherited v10 semantic subtrees;
- final AK-4689 proposal artifact SHA-256 and commit/tree from AK evidence;
- all v11 source hashes and unchanged accepted consumer hashes;
- exact owner source, lock, module, dependency payload, and `RECORD` identities;
- provider-visible request hashes and proof of hidden-label exclusion;
- task-bound ledger/root construction and absence-only preflight behavior;
- focused/adversarial results plus a passing current repo-wide provider-free gate;
- maximum claim, privacy, operation counts, and every nonclaim.

Review outcome is exactly `ACCEPT_V11_CANDIDATE_FOR_SEPARATE_LIVE_GATE` or `REJECT`. Acceptance grants no provider operation and creates no live task, gate receipt, ledger, or artifact root. Any source, contract, dependency, or Git drift requires fresh review.

## Gate 4 — explicit operator/live execution

Only after Gate 3 acceptance may a fresh AK task be created for the exact live proposition. Task creation alone is not provider authority. Its done contract and guardrails must name the exact reviewed candidate, route, maximum one corpus process, zero health probes/retries/fallbacks, task-bound identity `T`, and stop conditions. The operator must explicitly authorize that exact provider operation before a no-replace live-gate receipt is written.

Before entry, preflight re-binds every reviewed byte and proves the derived namespace/root is absent without creating it. Once entry is invoked, the ledger/root is created first and consumed even if a later source, dependency, contract, request, route, receipt, or backend preflight fails. There is no second entry for `T`.

This proposal, AK-4689 completion, Gate 2 implementation, Gate 3 acceptance, route availability, or credential presence cannot substitute for explicit Gate 4 operator authority.

## Gate 5 — independent provider-free verification

After Gate 4 terminalizes, a separate task re-derives contract, source, dependency, ledger, request, receipt-chain, reached-case, scoring, result, privacy, and operation-count facts without provider/network/auth/shared-store activity. It writes verification no-replace and cannot modify terminal bytes, fill missing events, retry a case, create another ledger, or promote the empirical disposition.

Independent review may accept a truthful `effect_indeterminate`, `error`, or `failed` packet as internally valid without accepting the empirical gate.

## Mandatory pause and rejection conditions

Select `pause_empirical_line` immediately if:

- the final proposal or any predecessor/owner/consumer/dependency identity cannot be bound exactly;
- v11 changes a semantic-bearing corpus, label, code, rubric, threshold, privacy, or authority subtree without a new owner decision;
- the public receipt path cannot preserve the exact semantic request bytes;
- any supported v11 path can omit/bypass/reuse a reservation, sink, journal, or one-delegation gate;
- wrapper/gate/effect-pending/transport entry can become acknowledgement;
- a missing/invalid effect-capable chain can avoid `effect_indeterminate` precedence;
- the future task-bound ledger/root construction can collide, be reused, or create state during absence preflight;
- raw, secret, unbounded, tainted, or absolute-path data can be retained;
- fixture results can enter empirical reduction;
- the current provider-free candidate gate is not green or exact review rejects;
- proposal, materialization, review, operator/live, and verification gates are collapsed or one gate synthesizes another;
- explicit operator authority for the exact Gate 4 operation is absent;
- v10 would need to be retried, rewritten, repaired, or reinterpreted.

A pause is a complete truthful disposition. It must not be routed around by broader diagnostics, weaker receipt semantics, a new task number, or a fallback provider path.

## Validation contract for this proposal

Gate 1 validation is documentation- and identity-only:

- strict project-doc reference validation;
- exact task-scope validation over the committed proposal slice;
- Git whitespace/integrity checks;
- independent exact-artifact contract review and adversarial falsification.

No source test, full repo gate, owner runtime import, provider fixture execution, network isolation claim, auth preflight, or live operation is part of AK-4689. The AK-4678 wide-gate non-pass remains disclosed. Unrelated pre-existing working-tree changes are excluded from the proposal and cannot be committed with it.

## Nonclaims

This proposal does not establish or authorize:

- materialized v11 contract bytes, implementation, runner, ledger, root, candidate, review receipt, live gate, verifier, or empirical result;
- provider availability, request completion, semantic quality, exact socket/write behavior, total transport cardinality, provider-internal retries, executed-model identity, or process-wide network isolation;
- owner-main integration, package release, installation, auth readiness, shared-store durability, publication, promotion, release, or activation;
- ROCS conformance, semantic-owner acceptance, or reversal of Decisions 106/107;
- a current repo-wide gate pass;
- mutation, retry, repair, or relabeling of AK-4643/v10.

## Legal next transition

If AK-4689 records **`v11_candidate_designable`**, the only admitted next leaf is a fresh provider-free **Gate 2 candidate-materialization task**. Gates 3–5 remain uncreated and unauthorized. If Gate 2 cannot preserve every identity, semantic byte, receipt rule, task-bound state rule, privacy boundary, test requirement, and gate separation above, it must record `pause_empirical_line` and create no review or live task.

Use [the v11 admission decision](oracle-semantic-analysis-v11-admission-decision.md) for the decision boundary, [the provider outcome receipt design](oracle-semantic-provider-outcome-receipt-design.md) for source-owner fact semantics, [the v10 design](oracle-semantic-analysis-v10-empirical-evaluation-design.md) for immutable predecessor intent, and [Product posture](product-posture.md) for the current frontier.
