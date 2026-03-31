---
summary: "Closed the remaining standardized-Justfile rollout gaps by making the verification recipes keep `uv.lock` clean and by aligning the contributor/docs surface with the standardized command contract."
read_when:
  - "You are resuming AK-646 and need the exact cleanup left after the standardized Justfile hardening pass."
  - "You need to know how DSPx closed the remaining clean-tree validation drift and rollout-documentation gaps."
---

# 2026-03-31 — Close Remaining Clean-Tree Validation Drift and Documentation Gaps

## What I Did
- Followed the atomic-completion protocol for the findings left after `AK-645`.
- Closed the remaining clean-tree validation drift by switching the read-only verification recipes in `Justfile` to `uv run --no-sync`:
  - `just test`
  - `just test-core`
  - `just test-forge`
  - `just replay-provenance-check`
  - `just module-synthesis-quality-check`
  - `just monorepo-check`
- Extended the workflow-contract checker so it now enforces:
  - the standardized Justfile vocabulary in `README.md`, `CONTRIBUTING.md`, and `docs/project/developer_workflow.md`, and
  - target-aware `--no-sync` bodies for the clean-tree validation recipes in `Justfile`.
- Updated `README.md`, `CONTRIBUTING.md`, `docs/project/developer_workflow.md`, and `docs/tech-stack.local.md` so the standardized surface and clean-lockfile validation behavior are discoverable instead of being buried only in `Justfile` or diary prose.
- Expanded `tests/test_workflow_contracts.py` so fixture coverage matches the stronger checker contract and the current repo runtime regression also proves `just replay-provenance-check` and `just monorepo-check` keep `uv.lock` untouched.

## Why It Mattered
- The previous hardening pass fixed the public `doctor`/`run` targets, but `verify-full` still dirtied `uv.lock` because several supposedly read-only validation recipes were still using syncful `uv run`.
- The rollout was also still partially hidden from contributors because only `docs/tech-stack.local.md` mentioned the standardized outer surface.
- This pass closes both the behavioral and documentation gaps so the Justfile rollout is closer to genuinely atomic instead of mostly-complete-but-fragile.

## Validation
- `python3 scripts/check_workflow_contracts.py` ✅
- `uv run -m pytest -q tests/test_workflow_contracts.py` ✅
- `git checkout -- uv.lock && just test` ✅ (`uv.lock` stayed clean)
- `git checkout -- uv.lock && just replay-provenance-check` ✅ (`uv.lock` stayed clean after internal `--no-sync` hardening)
- `git checkout -- uv.lock && just monorepo-check` ✅ (`uv.lock` stayed clean)
- `git checkout -- uv.lock && just verify-full` ✅ (`uv.lock` stayed clean after the no-sync verification path updates)
- `just task-scope-check task_id=646 mode=working-tree` ✅
- `./scripts/ci/smoke.sh` ✅
- `ak task complete 646 --result '{...}'` ✅
- `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅
- `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅
- `ak task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx")) | map({id,title})'` ✅ after completion (empty queue)

## Next
- Wait for operator direction or the next truthful post-`TG23` contract/materialization step before starting another repo-local implementation slice.
