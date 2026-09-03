---
summary: "Foundry jury adapter: closed tolerance for a bare judgment object (Qwen 3.8 via local vLLM) and a truthful reason for the post-failure adapter latch."
read_when:
  - "A foundry comparison-jury juror fails with AdapterParseError although the provider journal shows provider_response_completed."
  - "Later jurors report adapter_session_terminal (formerly adapter_lm_identity_drift) without calling the provider."
type: "diary"
---

# Fix: foundry jury bare judgment tolerance

## Observed

First live local vLLM jury (lineage `misegraph-foundry-local-vllm-5350.DoLQk8`, read-only):
juror 1 `inferred_correctness` completed HTTP 200 / `provider_response_completed`, observed model
`local/Qwen3.8-27B-AEON-NVFP4-FP8`, but DSPy raised `AdapterParseError` ("Expected to find output
fields ... [judgment_json] ... parsed: []"). The model returned the judgment object itself at top
level; Gemini (Copilot) and gpt-5.4 wrap it as `{"judgment_json": ...}`. Jurors 2 and 3 then failed
with `adapter_lm_identity_drift` without any provider call.

## Root causes

1. `FoundryJuryJSONAdapter` inherited `dspy.JSONAdapter.parse`
   (`.venv/.../dspy/adapters/json_adapter.py:168-202`), which keeps only keys named in
   `signature.output_fields`; a bare judgment object has none, so the parse fails. The signature
   desc asks for "exactly one JSON object with exactly six keys", which Qwen followed literally.
2. `program_foundry_gepa_comparison_jury_provider.py` `__call__` (previously line 127) collapsed two
   distinct conditions into one reason: `self._local_terminal or lm is not self._lm` ->
   `adapter_lm_identity_drift`. `_local_terminal` is set (line ~231) when `_call_postprocess`
   raises after a completed provider call, alongside
   `custodian.latch_closed_after_completed_call()`. So the label lied: no LM identity drifted; the
   session had latched closed by design.

## Decision

- Tolerance (A): `judgment_field_text_from_completion` in `program_model_jury_judgment.py`. Strict
  `json.loads` after fence strip; accept only (a) `{"judgment_json": str}` unchanged, (b)
  `{"judgment_json": object}` re-serialized, (c) a bare object whose key set equals `JUDGMENT_KEYS`
  exactly. Everything else returns `None` and DSPy's parser raises as before. `FoundryJuryJSONAdapter.parse`
  applies it only when the signature's sole output field is `judgment_json`. Downstream
  `parse_model_judgment` validation unchanged; prompt text unchanged (semantic request hash stable).
  Replaying the retained Qwen response through the helper yields `supports_review_evidence`.
- Latch (B): intended fail-closed, kept. The custodian already latches
  `local_postprocessing_failed_after_closed_receipt` and would raise `provider_session_terminal`
  anyway; the adapter latch is the inner guard. Only the label changed: `adapter_session_terminal`
  for the latch, `adapter_lm_identity_drift` for a real `lm is not self._lm`. Historical evidence
  JSONs under `docs/project/2026-09-02-*` keep the old label as recorded.

## Tests added

- `tests/test_program_model_jury_judgment.py`: bare accepted, bare+extra rejected, bare-missing
  rejected, wrapped string pass-through, wrapped object serialized, ten non-object/foreign shapes
  rejected, key contract pinned.
- `tests/test_program_foundry_gepa_comparison_jury_provider.py`: end-to-end through
  `_run_juror_model` with the fixture backend for four accepted shapes; four rejected shapes raise
  `AdapterParseError`, latch the custodian once, and the next juror fails `adapter_session_terminal`
  with no second backend request; LM identity drift still reports `adapter_lm_identity_drift`.

## Validation

- `uv run --no-sync pytest -q` over the seven jury test files: 242 passed.
- `ruff check` / `ruff format` on the four touched Python files: clean (one test file reformatted).
- `ty check` on the two touched src modules: clean. `git diff --check`: clean.

Not committed; no network; no AK mutation. Pre-existing uncommitted Copilot-dogfood docs/diary
changes in the tree were left untouched.
