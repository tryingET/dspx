---
summary: "Credential-free implementation evidence for the foundry-only maintained dspy-lm-auth jury custody seam (Codex and GitHub Copilot families)."
read_when:
  - "Using or changing a task-local dspy-lm-auth provider family for foundry GEPA comparison juries."
  - "Checking whether dspy-lm-auth was restored in the generic DSPx provider registry."
type: "evidence"
---

# Foundry dspy-lm-auth jury integration

## Status

AK task 5308 implements the fixed provider-neutral source/test slice. AK task 5322 then completed
one full live three-juror Misegraph Espresso Brownies comparison with `gpt-5.4`, followed by the
existing deterministic adjudicator. Tasks 5328 and 5329 repaired dogfood-discovered quality-contract
and runtime-evidence gaps. A new full lineage under AK task 5327 bound passing source/candidate
behavior and both runtime episodes, but the sole `gpt-5.6-luna` call terminalized as HTTP 400 before
any juror judgment. Neither lineage claims promotion, activation, release, or external authority.

## Boundary

The new provider name is:

```text
foundry-dspy-lm-auth-codex
```

It is a task-local foundry jury runtime, not a `provider_registry` entry. The generic DSPx typed
provider matrix remains `stub` plus `openai-compatible`; legacy `dspy-lm-auth` selection remains
unsupported.

The execution boundary is:

```text
receipt-bound foundry candidate comparison
  -> outer comparison-jury attempt marker
  -> exact maintained-fork source/runtime verification
  -> DSPx-owned DSPyTypedLMAdapter + foundry JSON adapter
  -> provider-neutral dspy-lm-auth CodexBackend
  -> one no-refresh Codex call custodian per selected juror
  -> one private no-replace provider-outcome journal per call
  -> model-jury evidence with closed provider receipts
  -> existing comparison-jury receipt
  -> existing deterministic comparison adjudicator
```

The existing outer no-replay rule is unchanged. An attempt without a terminal comparison-jury
receipt remains blocked; the implementation does not selectively rerun jurors after an
indeterminate provider effect.

## Exact owner and runtime posture

The task-local verifier binds:

- maintained fork commit `755a378757c3f863b0ac3e534a4205729506dbd7`;
- tree `a4630f403b90e89d61b99368ef88581a1924a418`;
- package version `0.1.6.dev0`;
- lock SHA-256 `e7d9eae5753be3fbf5ea4fc8e88380aeefecd74e5dccaf341fe362281d3c6889`;
- reviewed owner module hashes and the current DSPx locked dependency payload identities;
- the exact provider-neutral backend and backend-contract module hashes;
- `CodexBackend` is not a DSPy LM subclass and exposes no endpoint, retry, cache, callback, fallback, tool, or arbitrary-provider controls;
- backend-only package import does not load `dspy_lm_auth.lm`, so `DSPyTypedLMAdapter` remains the sole loaded LM subclass in the DSPx runtime;
- `dspy==3.3.1` and `litellm==1.82.1`;
- Codex `credential_mode=no-refresh`;
- zero retries, `cache=False`, synchronous calls, no fallback, no health probe, and the fixed
  `https://chatgpt.com/backend-api/codex` endpoint.

Each effect-capable call executes a digest-pinned AK binary through an already verified file
descriptor, revalidates the exact DSPx task id and `claimed_by` identity, and requires at least the
provider timeout plus 30 seconds of lease. Retained verification rebinds source and dependency
identity, route, model, logical/process/gate identifiers, semantic request hash, and closed journal
projection. Receipts retain only closed identity/effect facts; prompts, responses, credentials,
headers, URLs, exception text, and credential material are not written to provider-outcome
evidence.

Exact source execution also requires a bytecode-disabled process and an owner checkout without
`__pycache__` or `.pyc` artifacts. A live operator invocation must therefore use a clean exact
checkout and `PYTHONDONTWRITEBYTECODE=1`; AK-5322 used a fresh detached clone of the pinned fork
commit without mutating the maintained checkout.

The task-local runtime is one-shot and process-serialized. A second new jury in a process where
`dspy_lm_auth` is already loaded rejects before writing its outer attempt marker.
All supported model-jury entrypoints share one process-global DSPy configuration slot. The
runtime binding is a private trusted-in-process API boundary, not a sandbox against arbitrary
Python code already executing inside the DSPx process.

## CLI shape

A separately authorized live execution uses the existing command with the task-local provider
inputs:

