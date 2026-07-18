---
summary: "V4 provider runtime for mixed local/auth-backed DSPx execution."
read_when:
  - "You are wiring new providers into DSPx."
  - "You need the current mixed-provider runtime shape (vLLM local + dspy-lm-auth remote)."
---

# Provider Runtime V4

## Intent

Support a production-grade mixed-provider DSPx workflow:

- local student models via `vllm-local`
- auth-backed remote models via `dspy-lm-auth`
- runtime health checks and benchmarks
- receipt-safe provider metadata for replay/explain
- future auth-backed provider expansion without global `dspy.LM` monkeypatching

## Added provider families

- `dspy-lm-auth`
- `openai-compatible`
- `vllm-local`

## Core design

1. DSPx remains provider-registry-first.
2. `dspy-lm-auth.install()` is **not** used globally.
3. Auth-backed DSPy routing is wrapped inside a DSPx provider class.
4. Local OpenAI-compatible runtimes are exposed explicitly instead of being overloaded onto unrelated providers.
5. Run receipts capture safe provider details, but never secrets.

## New operational commands

- `dspx providers resolve`
- `dspx providers health [--probe]`
- `dspx providers benchmark --provider ...`

## Failure semantics

Registered subprocess/RPC providers fail closed by default. A transport exception,
timeout, failed RPC acknowledgement, or non-zero provider process exit is an error;
its diagnostic text is never treated as model output. Health, smoke, and benchmark
commands therefore report failure and exit non-zero instead of emitting a
success-shaped result.

Legacy soft-failure behavior is available only through explicit compatibility
opt-outs and is unsuitable for production probes or evidence-producing runs:

- `DSPX_PI_STRICT=0`
- `DSPX_CODEX_STRICT=0`
- `DSPX_CLAUDE_STRICT=0`
- `DSPX_GEMINI_STRICT=0`

DSPx classifies failure from provider-owned process/RPC status, typed error markers
set to true, non-empty explicit error fields, and declared failure statuses. Empty
optional error fields and false error markers are not failures. DSPx does not infer
failure from model text; a successful provider may return error-looking prose.

Benchmarks require at least one measured call, and any provider failure makes the
aggregate benchmark unsuccessful and the CLI exit non-zero.

### Multi-provider classification and fallback

`MultiProviderLM` applies the same provider-owned failure membrane to child
`forward`, `generate`, and async `collect` responses before accepting text. Typed
`_dspx_error: true`, non-empty explicit error fields, declared failure statuses,
missing or malformed response envelopes, and empty completions are conclusive
child failures. Error-looking model prose remains valid when those provider-owned
signals are absent.

Sequential and collection strategies may continue after a conclusive child
failure. A timeout is different: invocation may have begun without a determinate
result, so it is classified as indeterminate. Sequential fallback stops,
collection refuses partial output and stops before later children, and a parallel
timeout observed before a valid winner poisons the request. DSPx performs no
fallback replay after that timeout.

The registered `multi` provider uses a positive finite child-provider timeout
default:

```bash
DSPX_MULTI_TIMEOUT=60
```

The default is 60 seconds. A positive finite timeout already configured on a
child is preserved; an unset or non-finite `timeout`/`timeout_s` attribute is
filled from `DSPX_MULTI_TIMEOUT`. Invalid values fail provider construction.
Async readiness remains separately bounded and is capped by this multi-provider
timeout. Direct custom Python providers that expose no timeout contract remain
responsible for their own transport deadline; DSPx does not claim it can safely
cancel arbitrary Python callables.

Aggregate raw metadata is attributed by the actual child result and sanitized
before exposure. Provider authentication and transport remain source-owned by
the child provider; DSPx owns only aggregate classification, fallback policy,
timeout defaults, redaction, and local evidence behavior.

## Local editable checkout note

When DSPx should use a local editable `dspy-lm-auth` checkout, prefer the workspace contrib repo instead of an unrelated upstream clone:

```bash
just link-dspy-lm-auth
# optional explicit override:
# just link-dspy-lm-auth path=~/ai-society/softwareco/contrib/dspy-lm-auth
```

That helper installs the contrib checkout and verifies `import dspy_lm_auth` resolves from the requested path.

## How to prove DSPx is using your Pi auth store

DSPx only uses your Pi/Codex-backed auth when the active route is `dspy-lm-auth`.
That route defaults to `~/.pi/agent/auth.json`, not `~/.pi/auth.json`.

Fast path:

```bash
just show-dspy-lm-auth-route
```

That one command prints:
- the imported `dspy_lm_auth` module path
- the resolved `dspy-lm-auth` runtime config
- the auth-backed health/probe result

Equivalent manual checks:

```bash
just dspx providers resolve --provider dspy-lm-auth --json
```

In the JSON payload, confirm:
- `runtime.provider_family == "dspy-lm-auth"`
- `runtime.auth_storage == "[REDACTED]"`
- `runtime.auth_storage_exists == "[REDACTED]"`
- `runtime.requested_model` is the model you expect

DSPx intentionally does not expose local credential-store paths or existence bits in provider diagnostics. Use the health check below to prove credential usability without publishing local auth topology.

Then prove the auth-backed route can actually use those credentials:

```bash
just dspx providers health --provider dspy-lm-auth --probe --json
```

In the health payload, confirm:
- `checks` includes `auth available for provider=codex` (or your configured auth provider)
- `probe.ok == true`

Interpretation:
- if those checks pass, DSPx is able to use the credentials from the configured auth store for the `dspy-lm-auth` route
- if `DSPX_PROVIDER=vllm-local`, the run is local and does **not** use your Pi auth-backed subscription
- in the mixed optimize profile, the usual split is: student = `vllm-local`, reflection = `dspy-lm-auth`; that means only the reflection path uses the auth-backed route

