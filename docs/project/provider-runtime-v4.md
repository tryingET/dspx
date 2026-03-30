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

## Local editable checkout note

When DSPx should use a local editable `dspy-lm-auth` checkout, prefer the workspace contrib repo instead of an unrelated upstream clone:

```bash
just link-dspy-lm-auth
# optional explicit override:
# just link-dspy-lm-auth path=~/ai-society/softwareco/contrib/dspy-lm-auth
```

That helper installs the contrib checkout and verifies `import dspy_lm_auth` resolves from the requested path.

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
