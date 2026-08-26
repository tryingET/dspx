---
summary: "G3 v3b re-run (AK 5085) completed after a provider-429 stall and a duplicate-session race; resume protocol held."
read_when:
  - "Resuming a long benchmark run from durable state, or designing single-writer guards for pilot runners."
  - "Reviewing the v3b glm-recovery read before any candidate-rebinding decision."
type: "diary"
---

# G3 v3b resume: 429 stall, duplicate-session race, reconciliation

## Observed

The v3b run (AK 5085) stalled at 2026-08-26T07:10Z on a provider usage-limit
429 after 2 receipts. At resume (18:22Z+) a second, controller-watcher-launched
headless session (`dspx-g3pilot-v3b-5085-resume`, PID 1007837) was executing
the same resume protocol concurrently with the operator-directed session. It
raced pair B1: two duplicate arm executions, one duplicate receipt
(18:45:53Z), then launched B2 before being terminated at 18:48:53Z.

## What held

- **No receipt = not run.** The orphaned A3 evidence arm (logged 07:10Z, no
  receipt) was discarded and re-run cleanly; the killed-mid-arm B2 evidence arm
  never entered any ledger. Durable state (state.json + receipts.jsonl, both
  written under an flock per execution) was the only truth needed to resume.
- **Digest re-verification before resume.** Frozen v3b corpus digest, v3 base
  digests, wheel sha, guidance/request/ref3b digests all re-verified before the
  first execution; all five v3b module shas unchanged after the run.
- **Honest budget reconciliation.** Counter reset to receipt-backed count;
  final 20/20 receipt-backed, 24 total executor invocations (4 discarded)
  recorded in state incidents + results `budget_honesty`.

## What the race cost and how it was contained

- Damage: 1 duplicate B1 receipt, 2 duplicate B1 arm executions, 1 partial B2
  arm. Containment: duplicate receipt quarantined verbatim inside the state
  incident record (one-receipt-per-pair invariant restored by atomic rewrite),
  duplicate session tree killed, budget counter re-derived from receipts.
- Detection was **not** automatic — it surfaced because the budget counter
  disagreed with the receipt count after a pair completed. The runner's
  `cmd_run` has no guard against a second concurrent `run` for a pair already
  mid-flight (progress is only flipped to `completed` after both arms).

## Improvement candidates (not implemented; needs owner direction)

1. Runner: claim-style guard — flip `progress[pair]` to `in_flight` (with a
   lock file holding pid/start time) *before* the first arm, refusing to start
   when in-flight, so a duplicate session fails closed instead of racing.
2. Runner: per-pair receipt idempotency — refuse to append a receipt for a
   pair that already has one.
3. Controller pattern: never launch two resume sessions for the same AK task
   lease; the lease holder is the single writer.

## Outcome

10/10 pairs, 20 receipt-backed executions, commit `5516ee65`, evidence #7839
(pass), task 5085 done. glm evidence recovery confirmed (A2, B2: 0→1; family
1/5→3/5); sol B1/B3 hold, C1 regressed (5/5→4/5). All n=1, diagnostic-only.

See: `docs/v1-proof/g3pilot-v3b-results.json` (incident records inside),
`docs/v1-proof/g3pilot-v3b-state.json` (`incidents`).