The claimed execution task must have the exact title
`Execute one receipt-bound foundry comparison jury with dspy-lm-auth Codex`; an ordinary
implementation task, including AK-5308, is rejected as live-call authority.

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --no-sync dspx program-refine \
  jury-foundry-gepa-comparison \
  --receipt <foundry>/gepa-experiment/consumption-receipt.json \
  --provider foundry-dspy-lm-auth-codex \
  --owner-source-root <exact-clean-dspy-lm-auth-root> \
  --execution-task-id <claimed-live-execution-task> \
  --execution-claimant <exact-ak-claimed-by> \
  --codex-model gpt-5.4 \
  --reasoning-effort xhigh \
  --json
```

The command is documented for contract shape only. AK task 5308 did not authorize or perform that
live provider effect.

The reviewed default is the catalog-backed `gpt-5.4`. Preserved one-shot dogfoods recorded four
terminal HTTP 400 results without replay: AK-5315 used unlisted `gpt-5.6-luna`; AK-5318 used
`gpt-5.6-sol` with `json_object`; AK-5320 used `gpt-5.6-sol` with text transport; and AK-5327 used
`gpt-5.6-luna` with text transport after both quality-contract and runtime-evidence repairs. AK-5327 made
exactly one provider call, obtained `remote_http_error_final`, produced zero judgments, and left no
comparison-jury receipt. The retained evidence does not distinguish model availability from request,
endpoint, entitlement, or another provider-side cause of HTTP 400. It does not authorize client
impersonation, an unreviewed transport, or another replay. The results artifact mechanically marks
three jurors failed; only the first called the provider, while the other two are post-terminal uncalled
failures, so its generic rerun recommendation is non-actionable under the no-replay rule. The foundry
adapter keeps DSPy's exact JSON instructions and closed judgment parser while using text transport.

## Misegraph and adjudication

No Misegraph source was changed. The AK-5322 dogfood bound the actual Espresso Brownies `.mise`
source, canonical IR, and rendered text by SHA-256 into two program examples, produced a complete
GEPA execution/consumption comparison, and called all three selected jurors. All provider journals
completed successfully; the three outcomes were `request_more_evidence`.

The existing deterministic foundry comparison adjudicator then recorded `require_review`. It did
not rerun models, select a winner, mutate the candidate, or grant promotion/activation authority.
The self-contained secret-free evidence projection is
`docs/project/2026-09-02-misegraph-foundry-full-dogfood-evidence.json`.

The later AK-5327 lineage used DSPx commit `ba269144...`, the same exact maintained-fork owner
commit, two passing source and candidate examples, descriptor-confined source/candidate runtime
episodes over identical inputs, and a hash-bound comparison. Luna nevertheless ended at HTTP 400
on the first juror. AK evidence `8200` and
`docs/project/2026-09-02-misegraph-foundry-luna-full-dogfood-evidence.json` retain the terminal
secret-free facts. No adjudication was possible because no juror produced a judgment.

AK-5336 copied the selected 18 JSON artifacts needed to re-audit that terminal lineage from
transient `pi-quests` scratch into mode-0700 owner-local DSPx state. The deterministic archive is
`/home/tryinget/.local/state/dspx/misegraph-foundry-dogfood/AK-5327/ak-5327-luna-evidence.tar.zst`
(SHA-256 `25564d9e1317a9bce42dc067d907df82825efe289e0aa20af7b95ff91c0d6c69`). The tracked
custody manifest is `docs/project/2026-09-02-misegraph-foundry-luna-durable-custody.json`.
This improves local audit durability; it is not remote publication, release evidence, or a replacement
for AK evidence `8200`. The historical scratch root was retained and the consumed lineage was not replayed.

## Credential-free verification

The focused tests cover:

- the task-local runtime bypassing `_configure_provider` and the generic registry;
- backend preparation/invocation through the DSPx-owned JSON adapter without constructing `dspy_lm_auth.LM`;
- the formatting provider rejecting any direct typed-adapter invocation before effects;
- one closed provider receipt journal per juror;
- juror order and call-budget custody;
- indeterminate-effect latching and no replay;
- retained source/dependency/route/model/semantic journal binding;
- hash-bound selected-juror identity/status and complete/closed-terminal session disposition;
- shared-slot contention rejection before an attempt marker;
- foundry attempt/request binding;
- pinned AK runtime plus exact claimant/lease validation;
- CLI forwarding of exact owner/task/claimant/model inputs; and
- unchanged generic comparison-jury behavior.

The focused test command is:

```bash
uv run --no-sync pytest -q \
  tests/test_program_model_jury_execution.py \
  tests/test_program_foundry_gepa_comparison_jury.py \
  tests/test_program_foundry_gepa_comparison_jury_provider.py
