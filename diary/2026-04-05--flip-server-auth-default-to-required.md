---
summary: "Diary entry: AK-799 — Flip server auth default to required."
read_when:
  - "You need the historical implementation context captured in this diary entry."
  - "You are reviewing or extending work related to AK-799 — Flip server auth default to required."
type: "diary"
---

# AK-799 — Flip server auth default to required

## Summary
Completed `AK-799` by changing DSPx server auth startup semantics to fail closed by default and requiring an explicit local-only bypass (`DSPX_AUTH_SKIP_FOR_DEV=1`) when operators intentionally want to run the server without bearer-token configuration.

## Why
The server previously defaulted to unauthenticated startup when no token material was configured. For `TG25`, that left the server boundary too permissive for accidental local-to-shared drift.

## Changes
- changed `AuthConfig.from_env()` so server auth is required by default even when no auth env is present
- added the explicit local-only bypass `DSPX_AUTH_SKIP_FOR_DEV=1`
- kept `DSPX_AUTH_REQUIRED` as an explicit override surface while making fail-closed startup the default
- landed the lazy global ASGI app wrapper in `packages/dspx-core/src/dspx/server/app.py` so module import does not eagerly freeze or fail env-sensitive auth/rate-limit configuration before test or runtime env setup
- updated `docs/SERVER.md` to document the new required-by-default contract and the local-only bypass
- updated server-facing tests so auth-focused tests assert the new default and non-auth server tests opt into the bypass only when intended
- exported `governance/task-scopes/AK-799.snapshot.json`
- refreshed `governance/work-items.json` after task closure

## Validation
- `uvx ruff format packages/dspx-core/src/dspx/server/app.py packages/dspx-core/src/dspx/server/security.py tests/test_server_auth.py tests/test_server_rate_limit.py tests/test_server_api.py tests/test_server_confirm_mutations.py tests/test_server_metrics.py tests/test_server_metrics_negotiation.py tests/test_server_global_app.py` ✅
- `uvx ruff check packages/dspx-core/src/dspx/server/app.py packages/dspx-core/src/dspx/server/security.py tests/test_server_auth.py tests/test_server_rate_limit.py tests/test_server_api.py tests/test_server_confirm_mutations.py tests/test_server_metrics.py tests/test_server_metrics_negotiation.py tests/test_server_global_app.py` ✅
- `uvx ty check packages/dspx-core/src/dspx/server/security.py` ✅
- `uv run --no-sync -m pytest -q tests/test_server_auth.py tests/test_server_rate_limit.py tests/test_server_api.py tests/test_server_confirm_mutations.py tests/test_server_metrics.py tests/test_server_metrics_negotiation.py tests/test_server_global_app.py` ✅
- `./scripts/ak.sh task show 799 -F json` ✅ (`status=done`)
- `./scripts/ak.sh task ready --repo /home/tryinget/ai-society/softwareco/owned/dspx -F json` ✅ (`[800]`)
- `./scripts/ak.sh work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅
- `./scripts/ak.sh work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅
- `just task-scope-check 799 working-tree auto` ⚠️ fails in this shared dirty worktree because many pre-existing unrelated tracked/untracked files still fall outside `AK-799` scope
- `./scripts/ci/smoke.sh` ✅
- `just verify-full` ⚠️ fails because `verify-fast` binds to `AK-799` in the still-dirty shared worktree and the many pre-existing unrelated tracked/untracked files remain outside that task scope

## AK repair note
- `./scripts/ak.sh task complete 799 --result '{...}'` hit the same live foreign-key mutation blocker seen in earlier AK incidents.
- To keep repo truth aligned with the operator-directed slice, I rewrote only task row `799` in `society.v2.db` to repair the broken primary-key lookup, then performed a bounded direct status/result update for that same row after the CLI completion path still failed on the live FK blocker.
- Post-repair AK reads are truthful again for `AK-799`, and the repo-scoped ready queue now starts at `AK-800`.
