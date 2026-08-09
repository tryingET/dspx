---
summary: "Credential-free S3 custom-LM legacy-bridge probe and terminal unsupported disposition."
read_when:
  - "Before treating DSPy's 3.3 legacy BaseLM bridge as accepted for DSPx."
  - "When planning provider-specific bridge repairs before the canonical S5 transaction."
type: "evidence"
---

# DSPy 3.3 custom-LM legacy-bridge proof

## Status and authority

AK-4722 disposition: **`unsupported_legacy_bridge`**.

This is credential-free compatibility evidence, not a dependency change, provider-quality result, typed-LM migration, release decision, or activation authority. AK owns task/result truth. The exact target is the accepted Gate A lock with DSPy/DSPy-AI `3.3.0`, GEPA `0.1.1`, and lock SHA-256 `3c1a67002a7b2a42afda6ff5bba6e2cb10e164badab5e81620504b05772034a9`.

S5 is blocked. Do not move the canonical dependency/lock transaction to 3.3 until separately scoped provider-bridge repair and proof tasks close the required unsupported boundaries. A passing synchronous stub call cannot waive state, async, history, copy, error, capability, secret, or provider-specific proof.

## Inventory

DSPx has nine DSPy `BaseLM` bridge implementations:

1. `DSpyStubLM`
2. `DspyLMAuthLM`
3. `OpenAICompatibleLM`
4. `OpenRouterLM`
5. `PiRPCLM`
6. `GeminiCLILM`
7. `ClaudeHeadlessLM`
8. `CodexExecLM`
9. `MultiProviderLM`

DSPx-only `LMBase`/`StubLM` implementations remain DTO providers, not upstream DSPy bridge implementations. DSPx `LMRequest` and `LMResponse` remain distinct from DSPy 3.3's similarly named types.

## No-effect probe contract

The probe used only `DSpyStubLM`, fake/local values, import metadata, and inherited BaseLM methods. It made zero provider/model, credential, network, external-tool, shared-store, release, publication, or activation calls. The representative stub is sufficient to falsify acceptance of the shared required bridge contract; it does not classify unexecuted provider-specific transports as passing or failing.

## Exact current baseline — DSPy 3.1.3

Observed under canonical S0:

- prompt call returned `['stub: hello']`;
- message flattening remained synchronous and deterministic;
- DSPy history contained a dictionary entry;
- `copy()` returned a distinct `DSpyStubLM` with reset history;
- `acall()` terminated with `NotImplementedError: Subclasses must implement this method`;
- BaseLM exposed no `dump_state`/`load_state` or 3.3 capability-property surface;
- DSPx request/response identities were distinct from unavailable upstream typed identities, and `generate(DSPx LMRequest)` returned DSPx `LMResponse`.

This preserves the current synchronous rollback baseline. It is not async, streaming, cancellation, or state support.

## Exact target — DSPy 3.3.0

Observed under the retained target lock:

### Supported bounded behavior

- inherited `forward_contract` reported `legacy`;
- prompt and messages calls returned deterministic synchronous outputs;
- a valid upstream typed `dspy.LMRequest` adapted through `BaseLM.__call__` to an upstream `dspy.LMResponse` for the stub;
- DSPx `generate(DSPx LMRequest)` still returned the distinct DSPx `LMResponse`;
- `copy()` returned a distinct stub with reset history;
- upstream capability properties remained conservative: function calling, reasoning, and response schema were false; `supported_params` was empty.

These observations cover the stub only. They do not prove all nine transports, callbacks, timeout normalization, secret handling, or copy isolation of provider-owned mutable containers.

### Terminal falsifiers

- `acall()` terminated with `NotImplementedError`; target-stub async is unsupported. Cancellation was not reached or exercised.
- `dump_state()` emitted generic BaseLM fields including `_dspy_lm_class`, `model`, and `model_type`.
- direct constructor reconstruction failed because `DSpyStubLM.__init__` does not accept `_dspy_lm_class`.
- inherited `load_state()` failed because `DSpyStubLM.__init__` does not accept `model`.
- passing `stream=True` produced a completed synchronous list, not incremental DSPy streaming.