```

Additional credential-free readback observed:

- an isolated clean local clone of maintained-fork commit `755a378...` passed exact source,
  dependency-runtime, loaded-owner, provider-neutral-backend, and DSPx sole-adapter configuration
  checks without reading a credential or making a provider call;
- the digest-pinned AK reader successfully read AK-5308; the live-call revalidator then rejected
  AK-5308 because it is the implementation task rather than the exact live-execution task kind.

## 2026-09-03: GitHub Copilot provider family (AK-5345)

The task-local seam now carries two reviewed provider families, both outside `provider_registry`:

| | Codex family | GitHub Copilot family |
| --- | --- | --- |
| `--provider` | `foundry-dspy-lm-auth-codex` | `foundry-dspy-lm-auth-github-copilot` |
| auth provider | `codex` | `github-copilot` |
| backend | `dspy_lm_auth.codex_backend.CodexBackend` | `dspy_lm_auth.copilot_backend.GithubCopilotBackend` |
| model rule | `^gpt-[A-Za-z0-9][A-Za-z0-9.-]{0,63}$`, default `gpt-5.4` | `^gemini-[a-z0-9][a-z0-9.-]{0,63}$`, default `gemini-3.7-flash` |
| reasoning effort | `low/medium/high/xhigh`, default `xhigh` | not applicable (`None`; passing one is rejected) |
| request key | `codex_model` | `model` |
| routes | `dspy-lm-auth:codex:{model}` / `openai:{model}:responses` | `dspy-lm-auth:github-copilot:{model}` / `openai:{model}:chat` |
| endpoint origin | `https://chatgpt.com/backend-api/codex` | `https://api.individual.githubcopilot.com` |
| execution task title | `... with dspy-lm-auth Codex` | `... with dspy-lm-auth GitHub Copilot` |
| observed model | strict equality | recorded, not enforced |

Every Codex literal, route, request key, receipt shape, and CLI flag is unchanged; the Codex
constants are now aliases of `CODEX_FAMILY` in
`program_foundry_gepa_comparison_jury_provider_family.py`.

`endpoint_origin_sha256` uses the same derivation as the Oracle semantic v11 endpoint check:
`sha256(b"dspx-oracle-semantic-v11-endpoint-origin-v1\0" + canonical_json({"scheme": "https",
"hostname": <host>}))`. It reproduces the historical Codex constant `7d4b206e...94c8` and yields
`492c0bc03782d6829c9555ed9da0d359510619c2beb561c89505495cb241871d` for the Copilot origin; both
are pinned by test.

The Copilot backend takes chat messages (`system`/`user`/`assistant` only), no reasoning effort,
and no response format. The foundry JSON adapter therefore keeps text transport for both
families: DSPy's JSON instructions stay in the prompt and DSPx parses the judgment locally.

Observed-model rule: Codex evidence keeps the strict `observed_model == requested model` check.
Gemini through Copilot may report a versioned id, so the Copilot family records the closed
provider-reported label as `observed_model` in each call record and retained validation only
requires that record to match the journal; it does not fail on a mismatch. Codex call records are
unchanged (no `observed_model` key), so previously retained Codex evidence still validates.

Owner pins now bind maintained-fork commit `944f081de5abf44960995263355b42d41de38aba`
(tree `264689803386fd3e239542050c1dcaa08ef3839a`, version `0.1.6.dev0`, unchanged lock). The
eight-name `module_sha256` set bound into receipts is fixed by the receipt contract, so the new
fork modules (`_codex_credential`, `codex_request`, `outcome_receipt_chat`,
`copilot_backend_contract`, `_copilot_credential`, `copilot_receipt_transport`,
`copilot_receipt_runtime`, `copilot_backend`) are hash-pinned through `_EXTRA_OWNER_FILES`. The
pin block is regenerated with
`uv run --no-sync python tests/foundry_jury_owner_repin.py --print-pins <fork-root>`.

Loaded-owner rules for both families: the bound backend class must not subclass `dspy.BaseLM`,
and `dspy_lm_auth.lm` must not be loaded.

CLI shape for the Copilot family (contract only; no live call was authorized by AK-5345):

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --no-sync dspx program-refine \
  jury-foundry-gepa-comparison \
  --receipt <foundry>/gepa-experiment/consumption-receipt.json \
  --provider foundry-dspy-lm-auth-github-copilot \
  --owner-source-root <exact-clean-dspy-lm-auth-root> \
  --execution-task-id <claimed-live-execution-task> \
  --execution-claimant <exact-ak-claimed-by> \
  --model gemini-3.7-flash \
  --json
