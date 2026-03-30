---
summary: "Made DSPx prefer the workspace contrib dspy-lm-auth checkout for local editable installs and verified the active environment resolves imports from it."
read_when:
  - "You need to know why DSPx should use ~/ai-society/softwareco/contrib/dspy-lm-auth instead of an unrelated upstream clone or stale wheel for local auth-provider work."
  - "You are debugging where `import dspy_lm_auth` is resolving from in the DSPx environment."
---

# 2026-03-29 — Prefer the Contrib dspy-lm-auth Checkout

## What I Did
- Confirmed DSPx imports `dspy_lm_auth` directly in `packages/dspx-core/src/dspx/dspy_lm_auth_lm.py`, so the active environment decides which checkout or wheel is used.
- Verified the pre-fix environment was resolving `dspy_lm_auth` from the virtualenv site-packages copy rather than the workspace contrib repo.
- Added `just link-dspy-lm-auth`, which defaults to `~/ai-society/softwareco/contrib/dspy-lm-auth`, installs that checkout in editable mode, and fails if `import dspy_lm_auth` still resolves elsewhere.
- Documented the contrib-checkout rule in the developer workflow, local tech-stack notes, provider-runtime doc, upstream/contrib workflow doc, and README.
- Tightened the runtime import error message so the provider wrapper now points repo users at `just link-dspy-lm-auth`.
- Added regression coverage for that import-guidance message.
- Ran the helper and confirmed the active DSPx environment now resolves `dspy_lm_auth` from `~/ai-society/softwareco/contrib/dspy-lm-auth/src/dspy_lm_auth/__init__.py`.

## Why It Mattered
- The import itself was not wrong; the unresolved part was which installed package copy Python would load.
- Without a repo-local helper and explicit docs, DSPx could silently use a stale wheel or the wrong checkout even though the source code only says `import dspy_lm_auth`.
- Making the contrib path explicit removes that ambiguity without changing the provider surface or SG2 active slice.

## Validation
- `just link-dspy-lm-auth` ✅
- `uv run python -c "import dspy_lm_auth; print(dspy_lm_auth.__file__)"` ✅ (`/home/tryinget/ai-society/softwareco/contrib/dspy-lm-auth/src/dspy_lm_auth/__init__.py`)
- `uv run -m pytest -q tests/test_provider_v4.py tests/test_workflow_contracts.py` ✅
- `just workflow-contract-check` ✅
- `just task-scope-check task_id=564 mode=working-tree` ✅
- `./scripts/ci/smoke.sh` ✅
- `just verify-full` ✅
- `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅
- `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅

## Next
- Keep `AK-562` as the next active SG2 implementation slice.
- When the local auth-backed provider checkout needs to be reattached, use `just link-dspy-lm-auth` instead of relying on a wheel or an unrelated upstream clone.
