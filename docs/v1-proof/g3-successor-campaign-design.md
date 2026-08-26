---
summary: "Successor G3 gate-campaign design REV 3: pooled exact McNemar as primary (honestly labeled), floored template-level co-primary guard (>=4 discordant templates), cluster-robust sensitivity + pre-freeze joint-criterion operating-characteristic simulation; no substitution channel."
read_when:
  - "You are the engineering-core owner bound to the G3 successor instrument (AK 5096) reviewing what DSPx will freeze."
  - "You are the DSPx decision owner accepting the successor empirical protocol (conditioned on the EC binding)."
  - "You are freezing or executing the successor G3 campaign."
type: "design"
---

# G3 SUCCESSOR CAMPAIGN DESIGN — REV 3 (post re-review)

**Status: DRAFT REV 3.** Nothing frozen; nothing executed. Revision history:
REV 1 → independent review (`g3-successor-review-memo.md`, verdict
`revise_rfc`: F1 blocker, F2–F5 must-fixes) → REV 2 → delta re-review
(no blockers; must-fixes D1: the REV 2 "stratified permutation primary" is
numerically identical to pooled McNemar with strata inert, or rests on false
exchangeability — mislabeled either way; D2: the template guard had no
minimum discordant floor, admitting a 2-template PASS) → **this REV 3**.
Changes marked **[D#]** (delta findings) or **[R#]** (round-1 findings).
Authority split unchanged: EC binds candidate + reopened G3 (done: AK 5096,
commit 145c889); DSPx accepts conditioned on that binding; carrier = AK
decision with `rfc_ref` into the EC repo.

## 1. Problem this instrument solves

The stopped campaign (5059) is instrument-limited: control-arm success ≥0.9167
(ceiling); guidance lift unmeasurable at any feasible N. The
convention-space family (v3/v3b) separates: 6/10 and 4/10 task-level arm
splits at mid-range rates.

**Construct boundary (named, not hidden):** this instrument measures
*convention-conformance lift* — a **necessary, not sufficient**, proxy for
engineering value. This sentence travels into the decision record unchanged.

**[D7/F5 enrichment disclosure — travels into the decision record]:** the
TEMPLATE FAMILY was selected because diagnostics showed it separates arms.
Difficulty-based promotion and distinct-instance derivation mitigate
instance-level circularity; the template-level enrichment is disclosed, not
hidden, and is part of what the decision accepts.

## 2. Corpus promotion rules

1. **[R5] Promote the convention-space task FAMILY = class-level TEMPLATES
   (A/B/C), never observed instances.** Frozen corpus = **36 DISTINCT derived
   instances**: 12 templates (class A/B/C family + 2 harder variants) × 3
   distinct derived instances each. Byte-identical reuse of observed v3/v3b
   instances prohibited. Arm-direction-blind rule applies at template
   selection, instance derivation, and difficulty-based replacement.
2. **Saturation guard:** any template whose pre-freeze reference/static pilot
   pass-rate exceeds 0.8 is difficulty-re-targeted before freeze; target
   static-arm rate ∈ [0.4, 0.6] per template.
3. **Difficulty inputs (n=1, advisory only):** C-class variants calibrated
   toward static mid-range (sol C1 regression); exactly ONE A3-style rollback
   template retained as a hard cell (AK 5093 tracks investigation).
4. **Both families run all instances** (fam-gpt: gpt-5.6-sol:high; fam-glm:
   glm-5.3:high); arm order interleaved per pair; arms differ only by
   guidance presence; advisor = gpt-5.6-terra uniformly for class A/C
   evidence arms (class B: no advisor call).
5. **Anti-circularity clause:** promotion, derivation, replacement, weighting
   are difficulty-based only; diagnostic arm outcomes may not select, drop,
   or weight templates or instances; the one evidence-failure hard cell is
   retained by rule, not outcome. After freeze, no template or instance may
   be dropped or replaced for arm asymmetry; **[R4] no post-freeze
   substitution channel of any kind**.

## 3. Design, unit of analysis, and power

**Unit = pair** (one instance × one family, both arms). 36 instances × 2
families = **72 pairs, 144 executions max** (~43% of the dead campaign).
Repetitions are **distinct instances** of the same template, so clustering is
at template level (12 strata of 6 correlated pairs). v3b's cross-run
determinism (5/10 tasks identical across runs) makes independent-pairs
assumptions indefensible; **the design does not claim pair independence and
does not rely on it for the PASS bar** (see the co-primary guard).

**[D1] Primary endpoint — honestly labeled:** **pooled pair-level exact
McNemar** (two-sided) over all receipt-backed pairs. The delta review proved
the REV 2 "stratified permutation" adds nothing (within-pair sign-flips with
a global statistic are numerically identical to pooled McNemar; strata are
inert) and that across-arm within-stratum permutation rests on false
exchangeability (strata mix families with different base rates). REV 3
therefore names the standard test as what it is and puts the cluster
protection where it is real: the floored template-level **co-primary guard**
plus the cluster-robust sensitivity analysis below.

**[D1/D2] Co-primary template guard (floored):** let d = number of
**discordant templates** (a template is discordant if, over its 6 pairs, it
has at least one evidence-only and at least one static-only pair). PASS
requires **d ≥ 4 AND strict majority of the d discordant templates are
evidence-only** (majority = ≥ ⌊d/2⌋+1 evidence-dominant templates, where a
template is evidence-dominant if its evidence-only pairs outnumber its
static-only pairs). If d < 4 the criterion **cannot PASS** — signal confined
to fewer than 4 templates is not corpus-general and yields INCONCLUSIVE
(insufficient template dispersion), whatever the pooled p-value.

**[D1] Cluster-robust sensitivity (required report, never sufficient for
PASS):** template-cluster design-effect analysis — pooled McNemar p re-scaled
by the observed design effect DE = 1+(m−1)ρ̂ with m=6 and ρ̂ the estimated
within-template correlation of pair outcomes; reported alongside the primary
in every results artifact, with the unguarded/ guarded distinction explicit.

**[R2] Power — disclosed by pre-freeze simulation, not asserted.** The exact
facts (verified in review): π=0.80 → power 0.8042 at n_d=20; π=0.75 → exact
power ≥0.80 first at n_d≈33–35 (crossing 0.8034 at n_d=30; 0.7125 at n_d=29);
N=72 (E[n_d]=28.8 at p_d=0.4) sits below the π=0.75 corner. Pre-freeze
calibration therefore includes a **Monte Carlo simulation of the JOINT
criterion's operating characteristics** (primary p + floored guard + family
rule) under clustered DGMs parameterized from v3/v3b observables, INCLUDING
adversarial concentration scenarios (all signal in 1–3 templates) that must
be shown to be rejected or rendered INCONCLUSIVE by the floored guard. The
freeze records: the simulated power curve, type-I behavior under
concentration, and the ICC/determinism assumptions (which are assumptions —
v3/v3b contains no repeated instances, and the cross-run determinism read is
wheel-confounded; recorded as limitations).

