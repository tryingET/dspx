---
summary: "Diary entry: 2026-04-05 — Land AK-835 TG25 Atomic Hardening Cleanup."
read_when:
  - "You need the historical implementation context captured in this diary entry."
  - "You are reviewing or extending work related to 2026-04-05 — Land AK-835 TG25 Atomic Hardening Cleanup."
type: "diary"
---

# 2026-04-05 — Land AK-835 TG25 Atomic Hardening Cleanup

## Why this slice existed

`AK-834` closed the adversarial NEXUS findings, but `just verify-full` still exposed the remaining bounded `TG25` cleanup slice around config refresh semantics, secret handling, provider/runtime output hygiene, policy bypass observability, registry concurrency, retry boundaries, refine interaction safety, receipt environment hashing, preview bounding, generated-code fail-closed handling, and task-scope claim fallback.

This session isolated that remaining `AK-835` scope, landed the fixes inside the already-attested file set, and restored the full repo validation baseline.

## What landed

- taught `load_config_env()` to refresh previously config-managed env values across repeated loads while preserving explicit overrides, and to reject embedded TOML secrets fail-closed
- sanitized provider/runtime metadata, probe text, benchmark summaries, and error payloads before surfacing them through health/benchmark flows
- added policy bypass audit logging for capability/tool/provider checks
- locked provider and tool registry mutation/read surfaces against concurrent access
- narrowed Pi RPC retry behavior to process/transport failures instead of retrying every exception
- gated interactive refine flows on real prompting availability while preserving test/non-interactive paths
- redacted sensitive env fields before deriving receipt `execution_context.env_hash`
- bounded data preview row counts/value lengths
- hardened generated-code worker result handling to fail closed on missing/invalid result payloads with bounded stderr/stdout previews
- treated unavailable AK claim lookup in unregistered test repos as "no claim" so task-scope inference can still fall back to scope artifacts/HEAD changes
- added targeted regressions in `tests/test_provider_runtime.py` and `tests/test_tg25_atomic_completion.py`, plus focused updates in existing config/refine/receipt tests

## Validation

- `uv run --no-sync -m pytest -q tests/test_task_scope.py tests/test_config_loader.py tests/test_provider_runtime.py tests/test_provider_v4.py tests/test_provider_registry.py tests/test_policy_tools_and_providers.py tests/test_refine_service_memory.py tests/test_run_receipts.py tests/test_pi_rpc_provider_unit.py tests/test_policy_capabilities.py tests/test_policy_capabilities_fs.py tests/test_openapi_dry_run_cli.py tests/test_tg25_atomic_completion.py` ✅
- `./scripts/ak.sh work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅
- `./scripts/ak.sh work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅
- `./scripts/ci/smoke.sh` ✅
- `just task-scope-check task_id=835 mode=working-tree` ✅
- `just verify-full` ✅
- exported `governance/task-scopes/AK-835.snapshot.json` ✅

## Source-of-truth updates

- completed `AK-835` in AK with a result summary
- refreshed `docs/project/operational_goals.md` so the closed hardening wave and next truthful promotion/materialization step are explicit
- refreshed `next_session_prompt.md` to start from the post-`AK-835` clean baseline
- re-exported `governance/work-items.json`

## Next truthful step

Do not reopen `TG25` as an implied cleanup queue. Confirm the repo-scoped ready queue is still empty, then materialize/promote the next bounded `TG26` contract-freezing slice only when AK truth explicitly names it.
