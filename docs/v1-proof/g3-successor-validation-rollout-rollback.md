---
summary: "Validation, rollout, and rollback for decision 138: what validates each stage, how the campaign rolls out, and how to halt/rollback lawfully."
read_when:
  - "Executing, halting, or rolling back the G3 successor campaign under decision 138."
type: "validation-rollout-rollback"
---

# Validation / rollout / rollback — decision 138

## Validation (per stage)

- **Runner hardening (5092):** unit tests for both guards + simulated
  concurrent-run race test (two `run` calls, one proceeds, one refuses);
  receipts file unchanged for existing pairs.
- **Freeze:** manifest digest verification (instances, checkers, wheel sha
  921bff5e… re-verified at freeze); corpus digest; anti-circularity
  checklist attested in the manifest (no observed v3/v3b instance bytes
  reused; difficulty-only promotion).
- **Calibration:** reference 10/10 Y=1; stub 10/10 Y=0; tamper detection
  fires; joint-criterion simulation record produced. Any failure ⇒ freeze
  does not proceed (fail-closed).
- **Execution:** per-arm receipt-backed verification by the frozen checkers
  (v3b standard: claim, grounding, acceptance); budget counter reconciles
  to receipts at every step; interim look computed per frozen rule.
- **Results:** deterministic recomputation of the primary (pooled exact
  McNemar), the floored guard, the family rule, and completion from the
  receipts file (v3b closeout standard).

## Rollout

Single-track: execution happens only under AK 5095 after 5092 lands and the
freeze + calibration pass; the EC session receives the frozen corpus table
+ digests before first execution; the run executes interleaved per frozen
enrollment order with the one pre-registered interim look.

## Rollback / halt

- **Pre-freeze:** any calibration failure halts before execution; nothing
  to roll back (no run state exists).
- **Mid-run:** infrastructure block ⇒ pause + in-window resume (no
  substitution); harm-class incident ⇒ operator stop; partial state is
  resumable from durable state + receipts (v3b resume protocol).
- **Post-run:** results are immutable evidence; INCONCLUSIVE outcomes are
  terminal for this N (extension is the only continuation, and it requires
  operator re-authorization). No artifact of this decision rewrites frozen
  G0–G4 candidate-4 records or the stopped-5059 record.
- **Decision-level:** decision 138 is superseded only by a future AK
  decision; nothing in the implementation mutates AK authority out-of-band.
