---
summary: "AK-4661 candidate design for a provider-free, owner-typed outcome receipt that must land before any Oracle semantic-analysis successor can be proposed."
read_when:
  - "Designing or reviewing lower-layer outcome observation for an Oracle semantic-analysis successor."
  - "Deciding successor_designable versus pause_unattributable after v10."
type: "design"
status: "repo_recorded_candidate_ak_lifecycle_authoritative"
task_id: 4661
---

# Oracle semantic provider outcome receipt design

## Decision candidate

This design proposes the AK-4661 result **`successor_designable`**. Static, provider-free source inspection found a materially stronger observation seam than v10, but also proved that the stock lower layer is unsafe to reuse unchanged. `tryinget-dspy-lm-auth` can pass an exact caller-supplied LiteLLM `HTTPHandler` on the synchronous path and an owner-defined `AsyncHTTPHandler` subclass on the asynchronous path. Both can enforce one receipt-aware HTTPX transport gate and emit a terminal only after the outer call and complete stream validation finish. That owner implementation could distinguish an explicit failure before the transport became effect-capable, an entered but unresolved attempt, an HTTP response from the configured endpoint path, and a locally parsed typed provider-protocol terminal response.

`successor_designable` means only that owner-scoped implementation and fixture falsification are justified. It does **not** mean the interface exists, has owner acceptance, makes a v11 contract admissible, or authorizes any provider operation. AK evidence and result remain lifecycle authority; until AK-4661 records them, this document is a reviewed candidate.

If exact owner implementation cannot preserve this design through sync, async, cancellation, retry, redirect, cache, exception, and receipt-persistence paths, the result falls back to **`pause_unattributable`** and no empirical successor may be created.

## Proposition and authority ceiling

The proposition is:

> Can a provider-free, exact-source-bound receipt let DSPx classify one later semantic request using directly observed facts without upgrading local counters, wrapper entry, or exception text into transport truth?

The maximum positive answer is:

> A reviewed implementation can expose a closed chain of DSPx-local, auth-wrapper, HTTP-transport, configured-endpoint-response, and typed provider-protocol observations. A later separately authorized evaluator could use that chain to distinguish a proven pre-transport failure, an attributable terminal response, and an unresolved possible external effect.

This design does not answer semantic quality, ROCS conformance, shared-store durability, package release, publication, activation, or executed-model identity. It does not reopen Decisions 105–107 or alter AK-4643/v10.

## Bound baseline facts

Provider-free inspection used these baseline identities only to prove design feasibility. They are not implementation or execution bindings.

| Surface | Observed baseline identity | Relevant observed seam |
|---|---|---|
| DSPx | commit `9065c2758a558c34b850f48738d326a33b128aab`; `dspy_lm_auth_lm.py` SHA-256 `f3bdbdcebf185977abcaead9cfa167b60bd7aa4569964aeb6dd60e29be68402a` | DSPx owns the local effect reservation, request binding, receipt durability, consumption, and empirical terminal projection. Current `generate_invocation_count`, `history`, and post-return stream metadata are local bookkeeping, not transport facts. |
| `tryinget-dspy-lm-auth` | version `0.1.5`; commit `d9d8bb7b97764755865741da83cf63613bdf2126`; `lm.py` SHA-256 `10c930b2b00af8acdf8984bfa74281510cec975561e5ed2b4caefa768d14e3a8`; `codex_stream.py` SHA-256 `26baf7a946ccc2a58a9d33872f091ae748ccbc88c46842ff336dbdb28f5a991e` | `_litellm_codex_responses_completion` passes request kwargs into `litellm.responses`; the owner can inject an opt-in receipt-aware client and can observe typed Responses events. Current metadata is available only after successful return and cannot resolve v10. |
| LiteLLM | locked `1.82.1`; wheel SHA-256 `a9ec3fe42eccb1611883caaf8b1bf33c9f4e12163f94c7d1004095b14c379eb2` | `responses` forwards `client=kwargs.get("client")`; `BaseLLMHTTPHandler.response_api_handler` accepts a caller-supplied LiteLLM `HTTPHandler`. The async handler accepts an `AsyncHTTPHandler` object but its stock constructor has no injected-`AsyncClient` argument, so a reviewed subclass/override is required. |
| HTTPX/httpcore | locked HTTPX `0.28.1`, wheel SHA-256 `d909fcccc110f8c7faf814ca82a9a4d816bc5a6dbfea25d6591d6985b8ba59ad`; httpcore `1.0.9`, wheel SHA-256 `2d400746a40668fc9dec9810239072b40b4484b640a8c38fd654a024c7a1bf55` | LiteLLM's sync `HTTPHandler` accepts a caller-supplied `httpx.Client`; owner-defined sync/async handlers can bind HTTPX transport interfaces. Transport-gate or underlying-transport entry still does not prove bytes were written. |
| Lock projection | `dspy-lm-auth/uv.lock` SHA-256 `0d6c79b4b5d70f7a11a879b0bb26dc61dce064fe8dd2ca7e694a9099b43e90e1` | Supplies the inspected dependency identities. A future implementation and consumer must bind shipped wheel/source bytes, not assume this development lock proves an installed runtime. |

