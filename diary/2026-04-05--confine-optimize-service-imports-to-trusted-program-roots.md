---
summary: "Diary entry: AK-797 — Confine optimize-service imports to trusted program roots."
read_when:
  - "You need the historical implementation context captured in this diary entry."
  - "You are reviewing or extending work related to AK-797 — Confine optimize-service imports to trusted program roots."
type: "diary"
---

# AK-797 — Confine optimize-service imports to trusted program roots

## Summary
Completed `AK-797` by hardening `packages/dspx-core/src/dspx/services/optimize_service.py` so `_import_program_module()` only loads programs from trusted roots:
- the current working directory,
- the system temp root, and
- any extra roots listed in `DSPX_TRUSTED_PROGRAM_ROOTS`.

## Why
`dspx optimize gepa --program ...` imported arbitrary Python files directly from the supplied path. That was an avoidable trust-boundary gap in the optimizer path.

## Changes
- added `_trusted_program_roots()` and `_require_trusted_program_path()`
- rejected optimize program imports outside the trusted root set
- kept temp-dir based module-gen / optimize flows working by trusting the system temp root
- added regressions covering both rejection and explicit env allowlisting in `tests/test_optimize_gepa_stub.py`
- exported `governance/task-scopes/AK-797.snapshot.json`
- refreshed `governance/work-items.json` after marking the AK task done

## Validation
- `uv run --no-sync -m pytest -q tests/test_optimize_gepa_stub.py` ✅
- `uv run --no-sync -m pytest -q tests/test_provider_v4.py -k optimize_manifest_includes_provider_runtime_metadata` ✅
- `uvx ruff check packages/dspx-core/src/dspx/services/optimize_service.py tests/test_optimize_gepa_stub.py` ✅
- `uvx ty check packages/dspx-core/src/dspx/services/optimize_service.py` ✅
- `just task-scope-check task_id=797 mode=working-tree` ✅
- `./scripts/ci/smoke.sh` ✅
- `just verify-full` ⚠️ fails in the pre-existing `tests/test_task_scope.py` baseline because the global `ak` CLI rejects unregistered temp repos during claimed-task discovery; unrelated to `AK-797`
- `./scripts/ak.sh work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅

## AK truth after completion
- `AK-797` is `done`
- remaining ready queue: `AK-798`, `AK-799`, `AK-800`