```

`--model` applies to both families (family default when omitted); `--codex-model` remains the
Codex-only alias; `--reasoning-effort` defaults per family.

Known gap outside this task's file scope: `program_model_jury_provider_runtime.py` still restricts
the runtime binding to the single Codex provider name
(`_TASK_LOCAL_PROVIDER_RUNTIME_NAME`), so a live Copilot run through
`build_comparison_model_jury_result` is rejected with "task-local provider runtime binding is
restricted to the foundry provider" until that guard accepts both family names.

The focused test command adds `tests/test_program_foundry_gepa_comparison_jury_copilot.py`.

## 2026-09-03: xAI and local vLLM provider families (AK-5348)

The task-local seam now carries four reviewed provider families, all outside `provider_registry`:

| | xAI family | local vLLM family |
| --- | --- | --- |
| `--provider` | `foundry-dspy-lm-auth-xai` | `foundry-dspy-lm-auth-local-vllm` |
| auth provider | `xai` (Pi OAuth entry, no refresh) | `none` (no credential file is read) |
| backend | `dspy_lm_auth.xai_backend.XaiBackend` | `dspy_lm_auth.local_vllm_backend.LocalVllmBackend` |
| model rule | `^grok-[a-z0-9][a-z0-9.-]{0,63}$`, default `grok-4.6` | `^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$`, default `local/Qwen3.8-27B-AEON-NVFP4-FP8` |
| reasoning effort | not applicable | not applicable |
| request key | `model` | `model` plus `local_vllm_base_url` |
| routes | `dspy-lm-auth:xai:{model}` / `openai:{model}:chat` | `dspy-lm-auth:local-vllm:{model}` / `openai:{model}:chat` |
| endpoint origin | fixed `https://api.x.ai` | `DSPX_LOCAL_VLLM_BASE_URL`, default `http://127.0.0.1:2456/v1` |
| execution task title | `... with dspy-lm-auth xAI` | `... with dspy-lm-auth local vLLM` |
| observed model | recorded, not enforced | recorded, not enforced |

`COPILOT_FAMILY.model_re` is widened to `^(gemini|grok)-[a-z0-9][a-z0-9.-]{0,63}$` (Copilot also
serves `grok-4.6`); the default stays `gemini-3.7-flash`. Codex literals, routes, request keys, and
receipt shapes are unchanged.

Endpoint-origin constants pinned by test:

- xAI, same v11 derivation as before (`{"scheme": "https", "hostname": "api.x.ai"}`):
  `b1cca9c83dc27a51b9887f2a66a651bea19f23ac4d86dccc456fab2141f5e40d`.
- local vLLM default endpoint, loopback derivation over the exact origin including its explicit
  port (`{"scheme": "http", "hostname": "127.0.0.1", "port": 2456}` under the same domain
  prefix): `ba556a06889d35554dd17c01d1aa4f421082aefb8602d915919c4920872eb3bb`.

The local vLLM endpoint is not fixed in code. `execution_request()` resolves it from
`DSPX_LOCAL_VLLM_BASE_URL` (default above), validates it on the DSPx side with the same loopback
contract as the fork (`http` scheme only; host exactly `127.0.0.1`, `localhost`, or `[::1]`;
explicit port 1-65535 other than 80; path exactly `/v1`; no userinfo, query, fragment, whitespace,
or non-ASCII), and retains the validated base URL under `local_vllm_base_url` in the execution
request, attempt marker, and comparison-jury receipt. `family_for_request()` rebinds the family to
that retained value, so retained validation and the runtime binding use the exact origin hash from
the receipt rather than the current environment; a later environment change no longer matches the
retained attempt. Fixed families reject any explicit endpoint. Env-resolved families additionally
record `endpoint_origin` and `endpoint_origin_sha256` in the configured-provider metadata; the
fixed families keep their historical metadata shape, so retained Codex/Copilot evidence still
validates.

Backend construction goes through `FoundryJuryProviderFamily.construct_backend(owner, *,
auth_path=None, endpoint=None)`: fixed families call `backend_type()` (or with `auth_path`), the
local family passes its bound base URL positionally and refuses an `auth_path`. Every backend
instantiation in the provider runtime uses this hook.

Receipt routes are bounded ids (`^[A-Za-z0-9._:-]{1,128}$`), so a served model id containing
`/` is projected with `/` -> `:` in both routes (`dspy-lm-auth:local-vllm:local:Qwen3.8-27B-...`);
`:` is outside every family's model charset, so the projection is injective, and the exact model
stays in the request, metadata, and juror results. `model_allowed()` also rejects a model whose
projected route would exceed the receipt id bound.