**[R2/D8] Pre-registered N-extension rule (one-shot):** at the interim look,
if futility is NOT triggered and conditional power <0.80 — CP computed under
the frozen simulation model with discordance parameters re-estimated by
method-of-moments from accumulated pairs, procedure text frozen at freeze —
N extends to 96 pairs (+1 distinct instance per template per family; 192
executions), **subject to explicit operator budget re-authorization in AK
before any extension execution**. One extension maximum. Extension triggers
only on LOW conditional power (conservative direction); final α is unchanged;
no other looks or N changes.

## 4. Pre-registered criterion (frozen before any execution)

- **PASS requires ALL of:** (i) pooled exact McNemar p<0.05 over receipt-backed
  pairs; (ii) majority of discordant pairs evidence-only; (iii) **[D2] d ≥ 4
  discordant templates AND strict majority of them evidence-dominant**;
  (iv) no family-level reversal (each family's evidence rate ≥ its static
  rate); (v) ≥70% of planned pairs receipt-backed.
- **FAIL** if (i)–(ii) hold inverted (static dominance) at p<0.05 with ≥70%
  completion AND the mirrored template guard holds (d ≥ 4, static-dominant
  majority). **All other outcomes: INCONCLUSIVE** — never PASS-by-default;
  INCONCLUSIVE does not damage the candidate, instrument, or G3 record; it
  records that this N could not decide.
- **[R3] Interim look at N=48 (one look):** cohort = first 2 instances of
  every template × both families (enrollment order pre-registered at freeze).
  Efficacy stop: pooled exact McNemar p<0.001 on the interim cohort —
  execution stops; final verdict computed on all accumulated receipt-backed
  data against the FULL frozen criterion (early stop never lowers the bar).
  Futility stop: discordant asymmetry ≤0.5 — execution stops; verdict
  **INCONCLUSIVE (futility)**; note the semantics: with few interim discordant
  pairs (n_d<8) a futility stop means insufficient information, not evidence
  of no effect, and the extension rule is unavailable after any stop by
  design. Interim α impact ≤~0.001; no other looks.
- **Single-variable requirement:** wheel = exactly EC-bound candidate-5
  (main@cde7f14, sha 921bff5e…, verified at freeze); no mid-run wheel
  changes; guidance rendered from that wheel only.
- **Advisor fallback:** glm-5.3 fallback responses recorded; pairs using them
  excluded from the primary analysis (sensitivity only), exclusion reported.
- **[R4/D6] Infrastructure-block rule (no substitution):** a blocked provider
  pauses its family; **"in-window" means: resume is allowed only while the
  frozen run wall-clock budget remains** (window frozen at freeze); if the
  window closes the run ends and completion is judged then. Blocked pairs
  have no substitutes; completion = receipt-backed pairs only; <70% →
  INCONCLUSIVE (infrastructure). Budget reconciles to receipts only;
  incidents ledgered as in v3b.
- **Execution guard:** AK 5092 runner hardening (in-flight pair guard,
  per-pair receipt idempotency) lands BEFORE execution — hard precondition.

## 5. Governance path

1. **EC-side (done):** candidate-5 bound + G3 reopened (AK 5096, commit
   145c889); the c981e7d fan-in already consumed 5059 as incomplete/
   null-signal; `g3-g5-consumption-note.md` is corroborating input only.
2. **DSPx-side (this act):** fresh decision accepting THIS protocol (REV 3),
   conditioned on the AK 5096 binding, carrying verbatim: the v3b confound,
   the construct boundary, and the enrichment disclosure (§1). Replaces
   superseded decision 137's intent (incident: AK evidence 7840).
3. **On acceptance:** freeze the successor protocol manifest (instance
   digests, checker shas, wheel identity, criterion text, enrollment order,
   CP re-fit procedure, simulation model + seed + assumptions) + pre-freeze
   calibration (reference Y=1 / stub Y=0 / tamper detection) + **the joint
   operating-characteristic simulation record (§3)**.
4. Execute under AK 5095; receipts v3-shape + family + run_label `successor`;
   interim look per §4; incidents ledgered.
5. **Gate consumption:** the successor campaign is the gate-grade event for
   the reopened G3; a new owner fan-in consumes its result. No producer gate
   claims.

**Explicit non-claims:** REV 3 is text until accepted and frozen; the
simulation-based power disclosure replaces any closed-form ≥0.80 claim;
nothing here grades candidate-4, candidate-5, or the AK-5082 fix.