Observed source behavior supports the design, not the final implementation. No auth module was imported, no credential or auth-store content was inspected, and no provider, backend, health, network, or shared-store operation was invoked.

### Why the stock lower layer is insufficient

The inspected dependency bytes expose four mandatory owner repairs:

1. LiteLLM's synchronous Responses retry wrapper uses `kwargs.get("num_retries") or litellm.num_retries`; explicit zero can fall through to mutable global retry state. The owner implementation must not rely on `num_retries=0` alone.
2. LiteLLM's stock `AsyncHTTPHandler.post` retries `RemoteProtocolError` and `ConnectError` with a newly created client. That client can bypass an initially injected transport. Receipt mode requires an exact subclass/override that removes or gates this branch before any second effect.
3. post-streaming deployment callbacks can replace yielded chunks. Receipt mode must reject non-empty callback/hook registries before effect and derive terminal protocol facts only from the pre-hook stored completion plus complete stream validation.
4. a parsed `response.completed` can appear before stream exhaustion. It is nonterminal until the stream is exhausted and `dspy-lm-auth` has completed failure/refusal and completed-response validation.

The provider-owner task must fixture-prove these repairs against the exact locked behavior. If it cannot, the required result is `pause_unattributable`; configuration assertions are not a substitute.

## Fact-owner separation

| Layer | Owner | Directly observable facts | Forbidden inference |
|---|---|---|---|
| DSPx local custody | DSPx | task/ledger/case identity, durable reservation, domain-separated reviewed semantic-request hash, adapter entry/return, imported receipt bytes, verifier result | Local counters or missing output proving transport, no transport, retry absence, or provider behavior |
| Inner auth wrapper | `tryinget-dspy-lm-auth` | route resolution, wrapper request acceptance, exact injected-client selection, typed exception class, typed Responses events it consumes | Wrapper entry or `litellm.responses` entry proving network transport |
| HTTP client/transport | Exact reviewed LiteLLM + HTTPX instrumentation | effect-pending marker, instrumented transport entry, attempt ordinal, response headers/status class returned by the configured endpoint path | Transport entry proving socket write, provider processing, exact bytes sent, or no hidden provider retry |
| Configured endpoint response | Receipt producer observing the exact reviewed HTTP response | a response was returned through the instrumented request path; bounded status and endpoint-binding facts | Semantic output, model execution, or total process network cardinality |
| Locally parsed provider-protocol event | Receipt producer after complete stream validation | exact pre-hook parsed event kind, bounded response-id digest, and provider-reported status/model when present | Cryptographic provider attestation, unmodified wire provenance, independently verified executed model, or broad semantic correctness |
| Lifecycle/evidence | AK | task, evidence, direction, result, and successor authorization | A repo document or local result creating lifecycle authority |

The receipt producer remains `tryinget-dspy-lm-auth` for its wrapper and observed lower-layer facts. DSPx supplies owner-private durability and verifies/consumes the bytes; that custody does not make DSPx the source owner of transport semantics.

## Closed receipt family

The proposed family has two artifacts with different owners:

1. `dspy-lm-provider-outcome-receipt-v1` — producer-owned event semantics emitted through an explicit receipt sink;
2. `dspx-provider-outcome-consumption-v1` — DSPx-owned journal binding its reservation, the exact imported producer events, deterministic projection, and verification.

Neither artifact may embed the other owner's stronger conclusion. The consumer re-derives only the projection authorized below.

### Identity envelope

