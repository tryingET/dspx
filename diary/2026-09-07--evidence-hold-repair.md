---
summary: "AK-5511 implementation HOLD repair: semantic joins, shared reducers, default offline fixtures and explicit remaining gates."
read_when:
  - "Reviewing dispatch-1788781092681 corrections before target trust or repinning."
---

# HOLD corrections, not SHIP or lifecycle completion

Authority: continued exact AK-5511 scope; no auth pin, target, task-state, live-effect,
original-evidence or unrelated workstation mutation. The obsolete 7fbb491a capsule
must not be used as proof of complete closure. The single protocol and current
11-module hash manifest are in
[the contract](../docs/project/2026-09-07-evidence-integrity-design.md).

Corrections restore source/candidate runtime manifest schemas, identities, embedded
episode, mode and input/behavior joins; GEPA materialization identity/hash/inventory/
metric/status/authority contracts; and deterministic comparison reconstruction.
Nineteen pure helpers are shared with the producer. Finite historical dialects retain
pre-label exact semantics and later labels as assertions, never proof of live origin.

Default tests use frozen selected Espresso closure bytes and Copilot journal bytes.
They contain no credentials, env files, cache or derivation files; original paths
are inert aliases. Archive contents, including generated scripts/pickles, are never
executed. Fixture payload hashes and existing artifact hashes bind extraction.
Original saved scratch was read only. Mutants live in fresh test-owned directories.

Proof distinctions: runtime stripped/field mutants go through the isolated capsule
with unchanged subject/seven roots and fail at new semantic checks. GEPA/comparison
mutants also update real transitive references with immutable terminal roots; those
may fail at hash custody first. Separate exact inner-contract tests prove semantic
rejection, rather than presenting outer hash rejection as proof of a new reducer.
A frozen 777388a comparison golden and producer/shared-helper tests guard drift.

Observed validation:
- Default closure + comparison slice: 88 passed, no opt-in roots or skips.
- Final broader foundry/comparison/Oracle slice: 650 passed, one expected current-
  pin/fork mismatch. No repin authorization.
- Retained metric-honesty slice: 14 passed, now explicitly covers absent/present v1
  fields. Nine baseline type errors repaired by precise test casts/narrowing.
- Offline ci-quality and verify-fast passed; exact scope check passed.
- Full offline heavy-job attempt denied: retained-run process-reference scan was
  incomplete for kernel-protected same-UID processes. No bypass/cleanup attempted.
  Full verify-full additionally includes live/infrastructure residuals outside this
  authorization. No full-gate pass or independent corrected SHIP is claimed.

Scope/budget ledger: correction adds net 444 source LOC on top of the disputed
2597 baseline (cumulative 3041). Tests add net 1571 LOC, including 1225 LOC in three
frozen fixture/loader files. Shared extraction removes 399 lines from the producer;
this is disclosed net growth, not a claim that the pending budget reconciliation
is approved. Independent implementation/budget review must precede target trust.