Owner pins now bind maintained-fork commit `777388ad9c692b0657e6b6e1d4820b15fcb6641d` (tree
`a564fb0314292c739bebcd4b9362e5b3315974a9`, version `0.1.6.dev0`, unchanged lock). The rewritten
Copilot modules, `outcome_receipt_chat.py`, and `__init__.py` carry new hashes, and the generic
chat modules (`chat_backend.py`, `chat_backend_contract.py`, `chat_backend_runtime.py`,
`chat_backend_transport.py`, `_chat_credential.py`) plus `xai_backend.py` and
`local_vllm_backend.py` are hash-pinned through `_EXTRA_OWNER_FILES`.
`tests/foundry_jury_owner_repin.py` now lists the required reviewed files and refuses to print a
block that lacks one. Because the fork now defines `CopilotBackendMessage/Request/Response` as
aliases of the generic `ChatBackend*` contract types, the Copilot, xAI, and local vLLM families all
bind `dspy_lm_auth.chat_backend_contract` in the loaded-owner check; the loaded-owner rules (exact
backend class and source path, not a `dspy.BaseLM` subclass, `dspy_lm_auth.lm` never loaded) are
tested for all four families. DSPx keeps using the backend's own
`prepared.semantic_request_sha256` and never recomputes it, so the fork's provider-bound semantic
hash is carried through unchanged.

The runtime binding guard in `program_model_jury_provider_runtime.py` already keys off
`TASK_LOCAL_PROVIDER_NAMES`; a credential-free test now proves it accepts all four family names
and still rejects generic provider names.

CLI shape (contract only; no live call was authorized by AK-5348):

```bash
PYTHONDONTWRITEBYTECODE=1 uv run --no-sync dspx program-refine \
  jury-foundry-gepa-comparison \
  --receipt <foundry>/gepa-experiment/consumption-receipt.json \
  --provider foundry-dspy-lm-auth-xai \
  --owner-source-root <exact-clean-dspy-lm-auth-root> \
  --execution-task-id <claimed-live-execution-task> \
  --execution-claimant <exact-ak-claimed-by> \
  --model grok-4.6 \
  --json

DSPX_LOCAL_VLLM_BASE_URL=http://127.0.0.1:2456/v1 \
PYTHONDONTWRITEBYTECODE=1 uv run --no-sync dspx program-refine \
  jury-foundry-gepa-comparison \
  --receipt <foundry>/gepa-experiment/consumption-receipt.json \
  --provider foundry-dspy-lm-auth-local-vllm \
  --owner-source-root <exact-clean-dspy-lm-auth-root> \
  --execution-task-id <claimed-live-execution-task> \
  --execution-claimant <exact-ak-claimed-by> \
  --model local/Qwen3.8-27B-AEON-NVFP4-FP8 \
  --json
```

The focused test command adds `tests/test_program_foundry_gepa_comparison_jury_xai.py` and
`tests/test_program_foundry_gepa_comparison_jury_local_vllm.py`.

## 2026-09-03: first live Copilot jury (AK-5346)

AK task 5346 (done; AK evidence 8246, corrected by 8247) executed the first live receipt-bound
comparison jury through `foundry-dspy-lm-auth-github-copilot` with `gemini-3.7-flash`, owner
commit `777388ad9c692b0657e6b6e1d4820b15fcb6641d`, DSPx commit
`18db08c691db0e4a518d8d895d571eaafb5e6f70`. The lineage under
`misegraph-foundry-copilot-5346.DVXv7O` was built offline (stub provider, fixture-replay Oracle
with a per-run authored fixture entry, `DSPX_REPLAY_FIXTURE_JSON` derived from the intent
examples); the consume step used the operator-run hash-bound GEPA pickle opt-in. Three jurors
judged (2 `supports_review_evidence`, 1 `request_more_evidence`), recommendation
`request_more_evidence`, deterministic adjudication `require_review` / `held_for_local_review`;
all three journals terminate in `provider_response_completed` with HTTP 200, no replay, no
fallback, zero retries. Secret-free projection:
`docs/project/2026-09-03-misegraph-foundry-copilot-full-dogfood-evidence.json`.

## 2026-09-03: bare judgment object tolerance and terminal-latch reason

