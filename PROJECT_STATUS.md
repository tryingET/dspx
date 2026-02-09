# Project Status

Current working branch: `main`.
Working tree state: dirty (System4D workflow/extension updates + Wave-1 DSPx observability implementation + run artifacts/docs updates).

## Snapshot

- Monorepo split is active and enforced.
  - Core package: `packages/dspx-core/src/dspx`
  - Forge app package: `apps/forge/src/dspx_forge`
- Root `pyproject.toml` is workspace-only:
  - `[tool.uv.workspace] members = ["packages/dspx-core", "apps/forge"]`
- Boundary rule is active and tested:
  - allowed: `apps/* -> core`
  - forbidden: `core -> apps/*` (no `dspx_forge.*` imports from core)
- CI/release are package-aware and split (`core`, `forge`, compat matrix).
- Latest branch commits:
  - `fb6a8c6` (`✅ test(workflow): add router fixture coverage`)
  - `2fa8b32` (`✨ feat(extension): add system4d intake router`)
  - `e1cb0f0` (`✨ feat(workflow): add system4d intake workflow kit`)
  - `22eebe0` (`🚧 chore(prompts): add rfc expert prompt presets`)
  - `72337b3` (`📝 docs(observability): instantiate rfc kickoff drafts`)

## Completed now (branch state)

- System4D workflow kit is in place and exercised:
  - intake + kickoff prompt plumbing
  - extension router + fixtures
  - run artifacts authored through Stage 0..90 for:
    - `docs/subagent-runs/20260208-run-stage-0-intake-interview-for/`
- Canonical DB handling for workflow run was enforced and unblocked:
  - canonical DB remains `mlflow.db`
  - local `mlflow.db` materialized via CLI-generated runs
- Wave-1 DSPx observability implementation landed in working tree:
  - correlation tags in MLflow run tagging (`dspx.run_kind`, `dspx.template_version`, `dspx.output_basename`, `dspx.cache_key`, `dspx.output_hash_prefix`)
  - additive receipt hint helper (`mlflow_hints`) and receipt-writer integration
  - explain diagnostics hardening (`mlflow_context.lookup_mode`, `degrade_reason_codes`, `reason_code_version`)
  - explicit remote lookup flag on explain:
    - `dspx run explain --mlflow-remote-lookup`
  - remote lookup now enforces bounded MLflow HTTP request/retry behavior (timeout budget applied, retries forced to `0`) to avoid long hangs on unreachable remote URIs
- Replay/explain remains local-first and deterministic by default.

## Current runtime / packaging behavior

- Workspace/package flow:
  - install/sync: `uv sync`
  - core CLI: `just dspx ...`
  - forge CLI: `just forge ...`
- Monorepo boundary enforcement:
  - `just monorepo-check`
- MLflow runtime policy:
  - `MLFLOW_ENABLE=1` + unset URI => local `sqlite:///mlflow.db`
  - explicit run start semantics still apply (no implicit run creation on bootstrap)
- Explain behavior:
  - default: local-first explain, optional local MLflow enrichment with `--with-mlflow`
  - remote URI mode: safe default-off remote lookup
  - opt-in bounded remote candidate search with `--mlflow-remote-lookup`
- Receipt contract:
  - centralized helper module: `dspx.run_receipts`
  - v1 receipts emitted for signature gen/refine, module-gen, codegen
  - additive `mlflow_hints` now emitted by those writers

## Latest validation snapshot

Executed on current working tree:
- `uv run -m pytest -q tests -vv -s --maxfail=1 --durations=50` ✅ passing (`196 passed, 4 skipped`)
  - prior hotspot resolved: `tests/test_run_receipts.py::test_run_explain_remote_lookup_flag_graceful` now completes (~3s), no hang
- `pre-commit run --all-files` ✅ passing
- `just monorepo-check` ✅ passing
- `just test` ✅ passing (`196 passed, 4 skipped`)

## Known gaps and immediate risks

- Work is not committed yet; reviewable but broad working-tree delta remains.
- Wave-1 is implemented in-tree but still needs clean commit slicing and upstream handoff progression.
- Remote MLflow lookup is intentionally bounded/heuristic; not a full remote artifact-verification pipeline.
- Replay strictness policy (`warn` vs stricter enforcement modes) still needs explicit governance closure.
- Upstream execution (MLflow + DSPy umbrella issues/PR sequencing) remains next major milestone.

## Canonical docs

- `README.md`
- `docs/MONOREPO_TRANSITION.md`
- `docs/MLFLOW_OBSERVABILITY_PLAN.md`
- `docs/RUN_REPLAY_EXPLAIN.md`
- `docs/SUBAGENT_WORKFLOW.md`
- `PROJECT_STATUS.md`
- `NEXT_STEPS.md`

## Recommended posture

- Keep boundary guardrail strict and continuously tested.
- Keep replay/explain local-first by default; remote behavior explicit opt-in.
- Keep docs synchronized with actual CLI/runtime behavior after each scoped change.
