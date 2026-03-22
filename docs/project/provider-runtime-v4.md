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

## Verified local setup snapshot

The currently verified local/runtime combination is:

- vLLM endpoint: `http://127.0.0.1:1234/v1`
- vLLM model: `Qwen/Qwen3.5-27B`
- auth-backed reflection route: `dspy-lm-auth` with `auth_provider=codex`
- known-good remote model: `codex/gpt-5.4`
- known limitation: `codex/gpt-5.4-nano` is currently rejected on the active ChatGPT/Codex account route

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