The first live local vLLM jury (`local/Qwen3.8-27B-AEON-NVFP4-FP8`, lineage
`misegraph-foundry-local-vllm-5350`) completed its first provider call with HTTP 200 and
`provider_response_completed`, but the model returned the six judgment keys as the top-level JSON
object instead of wrapping them under `judgment_json`. DSPy's `JSONAdapter.parse` therefore found
no output field, raised `AdapterParseError`, and the adapter latched the session closed (evidence
`stop_reason: local_postprocessing_failed_after_closed_receipt`); jurors 2 and 3 then failed
without a provider call.

`FoundryJuryJSONAdapter.parse` now applies one closed, deterministic shape tolerance before DSPy's
parser, via `judgment_field_text_from_completion` in `program_model_jury_judgment.py`: the
completion is decoded with strict `json.loads` (fence-stripped; no repair, no substring search) and
is re-wrapped only when it is a single object whose key set equals the judgment contract exactly
(`outcome`, `rationale`, `evidence_strengths`, `concerns`, `improvement_requests`, `confidence`),
or when it is `{"judgment_json": <string | object>}`. Any other shape falls through to DSPy's
parser unchanged. Values are not touched; `parse_model_judgment` still enforces the closed
vocabularies and bounded text. The prompt text is unchanged, so the semantic request hash contract
is unchanged.

The post-terminal behaviour is intended fail-closed and is kept: a completed provider call whose
local post-processing fails latches both the custodian (`local_postprocessing_failed_after_closed_receipt`)
and the adapter, so remaining jurors are not called and nothing is replayed. What changed is the
label: the adapter's own latch now reports `adapter_session_terminal`; `adapter_lm_identity_drift`
is reserved for an actual `dspy.settings.lm` identity mismatch. Earlier retained evidence
(`2026-09-02-foundry-codex-sol*-terminal-failure-evidence.json`) carries the old label for the
same latch and is left as recorded.

## 2026-09-03: first live local vLLM jury (AK-5352)

AK task 5352 (done; AK evidence 8251) executed the first live receipt-bound comparison jury
through `foundry-dspy-lm-auth-local-vllm` with `local/Qwen3.8-27B-AEON-NVFP4-FP8` at endpoint
origin `http://127.0.0.1:2456` (base URL `/v1`), owner commit
`777388ad9c692b0657e6b6e1d4820b15fcb6641d`, DSPx commit
`1c120c3b07b4e9b191089413673d7e64dc95affd`. This lineage ran after the bare-judgment tolerance
fix `caf9a1abb528eb947cb448242ba2699334cec9ce` (an ancestor of that DSPx commit); the preceding
one-shot AK-5350 (evidence 8248, lineage `misegraph-foundry-local-vllm-5350.DoLQk8`) had failed on
exactly that gap after one completed HTTP 200 call and zero judgments.

The lineage under `misegraph-foundry-local-vllm-5352.5V8vH2` was built offline (stub provider,
fixture-replay Oracle with a per-run authored fixture entry, `DSPX_REPLAY_FIXTURE_JSON` derived
from the intent examples); the consume step used the operator-run hash-bound GEPA pickle opt-in
(`optimizer_manifest_sha256`
`0af3fe4127acbcc1d894ff9749ad7cdc183b2001fe7215f758538dad437e0019`). All three provider calls
were loopback-only with no credential (`auth_provider: none`, `credential_mode: no-refresh`), and
all three journals terminate in `provider_response_completed` with HTTP 200, no replay, no
fallback, zero retries. Three jurors judged `supports_review_evidence`, recommendation
`supports_review_evidence_only`, deterministic adjudication `promote_locally` /
`eligible_local_candidate`, reason `all_jurors_support_review_evidence`. `promote_locally` is a
bounded local disposition over the validated jury receipt: it grants no Misegraph acceptance,
release, or activation and selects no winner. Secret-free projection:
`docs/project/2026-09-03-misegraph-foundry-local-vllm-full-dogfood-evidence.json`.

The same day, the xAI one-shot AK-5349 (`grok-4.6`, lineage `misegraph-foundry-xai-5349.QscXoP`,
evidence 8250) ended after one provider call at HTTP 429 (`remote_http_error_final`,
`remote_http_status`; xAI capacity), zero judgments, no replay, no secrets in evidence. A fresh xAI
lineage is staged under AK-5353 and waits for stable capacity.

## 2026-09-03: first jury through preflight and the isolated child (AK-5358)

