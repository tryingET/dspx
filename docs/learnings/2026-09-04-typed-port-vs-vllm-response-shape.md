---
summary: "Learning: the typed openai-compatible port's exact-key response allowlist rejects vLLM 0.27 chat completions, so a live lineage must record failed_before_live_success instead of substituting stubs or fixtures."
read_when:
  - "A live openai-compatible lineage against the loopback vLLM ends in completed_failure with no model text."
  - "You are tempted to close a loop with DSPX_PROVIDER=stub or an authored Oracle fixture entry."
type: "learning"
---

# Typed port vs. vLLM response shape

**Observed (AK-5362, 2026-09-04).** `openai_compatible_provider._validated_response` requires the
assistant message to have exactly `{"role","content"}` and `usage` to have exactly
`{prompt_tokens, completion_tokens, total_tokens}`. vLLM 0.27 returns extra null message keys
(`refusal`, `annotations`, `audio`, `function_call`, `reasoning`) and `usage.prompt_tokens_details`,
so every typed-port call classifies as `completed_failure` even when the model answered.

**Pattern.**

- Label what actually ran (`provider_evidence_kind`); never let a stub or an authored fixture
  entry stand in for a live link without the label saying so.
- Keep the failure terminal and visible: the Oracle live backend returns
  `failed_before_live_success`, the live-marked test `xfail`s with the reason, the lineage's
  `commands-run.txt` records the exact rejection.
- Fix the port through its own owner surface (a reviewed change to the response allowlist that
  ignores null extras), not by loosening validation from a consumer module.

**Also learned.** `dspx program-gen` runs `eval_examples.py` under `DSPX_PROGRAM_HARNESS_TIMEOUT`
(default 60 s); a 27B local model over a ~30 KB evidence prompt needs several minutes, so a live
lineage must raise that timeout explicitly and record it.
