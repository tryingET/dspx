---
summary: "Successor G3 gate-campaign design: convention-space corpus at right-sized N with pre-registered criterion; DRAFT for decision-132 owner acceptance."
read_when:
  - "You are the decision-132 owner reviewing the successor instrument to the stopped 5059 campaign."
  - "You are freezing or executing the successor G3 campaign."
type: "design"
---

# G3 SUCCESSOR CAMPAIGN DESIGN — DRAFT (owner acceptance required before freeze)

**Status: DRAFT. Nothing here is frozen and nothing has executed.** Authority:
the decision-132 owner thread accepts or rejects this instrument; per the
5059 pattern, acceptance is followed by a protocol-manifest freeze and
pre-freeze calibration before any execution. Companion inputs:
`g3-g5-consumption-note.md`, `g3-candidate-5-rebind-decision-input.md`.

## 1. Problem this instrument solves

The stopped campaign (5059) is instrument-limited: control-arm success ≥0.9167
(ceiling), so guidance lift is unmeasurable at any feasible N. The
convention-space task family (v3/v3b) demonstrably separates: 6/10 (v3) and
4/10 (v3b) task-level arm splits, static/evidence rates near mid-range —
exactly the region where paired arm comparison has power.

**Construct boundary (named, not hidden):** this instrument measures
*convention-conformance lift* — whether guidance improves success on tasks
whose correct answers live in the convention space the candidate encodes.
That is a **necessary, not sufficient**, proxy for engineering value; any gate
verdict speaks to that construct, and this sentence travels into the decision
record unchanged.

## 2. Corpus promotion rules

1. **Promote the convention-space task FAMILY (templates), not the observed
   instances.** Successor corpus = 12 tasks: the class A/B/C family templates
   from v3/v3b plus 2 harder variants from the harder-tasks calibration line
   (`docs/v1-proof/g3pilot-harder-tasks.json`). Frozen instances must be **new
   derived instances** (fresh fixture materialization, difficulty re-targeted
   per rule 2) — byte-identical reuse of observed v3/v3b task instances is
   prohibited, so the frozen corpus is NOT the set that was observed to split.
2. **Saturation guard:** any task whose pre-freeze reference/static pilot
   pass-rate exceeds 0.8 is replaced (difficulty re-targeted) before freeze;
   target static-arm rate ∈ **[0.4, 0.6]** per task.
3. **Difficulty inputs from diagnostics (n=1, advisory only):** C1-style
   tasks regressed for sol in v3b (1→0 both arms) — calibrate C-class
   variants toward the static mid-range; A3-style rollback tasks persisted at
   evidence=0 for glm — keep one such task as a hard cell, do not saturate the
   corpus with them (AK 5093 tracks the investigation).
4. **Both families run all tasks** (fam-gpt: gpt-5.6-sol:high; fam-glm:
   glm-5.3:high); arm order interleaved per pair as in v3b; arms differ only
   by guidance presence; advisor = gpt-5.6-terra uniformly for class A/C
   evidence arms (class B: no advisor call, unchanged).5. **Anti-circularity clause:** promotion and derivation decisions are
   difficulty-based only; diagnostic arm outcomes may not be used to select,
   drop, or weight tasks. One evidence-arm-failure hard cell (A3-style) is
   retained by rule, not by outcome. After freeze, no task may be dropped or
   replaced for arm asymmetry — only the pre-registered
   infrastructure-block substitution applies.


## 3. Design and N (power calculation, paired binary / exact McNemar)

Unit = **pair** (one task, one family, both arms). With expected static rate
0.5 / evidence 0.8, within-pair discordance p_d ≈ 0.4–0.5 and among
discordant pairs an evidence-only share π ≈ 0.75–0.8, the required number of
discordant pairs at two-sided α=0.05, power 0.80 is:

| π (e-only | disc) | n_d required | N at p_d=0.4 | N at p_d=0.5 |
|---|---|---|---|
| 0.80 | 20 | 50 | 40 |
| 0.75 | 29 | 73 | 58 |

**Primary design: N=72 pairs = 12 tasks × 2 families × 3 repetitions**
(144 executions max) — power ≥0.80 across the plausible π range with p_d=0.4
(the v3b-observed discordance), and margin for infrastructure blocks.
Cells are n=3; inference is pooled across task strata, not per-cell claims.
Interim look at **N=48** (one look, pre-registered): stop for efficacy at
p<0.001; stop for futility if discordant asymmetry ≤ 0.5. Cost ceiling:
144 executions ≈ 43% of the dead campaign's 336.

## 4. Pre-registered criterion (frozen before any execution)

- **Primary endpoint:** pooled exact McNemar over all discordant pairs.
  **PASS** requires ALL of: (i) two-sided p<0.05; (ii) majority of discordant
  pairs evidence-only; (iii) no family-level reversal (each family's evidence
  rate ≥ its static rate); (iv) ≥70% of planned pairs receipt-backed.
- **FAIL** if (i)–(ii) hold inverted (static dominance) at p<0.05 with ≥70%
  completion. All other outcomes: **INCONCLUSIVE** (never PASS-by-default).
- **Single-variable requirement:** the wheel is exactly the owner-bound
  candidate (candidate-5 = main@cde7f14 if the rebind input is accepted);
  no mid-run wheel changes; guidance rendered from that wheel only.
- **Advisor fallback rule:** if gpt-5.6-terra is unavailable, glm-5.3 fallback
  responses are recorded and excluded from the primary analysis (sensitivity
  only).
- **Infrastructure-block rule (v3b lesson):** blocked family pauses, resumes
  in-window; no partial arms count; budget reconciles to receipts only.
- **Execution guard:** AK 5092 runner hardening (in-flight pair guard,
  per-pair receipt idempotency) must land BEFORE execution.

## 5. Governance path

1. Decision-132 owner accepts/rejects **one motion with three parts** —
   (a) the G5 consumption note, (b) the candidate-5 rebind, (c) this design
   as amended — recording in the decision text both the v3b confound (fix +
   wheel identity) and the construct boundary above. Acceptance is an owner
   act; DSPx supplies inputs, not the verdict.
2. On acceptance: freeze successor protocol manifest (corpus digests, checker
  shas, wheel identity, criterion text) + pre-freeze calibration (reference
  Y=1 / stub Y=0 / tamper detection, per v3b standard).
3. Execute under AK task (gated on 1–2), receipts in v3-shape + family +
   `run_label: successor`.
4. Gate consumption: successor campaign is the gate-grade event; the 5059
   campaign is consumed per `g3-g5-consumption-note.md` regardless of outcome.

**Explicit non-claims:** this design is text until accepted and frozen; n=3
cells support the pooled paired test only; nothing here grades candidate-4,
candidate-5, or the AK-5082 fix.
