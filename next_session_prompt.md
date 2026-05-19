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
- Objective (one sentence): Claim `AK-3164` and continue discovery for the `SF-DESIGNMD-VDOS` DesignMD visual-source dossier integration strategy.
- Constraints (hard limits): Keep DSPx outputs review-evidence-only; do not mutate DesignMD `DESIGN.md`, mark dossier guidance accepted, create AK/society authority from DSPx artifacts, or add an orchestration bridge before discovery/research/design settles custody and authority boundaries.
- Assumptions (max 3): DSPx-side prepare/program-gen/traceability/fitness flow is executable; DesignMD currently exposes requirements packet generation but not UI/program-gen orchestration; `IW-DV-01-DISCOVERY` is the active next wave.
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
3. If the DesignMD dossier discovery task is no longer ready, re-check AK direction before selecting a follow-on; do not skip directly to orchestration.
4. If a repo-scoped ready task exists, claim the current active task before editing docs or code.
5. Execute at most one operating slice end-to-end.
6. Validate truthfully with:
   - `./scripts/ci/smoke.sh`
   - `just task-scope-check task_id=<AK-ID> mode=working-tree`
   - `just verify-full`
7. Refresh source-of-truth docs/diary/ADR references before commit.

## SESSION CHECKPOINT (UPDATE BEFORE /commit)
- Slice executed: `AK-3162` / `AK-3169` — created the AK-native DesignMD visual-source dossier integration strategy and refreshed the handoff docs to point at the new ready discovery slice.
- Outcome: `SF-DESIGNMD-VDOS` is active, `IW-DV-01-DISCOVERY` is next, and `AK-3164` is the repo-scoped discovery execution task.
- Files changed: `docs/project/operational_goals.md`, `governance/work-items.json`, `next_session_prompt.md`.
- Validation commands + results: `ak direction check --repo /home/tryinget/ai-society/softwareco/owned/dspx --format json` ✅; `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅; `./scripts/ci/smoke.sh` ✅ after handoff refresh.
- Source-of-truth updates: created AK direction rows for discovery, research, design, implementation plan, and implementation waves; linked prior DSPx implementation anchors; seeded `AK-3164` as the first discovery task; refreshed the checked-in AK projection.
- Next-session starting point: claim `AK-3164` and perform discovery across DesignMD UI/API and DSPx evidence surfaces before choosing research/design or implementation work.

## END-OF-SESSION
Run `/commit` only if the repo is validation-clean and the handoff reflects the real checkpoint; otherwise preserve the truthful handoff and leave commit/closeout for the isolated slice.
