---
summary: "Direction-to-execution reset for the V9-compatible, V7-first synthesis wave."
read_when:
  - "You need the rationale behind the current V7/V8/V9 direction reset."
  - "You are resuming the post-M4 planning/materialization session."
---

# 2026-03-22 — Direction to Execution Reset for V7/V8/V9

## What I Did
- Used the repo-direction-to-execution Prompt Vault template to convert the repo's stale direction surfaces into an explicit lifecycle again.
- Audited the current state:
  - `docs/project/vision.md` and `docs/project/strategic_goals.md` were placeholders,
  - `docs/project/tactical_goals.md` still reflected the pre-synthesis-runtime wave,
  - `docs/VISION.md` held useful long-horizon material but was no longer the right canonical home,
  - the AK ready queue still pointed at older provider-runtime/evidence follow-ons rather than the next active architecture wave.
- Rewrote the direction stack so it now reads cleanly as:
  - vision -> strategic goals -> tactical goals -> operational goals -> AK tasks.
- Salvaged `docs/VISION.md` into a compatibility landing page and moved the canonical long-horizon direction into `docs/project/vision.md`.
- Added a dated ADR (`docs/adr/20260322-synthesis-architecture-v7-v9.md`) so the repo can reference V7/V8/V9 architecture terms without oral history.
- Created `docs/project/operational_goals.md` as the active operating-plan layer and materialized the corresponding AK tasks:
  - `AK-249` — synthesis contracts
  - `AK-250` — runtime/workspace/promotion shell
  - `AK-251` — route `module-gen` through the runtime MVP path
- Deferred two older ready tasks (`AK-224`, `AK-235`) because they belonged to non-active waves and would otherwise leave the ready queue pointing away from the chosen tactical goal.
- Updated the next-session handoff so the next operator starts by claiming `AK-249` rather than trying to infer the new architecture wave from stale backlog state.

## What Surprised Me
- The most important missing artifact was not another roadmap note; it was a dated reference for the V7/V8/V9 vocabulary itself. Without that, every conversation about the synthesis runtime had to re-negotiate its own terms.
- The AK queue already contained repo-local work, but the ready slice was misaligned with the repo's highest-leverage next wave. Direction repair without queue repair would have been incomplete.

## Patterns
- If a repo wants to evolve toward higher-order autonomy, the first architectural work is not autonomy; it is making strategy, evidence, policy, and promotion boundaries explicit enough that autonomy can someday be governed.
- When older overview docs are still linked from AGENTS/read-order surfaces, salvage them into compatibility entry points instead of hard-deleting them. That keeps navigation stable while moving canonical truth to a better location.
- A truthful operating-plan file should reference exact live AK task IDs and keep non-active tasks out of the ready queue, otherwise "planning" and "execution" silently diverge.

## Candidates Considered and Excluded
- Kept provider-runtime follow-ons as the active wave? No — those tasks remain real, but the repo's long-horizon direction and current leverage point are now the synthesis-runtime seam, so they were deferred.
- Deleted `docs/VISION.md` outright? No — AGENTS/read-order references still point there, so a compatibility landing page was safer and less surprising.
- Jumped directly to V8/V9 implementation tasks? No — the architecture is now documented for V7/V8/V9, but the active operating wave is intentionally V7-first.