The DSPx sink, not an arbitrary callback payload, constructs every closed canonical envelope from a single-use reserved context. The producer may submit only one allowlisted event enum and its bounded typed scalars. The envelope contains:

- schema name and version;
- producer owner/component and event fact layer;
- task, task-fixed ledger, process, case, logical-request, and transport-gate identifiers fixed by the reservation;
- reviewed contract SHA-256 and `semantic_request_sha256`;
- event sequence and previous-event SHA-256 computed by the sink;
- sync or async mode and contiguous transport-gate ordinal;
- requested route plus separately bound resolved route;
- producer distribution/version, exact wheel or source-tree identity, commit when source-built, concrete handler/transport class hashes, and instrumentation-module SHA-256;
- exact LiteLLM, HTTPX, and httpcore versions and wheel/source hashes;
- exact outer-wrapper, async-handler, HTTPX/httpcore, and declared provider-internal retry postures kept separate;
- cache, hook/callback, redirect, proxy, and endpoint-origin contract postures;
- one allowlisted event kind and only its bounded fields.

`semantic_request_sha256` is exactly SHA-256 over `b"dspx-oracle-semantic-request-v1\\0"` followed by canonical JSON for the reviewed non-secret semantic projection: requested model, instructions, input messages, reasoning, response schema, and storage/stream flags. The projection excludes credentials, API keys, headers, URLs, account/auth fields, transport metadata, and arbitrary kwargs. Both owners must re-derive it from an exact closed schema; if the request is not reviewed non-secret input or either digest disagrees, stop before effect.

The sink binds thread/task-local single-active-request state and rejects nested, concurrent, reentrant, stale, or replayed capabilities before any effect-capable transition. DSPx must also reject an unknown field, missing binding, alternate producer, source/dependency drift, cross-task/case/request event, non-contiguous sequence, broken hash chain, reused gate identity, or mixed sync/async chain. These controls provide exact custody/correlation, not cryptographic attestation against arbitrary same-UID malicious code.

### Event vocabulary

| Event | Fact layer | Required ordering | Maximum claim |
|---|---|---|---|
| `wrapper_request_accepted` | auth wrapper | first producer event | The reviewed wrapper accepted this exact logical request. No external effect claim. |
| `pre_transport_failed` | auth wrapper/lower-layer coordinator | terminal; permitted only before `transport_effect_pending` | This exact instrumented request did not reach its effect-capable underlying transport boundary. It does not prove process-wide network absence. |
| `transport_gate_entered` | receipt-aware sync/async gate | once per gate ordinal; no external delegation yet | The reviewed admission gate was entered. No transport or acknowledgement claim. |
| `retry_blocked_before_transport` | receipt-aware gate | nonterminal logical-request fact for the extra gate ordinal; permitted only when an earlier effect-capable ordinal exists | A repeated client-visible attempt was stopped before delegating that repeated attempt. It cannot close the earlier attempt; exactly one later logical-request terminal remains required. |
| `transport_effect_pending` | receipt-aware gate | allowed only for ordinal 1; durably acknowledged before delegating to the underlying HTTPX transport | External effect is now possible. A later missing terminal is indeterminate. |
| `transport_entered` | underlying HTTPX sync/async transport | after `transport_effect_pending` | The exact underlying transport handler was entered. It does not prove a socket connection, byte write, request completion, or provider acknowledgement. |
| `http_response_observed` | configured endpoint response | nonterminal; after matching `transport_entered` | The instrumented path returned HTTP response headers/status from the bound endpoint path. This is the first lawful lower-layer request acknowledgement, but not model execution proof. |
| `parsed_protocol_event_observed` | local pre-hook protocol parser | nonterminal; after `http_response_observed`; closed event-kind allowlist | The exact local parser observed the named typed Responses event before post-stream callbacks. It is not authenticated provider attestation. |
| `remote_http_error_final` | outer auth-wrapper coordinator | terminal; only after the outer call stops and no later effect-capable attempt was admitted | The final attributable outcome was a bounded HTTP error response. The empirical case is an error, not an open transport outcome. |
| `provider_response_completed` | outer auth-wrapper coordinator | terminal only after complete stream exhaustion, empty callback posture, accumulator checks, and completed-response validation | The exact local parser accepted a provider-protocol completed response with separately identified provider-reported fields. Content may still fail semantic parsing or scoring. |
| `provider_response_failed` | outer auth-wrapper coordinator | terminal only after the outer call stops and a matched typed failure survives complete validation | The locally parsed provider protocol reported a terminal failure. It does not prove no remote side effect. |
| `provider_response_incomplete` | outer auth-wrapper coordinator | terminal only after the outer call stops and a matched typed incomplete event survives complete validation | The locally parsed provider protocol reported terminal incompletion. |
| `outcome_unresolved` | outer producer projection | terminal after `transport_effect_pending` when no stronger terminal is durably observable | External effect remains possible; no retry or later case is permitted. |

