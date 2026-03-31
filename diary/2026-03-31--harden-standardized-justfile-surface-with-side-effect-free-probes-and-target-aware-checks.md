---
summary: "Hardened DSPx's standardized Justfile surface so public run/doctor probes stay side-effect-free and the workflow-contract checker enforces target behavior instead of raw substring presence."
read_when:
  - "You are resuming AK-645 and need the exact hardening work for the standardized Justfile rollout."
  - "You need to know how DSPx fixed the false-green Justfile contract checks found in deep review."
---

# 2026-03-31 — Harden Standardized Justfile Surface With Side-Effect-Free Probes and Target-Aware Checks

## What I Did
- Followed the deep-review nexus: make the standardized Justfile surface executable and cleanliness-enforced instead of relying on textual presence alone.
- Hardened the public standardized targets in `Justfile`:
  - `just doctor` now probes DSPx/DSPx Forge help through `uv run --no-sync` so it no longer dirties `uv.lock`.
  - `just run` now defaults to CLI help when called without args and also uses `uv run --no-sync`, making the standard one-shot entrypoint truthful and side-effect-free.
- Reworked `scripts/check_workflow_contracts.py` so the checker inspects specific Justfile recipe bodies (`help`, `check`, `ci`, `doctor`, `run`) rather than only scanning for required substrings anywhere in the file.
- Extended `tests/test_workflow_contracts.py` with:
  - an adversarial regression showing a broken `run`/`doctor` recipe can no longer pass just because the required command text appears elsewhere, and
  - a current-repo runtime check that `just doctor` and `just run` leave `uv.lock` untouched while `just run` succeeds with its zero-arg help fallback.
- Updated `docs/tech-stack.local.md` so the standardized `run` contract now mentions the zero-arg help fallback and clean-lockfile behavior.

## Why It Mattered
- The previous rollout had a dangerous false-green shape: the new public targets could mutate tracked state or fail at runtime while the checker still reported success.
- By enforcing the target bodies and their side-effect-free runtime behavior together, the Justfile contract is now closer to an actual API contract rather than a string checklist.
- The same hardening pattern is reusable for future Justfile-rollout follow-ons in other repos.

## Validation
- `python3 scripts/check_workflow_contracts.py` ✅
- `uv run -m pytest -q tests/test_workflow_contracts.py` ✅
- `git checkout -- uv.lock && just doctor` ✅ (`uv.lock` stayed clean)
- `git checkout -- uv.lock && just run` ✅ (`uv.lock` stayed clean; zero-arg help fallback worked)
- `just task-scope-check task_id=645 mode=working-tree` ✅
- `./scripts/ci/smoke.sh` ✅
- `just verify-full` ✅ (then restored incidental pre-existing `uv.lock` drift from other syncful `uv run` validation paths outside the public-target hardening scope)
- `ak task complete 645 --result '{...}'` ✅
- `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅
- `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅
- `ak task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx")) | map({id,title})'` ✅ after completion (empty queue)

## Next
- Wait for operator direction or the next truthful post-`TG23` contract/materialization step before starting another repo-local implementation slice.
