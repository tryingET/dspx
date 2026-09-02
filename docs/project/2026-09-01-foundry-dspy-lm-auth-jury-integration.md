---
summary: "Credential-free implementation evidence for the foundry-only maintained dspy-lm-auth Codex jury custody seam."
read_when:
  - "Using or changing the task-local dspy-lm-auth provider for foundry GEPA comparison juries."
  - "Checking whether dspy-lm-auth was restored in the generic DSPx provider registry."
type: "evidence"
---

# Foundry dspy-lm-auth jury integration

## Status

AK task 5308 implements the credential-free source and test slice that binds the maintained
`dspy-lm-auth` fork to the existing receipt-bound foundry GEPA comparison jury.

This record does **not** claim a live provider call, successful Codex response, Misegraph recipe
run, promotion, activation, release, or external-authority effect.

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
checkout and `PYTHONDONTWRITEBYTECODE=1`; this implementation pass did not clean or mutate the
maintained fork checkout.

The task-local runtime is one-shot and process-serialized. A second new jury in a process where
`dspy_lm_auth` is already loaded rejects before writing its outer attempt marker.
All supported model-jury entrypoints share one process-global DSPy configuration slot. The
runtime binding is a private trusted-in-process API boundary, not a sandbox against arbitrary
Python code already executing inside the DSPx process.

## CLI shape

A later separately authorized live execution uses the existing command with the task-local
provider inputs:

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
  --codex-model gpt-5.6-sol \
  --reasoning-effort xhigh \
  --json
```

The command is documented for contract shape only. AK task 5308 did not authorize or perform that
live provider effect.

The reviewed default is `gpt-5.6-sol`. A preserved one-shot dogfood under AK-5315 used
`gpt-5.6-luna` and received a terminal HTTP 400 on the first juror; its attempt and receipt evidence
forbid replay. That failed model assumption is not used as a fallback.
AK-5318 then proved `gpt-5.6-sol` also returned terminal HTTP 400 when the backend forced
Responses `json_object`; its evidence is retained at
`docs/project/2026-09-02-foundry-codex-sol-terminal-failure-evidence.json`. The foundry adapter now
keeps DSPy's JSON instructions and closed judgment parser but uses the Codex-compatible text
transport format. Neither failed attempt is retried or treated as a fallback.

## Misegraph and adjudication

No Misegraph source was changed. Misegraph recipe metrics and graph/linter evidence can enter this
boundary only through the already receipt-bound foundry candidate-comparison evidence. This slice
does not claim that a concrete Misegraph recipe has yet produced such a comparison.

No adjudicator implementation was replaced. Successful jury evidence continues to the existing
deterministic foundry comparison adjudicator and retains its local/non-authoritative limits.

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