`request_acknowledged` is derived only from a valid `http_response_observed` or stronger terminal. It must never be emitted or inferred from wrapper/gate entry, `transport_effect_pending`, `transport_entered`, a call counter, elapsed time, exception text, or receipt absence.

A parsed `response.completed`, failure, incompletion, refusal, or delta event is nonterminal while iteration is still open. A refusal becomes a case error only after the outer coordinator emits a valid terminal. No transport layer may emit `remote_http_error_final`; it may emit only the nonterminal response observation, because retry coordination happens above it.

### Logical-request state machine

```text
ABSENT
  -> wrapper_request_accepted

wrapper_request_accepted
  -> pre_transport_failed                   # terminal
  -> transport_gate_entered(ordinal=1)

transport_gate_entered(ordinal=1)
  -> pre_transport_failed                   # terminal; only before pending/delegation
  -> transport_effect_pending(ordinal=1)    # fsync before delegation

transport_effect_pending(ordinal=1)
  -> transport_entered(ordinal=1)
  -> outcome_unresolved                     # terminal

transport_entered(ordinal=1)
  -> http_response_observed(ordinal=1)       # nonterminal
  -> outcome_unresolved                     # terminal

# Any outer retry reaches the same gate, never an alternate client.
open request
  -> transport_gate_entered(ordinal>1)
  -> retry_blocked_before_transport          # nonterminal; no repeated delegation

http_response_observed | parsed_protocol_event_observed*
  -> remote_http_error_final                 # terminal after outer stop
  -> provider_response_completed             # terminal after exhaustion/validation
  -> provider_response_failed                # terminal after outer stop/validation
  -> provider_response_incomplete            # terminal after outer stop/validation
  -> outcome_unresolved                      # terminal
```

Only ordinal 1 may cross `transport_effect_pending`. The gate blocks every later client-visible retry before underlying delegation. `retry_blocked_before_transport` is not a logical-request terminal: an earlier effect-capable ordinal remains open until exactly one valid outer terminal closes it, and the blocked retry never erases that state.

No other transition is legal. A missing producer terminal after `transport_effect_pending`, process crash, cancellation, timeout, callback/hook presence, receipt failure, sequence gap, source mismatch, contradictory terminal, or bypassed path projects to `effect_indeterminate`. Recovery and verification may reject or accept custody but may not synthesize a producer event.

### Retry, hook, redirect, cache, and alternate-path rules

- The implementation must use one single-use transport gate for every supported sync and async Codex Responses path. The async path requires an exact `AsyncHTTPHandler` subclass/override whose `post`, `create_client`, and fallback behavior cannot manufacture a default client.
- The gate admits at most one underlying transport delegation. Any LiteLLM/DSPy retry call re-enters that same gate and is blocked before repeated effect; fixture proof must cover the synchronous mutable-global retry fallback and the stock async new-client retry branch.
- A later empirical contract still requests zero retries and binds the exact DSPy, LiteLLM outer-wrapper, async-handler, HTTPX/httpcore, and provider-internal postures separately. The admission gate, not configuration alone, enforces one client-visible effect-capable attempt.
- HTTPX/httpcore connection behavior inside the one delegated transport and provider-internal retries remain `not_proven`; the receipt never claims wire-write or provider-operation cardinality.
- Receipt mode requires empty LiteLLM callback/hook registries before effect. Terminal protocol facts come from the pre-hook stored completion only after stream exhaustion and `dspy-lm-auth` validation; a hook or callback appearing later invalidates the chain.
- Exact clients must set `trust_env=False`, `follow_redirects=False`, no cache, and no mock/fake response path. A cache, mock, redirect, proxy, unbound client, alternate transport, or nested/concurrent request fails before effect or leaves an already open effect indeterminate.
- Auth refresh outside the instrumented semantic-request path remains possible and explicitly out of scope. The receipt cannot claim process-wide network isolation or total network-operation cardinality.

