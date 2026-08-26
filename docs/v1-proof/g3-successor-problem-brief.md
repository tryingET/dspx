---
summary: "Problem brief: G3 remains the sole open v1 gate question; the 5059 campaign cannot answer it (ceiling); a discriminating successor instrument is required."
read_when:
  - "You are reviewing or deciding the G3 successor campaign protocol (DSPx-side conditioned acceptance)."
type: "problem-brief"
---

# Problem brief — G3 successor empirical protocol

## The problem

engineering-core v1 qualification is blocked solely on G3 (empirical
guidance-value question). The production campaign (AK 5059, decision 132
protocol) terminated **operator-stopped incomplete at 127/168 pairs** with a
**ceiling effect**: fam-gpt both arms 77/84 (0.9167); fam-grok 43/84 both arms
43/43 (1.0). Under the frozen criterion the campaign is not evaluable, and —
decisively — it is **instrument-limited**: a corpus whose control arm passes
≥ 91.7% of tasks cannot measure guidance lift at any feasible N. The G5
fan-in (engineering-core c981e7d, AK 4877) records G3 as NOT PASSED
(incomplete, null signal) and names the successor path.

## Why a successor instrument, not a re-run

- Re-running the saturated corpus spends ~336 more executions to learn
  nothing: the null is a property of the task difficulty distribution, not of
  sample size.
- The v3 (AK 5081) and v3b (AK 5085) diagnostics established that a
  **convention-space** task family separates the arms: 6/10 and 4/10
  task-level splits at mid-range success rates — the responsive region for a
  paired comparison. v3b additionally showed the AK-5082-fixed advise surface
  restores glm evidence-arm conformance on both prior failure pairs
  (A2 0→1, B2 0→1) with sol stable on its directive targets (B1/B3).
- The engineering-core owner has bound **candidate-5 = main@cde7f14**
  (wheel sha 921bff5e…) for the G3 successor instrument and reopened G3
  (AK 5096, engineering-core commit 145c889, operator-accepted "accept both").
  Frozen G0–G4 gate records stay candidate-4; this binding is G3-instrument
  only.

## What must be decided (DSPx side)

Accept the successor empirical protocol
(`g3-successor-campaign-design.md`, as amended): 12 fresh-derived
convention-space tasks × 2 families × 3 reps = N=72 pairs (≤144 executions),
pooled exact-McNemar pre-registered criterion, one interim look at N=48,
anti-circularity corpus rules, runner hardening (AK 5092) as hard
precondition — **conditioned on the EC binding (AK 5096)**.

## Honest constraints that travel with the decision

1. **Confound:** v3→v3b differed by fix + wheel identity; the recovery read
   is not single-variable causal evidence for the AK-5082 fix. The successor
   instrument is single-variable by design (one bound candidate).
2. **Construct boundary:** the instrument measures *convention-conformance
   lift* — a necessary, not sufficient, proxy for engineering value.
3. **n=1 diagnostics:** corpus difficulty targeting uses v3/v3b observations
   as advisory inputs only; promotion/derivation decisions are
   difficulty-based, arm-direction-blind (anti-circularity clauses).
4. **No gate claim by producers:** DSPx supplies the instrument and evidence;
   gate consumption is an owner act (new fan-in), never a producer claim.
