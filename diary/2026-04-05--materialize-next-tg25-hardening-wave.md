---
summary: "Diary entry: 2026-04-05 — Materialize the Next TG25 Hardening Wave."
read_when:
  - "You need the historical implementation context captured in this diary entry."
  - "You are reviewing or extending work related to 2026-04-05 — Materialize the Next TG25 Hardening Wave."
type: "diary"
---

# 2026-04-05 — Materialize the Next TG25 Hardening Wave

## Why this refresh was needed

The repo-scoped AK ready queue was empty after `AK-800`, but the repo was not complete:
- `SG2` was still unfinished in the direction docs,
- `TG25` was still marked as active,
- `docs/learnings/tg25-adversarial-review-nexus.md` had already crystallized concrete fail-closed gaps,
- the working tree already contained bounded in-progress fixes and regressions for those gaps.

That meant the empty queue was a decomposition/materialization failure, not evidence that the repo had reached a truthful idle state.

## Evidence used

- direction stack: `docs/project/vision.md`, `strategic_goals.md`, `tactical_goals.md`, `operational_goals.md`
- handoff: `next_session_prompt.md`
- live AK truth: repo-scoped ready queue plus last 5 repo-local tasks (`AK-800`, `AK-799`, `AK-798`, `AK-797`, `AK-734`)
- repo-local learnings: `docs/learnings/tg25-adversarial-review-nexus.md`
- current working tree: bounded dirty files and new regression tests already clustered around the adversarial hardening findings

## Candidates considered

### Selected
1. **Adversarial NEXUS boundary fixes across Forge, replay, provider racing, and Oracle seams**
   - grounded by the learning doc plus the existing dirty files/tests
   - materialized as `AK-834`
2. **Atomic hardening cleanup across config, runtime, policy, and task-scope guards**
   - grounded by the current working tree and the new regression files already present
   - materialized as `AK-835`

### Deliberately not materialized yet
1. **Freeze the human-governed promotion-eligibility contract (`TG26`)**
   - excluded for now because the hardening prerequisites are still open
2. **Older provider/runtime and Oracle backlog (`AK-224`, `AK-235`–`AK-239`)**
   - kept non-active because they are not selected by the current TG25 wave
3. **A larger speculative cleanup queue**
   - rejected because the current repo truth already supports two bounded slices without inventing more backlog

## Direction updates made

- kept `SG2` active, but refreshed its wording so the remaining hardening prerequisites are visible instead of implicit
- refreshed `TG25` from a stale empty-ready-queue waiting state into an active adversarial hardening wave
- pinned `TG26` as next, not active
- refreshed `docs/project/operational_goals.md` so the active wave now maps to live AK tasks (`AK-834`, `AK-835`) plus the explicit blocked promotion step
- refreshed `next_session_prompt.md` so the next session starts from the live ready queue rather than the stale post-`AK-800` checkpoint

## Source-of-truth actions

- created `AK-834` with bounded repo scope
- created `AK-835` with bounded repo scope
- refreshed the direction stack/handoff docs
- re-exported `governance/work-items.json` from AK after the mutations

## Result

The repo now has truthful live backlog coverage for the next active `TG25` wave without inventing a speculative queue, and the direction-to-execution chain is again explicit:

`SG2 -> TG25 -> AK-834 / AK-835 -> TG26 blocked until hardening closes`
