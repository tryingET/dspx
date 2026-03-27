---
summary: "Complete AK-367 by eliminating the current repo-wide ty diagnostics without weakening runtime contracts."
read_when:
  - "You are resuming typecheck-debt cleanup after AK-367."
  - "You need the rationale behind the current ty remediation pass."
---

# 2026-03-27 — Eliminate Repo-Wide Ty Diagnostics

## What I Did
- Claimed `AK-367` under operator override to clear the current repo-wide `ty` debt.
- Tightened provider smoke typing in `packages/dspx-core/src/dspx/cli/commands/providers.py` so registry-returned providers are handled through explicit casts instead of object-typed call sites.
- Reworked optional-import boundaries so missing extras no longer create unresolved-import diagnostics:
  - `packages/dspx-core/src/dspx/cli/commands/signature.py`
  - `packages/dspx-core/src/dspx/cli/utils.py`
  - `packages/dspx-core/src/dspx/coordinates/embeddings.py`
- Cleaned `packages/dspx-core/src/dspx/cli/dspx_mermaid2dspy.py` so optional MLflow helpers are tracked through local nullable variables instead of invalid `None` reassignments to imported symbols.
- Narrowed literal typing around GEPA auto-budget selection in:
  - `packages/dspx-core/src/dspx/cli/commands/optimize.py`
  - `packages/dspx-core/src/dspx/services/optimize_service.py`
- Removed typecheck traps in OpenAPI/tooling helpers by iterating over validated `allOf` lists and using `setattr(...)` for dynamic function metadata instead of direct unresolved attribute mutation:
  - `packages/dspx-core/src/dspx/tools/openapi/caller.py`
  - `packages/dspx-core/src/dspx/tools/registry.py`
- Fixed stray corrupted lines left in touched files while normalizing the typing pass.

## Why It Mattered
- `just verify-full` could not reach green because `ty` failed on repo-wide debt outside the recent SG2 slices.
- Several diagnostics were not real logic bugs; they were mismatches between dynamic Python patterns and the contracts `ty` can actually prove.
- Clearing the standing typecheck debt restores repo-level confidence so later slices can rely on `just verify-full` again.

## Patterns
- Use runtime import discovery (`find_spec`, `import_module`) at optional dependency boundaries instead of static imports for extras that are intentionally absent in some environments.
- For dynamic metadata on callables, prefer `setattr(...)` over direct dotted mutation when the callable type is otherwise opaque to static analysis.
- When a static-analysis cleanup touches dynamic code, keep the runtime behavior unchanged and let `ty` be the regression oracle.

## Validation
- `uvx ty check packages/dspx-core/src apps/forge/src` ✅
- `python scripts/check_task_scope.py --task-id 367 --mode working-tree` ✅
- `./scripts/ci/smoke.sh` ✅
- `just verify-full` ✅

## Next
- Return to the repo-scoped ready queue; `AK-356` remains the planned SG2 contract-definition slice unless the operator redirects scope again.
