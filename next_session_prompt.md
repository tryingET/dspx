---
summary: "Single-file session handoff to avoid stale status/next-steps docs."
read_when:
  - "At the start of every work session"
  - "When resuming after a pause"
---

# Next Session Prompt

## SESSION TRIGGER (AUTO-START)
Reading this file is authorization to begin immediately.
Do not ask for permission to start.

## ANTI-STALE RULES (HARD)
- Keep this file short and current.
- Keep only the active handoff window (not a history log).
- Move finished session narrative to `diary/`.
- Crystallize durable patterns in `docs/learnings/` and decisions in `docs/adr/` or `docs/decisions/`.
- Keep live execution truth in Agent Kernel; do not treat checked-in backlog mirrors as the live source of truth.
- Keep this file and `docs/project/operational_goals.md` DRY: point at the active slice, do not restate a second roadmap here.

## SOURCE-OF-TRUTH MAP
- Repo operating contract: `AGENTS.md`
- Mission and long-horizon direction: `docs/project/mission.md`, `docs/project/vision.md`
- Strategic/tactical direction: `docs/project/strategic_goals.md`, `docs/project/tactical_goals.md`
- Active operating slices: `docs/project/operational_goals.md`
- Durable architecture decisions: `docs/adr/`
- Live execution truth: `./scripts/ak.sh task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'`
- Planned active/deferred work map: `governance/work-items.json` (checked-in projection/mirror; do not treat as live execution truth)
- Latest completed-slice diary: `diary/2026-04-05--land-ak835-tg25-atomic-hardening-cleanup.md`
- Latest direction refresh artifact: `docs/project/program-synthesis-boundary.md`
- Latest repo-local learning: `docs/learnings/2026-02-28-receipt-v2-phase-c.md`

## SESSION PREFLIGHT (FILL BEFORE EXECUTION)
- Objective (one sentence): Claim `AK-1047` and freeze the first human-governed promotion-eligibility contract for governance-only policy variants without widening live authority.
- Constraints (hard limits): Keep the completed `AK-797`, `AK-798`, `AK-799`, `AK-800`, `AK-834`, `AK-835`, `AK-1085`, `AK-1093`, and `AK-1094` boundaries closed; keep `AK-1047` bounded to the ADR/doc contract surface, the supporting tactical/operational/handoff/projection refresh, and the frozen task-scope snapshot.
- Assumptions (max 3): the runtime spine from `AK-1085` now supplies the contract's evidence vocabulary; `AK-1047` is the single ready repo-scoped slice; the contract must remain governance-only and must not silently widen live ranking/promotion authority.
- Blockers (none or list): none.

## READ-FIRST ALLOWLIST (STARTUP BUDGET)
1. `AGENTS.md`
2. `docs/project/vision.md`
3. `docs/project/strategic_goals.md`
4. `docs/project/tactical_goals.md`
5. `docs/project/operational_goals.md`
6. `docs/adr/README.md`
7. `docs/adr/20260330-synthesis-evidence-governed-policy-evaluation-contract-v1.md`
8. `docs/project/program-synthesis-boundary.md`
9. `docs/project/developer_workflow.md`
10. `governance/work-items.json`

## EXECUTION MODE (ONE SESSION = ONE SLICE)
1. Choose one highest-leverage actionable slice from `governance/work-items.json` unless operator direction overrides it. In this repo, treat that file as a checked-in projection and confirm the live slice against AK before acting.
2. Confirm the repo-scoped ready queue with `./scripts/ak.sh task ready --repo /home/tryinget/ai-society/softwareco/owned/dspx -F json --json-contract normalized | jq '.tasks | map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'`.
3. If the ready queue is empty, do not guess a hidden governance backlog; only materialize the next slice when AK truth and the direction stack justify it. In the current state, AK truth already names `AK-1047` as the active bounded governance slice.
4. Execute at most one operating slice end-to-end.
5. Validate truthfully with:
   - `./scripts/ci/smoke.sh`
   - `just task-scope-check task_id=<AK-ID> mode=working-tree`
   - `just verify-full`
6. Refresh source-of-truth docs/diary/ADR references before commit.

## SESSION CHECKPOINT (UPDATE BEFORE /commit)
- Slice executed: `AK-1094` — activated the next bounded governance-contract wave after the runtime-spine refresh, released `AK-1047` from deferral under explicit operator direction, and refreshed the tactical/operational/handoff stack so the next governance contract is now the single ready repo-scoped slice.
- Outcome: `AK-1094` is complete in AK, `AK-1047` is now ready in the repo-scoped queue, and the direction stack now truthfully points at the human-governed promotion-eligibility contract as the next bounded wave.
- Files changed: `docs/project/tactical_goals.md`, `docs/project/operational_goals.md`, `governance/task-scopes/AK-1094.snapshot.json`, `governance/work-items.json`, `next_session_prompt.md`.
- Validation commands + results: `./scripts/ak.sh task ready --repo /home/tryinget/ai-society/softwareco/owned/dspx -F json --json-contract normalized | jq '.tasks | map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'` ✅ (`AK-1047` only); `./scripts/ak.sh work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅; `./scripts/ci/smoke.sh` ✅; `just task-scope-check task_id=1094 mode=working-tree` ✅; `just verify-full` ✅.
- Source-of-truth updates: completed `AK-1094` in AK with result evidence, released the deferral on `AK-1047`, exported `governance/task-scopes/AK-1094.snapshot.json`, re-exported `governance/work-items.json`, refreshed `docs/project/tactical_goals.md` and `docs/project/operational_goals.md`, and replaced the handoff with the `AK-1047` starting point.
- Next-session starting point: claim `AK-1047`, author the human-governed promotion-eligibility contract, and keep the slice governance-only.

## END-OF-SESSION
Run `/commit` only if the repo is validation-clean and the handoff reflects the real checkpoint; otherwise preserve the truthful handoff and leave commit/closeout for the isolated slice.