AK task 5358 (done; AK evidence 8255) executed a receipt-bound comparison jury through
`foundry-dspy-lm-auth-local-vllm` with `local/Qwen3.8-27B-AEON-NVFP4-FP8` (loopback
`http://127.0.0.1:2456`, no credential), owner commit `777388ad9c692b0657e6b6e1d4820b15fcb6641d`,
DSPx commit `1ce51274cb06f510b12b779985b186ab4decd11d`. It is the first live jury of any family
through the pre-marker preflight (`54568ce2`) and the fresh `-I -B` child subprocess (`1ce51274`):
the preflight reported `provider_completion_calls: 0`, catalog membership and a private
destination before the attempt marker, and the child wrote the three provider journals while the
parent validated and wrote results and receipt unchanged. Lineage `misegraph-foundry-local-vllm-5358.CYMSb7`
was built offline as for AK-5352 (stub provider, fixture-replay Oracle with a per-run entry,
operator-run consume with `optimizer_manifest_sha256` `19a8a2be...`). Three jurors judged
`supports_review_evidence`, recommendation `supports_review_evidence_only`, adjudication
`promote_locally` / `eligible_local_candidate`; all journals end in `provider_response_completed`
with HTTP 200, no replay, zero retries. Secret-free projection:
`docs/project/2026-09-03-misegraph-foundry-local-vllm-subprocess-dogfood-evidence.json`.

## 2026-09-03: first jury on an imported Misegraph evidence package (AK-5360)

AK task 5360 (done; AK evidence 8258) is the first jury whose evidence came from a real
`misegraph-evidence-package-v1` through `dspx foundry import-misegraph-evidence` (Phase 2
end-to-end). The package was exported by the committed Misegraph CLI
(`misegraph evidence export examples/espresso-brownies.mise --formats text,svg --deny-warnings`,
`package_sha256` `0be06d8d561751e9be26f43ada7e0c20ee4fbc7982194c7396986add07114905`); the
importer (DSPx `ff4b7af3`) validated it read-only and emitted `import/intent.json`
(`959cec33...`), `inputs.json`, the `dspx-misegraph-evidence-binding-v1` (`ca97a9c1...`) and the
import provenance, with the operator answers file a byte copy of the checked-in fixture
(`ed24fdd6...`). No repo tool emits a quality proposal for an existing intent offline, so the
AK-5346 proposal was copied with `candidate_intent` set to the imported intent and its three
derived hashes recomputed with the repo's own quality-contract helpers (criteria untouched); the
derivation is recorded in the lineage's `commands-run.txt`. The offline lineage
(`misegraph-foundry-imported-vllm.RByYoY`, `optimizer_manifest_sha256` `e837d77b...`) then ran
the local vLLM jury (`local/Qwen3.8-27B-AEON-NVFP4-FP8`, DSPx `9ac6dc26`): three jurors
`supports_review_evidence`, adjudication `promote_locally` / `eligible_local_candidate`, HTTP 200
throughout, no replay. Misegraph's `evidence verify-receipt` wrote the non-deciding
`misegraph-jury-recommendation-v1` record (`review_recommended`, `decision: null`,
`requires_owner_action: true`) at `misegraph/docs/project/evidence/espresso-brownies-0be06d8d5617-jury-recommendation.json`.
Nothing in this loop grants Misegraph acceptance, release, or activation. Secret-free projection:
`docs/project/2026-09-03-misegraph-foundry-imported-package-dogfood-evidence.json`.

## 2026-09-03: first live xAI jury (AK-5361) after two burned one-shots

Two xAI one-shots burned before this run. AK-5349 (failed; evidence 8250, lineage
`misegraph-foundry-xai-5349.QscXoP`, DSPx `1c120c3b`) ended after one call at HTTP 429
(`remote_http_error_final`, `remote_http_status`; grok-4.6 at capacity), zero judgments. AK-5353
(failed; evidence 8256, lineage `misegraph-foundry-xai-5353.jrIysb`, DSPx `1ce51274`) passed the
preflight (catalog listed `grok-4.6`, credential valid) and then hit a 60 s transport read timeout
on the first juror (`outcome_unresolved`, `transport_timeout`); the isolated child exited 1 and
lost its results object, so no `comparison-jury-results.json` was written. DSPx `36444b43`
(AK-5359) fixed both gaps: the child now emits a closed result envelope and retains results on
failure, and `FoundryJuryProviderFamily.default_timeout_seconds` gives xAI 180 s.

