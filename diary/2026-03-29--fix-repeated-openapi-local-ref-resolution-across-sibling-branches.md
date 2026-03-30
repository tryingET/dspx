---
summary: "Fixed repeated local OpenAPI schema ref resolution so reused sibling properties and combinator branches no longer collapse into unconstrained schemas under AK-559."
read_when:
  - "You need the 2026-03-29 follow-on validation fix after AK-558."
  - "You are checking why repeated local OpenAPI refs across sibling branches/properties changed."
---

# 2026-03-29 — Fix Repeated OpenAPI Local Ref Resolution Across Sibling Branches

## What I Did
- Created, claimed, and completed `AK-559` as an operator-directed follow-on validation slice after reproducing a residual false-pass case in the new OpenAPI combinator surface.
- Fixed `_resolve_schema()` so repeated local `$ref` usage resolves independently across sibling properties and combinator branches instead of sharing one mutable seen-set across the whole sibling walk.
- Added regressions covering repeated-ref `oneOf` branches and reused sibling property refs so invalid bodies now fail closed while valid bodies still pass.
- Refreshed the OpenAPI docs and repo handoff artifacts to match the current behavior.

## Why It Mattered
- The previous `AK-558` hardening closed `oneOf|anyOf` semantics for ordinary branch refs, but repeated reuse of the same local schema ref across sibling branches or sibling properties could still collapse later siblings into `{}` and silently accept invalid request bodies.
- That left a boundary-validation false-pass in exactly the safety-critical path the nexus slice was supposed to harden.
- Fixing it in the same pass keeps the validation contract coherent instead of leaving a freshly introduced trust gap behind.

## Validation
- `uv run -m pytest -q tests/test_openapi_schema_combinators.py tests/test_openapi_schema_refs_allof.py tests/test_openapi_numeric_bounds.py tests/test_openapi_url_loading.py` ✅
- `uvx ty check packages/dspx-core/src apps/forge/src` ✅
- `just task-scope-check task_id=559 mode=working-tree` ✅
- `./scripts/ci/smoke.sh` ✅
- `just verify-full` ✅
- `ak task complete 559 ...` ✅
- `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅
- `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅
- `ak task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'` ✅ after `AK-559` (`[]`)

## Next
- Re-run the repo-scoped `ak task ready` filter at the next session start.
- If it is still empty, wait for operator direction or a newly frozen SG2 contract before starting another slice.