Run receipts record safe provider details such as `provider` and `requested_model`; credential-store path and existence fields are retained only as redacted markers (`[REDACTED]`) so receipts can identify the route without exposing local auth topology.

## Verified local setup snapshot

The currently verified local/runtime combination is:

- vLLM endpoint: `http://127.0.0.1:1234/v1`
- vLLM model: `Qwen/Qwen3.5-27B`
- auth-backed reflection route: `dspy-lm-auth` with `auth_provider=codex`
- known-good remote model: `codex/gpt-5.4`
- known limitation: `codex/gpt-5.4-nano` is rejected on the active ChatGPT/Codex account route with `The 'gpt-5.4-nano' model is not supported when using Codex with a ChatGPT account.`

## Live verification snapshot (2026-03-22)

Using `DSPX_CONFIG=config.provider-runtime-v4.example.toml`, the mixed-provider profile was live-validated with the operator's real local/auth-backed environment.

### Health probes

- `dspx providers health --provider vllm-local --probe --json`
  - ✅ config and probe passed
  - probe latency: ~736 ms total (`~732 ms` model call)
  - model returned extra reasoning-preface text instead of only `hello`, so the command should be treated as connectivity/runtime validation rather than strict output-format validation
- `dspx providers health --provider dspy-lm-auth --probe --json`
  - ✅ dependency, credentials, and probe passed
  - probe latency: ~4.3 ms total (`~0.8 ms` model call)
  - returned the expected `hello` payload for `codex/gpt-5.4`

### Benchmark snapshot

Command:

```bash
dspx providers benchmark \
  --provider vllm-local \
  --provider dspy-lm-auth \
  --repeats 3 \
  --warmup 1 \
  --json
```

Observed results:

- `vllm-local` (`Qwen/Qwen3.5-27B`)
  - success rate: `1.00`
  - median latency: `639.852 ms`
  - range: `637.161–640.924 ms`
- `dspy-lm-auth` (`codex/gpt-5.4`)
  - success rate: `1.00`
  - median latency: `0.074 ms`
  - range: `0.066–0.102 ms`

Benchmark ranking for this local setup: `dspy-lm-auth`, then `vllm-local`.

### End-to-end optimize smoke (`DSPX-M4-03`)

Command path used for the live smoke:

```bash
TD="$(mktemp -d)"
DSPX_CONFIG=config.provider-runtime-v4.example.toml MLFLOW_ENABLE=0 uv run -q python -m dspx.cli.dspx module-gen \
  --name Student \
  --description "Answer a short question with a short answer" \
  --input question \
  --output answer \
  --template-version simple-v1 \
  --outfile "$TD/student.py"

DSPX_CONFIG=config.provider-runtime-v4.example.toml MLFLOW_ENABLE=0 uv run -q python -m dspx.cli.dspx optimize gepa \
  --program "$TD/student.py" \
  --train examples/gepa_modulegen_train.csv \
  --out "$TD/optimized" \
  --metric contains \
  --max-metric-calls 2 \
  --nrows 3
```

Observed results:

- ✅ optimize completed and wrote `manifest.json`
- ✅ manifest recorded the intended mixed-provider runtime: `student=vllm-local`, `reflection=dspy-lm-auth`
- ⏱️ wall-clock runtime for the 3-row / 2-metric-call smoke was ~61 seconds on the verified local setup
- ⚠️ the local `Qwen/Qwen3.5-27B` student still sometimes wrapped `hello` in extra text, so `contains` was the stable smoke metric while `exact` would have been brittle for this proof
- ⚠️ no valset was provided, so DSPy reused the trainset as valset and emitted the expected overfitting warning; acceptable for this tiny smoke, but not for real optimization runs

Implementation caveat found during the smoke:

- The first live run exposed a CLI ordering bug: `optimize gepa` resolved provider defaults before loading `DSPX_CONFIG`, so `[optimize]` defaults were ignored and the reflection provider fell back to the student provider.
- Fixed in `packages/dspx-core/src/dspx/cli/commands/optimize.py` and pinned with a CLI regression test in `tests/test_provider_v4.py`.
- Result: the mixed-provider smoke can now rely on `[optimize]` defaults from `config.provider-runtime-v4.example.toml` without passing explicit provider flags.

### Known-good / known-bad model notes

- ✅ known-good: `codex/gpt-5.4` via `dspy-lm-auth`
- ❌ known-bad on this account route: `codex/gpt-5.4-nano`
  - reproduced with `DSPX_LM_AUTH_MODEL=codex/gpt-5.4-nano dspx providers health --provider dspy-lm-auth --probe --json`
  - failure: `litellm.BadRequestError: OpenAIException - {"detail":"The 'gpt-5.4-nano' model is not supported when using Codex with a ChatGPT account."}`

## Config sections

```toml
[lm_auth]
model = "codex/gpt-5.4"
auth_provider = "codex"
auth_storage = "~/.pi/agent/auth.json"
timeout_s = 60

[vllm]
api_base = "http://127.0.0.1:1234/v1"
model = "Qwen/Qwen3.5-27B"
timeout_s = 120
json_mode = false

[optimize]
student_provider = "vllm-local"
reflection_provider = "dspy-lm-auth"

[provider]
name = "vllm-local"
```

Reference example: `config.provider-runtime-v4.example.toml`

## Near-term usage pattern

- student: `vllm-local`
- reflection: `dspy-lm-auth`
- optimize defaults can be set via `[optimize]`
- use `dspx providers health --provider vllm-local --probe` to confirm the local endpoint before optimize runs
- use `dspx providers health --provider dspy-lm-auth --probe` to confirm the auth-backed reflection route and current model availability
- routing/fallback: `multi` over these providers when desired