## DSPx consumption and terminal projection

DSPx must durably reserve the task/ledger/process/case/logical-request identity and create one single-use, non-reentrant sink capability before wrapper entry. The sink constructs and writes canonical events no-replace, fsyncing each event and the parent directory before acknowledging an event whose order guards an effect. The producer must not delegate to the underlying transport until `transport_effect_pending` persistence succeeds. The sink accepts no caller-supplied sequence, identity envelope, hash-chain value, raw mapping, or exception object.

The consumer then applies this precedence:

1. any open, ambiguous, invalid, bypassed, callback-mutated, or contradictory effect-capable chain -> `effect_indeterminate`;
2. valid `pre_transport_failed`, `remote_http_error_final`, `provider_response_failed`, `provider_response_incomplete`, or a completed response that later fails semantic parsing/schema/retention -> `error`;
3. valid `provider_response_completed` plus a well-formed attributable response that misses a frozen score/content gate -> `failed`;
4. valid attributable completed responses for every frozen case plus every threshold/falsifier -> `passed`.

Artifact integrity remains independent:

```text
artifact_integrity_review = accepted | rejected
empirical_gate = effect_indeterminate | error | failed | passed
provider_outcome_receipt = accepted | rejected
```

A producer terminal must be durable before DSPx closes the local case. If the producer terminal is durable but later DSPx projection fails, verification may derive `error`; it must not reopen an already observed provider terminal. If the producer terminal is absent or invalid after the effect-pending marker, the result remains `effect_indeterminate`.

## Bounded sanitization and retention

The receipt retains enums, booleans, small integers, exact hashes, and tightly bounded identifiers only. Proposed limits are 16 KiB per canonical event, 64 events per logical request, 128 UTF-8 bytes for an observed model label after control-character rejection, and fixed lowercase SHA-256 for provider response identifiers and endpoint origins.

It must not retain:

- prompt, input, generated output, response body, stream delta text, or raw provider event;
- raw exception text, traceback, arbitrary mapping, or unbounded diagnostic;
- URL, path, header, cookie, token, credential, account identifier, auth-store identity/content, or proxy value;
- request payload bytes or any digest outside the exact domain-separated, closed, reviewed non-secret semantic-request projection.

Allowed error information is a closed enum such as `pre_transport_validation`, `transport_timeout`, `transport_exception`, `remote_http_status`, `provider_failed`, `provider_incomplete`, `provider_refusal`, `response_parse`, `receipt_persistence`, or `receipt_invalid`. Exception objects and response errors are tainted: receipt code must never call `str`, `repr`, traceback formatting, mapping serialization, or header/body extraction on them. Exact exception types and integer status classes map directly to enums; unknown types become one fixed `transport_exception_unknown`. Sanitization validates before persistence; failure emits only a fixed `sanitization_rejected` classification when that can be written safely. Existing regex redaction is defense in depth, not source proof.

The receipt is not the semantic output artifact. Any separately authorized evaluator may retain its existing bounded typed analysis under its own privacy contract, but raw/unbounded response retention does not become legal by association.

## Fixture-only falsifier matrix

All implementation proof for this prerequisite is provider-free. Fake transports and typed event fixtures may exercise plumbing but can never contribute to an empirical result.

