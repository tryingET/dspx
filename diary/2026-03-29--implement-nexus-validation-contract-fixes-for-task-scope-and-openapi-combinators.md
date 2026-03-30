---
summary: "Implemented the nexus validation-contract slice by making task-scope mode selection deterministic for dirty vs clean repos and by hardening OpenAPI oneOf/anyOf ref resolution and exclusivity semantics."
read_when:
  - "You need the 2026-03-29 nexus implementation details after the deep review."
  - "You are checking why verify-fast/verify-full task-scope mode selection and OpenAPI combinator validation changed together."
---

# 2026-03-29 — Implement Nexus Validation-Contract Fixes for Task-Scope and OpenAPI Combinators

## What I Did
- Created, claimed, and completed `AK-558` as an operator-directed validation-contract slice after the deep-review nexus identified two cross-cutting trust-boundary gaps.
- Made `just task-scope-check` default to `mode="auto"`, so the gate now validates the working tree when the repo is dirty and otherwise validates the committed task slice through `HEAD`.
- Extended `check_task_scope()` and the CLI contract to support `mode="auto"`, updated workflow-contract expectations, and added regressions covering uncommitted slices plus dirty out-of-scope working-tree drift.
- Hardened OpenAPI request-body validation so `_resolve_schema()` resolves local `$ref` values inside `oneOf|anyOf` branches, `oneOf` now enforces exactly one matching branch, and `anyOf` still requires at least one matching branch.
- Added focused OpenAPI combinator regressions and refreshed the workflow/OpenAPI docs plus the repo handoff artifacts.

## Why It Mattered
- The documented workflow treated `just verify-full` as part of active-slice validation, but the default task-scope gate only inspected committed slice history and could miss dirty working-tree drift or fail on a brand-new uncommitted slice.
- DSPx had hardened `allOf`, but `oneOf` still behaved like `anyOf`, and request-body combinator branches containing `$ref` could silently validate anything.
- Both gaps undermined confidence in boundary validation exactly where the repo depended on those rails for safe execution and trustworthy workflow enforcement.

## Validation
- `uv run -m pytest -q tests/test_openapi_schema_combinators.py tests/test_openapi_schema_refs_allof.py tests/test_openapi_numeric_bounds.py tests/test_openapi_url_loading.py tests/test_task_scope.py tests/test_workflow_contracts.py tests/test_direction_to_execution.py` ✅
- `just task-scope-check task_id=558 mode=working-tree` ✅
- `./scripts/ci/smoke.sh` ✅
- `just verify-full` ✅
- `ak task complete 558 ...` ✅
- `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅
- `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅
- `ak task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'` ✅ after `AK-558` (`[]`)

## Next
- Re-run the repo-scoped `ak task ready` filter at the next session start.
- If it is still empty, wait for operator direction or a newly frozen SG2 contract before starting another slice.
