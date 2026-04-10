---
summary: "Complete AK-1047 by freezing the first human-governed promotion-eligibility contract for governance-only policy variants and refreshing the bounded handoff stack."
read_when:
  - "You are resuming work after AK-1047."
  - "You need the rationale for leaving the post-contract implementation slice unmaterialized."
---

# 2026-04-09 — Freeze the Human-Governed Promotion-Eligibility Contract

## What I Did
- Claimed `AK-1047` after re-reading the session handoff, repo workflow contract, and the current SG2/TG26 direction stack.
- Authored `docs/adr/20260409-human-governed-promotion-eligibility-contract-v1.md` to freeze the first human-governed promotion-eligibility contract for governance-only policy variants, grounded in the runtime-spine objects from `AK-1085`.
- Refreshed `docs/project/tactical_goals.md` and `docs/project/operational_goals.md` so `TG26` / `AK-1047` now read as completed truth, while the post-contract implementation slice remains intentionally unmaterialized.
- Updated `docs/adr/README.md`, refreshed `next_session_prompt.md`, completed `AK-1047` in AK, re-exported `governance/work-items.json`, and exported `governance/task-scopes/AK-1047.snapshot.json`.

## Why It Mattered
- `governed_policy_evaluations` already let DSPx say what a named governance-only policy variant would have concluded, but the repo still lacked a dated contract for when those governance receipts plus runtime-spine provenance were strong enough to justify explicit human review.
- Without the contract, repeated governance-only outcomes could drift into de facto authority or force humans to assemble inconsistent review packets by hand.
- Freezing the nomination boundary before materializing any new receipt wave keeps future policy-promotion discussions inspectable without silently widening live authority.

## Candidates Considered

### Selected now
- Freeze the first human-governed promotion-eligibility contract and refresh the bounded direction / handoff surfaces (`AK-1047`).

### Deferred on purpose
- Materialize the first post-contract implementation slice immediately — rejected because `AK-1047` was explicitly bounded to the ADR/doc contract surface, and the repo should not guess the next implementation task just to keep the ready queue non-empty.
- Treat repeated governed policy-evaluation receipts as implicit eligibility — rejected because the whole point of the ADR is to prevent governance-only evidence from silently acquiring live authority.
- Reopen live ranking, pruning, or promotion behavior while freezing the contract — rejected because `TG26` remains governance-only.

## Validation
- `./scripts/ak.sh task ready --repo /home/tryinget/ai-society/softwareco/owned/dspx -F json --json-contract normalized | jq '.tasks | map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'` ✅ before completion (`AK-1047` only)
- `./scripts/ci/smoke.sh` ✅
- `just task-scope-check task_id=1047 mode=working-tree` ✅ (`repo-default scope applies` before the first snapshot export)
- `just verify-full` ✅
- `ak task complete 1047 --result '{...}'` ✅
- `./scripts/ak.sh work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅
- `./scripts/ak.sh work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅
- `ak task scope export 1047 > governance/task-scopes/AK-1047.snapshot.json` ✅
- `./scripts/ak.sh task ready --repo /home/tryinget/ai-society/softwareco/owned/dspx -F json --json-contract normalized | jq '.tasks | map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'` ✅ after completion (`[]`)

## Source-of-Truth Updates
- completed `AK-1047` in AK with a result summary
- refreshed the tactical / operational / handoff docs to reflect that `TG26` is complete and no next repo-scoped slice is pinned yet
- added the new ADR to `docs/adr/README.md`
- re-exported `governance/work-items.json`
- exported `governance/task-scopes/AK-1047.snapshot.json`

## Next Truthful Step
- Re-run the repo-scoped ready queue before starting new work.
- If it is still empty, do not guess the post-contract implementation slice.
- Materialize the first bounded `promotion_eligibility_nominations` receipt wave only when a later direction-to-execution pass or operator instruction explicitly pins it.
