---
summary: "Machine-checked direction-to-execution coherence contract for docs, AK, and the checked-in work-items projection."
read_when:
  - "You need to understand why direction coherence is now a validation gate."
  - "You are changing startup docs, AK task waves, or the work-items projection contract."
---

# 2026-03-22 — Direction Coherence Contract

## What I Did
- Implemented the NEXUS intervention from the adversarial review: turn the recent direction reset from a one-shot docs/AK edit into a machine-checked repo invariant.
- Added `scripts/check_direction_to_execution.py` to verify that:
  - `strategic_goals.md`, `tactical_goals.md`, `operational_goals.md`, and `NEXT_STEPS.md` agree on the active strategic/tactical markers,
  - `AGENTS.md` read order points at the canonical project-direction docs,
  - the first operating slice in `docs/project/operational_goals.md` matches the active AK task named in `next_session_prompt.md`,
  - the claimed next task is actually ready in AK,
  - `governance/work-items.json` matches the live AK projection via `ak work-items check`.
- Wired that check into `./scripts/ci/smoke.sh` and `just verify-full`.
- Updated `AGENTS.md` so the startup read order now points at `docs/project/vision.md`, `strategic_goals.md`, `tactical_goals.md`, and `operational_goals.md` instead of relying on the older top-level surfaces alone.
- Updated `NEXT_STEPS.md` to expose explicit markers for the current active strategic goal, tactical goal, and operating wave.
- Updated `governance/README.md` and `docs/project/operational_goals.md` so AK-backed projection refresh/check commands are part of the written operating contract.
- Exported `governance/work-items.json` from AK so the checked-in mirror now matches live execution truth.

## What Surprised Me
- The most important bug was not in any single doc; it was in the *space between docs*.
- Once the projection drift was mechanized, the repo immediately surfaced that the previous change had only repaired the docs/AK layer, not the mirror/startup layer.

## Patterns
- Prompt templates can restore coherence once; validation contracts are what keep coherence from decaying again.
- If a repo has multiple planning/execution surfaces, the highest-leverage check is the one that proves they all agree on the *same current wave*.
- Checked-in projections should either be exported deterministically or deleted; manually maintained mirrors are drift magnets.

## Crystallization Candidates
- Add a stable "direction coherence" section to repo-level workflow docs for repos that use AK + checked-in projections + direction docs simultaneously.