| Fixture | Required projection |
|---|---|
| Valid explicit failure before effect pending | `error`; request transport false only for this instrumented logical request |
| Gate -> effect pending -> transport entered -> HTTP response -> parsed completed -> stream exhaustion/validation -> outer terminal | attributable locally parsed completed response |
| Completed response with malformed semantic payload | `error`, not indeterminate and not failed |
| Completed response with valid score miss | `failed` |
| HTTP error observed, then outer retry coordinator stops | `remote_http_error_final` and attributable `error`; transport alone cannot terminalize |
| Provider failed or incomplete event | attributable `error` |
| Crash/cancel/timeout after effect pending but before terminal | `effect_indeterminate` |
| Transport entry with DNS/connect/TLS/write exception and no response | `effect_indeterminate`; do not infer no transport |
| Missing effect-pending marker but later transport/response event | reject chain and result |
| Missing terminal after response headers | `effect_indeterminate` |
| Missing, reordered, sequence-gap, or broken-hash event | reject; indeterminate whenever effect may have begun |
| Byte-identical duplicate delivery | idempotent import only; never a second durable event |
| Conflicting duplicate or two terminals | reject and apply indeterminate precedence |
| Cross-task/ledger/process/case/request receipt | reject both the attempted close and attribution |
| Wrong request, contract, producer, module, wheel, dependency, endpoint, or runtime hash | reject before consumption |
| LiteLLM sync outer retry after first effect-capable attempt | same gate records next ordinal and blocks before repeated delegation; earlier attempt remains unresolved unless otherwise closed |
| Stock async `RemoteProtocolError`/`ConnectError` retry branch | owner override prevents new default client; fixture proves no bypass and no repeated delegation |
| Gate ordinal reuse/gap or a second underlying transport delegation | reject implementation and success claim; effect-capable ambiguity is indeterminate |
| Sync and async equivalent trace | byte-equivalent canonical state and terminal projection from separately hash-bound handlers |
| Async cancellation plus late callback | no terminal rewrite; unresolved unless the terminal was durably ordered first |
| Synchronous `KeyboardInterrupt`, `SystemExit`, or other `BaseException` before effect-pending | outer coordinator attempts explicit `pre_transport_failed` without serializing the exception and re-raises; if that terminal is not durable, the incomplete chain supports no no-transport claim |
| Synchronous `BaseException` during underlying delegation or after HTTP headers | `effect_indeterminate` unless a stronger terminal was already durable; re-raise after bounded custody closeout |
| Synchronous `BaseException` during terminal sink persistence | `effect_indeterminate` unless the terminal event and parent-directory sync completed |
| Synchronous `BaseException` after durable terminal acknowledgement | terminal remains immutable; interruption cannot rewrite it |
| Redirect, proxy, cache, mock, fake stream, or alternate client | reject reviewed-route binding |
| Local invocation/history counter without producer receipt | no transport claim; unresolved after local effect reservation |
| Nonterminal provider event without terminal event | `effect_indeterminate` |
| `response.completed` observed before later stream failure/refusal/incompletion | no early terminal; final projection follows complete stream validation |
| Non-empty or mutating LiteLLM callback/hook registry | reject before effect; if discovered after effect pending, `effect_indeterminate` |
| Nested/reentrant/concurrent sink callback | reject before effect or indeterminate if an effect is already open |
| Secret/raw/unknown/nested/oversize/control-character field | reject before persistence; no secret retained |
| Receipt sink failure before guarded effect | abort; no execution fallback; incomplete chain cannot support a no-transport claim |
| Receipt sink failure after guarded effect | `effect_indeterminate` unless a stronger terminal was already durable |
| Verifier attempts provider, modifies terminal bytes, or fills a missing event | reject verification |

## Cross-repo handoff boundary

### `tryinget-dspy-lm-auth` owner task

A fresh task in the owner repo must, without provider execution:

- accept an explicit opt-in outcome-receipt sink; default behavior remains unchanged when absent;
- introduce an exact sync `HTTPHandler` and exact async `AsyncHTTPHandler` subclass/override, both bound to one receipt-aware transport gate; do not claim the stock async constructor accepts an injected `AsyncClient`;
- prevent the stock async new-client retry and block every outer retry at the shared gate before repeated underlying delegation, regardless of mutable LiteLLM global retry state;
- require empty callback/hook registries and emit terminal protocol events only after stream exhaustion and complete `dspy-lm-auth` validation of the pre-hook stored completion;
- ensure sink fsync acknowledgement precedes the one effect-capable transport delegation;
- make the sink construct envelopes from a single-use, thread/task-local non-reentrant reservation and accept only closed enums/scalars;
- bind every gate entry, underlying transport entry, response, parsed event, retry attempt, and outer terminal to one logical request;
- disable or fail closed on cache, mock, proxy, redirect, alternate-client, callback, and bypass paths under receipt mode;
- treat exception/error objects as tainted and retain no prompts, response text, headers, credentials, URLs, paths, exception strings, tracebacks, or raw diagnostics;
- wrap the complete sync and async receipt-mode coordinator in `BaseException`-safe custody: attempt the state-appropriate bounded terminal, never swallow the interruption, and re-raise only after the sink outcome is known;
- prove sync/async/cancellation/retry/late-event/reentrancy/duplicate/reorder/sanitization behavior with fake transports only;
- publish or release nothing unless a separate owner task authorizes it.

