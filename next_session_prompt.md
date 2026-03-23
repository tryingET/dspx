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
- Live execution truth: `ak task ... --repo /home/tryinget/ai-society/softwareco/owned/dspx`
- Planned active/deferred work map: `governance/work-items.json` (legacy checked-in projection/mirror; do not treat as live execution truth)
- Raw session capture: `diary/`

## SESSION PREFLIGHT (FILL BEFORE EXECUTION)
- Objective (one sentence): Claim `AK-274` and implement the read-only v1 evidence retrieval bundle for ranked module synthesis.
- Constraints (hard limits): Keep the repo green under `just verify-full`; preserve the ranked module-synthesis hardening shipped under `AK-260`/`AK-266`/`AK-271`; do not start predictive ranking or policy mutation before the retrieval bundle exists behind the frozen contract.
- Assumptions (max 3): `AK-263` is complete; `docs/adr/20260323-synthesis-evidence-retrieval-v1.md` is the canonical SG2 retrieval contract; `TG6` is now the active tactical goal.
- Blockers (none or list): None.

## READ-FIRST ALLOWLIST (STARTUP BUDGET)
1. `AGENTS.md`
2. `docs/project/vision.md`
3. `docs/project/strategic_goals.md`
4. `docs/project/tactical_goals.md`
5. `docs/project/operational_goals.md`
6. `docs/adr/20260322-synthesis-architecture-v7-v9.md`
7. `docs/adr/20260323-synthesis-evidence-retrieval-v1.md`
8. `diary/2026-03-23--freeze-synthesis-evidence-retrieval-contract.md`

## EXECUTION MODE (ONE SESSION = ONE SLICE)
1. Choose one highest-leverage actionable slice from `governance/work-items.json` unless operator direction overrides it. In this repo, treat that file as a checked-in projection and confirm the live slice against AK before acting.
2. Confirm the ready queue with `ak task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx"))'`.
3. Claim the current active task before editing code.
4. Implement one operating slice end-to-end.
5. Validate:
   - `./scripts/ci/smoke.sh`
   - `just verify-full`
6. Update source-of-truth docs/diary/ADR references before commit.

## SESSION CHECKPOINT (UPDATE BEFORE /commit)
- Slice executed: `AK-263` — synthesis evidence substrate: freeze the first SG2 receipt/replay/Oracle retrieval contract.
- Outcome: DSPx now has a dated ADR for the first evidence bundle ranked synthesis should consume, replay health is explicit as a trust boundary, and `AK-274` is queued as the first contract-aligned implementation slice.
- Files changed: `docs/adr/20260323-synthesis-evidence-retrieval-v1.md`, `docs/adr/README.md`, `docs/project/tactical_goals.md`, `docs/project/operational_goals.md`, `diary/2026-03-23--freeze-synthesis-evidence-retrieval-contract.md`, `governance/task-scopes/AK-263.json`, `next_session_prompt.md`, and `governance/work-items.json` after AK export.
- Validation commands + results: `./scripts/ci/smoke.sh` ✅; `just verify-full` ✅; `ak evidence record --task 263 --check-type validation:verify-full --result pass --details '{"commands":["./scripts/ci/smoke.sh","just verify-full"]}'` ✅; `ak task complete 263 --result '{"summary":"Froze the SG2 evidence retrieval contract in a dated ADR and aligned the next implementation slice.","next_task":274}'` ✅; `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅; `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅.
- Source-of-truth updates: tactical/operational docs now point to `TG6`/`AK-274`; the new ADR and diary capture the evidence retrieval contract.
- Next-session starting point: claim `AK-274`, implement the read-only evidence retrieval bundle, and keep predictive ranking out of scope.

## END-OF-SESSION
Run `/commit` and ensure this file reflects the real checkpoint for the next operator/agent.
