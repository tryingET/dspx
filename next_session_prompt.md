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
- Live execution truth: `./scripts/ak.sh task ready --repo /home/tryinget/ai-society/softwareco/owned/dspx -F json --json-contract normalized | jq '.tasks | map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'`
- Planned active/deferred work map: `governance/work-items.json` (checked-in projection/mirror; do not treat as live execution truth)
- Latest completed-slice diary: `diary/2026-04-10--materialize-promotion-eligibility-nomination-wave.md`
- Latest contract artifact: `docs/adr/20260409-human-governed-promotion-eligibility-contract-v1.md`
- Latest repo-local learning: `docs/learnings/2026-02-28-receipt-v2-phase-c.md`

## SESSION PREFLIGHT (FILL BEFORE EXECUTION)
- Objective (one sentence): Claim `AK-1102` and emit the first promotion-eligibility nomination receipts for governance-only policy variants from governed policy-evaluation receipts plus runtime-spine provenance without widening live authority.
- Constraints (hard limits): Keep the completed `AK-593`, `AK-797`, `AK-798`, `AK-799`, `AK-800`, `AK-834`, `AK-835`, `AK-1047`, `AK-1085`, `AK-1093`, `AK-1094`, and `AK-1101` boundaries closed; keep `AK-1102` bounded to the nomination receipt payload / attachment surface, the supporting tactical/operational/handoff/projection refresh, and the frozen task-scope snapshot.
- Assumptions (max 3): the governed policy-evaluation receipts from `AK-593` already provide the nomination input surface; the runtime spine from `AK-1085` already provides candidate-assembly / execution-episode / receipt-bundle provenance; `AK-1102` is the single ready repo-scoped slice.
- Blockers (none or list): none.

## READ-FIRST ALLOWLIST (STARTUP BUDGET)
1. `AGENTS.md`
2. `docs/project/vision.md`
3. `docs/project/strategic_goals.md`
4. `docs/project/tactical_goals.md`
5. `docs/project/operational_goals.md`
6. `docs/adr/README.md`
7. `docs/adr/20260409-human-governed-promotion-eligibility-contract-v1.md`
8. `docs/project/program-synthesis-boundary.md`
9. `docs/project/developer_workflow.md`
10. `governance/work-items.json`

## EXECUTION MODE (ONE SESSION = ONE SLICE)
1. Choose one highest-leverage actionable slice from `governance/work-items.json` unless operator direction overrides it. In this repo, treat that file as a checked-in projection and confirm the live slice against AK before acting.
2. Confirm the repo-scoped ready queue with `./scripts/ak.sh task ready --repo /home/tryinget/ai-society/softwareco/owned/dspx -F json --json-contract normalized | jq '.tasks | map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'`.
3. If the ready queue is empty, do not guess a hidden governance backlog; only materialize the next slice when AK truth and the direction stack justify it. In the current state, AK truth already names `AK-1102` as the active bounded nomination-receipt slice.
4. Claim the current active task before editing docs or code.
5. Execute at most one operating slice end-to-end.
6. Validate truthfully with:
   - `./scripts/ci/smoke.sh`
   - `just task-scope-check task_id=<AK-ID> mode=working-tree`
   - `just verify-full`
7. Refresh source-of-truth docs/diary/ADR references before commit.

## SESSION CHECKPOINT (UPDATE BEFORE /commit)
- Slice executed: `AK-1101` — promoted `TG27` into the active tactical slot after `TG26` closed, created `AK-1102` as the next ready repo-scoped implementation slice, and refreshed the strategic/tactical/operational/handoff stack around the nomination-receipt wave.
- Outcome: `AK-1101` is complete in AK, `AK-1102` is now the single ready repo-scoped task, and the direction stack now truthfully points at the first bounded `promotion_eligibility_nominations` receipt wave.
- Files changed: `diary/2026-04-10--materialize-promotion-eligibility-nomination-wave.md`, `docs/project/strategic_goals.md`, `docs/project/tactical_goals.md`, `docs/project/operational_goals.md`, `governance/task-scopes/AK-1101.snapshot.json`, `governance/work-items.json`, `next_session_prompt.md`.
- Validation commands + results: `./scripts/ak.sh task ready --repo /home/tryinget/ai-society/softwareco/owned/dspx -F json --json-contract normalized | jq '.tasks | map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'` ✅ after completion (`AK-1102` only); `./scripts/ak.sh work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅; `./scripts/ci/smoke.sh` ✅; `just task-scope-check task_id=1101 mode=working-tree` ✅; `just verify-full` ✅.
- Source-of-truth updates: completed `AK-1101` in AK with result evidence, created `AK-1102`, exported `governance/task-scopes/AK-1101.snapshot.json`, re-exported `governance/work-items.json`, refreshed `docs/project/strategic_goals.md`, `docs/project/tactical_goals.md`, and `docs/project/operational_goals.md`, and replaced the handoff with the `AK-1102` starting point.
- Next-session starting point: claim `AK-1102`, emit the first promotion-eligibility nomination receipts, and keep the slice governance-only.

## END-OF-SESSION
Run `/commit` only if the repo is validation-clean and the handoff reflects the real checkpoint; otherwise preserve the truthful handoff and leave commit/closeout for the isolated slice.
