---
summary: "Complete AK-317 by removing the repo-local rocs_cli compatibility path and switching DSPx onto workspace-core ROCS resolution."
read_when:
  - "You need the implementation record for AK-317."
  - "You are checking why DSPx no longer vendors tools/rocs-cli."
---

# 2026-03-28 — Remove rocs_cli GitLab Baseline Compatibility Path

## What I Did
- Claimed and completed `AK-317`.
- Switched `ontology/manifest.yaml` from legacy `gitlab:` locators to workspace-only `repo:` locators.
- Simplified `scripts/rocs.sh` so DSPx now resolves ROCS from `ROCS_BIN`, workspace core `~/ai-society/core/rocs-cli`, or `PATH` instead of the repo-local vendored copy.
- Deleted the vendored `tools/rocs-cli/` tree and updated the ontology browsing tip to use `./scripts/rocs.sh`.
- Updated `scripts/check_direction_to_execution.py` so the repo’s direction contract can fail closed with an intentionally empty ready queue after `AK-317` instead of requiring a phantom active slice.
- Refreshed the repo source-of-truth artifacts so the operational docs, next-session handoff, task-scope manifest, and AK projection all agree that `AK-317` is done and the repo-scoped ready queue is empty.

## Why It Mattered
- DSPx no longer needs a repo-local ROCS compatibility fork just to keep GitLab baseline-resolution behavior alive.
- Keeping the vendored copy would leave this repo on a stale private path while the workspace ROCS contract has already moved to workspace-only `repo:` resolution.
- Removing the vendored path makes the repo’s ontology/tooling story match the current ai-society ROCS direction instead of silently preserving legacy behavior.

## Patterns
- When shared tooling drops a compatibility mode, migrate repo manifests and wrappers to the shared contract instead of carrying a permanent local fork.
- Keep repo-local launchers thin: prefer `ROCS_BIN`, shared workspace tooling, then `PATH`.
- Update the checked-in handoff/projection files in the same slice as the implementation so AK, docs, and local helpers stay aligned.

## Validation
- `./scripts/rocs.sh --doctor` ✅
- `./scripts/rocs.sh --which` ✅
- `uv run -q python scripts/check_task_scope.py --task-id 317 --mode working-tree` ✅
- `./scripts/ci/smoke.sh` ✅
- `just verify-full` ✅
- `ak task complete 317 ...` ✅
- `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅
- `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅

## Notes
- A direct workspace-core `rocs build --repo . --resolve-refs --clean` still fails against the current `softwareco/ontology` dependency because `co.software.SLO.md` has invalid `ont.relations` frontmatter upstream; this slice stayed repo-scoped and did not patch the foreign ontology repo.

## Next
- Keep the repo idle until AK exposes a new ready slice or the operator redirects the repo to a new SG2 contract/implementation task.
