---
summary: "Audit DSPx's existing Justfile against the standardized owned-lane contract and reconcile the missing standard surface with the repo's existing workflow helpers."
read_when:
  - "You are resuming AK-615 and need the exact Justfile rollout changes already made in DSPx."
  - "You need to know how DSPx mapped the standardized owned-lane Justfile surface onto its existing verify/task-scope workflow."
---

# 2026-03-31 — Audit DSPx Justfile Against the Standardized Contract Control Case

## What I Did
- Re-read the owned-lane standardized Justfile contract plus the Python-lane addendum and compared them against DSPx's existing repo-local `Justfile`.
- Confirmed DSPx already had truthful repo-specific helpers for `test`, `build`, `lint`, `fmt`, and the AK-native `verify-*` workflow, but it was still missing the standard owned-lane `help`, `check`, `ci`, `doctor`, and `run` surface.
- Added the missing standardized targets as thin wrappers around existing DSPx behavior instead of rewriting the repo's canonical commands:
  - `just help` -> `just --list`
  - `just check` -> `just verify-fast`
  - `just ci` -> `just verify-full`
  - `just doctor` -> tool/runtime sanity checks plus DSPx/DSPx Forge CLI help probes
  - `just run ...` -> the existing DSPx CLI entrypoint
- Kept `just dev` intentionally omitted because DSPx has multiple long-running helper surfaces but no single truthful dev/watch entrypoint.
- Extended the workflow-contract checker and regression fixture so the standardized surface is now enforced alongside the repo's existing AK-native workflow contract.

## Why It Mattered
- DSPx now matches the standardized owned-lane outer `just` vocabulary without losing the repo's stronger local workflow semantics (`verify-fast`, `verify-full`, task-scope checking, repo-specific helper recipes).
- Operators and agents can now rely on the same top-level `help`/`check`/`ci`/`doctor`/`run` vocabulary here as in the other Justfile-rollout pilot repos.
- The contract is locked into regression coverage so future Justfile drift is less likely to silently remove the standardized surface again.

## Validation
- `python3 scripts/check_workflow_contracts.py` ✅
- `uv run -m pytest -q tests/test_workflow_contracts.py` ✅
- `just help` ✅
- `just doctor` ✅
- `just run tools list` ✅
- `just check` ✅
- `just task-scope-check task_id=615 mode=working-tree` ✅
- `./scripts/ci/smoke.sh` ✅
- `just verify-full` ✅
- `ak task complete 615 --result '{...}'` ✅
- `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅
- `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅
- `ak task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx")) | map({id,title})'` ✅ after completion (empty queue)

## Next
- Wait for operator direction or the next truthful post-`TG23` contract/materialization step before starting another repo-local implementation slice.
