---
summary: "AK-5348: xAI and loopback local vLLM task-local foundry jury provider families over the dspy-lm-auth generic chat backend; Copilot model rule widened to grok; owner re-pinned to fork 777388a."
read_when:
  - "Adding or re-pinning a task-local dspy-lm-auth provider family for foundry comparison juries."
  - "Checking how the local vLLM endpoint is resolved, validated, and bound into receipts."
type: "diary"
---

# Implementation: foundry jury xAI and local vLLM families

## What changed

- Family module: `XAI_FAMILY` (`foundry-dspy-lm-auth-xai`, fixed `https://api.x.ai`, default
  `grok-4.6`) and `LOCAL_VLLM_FAMILY` (`foundry-dspy-lm-auth-local-vllm`, auth `none`, default
  `local/Qwen3.8-27B-AEON-NVFP4-FP8`, endpoint from `DSPX_LOCAL_VLLM_BASE_URL`, default
  `http://127.0.0.1:2456/v1`). New dataclass fields `endpoint_env` / `endpoint_key`, plus
  `with_endpoint()`, `construct_backend(owner, *, auth_path=None, endpoint=None)`,
  `validate_loopback_endpoint()`, `loopback_endpoint_origin_sha256()`, `family_for_request()`.
  `COPILOT_FAMILY.model_re` now `^(gemini|grok)-...$`; Copilot/xAI/local families bind the
  generic `dspy_lm_auth.chat_backend_contract` types because the fork aliases the Copilot names.
- Runtime: `execution_request(..., endpoint=None)` resolves env/default for env families, records
  `local_vllm_base_url`; `revalidate_execution_request()` passes the retained value back;
  `task_local_family(request)` rebinds the family from the request (result validation and the
  runtime binding use it), so the receipt, not the environment, is the binding source.
- Metadata: env-resolved families add `endpoint_origin` and `endpoint_origin_sha256`; fixed
  families keep the historical shape.
- Provider: `backend = family.construct_backend(owner)` replaces `owner.backend_type()`.
- Routes: receipt route ids forbid `/` and cap at 128 chars, so `_route_model()` projects
  `/` -> `:` (injective; `:` is outside every model charset) and `model_allowed()` rejects a model
  whose projected route would overflow the bound.
- Owner pins: commit `777388ad9c692b0657e6b6e1d4820b15fcb6641d`, tree
  `a564fb0314292c739bebcd4b9362e5b3315974a9`; updated hashes for `__init__.py`,
  `outcome_receipt_chat.py`, the rewritten Copilot modules; new `_EXTRA_OWNER_FILES` entries for
  the generic chat modules, `xai_backend.py`, `local_vllm_backend.py`. `foundry_jury_owner_repin.py`
  gained `REQUIRED_EXTRA_OWNER_FILES` / `missing_required_extra_files()`.
- CLI: `--provider`, `--model`, `--reasoning-effort` help lists the four families and defaults.
- Tests: `tests/test_program_foundry_gepa_comparison_jury_xai.py` (922 lines) and
  `tests/test_program_foundry_gepa_comparison_jury_local_vllm.py` (869 lines); Copilot test
  updated for four names, widened model rule, and new pin coverage.

## Decisions

- Local vLLM origin hash covers `{scheme, hostname, port}` (same domain prefix) so the explicit
  port is bound; the full base URL is additionally retained in the execution request.
- Port 80 is rejected on the DSPx side to match the fork transport's default-port normalization
  without importing httpx.
- Endpoint keys are added to metadata only for env-resolved families so retained AK-5322/5327
  Codex evidence still validates.
- DSPx uses the backend's `prepared.semantic_request_sha256` verbatim (fork now folds the provider
  id into the hash for non-Copilot profiles); nothing is recomputed on the DSPx side.

## Validation

- Focused tests (jury, provider, copilot, xai, local_vllm, model_jury_execution): 207 passed.
- `ruff check` / `ruff format --check` on touched paths: clean; `ty check` on touched src: clean;
  `git diff --check`: clean; `uvx prek run --all-files`: passed.
- `just check` passes workflow/direction/governance checks; `task-scope-check` without an explicit
  task id aborts because AK holds two claimed tasks for this repo (5346, 5348);
  `just task-scope-check task_id=5348 mode=working-tree` reports skip (repo-default scope).

## Out of scope / follow-up

- No live provider call, no AK mutation, no commit.
- `program_foundry_gepa_comparison_jury.py` remains at 628 lines (untouched, still above the
  500 budget from earlier slices).
