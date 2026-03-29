---
summary: "Closed residual boundary-hardening regressions across empty allowlists, OpenAPI validation semantics, Forge issue identity/pagination, verify-full wait handling, and task-scope forbidden-path matching under AK-534."
read_when:
  - "You need the rationale behind AK-534 or the regressions it closed."
  - "You are checking why empty URL allowlists, OpenAPI allOf/exclusive-bounds handling, Forge issue references, or verify-full parallel failure capture changed together."
---

# 2026-03-29 — Close Residual Allowlist/OpenAPI/Forge/verify-full Regressions

## What I Did
- Claimed `AK-534` as an operator-directed boundary-hardening/workflow slice after finding the repo-scoped ready queue still empty.
- Made host-allowlist enforcement fail closed on an explicit empty allowlist so URL-backed OpenAPI loads and generic web tools no longer treat `{}` like unrestricted access.
- Preserved `allOf` branch semantics during OpenAPI validation, added OpenAPI 3.1 numeric exclusive-bound support, and covered the new behavior with focused regression tests.
- Stabilized Forge issue managed-block references by emitting `workorder://<workorder_id>/system_definition_card.md` instead of output-root-specific paths, and paginated GitLab issue listing so overlap detection can see all matching issues.
- Fixed `scripts/ci/verify-full.sh` so parallel branch failures preserve the real exit status, and extended task-scope forbidden-path matching to catch root-level `*.pyc` / `*.backup` artifacts.
- Refreshed `docs/OPENAPI_TOOLING.md`, `docs/FORGE.md`, `docs/project/operational_goals.md`, and `next_session_prompt.md` so the source-of-truth docs match the current behavior and handoff state.

## Why It Mattered
- An explicit empty allowlist should be safer than `None`; treating `{}` as allow-all weakened the repo's documented network-boundary contract.
- The previous OpenAPI `allOf` flattening dropped branch-local constraints like `additionalProperties: false`, and the numeric bound checks did not understand OpenAPI 3.1's numeric `exclusiveMinimum` / `exclusiveMaximum` form.
- Forge issue identity should remain stable across output-root changes and should not miss duplicates just because GitLab returns them on later pages.
- `verify-full` needs to report the real failing parallel branch or workflow debugging becomes misleading.
- Task-scope forbidden-path patterns should guard root-level junk files as well as nested ones.

## Validation
- `uv run -m pytest -q tests/test_forge_gitlab_client.py tests/test_forge_mvp.py tests/test_openapi_numeric_bounds.py tests/test_openapi_schema_refs_allof.py tests/test_openapi_url_loading.py tests/test_task_scope.py tests/test_web_tools_allowlist.py tests/test_verify_full.py` ✅
- `just task-scope-check task_id=534 mode=working-tree` ✅
- `./scripts/ci/smoke.sh` ✅
- `just verify-full` ✅
- `ak task complete 534 ...` ✅
- `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅
- `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅
- `ak task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'` ✅ after `AK-534` (`[]`)

## Next
- Re-run the repo-scoped `ak task ready` filter at the next session start.
- If it is still empty, wait for operator direction or a newly frozen SG2 contract before starting another implementation slice.
