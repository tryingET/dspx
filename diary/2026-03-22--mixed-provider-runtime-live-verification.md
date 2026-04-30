---
summary: "Diary entry: 2026-03-22 — Mixed-Provider Runtime Live Verification."
read_when:
  - "You need the historical implementation context captured in this diary entry."
  - "You are reviewing or extending work related to 2026-03-22 — Mixed-Provider Runtime Live Verification."
type: "diary"
---

# 2026-03-22 — Mixed-Provider Runtime Live Verification

## What I Did
- Used `DSPX_CONFIG=config.provider-runtime-v4.example.toml` to live-resolve and probe the mixed-provider runtime v4 profile.
- Ran `dspx providers health --provider vllm-local --probe --json` against the local vLLM endpoint at `http://127.0.0.1:1234/v1` and confirmed `Qwen/Qwen3.5-27B` responded successfully.
- Ran `dspx providers health --provider dspy-lm-auth --probe --json` and confirmed the auth-backed `codex/gpt-5.4` route was healthy with the current `~/.pi/agent/auth.json` credentials.
- Ran `dspx providers benchmark --provider vllm-local --provider dspy-lm-auth --repeats 3 --warmup 1 --json` and captured the latency snapshot in repo docs.
- Reproduced the known-bad `codex/gpt-5.4-nano` failure through `dspy-lm-auth` and documented the exact ChatGPT/Codex-account limitation.
- Marked `DSPX-M4-02` done and queued `DSPX-M4-03` as the next end-to-end mixed-provider optimize smoke.

## What Surprised Me
- The local vLLM probe passed cleanly but did not honor the single-word prompt literally; it prefixed a reasoning-style response. That means provider-health success should be interpreted as runtime reachability, not strict formatting compliance.
- The `dspy-lm-auth` route responded essentially instantly in this setup, so the local student model remains the obvious latency bottleneck in the mixed profile.

## Patterns
- Mixed-provider validation should explicitly test three layers: config resolution, live health probes, and repeated benchmark calls. Each catches a different failure mode.
- Account-route limitations belong in source-of-truth docs as exact reproduced errors, not just informal warnings, because they determine which model names operators can safely choose.

## Deferred / Next
- `DSPX-M4-03`: run one live `dspx optimize gepa` smoke with `vllm-local` student + `dspy-lm-auth` reflection defaults and document any caveats that only appear in the end-to-end path.
