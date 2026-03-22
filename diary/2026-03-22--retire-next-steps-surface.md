---
summary: "Retire NEXT_STEPS.md and converge roadmap references on the canonical project direction stack."
read_when:
  - "You want to know why NEXT_STEPS.md was deleted."
  - "You are updating roadmap/status/doc references after the direction-stack migration."
---

# 2026-03-22 — Retire NEXT_STEPS Surface

## What I Did
- Treated `NEXT_STEPS.md` as a prompt/reality mismatch surface: it kept advertising itself as a roadmap even after `docs/project/vision.md`, `strategic_goals.md`, `tactical_goals.md`, and `operational_goals.md` became the canonical direction stack.
- Salvaged the remaining useful content instead of preserving the obsolete surface:
  - active-wave truth already lived in `docs/project/strategic_goals.md`, `docs/project/tactical_goals.md`, and `docs/project/operational_goals.md`
  - provider-runtime v4 context already lived in `docs/project/provider-runtime-v4.md` and ADR 20260322
  - Oracle/evidence substrate status was folded into the strategic-goals framing rather than left in a separate roadmap monolith
- Updated live references in startup and operational docs so they now point at the canonical `docs/project/*` stack instead of `NEXT_STEPS.md`.
- Updated the direction/workflow checks so the repo no longer depends on `NEXT_STEPS.md` existing.
- Deleted `NEXT_STEPS.md` and kept the work-items projection, next-session handoff, and operational goals DRY.

## What Surprised Me
- The file was no longer needed for current truth, but a surprising amount of operational gravity still flowed through it because validations and read-order docs had been taught to expect its presence.
- Deleting the file safely required more work on references/contracts than on content salvage.

## Patterns
- Once a canonical direction stack exists, keeping an extra top-level roadmap file usually creates prompt/runtime mismatch rather than clarity.
- The right deletion pattern is: salvage unique content -> repoint startup/validation surfaces -> export/update mirrors -> delete the obsolete file.
- DRY execution memory means `next_session_prompt.md` should point at the active slice and `docs/project/operational_goals.md` should list only the active operating wave; neither should re-host a secondary roadmap.

## Crystallization Candidates
- Add a general repo rule: when a new canonical direction stack replaces an older planning surface, delete the superseded surface once all startup/read-order/validation references are migrated.
