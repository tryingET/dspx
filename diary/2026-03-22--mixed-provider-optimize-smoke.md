---
summary: "Diary entry: 2026-03-22 — Mixed-Provider Optimize Smoke."
read_when:
  - "You need the historical implementation context captured in this diary entry."
  - "You are reviewing or extending work related to 2026-03-22 — Mixed-Provider Optimize Smoke."
type: "diary"
---

# 2026-03-22 — Mixed-Provider Optimize Smoke

## What I Did
- Started from `next_session_prompt.md` and executed `DSPX-M4-03`: one live end-to-end `dspx optimize gepa` smoke against the mixed-provider runtime defaults in `config.provider-runtime-v4.example.toml`.
- Re-ran provider probes first to confirm the verified runtime was still available:
  - `vllm-local` (`Qwen/Qwen3.5-27B`) on `http://127.0.0.1:1234/v1`
  - `dspy-lm-auth` (`codex/gpt-5.4`) via the authenticated Codex route
- Used a tiny `module-gen` student plus `examples/gepa_modulegen_train.csv`, then ran `optimize gepa` with `--metric contains --max-metric-calls 2 --nrows 3` and `DSPX_CONFIG=config.provider-runtime-v4.example.toml`.
- The first live optimize run exposed a real bug: `optimize gepa` resolved provider defaults before loading `DSPX_CONFIG`, so the reflection provider silently fell back to the student provider.
- Fixed the ordering bug in `packages/dspx-core/src/dspx/cli/commands/optimize.py` and added a regression test in `tests/test_provider_v4.py` to pin config-driven optimize defaults.
- Re-ran the live smoke and confirmed the output manifest recorded `student=vllm-local` and `reflection=dspy-lm-auth` as intended.
- Updated the README, provider-runtime-v4 docs, roadmap, backlog, and next-session handoff to reflect the completed proof.

## What Surprised Me
- The mixed-provider runtime itself was healthy; the real failure mode was a CLI sequencing bug that only surfaced when the operator relied on config defaults instead of explicit provider flags.
- The local Qwen student still wraps `hello` in extra text often enough that `contains` is the right metric for a tiny connectivity-style optimize smoke, even though the run still completes end-to-end.

## Patterns
- If command defaults depend on config-derived environment variables, load config before resolving any fallback chain; otherwise “defaults” only work for callers who redundantly pass explicit flags.
- For live mixed-provider proofs, record evidence from the output manifest, not just the console logs. The manifest is where the actual student/reflection routing contract becomes auditable.
- Tiny end-to-end optimize smokes should keep the budget low, use a forgiving metric, and document DSPy warnings like train-as-val reuse explicitly so the proof stays honest.

## Crystallization Candidates
- A reusable pattern for config-backed CLIs: normalize explicit flags, load config/env, then resolve dependent defaults, and pin it with a regression test whenever two providers or roles can diverge.
