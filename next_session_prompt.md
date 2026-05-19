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
- Live execution truth: `ak task ready --repo /home/tryinget/ai-society/softwareco/owned/dspx -F json --json-contract normalized | jq '.tasks | map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'`
- Planned active/deferred work map: `governance/work-items.json` (checked-in projection/mirror; do not treat as live execution truth)
- Latest completed-slice diary: `diary/2026-04-10--freeze-human-review-decision-contract.md`
- Latest contract artifact: `docs/adr/20260410-human-governed-review-decision-contract-v1.md`
- Latest repo-local learning: `docs/learnings/2026-02-28-receipt-v2-phase-c.md`

## SESSION PREFLIGHT (FILL BEFORE EXECUTION)
- Objective (one sentence): Claim `AK-3176` and plan the imported DSPx visual-dossier evidence viewer for `IW-DV-06-IMPLEMENT-PREPARE-EVIDENCE`.
- Constraints (hard limits): Keep DSPx outputs review-evidence-only; do not mutate DesignMD `DESIGN.md`, mark dossier guidance accepted, create AK/society authority from DSPx artifacts, or add an orchestration bridge before a later explicit decision widens execution custody.
- Assumptions (max 3): DesignMD packet export UX landed in commit `ab8e325`; imported evidence viewer is next; orchestration remains deferred.
- Blockers (none or list): none.

## READ-FIRST ALLOWLIST (STARTUP BUDGET)
1. `AGENTS.md`
2. `docs/project/vision.md`
3. `docs/project/strategic_goals.md`
4. `docs/project/tactical_goals.md`
5. `docs/project/operational_goals.md`
6. `docs/adr/README.md`
7. `docs/adr/20260410-human-governed-review-decision-contract-v1.md`
8. `docs/project/program-synthesis-boundary.md`
9. `docs/project/developer_workflow.md`
10. `governance/work-items.json`

## EXECUTION MODE (ONE SESSION = ONE SLICE)
1. Choose one highest-leverage actionable slice from `governance/work-items.json` unless operator direction overrides it. In this repo, treat that file as a checked-in projection and confirm the live slice against AK before acting.
2. Confirm the repo-scoped ready queue with `ak task ready --repo /home/tryinget/ai-society/softwareco/owned/dspx -F json --json-contract normalized | jq '.tasks | map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'`.
3. If imported evidence viewer planning is already complete, re-check AK direction before selecting a follow-on; do not skip directly to orchestration.
4. If a repo-scoped ready task exists, claim the current active task before editing docs or code.
5. Execute at most one operating slice end-to-end.
6. Validate truthfully with:
   - `./scripts/ci/smoke.sh`
   - `just task-scope-check task_id=<AK-ID> mode=working-tree`
   - `just verify-full`
7. Refresh source-of-truth docs/diary/ADR references before commit.

## SESSION CHECKPOINT (UPDATE BEFORE /commit)
- Slice executed: DesignMD `AK-3174` plus DSPx `AK-3175` — landed packet export UX in DesignMD Foundry and recorded completion in the DSPx strategy.
- Outcome: DesignMD commit `ab8e325` adds the review-only DSPx requirements export panel; `IW-DV-05-IMPLEMENT-PACKET-UX` is done and `IW-DV-06-IMPLEMENT-PREPARE-EVIDENCE` is next.
- Files changed: `docs/project/operational_goals.md`, `governance/work-items.json`, `next_session_prompt.md`.
- Validation commands + results: DesignMD `npm test && npm run typecheck && npm run lint:design && npm run smoke:web` ✅; DesignMD agent-prompt/css exports ✅; DSPx `ak direction check`, `ak work-items check`, and `./scripts/ci/smoke.sh` pending after this handoff refresh.
- Source-of-truth updates: marked `IW-DV-05-IMPLEMENT-PACKET-UX` done; promoted `IW-DV-06-IMPLEMENT-PREPARE-EVIDENCE` to next; seeded `AK-3176` as the imported-evidence viewer planning task; refreshed projections.
- Next-session starting point: claim `AK-3176` and plan imported DSPx evidence viewer storage/schema/review-record details before implementation.

## END-OF-SESSION
Run `/commit` only if the repo is validation-clean and the handoff reflects the real checkpoint; otherwise preserve the truthful handoff and leave commit/closeout for the isolated slice.
