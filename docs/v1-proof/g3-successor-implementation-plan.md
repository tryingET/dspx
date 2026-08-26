---
summary: "Implementation plan for decision 138 (G3 successor protocol): 5092 runner hardening, then 5095 freeze + calibration + execution of the N=72 successor campaign."
read_when:
  - "Executing the G3 successor campaign sequence under decision 138 / AK 5095."
type: "implementation-plan"
---

# Implementation plan — decision 138 (G3 successor protocol)

Ordered; each step gated on the previous.

1. **AK 5092 — runner hardening (hard precondition).** Implement in the
   successor runner modules: (a) in-flight pair guard — `progress[pair]`
   flips to `in_flight` (lock file with pid/start time) before the first
   arm; `run` refuses to start an in-flight pair; (b) per-pair receipt
   idempotency — append refuses when a receipt for the pair exists;
   (c) single-writer execution log. Validated by unit tests + a
   simulated-race test (two concurrent `run` invocations, exactly one
   proceeds). Closes the v3b duplicate-session race class (AK 5085
   incidents).
2. **AK 5095 — freeze.** Author the successor corpus: 12 templates × 3
   distinct derived instances each (anti-circularity rules, difficulty
   targeting static-arm [0.4,0.6], saturation guard ≤0.8). Freeze the
   protocol manifest: instance digests, checker shas, wheel identity
   (candidate-5, sha 921bff5e… verified at freeze), criterion text (REV 3
   §4), enrollment order, CP re-fit procedure, simulation model + seed +
   assumptions. Discharge review observes N1–N6 into the manifest
   (wording clause; at-floor d=4 + ICC>0 clustered-null simulation
   scenarios; DE computation pinned; budget value; CP estimator note).
3. **Pre-freeze calibration.** Reference Y=1 (10/10), stub Y=0 (10/10),
   tamper detection (A-style + C-style), plus the joint-criterion Monte
   Carlo operating-characteristics record (power curve, concentration
   rejection, ICC/determinism assumptions as limitations). Freeze only if
   calibration passes.
4. **EC pre-execution ping.** Frozen corpus table + digests to the
   engineering-core session (per AK 5096 cooperation note) before first
   execution.
5. **Execution.** N=72 pairs interleaved per frozen order; interim look at
   N=48 per REV 3 §4; incidents ledgered; budget reconciled to receipts
   only. Extension (72→96) only via the pre-registered rule + operator
   budget re-authorization in AK.
6. **Results + self-close per the design doc.** Results artifact with the
   primary, guard, sensitivity, and honest completion; gate consumption is
   a future owner fan-in — no producer gate claims.