State reconstruction is a required S3 boundary. Its exact target-stub failure alone falsifies `accepted_legacy_bridge`. Target-stub async is observed unsupported. Cancellation was not separately exercised because async fails before an operation can start; it remains an unproved required boundary, not an observed cancellation failure. The stub's `stream=True` call returned one completed synchronous list, so incremental streaming is unsupported for the stub without implying the same empirical result for every provider.

## Probe reproducibility

Both probes imported `DSpyStubLM`, DSPx `LMRequest`/`LMResponse`, `dspy`, and `importlib.metadata`; printed exact DSPy/DSPy-AI versions; then executed prompt/messages calls, `copy()`, `acall()`, DTO identity, and `generate()`. The target probe additionally printed `forward_contract` and capability properties; ran `dump_state()`; attempted `DSpyStubLM(**state)` and inherited `load_state(state)`; submitted a valid typed `dspy.LMRequest`; and called the stub with `stream=True`. Commands used `uv run --frozen --no-sync python` in the canonical S0 checkout and the reconstructed target clone whose lock SHA-256 is recorded above. The bounded observations and exact exception classes/messages are retained in AK-4722 verification evidence; no provider transport was constructed.

## Inspected cross-provider risks requiring separate proof

Bounded source/test inspection found no all-nine exact-version proof for callback lineage, upstream capability properties, provider-owned copy isolation, state reconstruction, DSPy/provider history separation, timeout/cancellation, error normalization, or secrets in state/callback/history. These are gaps, not empirical failures for every provider.

Provider-specific repair tasks should start with one shared bridge contract and one provider at a time. They must not mechanically replace DSPx DTOs with upstream types, invent thread-based async, call completed HTTP/CLI responses incremental streaming, or overstate DSPx tool/JSON capabilities as upstream typed capability support.

## Supported and unsupported matrix

| Boundary | Target-stub observation | All-nine / S3 disposition |
|---|---|---|
| Current 3.1.3 synchronous prompt/messages | supported baseline | provider-specific behavior beyond stub unproved |
| Target 3.3 synchronous prompt/messages | supported bounded observation | all-nine synchronous bridge unproved |
| Target typed DSPy request/response adaptation | supported bounded observation | provider-specific typed adaptation unproved; not typed-LM conversion |
| DSPx DTO identity | distinct types; DSPx `generate()` returned DSPx response | preserved boundary |
| Async | `acall()` raised `NotImplementedError` | unsupported for stub; all-nine unproved; required bridge not accepted |
| Cancellation | not reachable/exercised because stub async did not start | unproved required boundary; not claimed supported |
| Incremental streaming | `stream=True` returned one completed synchronous list | unsupported for stub; all-nine unproved |
| State dump | `dump_state()` succeeded | dump bytes alone do not prove reconstruction |
| Direct state reconstruction | constructor rejected `_dspy_lm_class` | unsupported for stub; terminal S3 falsifier |
| Inherited `load_state` | constructor rejected `model` | unsupported for stub; terminal S3 falsifier |
| Copy | distinct stub and reset history observed | provider-owned mutable-container isolation unproved |
| Capability properties | function calling/reasoning/response schema false; params empty | conservative stub observation; all-nine capability mapping unproved |
| History | ordinary target call used dictionary history; typed request used upstream history entry in a separate probe | callback/provider-history separation unproved |
| Error normalization | exact state and async errors observed | general provider normalization unproved |
| Secret exclusion | no secrets supplied or inspected | state/copy/callback/history redaction unproved |
| Typed-LM conversion | not attempted | later gate only |

## Consequence

The lawful terminal result is `unsupported_legacy_bridge`. S5 and every downstream 3.3-dependent gate remain blocked; no canonical dependency, source, or lock transaction is authorized. S0's exact 3.1.3 wheel/lock/environment remains the supported rollback baseline. S1 and S2 remain accepted compatibility repairs, not permission to ignore S3.
