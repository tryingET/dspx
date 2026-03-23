---
summary: "Complete AK-266 by adding task-scope attestation to verify-full and hardening module-synthesis receipt invariants/runtime quality telemetry."
read_when:
  - "You are continuing workflow/evidence guardrail work after AK-266."
  - "You need the rationale behind task-scope manifests, semantic receipt checks, or runtime module-quality logging."
---

# 2026-03-23 — Task-Scope Attestation and Receipt Invariants

## What I Did
- Added a task-scope attestation system (`dspx.task_scope` + `scripts/check_task_scope.py`) that can infer the currently claimed AK task, load `governance/task-scopes/AK-<id>.json`, and verify the latest committed slice stays within an attested file set.
- Wired `just task-scope-check` into `just verify-full` so a claimed task now needs an explicit scope manifest before the full validation gate passes.
- Hardened module-synthesis quality semantics by replacing structural-only receipt checks with semantic invariants that verify candidate/workspace/evaluation/ranking/promotion agreement.
- Connected `module_service.run_generate()` to runtime module-quality logging so module telemetry is emitted by real generation runs instead of existing only as CI-built synthetic corpus events.
- Added regression coverage for task-scope manifests, runtime module-quality logging, semantic receipt drift detection, and the repo-hygiene guard against tracked `__pycache__` / `.pyc` / `.backup` artifacts.

## What Surprised Me
- The biggest workflow trap is timing: a scope gate that inspects the latest committed slice is robust against unrelated dirty worktree state, but it also means the strongest attestation signal appears after the slice is committed rather than while files are still half-shaped.
- Receipt drift was easier to produce than expected; you can build payloads that look complete structurally while still pointing the promotion shell at the wrong selected candidate.

## Patterns
- Evidence systems need semantic invariants, not just presence checks.
- If a repo claims task-scoped work, the validation gate should know what file families that task was allowed to touch.
- Telemetry abstractions that are not called by the runtime path are not telemetry yet; they are just CI fixtures.

## Validation
- `uv run -m pytest -q tests/test_task_scope.py tests/test_module_synthesis_quality_runtime.py tests/test_module_synthesis_quality_corpus.py tests/test_module_synthesis_quality_summary.py tests/test_module_synthesis_golden_corpus.py tests/test_module_service.py tests/test_repo_hygiene.py`
- `uv run -q python scripts/build_module_synthesis_quality_log.py`
- `just task-scope-check` (after committing the attested slice)
- `./scripts/ci/smoke.sh`
- `just verify-full`

## Next
- Return to `AK-263` and define the first SG2 evidence-retrieval contract now that verify-full can bind a claimed task to an attested scope and module-quality telemetry has real runtime emitters.