The exact owner task must choose and accept the public API/schema names. This DSPx document is the consumer requirement and handoff proposal, not source authority for that repo.

### DSPx consumer task

Only after the owner implementation and exact independent review are accepted may a fresh DSPx task:

- implement the owner-private sink, consumption journal, exact source/dependency verifier, and fail-closed state reducer;
- bind a reviewed `tryinget-dspy-lm-auth` implementation artifact without creating v11;
- prove the complete falsifier matrix using fixtures only;
- retain v10 and all prior ledgers unchanged;
- conclude whether an empirical successor is technically admissible.

No source implementation belongs in AK-4661.

### Independent review requirement

The cross-repo review must answer all of these with exact bytes and fixture evidence:

1. Does every supported sync/async Codex Responses path pass through the exact hash-bound handler and one admission gate?
2. Can the sync mutable-global retry path or async new-client retry branch cause repeated or unobserved delegation?
3. Can any wrapper entry, counter, exception, cache, hook, mock, proxy, redirect, or missing receipt become transport truth?
4. Is effect-pending durability acknowledged before the one permitted underlying transport delegation?
5. Are every gate/transport attempt and outer terminal source/dependency/semantic-request bound and no-replace?
6. Can synchronous `BaseException`, async cancellation, retry, late stream event, post-stream callback, reentrancy, or receipt failure create or rewrite a terminal state?
7. Can any raw/secret/unbounded data or tainted exception serialization reach the retained receipt?
8. Does the maximum claim remain narrower than provider attestation, executed-model proof, wire-write proof, network isolation, and provider-internal retry proof?

Acceptance token for the implemented cross-repo slice should be `ACCEPT_PROVIDER_OUTCOME_RECEIPT_IMPLEMENTATION`; any unresolved material question is `REJECT`.

## Design acceptance and pause gate

AK-4661 may select `successor_designable` only if independent design review accepts that:

- the inspected synchronous client seam and asynchronous subclass/override seam are real and owner-addressable;
- the design explicitly repairs stock retry, callback, completion-order, and async-client bypass hazards before treating the state machine as implementable;
- the state machine adds a direct lower-layer acknowledgement unavailable to v10;
- transport entry remains distinct from request acknowledgement;
- no live operation is needed to implement or falsify the contract;
- exact source/dependency identity, durability, sanitization, and owner handoff are closed;
- a failed owner implementation automatically yields pause rather than a weaker v11.

Select or revert to `pause_unattributable` if the owner rejects the seam, any route bypasses it, receipt persistence cannot guard the effect boundary, provider terminal events cannot be retained in bounded typed form, or implementation needs a live probe to establish basic correctness.

## Legal next transitions

If AK-4661 records `successor_designable`, the next leaf is the fresh provider-owner implementation/review task above. It is **not** v11. After that implementation is accepted, a fresh DSPx fixture-only consumer task is required. Only after both owner slices pass may a separate decision task propose a unique v11 contract, ledger, candidate review, operator/live gate, and provider-free verifier.

If either owner slice fails, record `pause_unattributable`; do not weaken the receipt, broaden diagnostics, or repeat v10.

## Nonclaims and immutable history

This design:

- invokes no provider, model, backend, health probe, network, auth refresh, or shared store;
- creates no v11 benchmark, runner, ledger, artifact root, or live authority;
- changes no source, benchmark, generated artifact, package, script, semantic label, or decision;
- does not prove the proposed interface has been implemented, accepted by its owner, released, or installed;
- does not prove provider transport-call cardinality, provider-internal retries, exact wire bytes, executed model identity, process-wide network isolation, semantic quality, ROCS conformance, publication, release, or activation;
- preserves AK-4643/v10 as immutable, consumed, non-retryable `effect_indeterminate` history and preserves AK-4653 artifact verification separately.

Use [Oracle semantic truth next move](oracle-semantic-truth-next-move.md) for the predecessor selection, [Oracle semantic-analysis v10 design](oracle-semantic-analysis-v10-empirical-evaluation-design.md) for the immutable attempt membrane, [Semantic benchmarks](semantic-benchmarks.md) for empirical history, [Product posture](product-posture.md) for the current frontier, and the [DSPx verdict classification and source-owner contract](dspx-verdict-classification-and-source-owner-contract.md) for proposition/owner routing.