AK task 5361 (done; AK evidence 8259) then executed the first live receipt-bound jury through
`foundry-dspy-lm-auth-xai` with `grok-4.6` (`auth_provider: xai`, `credential_mode: no-refresh`,
endpoint origin `https://api.x.ai`, 180 s timeout, no `reasoning_effort` or `response_format`),
owner commit `777388ad...`, DSPx `9ac6dc26`, lineage `misegraph-foundry-xai-5361.ErwrBQ`
(`optimizer_manifest_sha256` `22ebcf07...`). All three calls completed
(`provider_response_completed`, HTTP 200, observed model `grok-4.6`, no replay, zero retries).
Three jurors judged `request_more_evidence` at `medium` confidence with blocking concerns present;
recommendation `request_more_evidence`, deterministic adjudication `require_review` /
`held_for_local_review`, reason `jury_requests_more_evidence`. The credential is not recorded
anywhere in the lineage or the projection. Secret-free projection:
`docs/project/2026-09-03-misegraph-foundry-xai-full-dogfood-evidence.json`.

## 2026-09-04: first fully live Misegraph loop (AK-5365)

AK task 5365 (done; AK evidence 8265) closed the Misegraph foundry loop once with
`provider_evidence_kind: live` at every link. Lineage `misegraph-foundry-honest-5366.RZzphH`
(DSPx `d8348fce` plus the then-uncommitted AK-5366 fix, later `e629be74`; jury and consume at
`2ccfbe65`): the committed Misegraph CLI exported package `0be06d8d5617...`;
`dspx foundry import-misegraph-evidence` ran without `--answers`, so the expected projection
and example answers are package-derived (`answers.origin: package_derived`, binding
`e97f0080...`, intent `6acb0d91...`, cases `render-text` and `check-json`); program-gen and
program-run executed the generated program against the loopback vLLM
`local/Qwen3.8-27B-AEON-NVFP4-FP8` through the typed openai-compatible port (no replay fixture);
the Oracle semantic stage ran the live typed backend (`execution_status: succeeded`,
`fixture_sha256: null`, one recommended experiment, `request_sha256` `548c5028...`); the GEPA
proposal bound the `concept_coverage` metric to the package-derived criterion
`misegraph_recipe_fidelity` (`criteria_sha256` `57e44042...`); `execute-foundry-gepa` completed
with four metric calls and a closed `metric_honesty` block (`wrapper_program_sha256`
`2454e901...`, `source_program_sha256` `ecbb8c7c...`, byte-equal in the optimizer manifest
`8d5701c2...`, the execution receipt and the candidate lineage); the operator-run consume verified
those hashes and re-derived the wrapper; the live jury (owner release 0.1.6, commit `80cc409d`,
`owner_tree` `552f2f66`, preflight then isolated child) made three calls, all
`provider_response_completed` with HTTP 200, no replay, zero retries. Three jurors judged
`supports_review_evidence` at `medium` confidence; recommendation
`supports_review_evidence_only`; deterministic adjudication `promote_locally` /
`eligible_local_candidate`, reason `all_jurors_support_review_evidence` (jury receipt
`634a9fe4...`, adjudication `7745f747...`). Misegraph's `evidence verify-receipt` wrote the
non-deciding live record (`misegraph-jury-recommendation-v1`, policy
`live_evidence_required_v1`, `review_recommended`, `decision: null`,
`requires_owner_action: true`) at
`misegraph/docs/project/evidence/espresso-brownies-0be06d8d5617-jury-recommendation-live.json`
(`9c880c61...`, Misegraph commit `12fd8810`), superseding the stub-lineage record for review.

Caveats recorded in the projection: GEPA proposed no new candidate at the four-call budget
(one candidate retained, nothing accepted, every score 1.0), so the materialized candidate is a
loader wrapper over the unchanged base program and the jury compared the source program's live
evidence to itself; the quality-proposal envelope's `model_execution` is still the AK-5346
injected test double re-bound to the package-derived intent (`stub/misegraph-quality`), the one
remaining hollow link; the comparison carries the non-blocking `differs:answer` signal on both
sides with `needs_more_evidence: true`. Two attempts preceded this run and are bound by path and
sha256: AK-5362's lineage `misegraph-foundry-honest-5362.NtdPDD` was blocked at the Oracle stage
(canonical sidecar indeterminate on a 180 s read timeout; a deliberate 600 s retry sidecar completed
the call but the typed port rejected the vLLM 0.27 reply shape, fixed by AK-5364 `c9a52177`), and
lineage `misegraph-foundry-honest-5365.uMYFWr` completed every stage live but burned at consume,
whose contract rejected an optimizer manifest hashing the generated concept-coverage wrapper
instead of the source program (fixed by AK-5366 `e629be74`). Nothing in this loop grants Misegraph
acceptance, release, or activation. Secret-free projection:
`docs/project/2026-09-04-misegraph-foundry-live-loop-dogfood-evidence.json`.
