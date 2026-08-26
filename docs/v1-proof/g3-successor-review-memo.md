---
summary: "Independent adversarial review of the G3 successor campaign protocol: exact-McNemar power verified at pi=0.80 but overstated at pi=0.75 (0.7125 at n_d=29); pooled primary analysis ignores within-cell clustering (blocker); interim look and post-freeze substitution under-specified. Verdict: revise_rfc."
read_when:
  - "You are the DSPx decision owner accepting the G3 successor protocol and need the independent review before conditioned acceptance."
  - "You are freezing or amending g3-successor-campaign-design.md and need the required-change list."
type: "review-memo"
---

# Independent review memo — G3 successor campaign protocol

**Under review:** `docs/v1-proof/g3-successor-campaign-design.md` (DRAFT, as amended with
anti-circularity clauses and split governance), against the problem brief
(`g3-successor-problem-brief.md`), the evidence note (`g3-successor-evidence-note.md`),
the v3b results (`g3pilot-v3b-results.json`), and the EC-side binding
(`engineering-core/docs/project/2026-08-26-v1-g3-successor-binding.md`).

**Reviewer posture:** adversarial. I recomputed the power claims from first principles
(exact two-sided binomial/McNemar enumeration, no normal approximation), recomputed the
v3b descriptive statistics from `corpus_table`, and verified the EC-side git facts on disk.

---

## 0. What was verified independently (observed, not asserted)

1. **v3b results file is internally consistent.** Recomputed from `corpus_table`:
   overall evidence 7/10 = 0.7, static 5/10 = 0.5; fam-gpt 4/5 vs 2/5, fam-glm 3/5 vs 3/5;
   4 splits (A1, B1, B2 evidence-only; A3 static-only) — all match
   `results.overall`, `results.per_family`, `discrimination_verdict`, and the
   recovery/stability verdicts (A2 0→1, B2 0→1; C1 1→0). Observed discordance = 4/10 = 0.40
   and evidence-only share = 3/4 = 0.75 — the design's p_d=0.4 / π=0.75 inputs are the
   *observed* v3b values, not hypotheticals.
2. **Power table, π=0.80 row is correct.** Exact two-sided McNemar at n_d=20, π=0.80:
   power = 0.8042 (rejection region X≥15 or X≤5 of 20, realized α=0.0414). Verified by
   full enumeration.
3. **Power table, π=0.75 row is wrong for the exact test.** Exact power at n_d=29,
   π=0.75 = **0.7125** (rejection region X≥21 of 29, realized α=0.0241). The design's 29
   matches the *normal-approximation* formula, not the exact test the protocol
   pre-registers as its primary endpoint. Exact power ≥0.80 at π=0.75 first occurs at
   n_d=30 (0.8034 — razor-thin), robustly at n_d≈33–35.
4. **N=72 contradicts the design's own table at the conservative corner.** At p_d=0.4,
   N=72 gives E[n_d]=28.8 — below the table's own requirement of N=73 (n_d=29) at
   π=0.75, which itself yields only 0.7125 exact power. The claim "power ≥0.80 across the
   plausible π range with p_d=0.4" is false at that corner, and the corner is the observed
   v3b discordance.
5. **Interim-look α accounting is negligible.** At E[n_d]≈19.2 (N=48, p_d=0.4), two-sided
   exact p<0.001 requires ≥17/19 evidence-only; P(stop | H0) ≈ 0.0007. One look with this
   bar does not materially inflate type-I error; the futility stop can only reduce it.
   Under π=0.75, P(early efficacy stop) ≈ 11%; under π=0.80 ≈ 24%.
6. **EC-side git facts check out.** In `core/engineering-core`: `145c889` ("bind G3
   successor instrument to candidate-5; reopen G3 (AK #5096)"), `c981e7d` (G5 fan-in NOT
   READY, AK #4877), `bc43bb9` (candidate-4 freeze follow-up) all exist and match the
   documents' claims; the binding doc on disk states operator acceptance 2026-08-26.
7. **Referenced companion artifacts exist** (`g3-g5-consumption-note.md`,
   `g3-candidate-5-rebind-decision-input.md`, `g3pilot-harder-tasks.json`).

---

## Review question A — statistical validity

**Framing: sound.** The paired-binary design (unit = task×family pair, exact McNemar on
discordant pairs) is the correct test for matched binary arms, and the π/p_d
parameterization is standard. Inputs (π=0.75–0.80, p_d=0.4–0.5) are anchored to observed
v3b values (0.75, 0.40) rather than invented.

**Power claims: partially wrong.** See verification items 3–4. The π=0.80 corner is
correct; the π=0.75 corner is overstated (0.7125 exact vs claimed ≥0.80), and N=72 is
below the design's own table requirement at p_d=0.4. The table was computed with a normal
approximation while the pre-registered primary endpoint is the exact test, whose
discreteness both costs power and produces a sawtooth (e.g., n_d=28 → 0.7501 but n_d=29 →
0.7125) that a single-N plan should not paper over.

**Interim look: coherent in α, under-specified in execution.** One look, efficacy
p<0.001, futility at asymmetry ≤0.5 — no multiple-testing problem (item 5). But the
design does not state (a) which pairs constitute the first 48 (family/task balance of the
interim cohort), (b) that an early efficacy stop still requires PASS conditions
(ii)–(iv), or (c) what verdict a futility stop produces. The futility rule has a modest
false-stop risk at small realized n_d: P(share ≤ 0.5 | π=0.75) ≈ 11.4% at n_d=8, ≈ 0.9%
at n_d=19.

**The bigger validity problem is not in the table — it is clustering** (finding F1
below): 72 "pairs" are 24 task×family cells × 3 correlated repetitions, and the pooled
exact McNemar assumes pair independence. v3→v3b itself supplies evidence of strong
task-level determinism: 5/10 tasks produced *identical* (static, evidence) outcome pairs
across two independent runs that even differed by wheel (A1, B1, C2, C3, C4). If
repetitions of a frozen instance behave that deterministically, the effective sample size
is far below 72 and the pooled p-values are anti-conservative.

## Review question B — anti-circularity

The amendments neutralize **instance-level** circularity and **post-freeze
cherry-picking**: fresh derived instances with byte-identical reuse prohibited (rule 1);
difficulty-only promotion with static/reference pre-freeze calibration that never runs the
evidence arm (rule 2); A3-style hard cell retained *by rule* (conservative — biases
against PASS, a good property); no post-freeze drop/replace for arm asymmetry (rule 5).

**Residual channels, named precisely:**

1. **Template-level selection (real, partially disclosed).** The corpus is "the class A/B/C
   family templates from v3/v3b plus 2 harder variants" — a family/template set chosen
   because diagnostics showed it separates (§1 says this openly). The anti-circularity
   clause ("diagnostic arm outcomes may not be used to select, drop, or weight tasks")
   governs task-level decisions within that family; under a strict reading it is violated
   by rule 1 itself, under a loose reading it is silently family-scoped. Either way, the
   corpus is enriched at template level for structures that produced evidence-only splits
   (7 evidence-only vs 2 static-only across v3+v3b at task level). Consequence: expected π
   is plausibly inflated — which interacts with the power corner in F2 — while the
   *within-corpus* inference remains valid and the construct boundary covers
   generalization. The channel must be named in the decision text, not only the
   instance-level clauses.
2. **Derivation-knowledge channel (mitigated).** Whoever materializes "fresh instances,
   difficulty re-targeted" knows which structural features produced splits. The
   static-mid-range saturation guard is direction-blind and mitigates this, but nothing
   verifies derivation neutrality beyond the guard.
3. **Post-freeze substitution (undefined, must be closed).** Rule 5 references "the
   pre-registered infrastructure-block substitution," which is defined nowhere; §4's
   infrastructure-block rule is pause/resume with *no* substitution. An undefined
   substitution mechanism is an unbounded post-freeze replacement channel — the exact
   thing the anti-circularity section exists to prevent.

## Review question C — criterion integrity

**PASS can be misleading under clustering.** Concrete pattern: 6 cells contribute all-3-reps
evidence-only (18 e-only discordants from 6 independent clusters) vs 6 static-only → pooled
p ≈ 0.023, conditions (i)–(iv) met → PASS, while cluster-aware evidence is far weaker.
This is the executable form of F1 and the single most plausible "flaw that survives."

**Early-stop verdict mapping is unspecified.** If "stop for efficacy at p<0.001" is read as
PASS without conditions (ii)–(iv) at interim, a PASS could be declared without the
family-reversal or completion checks. Must be closed before freeze.

**Family concentration passes.** Condition (iii) blocks reversals, not concentration: a
PASS driven entirely by fam-gpt with fam-glm exactly tied is protocol-valid. Not misleading
per the construct, but the decision record should report per-family discordant
contributions.

**FAIL is symmetric and completion-gated; INCONCLUSIVE-default is sound.** Static
dominance at p<0.05 with ≥70% completion, everything else INCONCLUSIVE, "never
PASS-by-default" — this is the right shape and I found no PASS-by-default path. The ≥70%
completion requirement plus "no partial arms count" correctly encodes the v3b mid-arm-kill
lesson; the remaining hole is the undefined substitution (F4), which could otherwise
rescue a completion shortfall post hoc.

## Review question D — construct boundary

Honestly stated and it travels. §1 names it ("convention-conformance lift … necessary,
not sufficient … this sentence travels into the decision record unchanged"), §5.2 requires
it "verbatim" in the DSPx decision, the problem brief carries it as constraint 2, and the
EC binding repeats it ("travels unchanged"). One nit: the EC binding's text is a
paraphrase; at freeze, pin the exact sentence so "verbatim" is checkable. No finding
beyond that — this dimension is done well.

## Review question E — governance

Coherent with the artifacts read, and verified where verifiable:

- Split routing matches: EC binds candidate-5 + reopens G3 (AK 5096 / commit `145c889`,
  operator "accept both" — verified on disk); DSPx accepts the protocol *conditioned on*
  that binding via a fresh decision replacing superseded decision 137 (incident disclosed,
  evidence 7840); carrier AK decision with `rfc_ref`; execution gated on AK 5092; release
  under #5095. Sequencing (EC → DSPx conditioned decision → 5092 hardening → execute) is
  stated and consistent with the EC doc's "Companion DSPx-side acceptance" framing.
- Owner boundaries: no violation found. DSPx disclaims gate authority ("gate consumption
  is an owner act (new fan-in), never a producer claim"); the design's step-1 description
  of EC-side action is routing context, not DSPx executing another owner's surface; G5's
  closed record is not edited, only re-consumed by a future fan-in.
- Limit: AK runtime states (5092 open, 5096 done, evidence 7839/7840/7841) were not
  queried directly; I relied on the documents plus git verification of the EC commits.
- Editorial defect with governance weight: §5 has two steps numbered "3" — in a document
  whose freeze step cites criterion/governance text into a manifest, numbering ambiguity
  is not cosmetic.

## Review question F — operational encoding of v3b lessons

Adequately encoded, with gaps:

- **429 stall → §4 infrastructure-block rule** ("blocked family pauses, resumes
  in-window; no partial arms count; budget reconciles to receipts only") — matches the
  v3b handling (pause at 07:10Z, resume 18:26Z after provider probes, counter reset to
  receipt-backed count). Gap: "in-window" is undefined; v3b used a concrete 21600 s wall
  budget and lease expiry — the successor doc should state the window and lease rules it
  will use.
- **Duplicate-session race → AK 5092 in-flight pair guard as a hard execution
  precondition** — matches the exact failure mode (two runner processes racing pair
  PL3-B1). Gap: the guard prevents pair corruption, not duplicate *sessions*; the v3b root
  cause was a controller watcher spawning an uncoordinated resume session. Wasted
  executions/budget (3 in v3b) recur unless session-level exclusivity is also required.
- **Duplicate receipt → per-pair receipt idempotency (AK 5092)** — matches the quarantined
  B1 duplicate-receipt incident and the one-receipt-per-pair invariant that had to be
  restored manually.
- Limit: AK 5092's actual contents were not inspected; "must land BEFORE execution" is the
  right gate shape, but this review cannot confirm the hardening covers both guard types.

---

## Findings (ranked by consequence, with severity and confidence)

| # | Finding | Severity | Confidence | Evidence |
|---|---|---|---|---|
| F1 | Pooled exact McNemar treats 72 pairs as independent; they are 24 task×family cells × 3 correlated reps. Positive within-cell correlation (supported by 5/10 identical v3→v3b outcome pairs across a wheel change) makes pooled p-values anti-conservative → plausible misleading PASS. | **blocker** | high (mechanism), med-high (magnitude; ρ unmeasured) | design §3 ("12 tasks × 2 families × 3 repetitions", "pooled exact McNemar over all discordant pairs"); v3b `per_task_comparison` |
| F2 | Power claim false at the conservative corner: exact power at n_d=29, π=0.75 is 0.7125 (not ≥0.80); N=72 < own table's N=73 at p_d=0.4; table uses normal approximation while the pre-registered test is exact. | must-fix | high (verified by enumeration) | design §3 table + "power ≥0.80 … with p_d=0.4" |
| F3 | Interim look under-specified: interim cohort composition undefined; early-efficacy verdict mapping (does PASS require (ii)–(iv) at interim?) unstated; futility-stop verdict unstated. | must-fix | high (omission is in the text) | design §3, §4 |
| F4 | "Pre-registered infrastructure-block substitution" (§2 rule 5) is defined nowhere and contradicts §4's no-substitution pause/resume rule — an undefined post-freeze replacement channel. | must-fix | high (textual contradiction) | design §2.5 vs §4 |
| F5 | Anti-circularity clause scope conflicts with rule 1's template promotion (family-level choice rests on diagnostic separation); template-level enrichment not carried into the decision payload. | must-fix | high (textual), medium (direction of bias: inflates expected π) | design §1, §2.1, §2.5 |
| F6 | Editorial defects a frozen manifest would inherit: duplicate step "3" in §5; §2 rules 4/5 merged on one line; "in-window" undefined; construct boundary "verbatim" not pinned to an exact sentence. | must-fix (pre-freeze editorial pass) | high (visible in text) | design §2, §4, §5 |
| F7 | Futility false-stop risk at small realized n_d (≈11% at n_d=8, π=0.75); combined with F2 the realistic inconclusive risk at the corner is material — decision text should set expectations. | observe | high (computed) | design §3 |
| F8 | PASS may concentrate in one family (condition (iii) blocks reversal, not concentration); per-family contributions should be reported. | observe | high | design §4 |
| F9 | AK 5092 pair guard does not prevent duplicate sessions (v3b root cause), only pair corruption; session-level exclusivity unaddressed. | observe | medium | v3b incidents; design §4 |
| F9p | Positive findings: INCONCLUSIVE-default sound; no PASS-by-default path found; hard-cell retention conservative; multiple-testing negligible (≈0.0007 interim α); construct boundary travels; v3b evidence base internally consistent and honestly reconciled (24 invocations vs 20 receipts, quarantined duplicate receipt verbatim). | observe (positive) | high | design §1/§4; v3b `budget_honesty`, `incidents` |

**Blockers:** F1. **Must-fix:** F2–F6. **Observe:** F7–F9p. Under the dispatch rules
(must-fixes requiring document changes ⇒ revise), the verdict follows.

## Exact required changes (for revise_rfc)

1. **(F1, blocker)** Amend §3/§4: declare a cluster-aware primary analysis at the
   task×family level (24 cells) — e.g., exact sign test on cell-level discordance
   indicators (majority across reps), or a permutation test stratified by cell — *or*
   (weaker) keep pooling but justify pair-level independence with a measured within-cell
   correlation from pre-freeze calibration reps AND pre-register the cell-level test as a
   mandatory co-primary/sensitivity analysis. Recompute N and power under whichever
   analysis is chosen.
2. **(F2)** Recompute the §3 table with exact two-sided McNemar powers (label the method);
   correct the "power ≥0.80 across the plausible π range with p_d=0.4" sentence. Either
   raise N (unclustered exact ≥0.80 at π=0.75 needs n_d≥30 ⇒ N≥75 at p_d=0.4; more under
   change 1) or state the corner power honestly (≈0.71 unclustered, lower clustered).
3. **(F3)** Specify the interim look: (a) deterministic family-balanced composition of the
   first 48 (e.g., all 3 reps of the first 8 tasks × both families); (b) an early
   efficacy stop yields PASS only if §4 conditions (ii)–(iv) hold at interim; (c) a
   futility stop yields INCONCLUSIVE.
4. **(F4)** Define the infrastructure-block substitution exactly (trigger, selector,
   difficulty-only/arm-blind constraints, source = pre-frozen harder-tasks line, numeric
   cap) or delete the phrase and rely on §4 pause/resume only.
5. **(F5)** State the anti-circularity clause's scope (task-level within the chosen
   family), and add the template-level-enrichment caveat to the verbatim decision-text
   payload alongside the construct boundary.
6. **(F6)** Pre-freeze editorial pass: fix §5 duplicate "3" numbering; separate §2 rules
   4/5; define the resume window and lease rules (v3b precedent: 21600 s wall budget,
   lease expiry); pin the exact construct-boundary sentence as the verbatim payload;
   add session-level exclusivity to the AK 5092 gate or §4 (F9) while at it.

## Coverage limits (what this review did NOT inspect)

- AK runtime state (tasks 5092/5095/5096, decisions 132/137, evidence 7839/7840/7841,
  task scopes) — relied on the four documents plus EC git verification of `145c889`,
  `c981e7d`, `bc43bb9`.
- Contents of `g3pilot-harder-tasks.json`, `g3-g5-consumption-note.md`,
  `g3-candidate-5-rebind-decision-input.md`, the 5059 campaign results JSON, and the v3
  results JSON — existence confirmed only.
- Runner/harness code and AK 5092 hardening contents.
- Unconditional power integrating over the distribution of realized n_d (computed at
  E[n_d]; the exact-test sawtooth makes single-point planning fragile, which is itself
  part of F2).
- Nothing was executed, frozen, or mutated beyond writing this memo.

VERDICT: revise_rfc

---

## Delta re-review (REV 2) — 2026-08-26

**Input:** `g3-successor-campaign-design.md` REV 2 (post-review draft), re-read in full.
**Method:** finding-by-finding verification against REV 2 text; independent recomputation
of every number REV 2 now cites plus the new machinery it introduces (permutation scheme,
guard edge cases, extension rule). The REV 1 verdict line above is historical; the
current verdict is the final line of this section.

### Structural checks (arithmetic and editorial, verified)

- 12 templates × 3 distinct instances = 36 instances; × 2 families = 72 pairs / 144
  executions ✓. Interim cohort = first 2 instances × 12 templates × 2 families = 48 ✓.
  Extension = +1 instance per template = +12 instances = +24 pairs → 96 pairs / 192
  executions ✓ ("48 instances" ✓).
- §5 numbering fixed (1–5, no duplicate "3") ✓; §2 rules 4/5 separated ✓; FAIL symmetry
  retained (i)–(iii) inverted ✓; INCONCLUSIVE-default preserved with labeled sub-types
  (futility / infrastructure) ✓; construct-boundary sentence in §1 marked as traveling
  unchanged ✓.

### F1 (blocker → residual must-fix): clustering — substantially addressed, NOT fully neutralized

**What REV 2 does that works:** repetitions are now distinct derived instances (real
structural change; clustering honestly relocated to template level, "12 strata of 6
pairs"); the design explicitly concedes "treating pairs as independent [is] indefensible,
and the design does not claim it"; and the mandatory co-primary guard (iii) — "a PASS can
never rest on pooled pairs contradicting the strata" — blocks the specific false-PASS
patterns from the REV 1 memo (my REV 1 example of 6 e-dominant vs 6 s-dominant clusters is
now a 6–6 tie, not a majority → INCONCLUSIVE). The blocker is downgraded.

**Residual defect D1 (must-fix): the "cluster-aware" label is not delivered by the primary
test itself, in either coherent reading of the spec.** REV 2 §3: "stratified exact test
over the 12 template strata — arm-label permutation within stratum (…), test statistic =
summed within-pair arm difference. Exact under the null of no arm effect given
within-stratum exchangeability."

- Reading A (arm-label permutation **within pair**, i.e., sign flips): for a *global*
  summed-difference statistic the strata are inert — the reference distribution is exactly
  the binomial(n_d, 0.5) sign distribution, i.e., **identical to pooled exact McNemar**.
  Verified numerically: on a clustered dataset (10 e-only pairs from one template-pair
  group, 2 s-only from another) the stratified sign-flip MC p = 0.0383 vs exact McNemar
  p = 0.0386 (MC noise). Under this reading the REV 1 defect (correlated flip directions
  across the 6 pairs of a template under the null → anti-conservative reference) is
  unchanged, merely relabeled "stratified."
- Reading B (permuting arm labels **among the 12 arms within a stratum**): strata now
  matter, but "within-stratum exchangeability" is false — a stratum's 6 pairs are
  3 instances × 2 **families**, and v3b itself measured family heterogeneity
  (fam-gpt static 0.4 vs fam-glm static 0.6), plus instances are *individually*
  difficulty-re-targeted. Mixing family/instance arms in the permutation group breaks the
  exchangeability the test's exactness claim rests on (dominant effect: reference-variance
  inflation → conservative → power loss, elevated INCONCLUSIVE risk; level not guaranteed).

Either way the sentence "Exact under the null … given within-stratum exchangeability" is
unsupportable as written, and the freeze manifest records "criterion text" — freezing an
ambiguous primary endpoint leaves the implementation to be chosen at analysis time, which
is exactly the researcher degree of freedom pre-registration exists to remove.

**Residual defect D2 (must-fix): the guard — the only element actually carrying cluster
protection — is under-defined and has no minimum floor.** "Majority of discordant
TEMPLATES evidence-only (template-level sign test on discordant strata)":

- "Discordant template" is undefined (≥1 discordant pair? non-zero summed sign?).
- Template-level sign on a 3–3 within-template split is a tie — uncounted how?
- **No minimum number of discordant templates.** Demonstrated hole: 2 discordant
  templates, 10 e-only vs 2 s-only pairs → exact McNemar p = 0.0386 < 0.05, majority of
  discordant pairs ✓, majority of discordant templates = 2/2 ✓ → all of (i)–(v) can be
  satisfied with the entire signal coming from **2 clusters**. A gate PASS resting on 2
  templates is the clustered false-positive shape F1 was about, at reduced but real
  plausibility.

Net: F1's blocker is neutralized **only if** D1 + D2 are fixed; the mandatory conjunction
now bounds the false-PASS risk, so these are must-fixes, not a blocker.

### F2 (power): resolved — honest and sufficient, with two observes

REV 2 withdraws the closed-form claim, reproduces the exact facts this review verified
(π=0.80/n_d=20 → 0.8042; n_d=29 → 0.7125; N=72 below the π=0.75 corner at p_d=0.4), and
replaces assertion with a pre-freeze Monte Carlo power simulation under a clustered DGM
recorded at freeze, with "claims only what the simulation supports" and a one-shot
pre-registered extension (72→96, operator budget re-authorization in AK). This is the
right shape. Observes:

- **D3a (observe):** the DGM's clustering parameters are assumption-driven, not
  identified. v3/v3b contain **no repeated instances of a template** (one instance per
  task per run), and the cross-run comparison is confounded by the wheel change — so
  "fraction of deterministic tasks" and any within-template ICC are assumptions. Freeze
  should record the power **curve across an assumption grid**, labeled as such, not only
  "the point estimate at the target effect."
- **D4 (observe, accuracy nit):** REV 2 states exact power ≥0.80 at π=0.75 "first occurs
  at n_d≈33–35." First occurrence is actually n_d=30 (0.8034, razor-thin; 31 → 0.7710);
  33 is the first *stable* crossing (0.8190). The omission is in the conservative
  direction (implies needing more pairs), but the sentence should match the verified
  sawtooth facts it cites.
- **Extension-rule optional stopping (checked, clean):** extension triggers on **low**
  conditional power (unpromising direction), one-shot, final α fixed at 0.05 with no
  threshold change → α inflation negligible (conservative selection); the interim
  efficacy stop adds ≤~0.001. No optional-stopping bias found. **D3b (observe):** the CP
  "re-fit to accumulated data" procedure (which parameters re-fit, how) must be
  pre-registered at freeze, else it is a degree of freedom; and note the gap that CP ≥0.80
  at interim locks in N=72 even if the frozen simulation showed power <0.80 at 72 — the
  disclosed-remedy path only fires on low CP. Consider a freeze-time default-extend rule
  if simulated power at 72 is <0.80.

### F3 (interim look): resolved

Cohort defined (first 2 instances × every template × both families — balanced across all
strata; enrollment order pre-registered at freeze); early efficacy stop computes the
verdict on accumulated data against the **full** frozen criterion ("an early stop never
lowers the PASS bar"); futility → **INCONCLUSIVE (futility)**, recorded. Sufficient.
Residual observe **D6**: futility at small realized n_d has false-stop risk
(P(asymmetry ≤ 0.5 | π=0.75) ≈ 11% at n_d=8, ≈ 17% at n_d=6 — recomputed), and because
the extension rule requires "futility is not triggered," a noise-level futility stop also
**forecloses the extension remedy**. Consider requiring a minimum realized n_d before the
futility rule is active.

### F4 (substitution): fully resolved

"NO post-freeze substitution channel of any kind"; blocked pairs have no substitutes;
completion measured on receipt-backed pairs only; <70% → INCONCLUSIVE (infrastructure).
The REV 1 undefined-substitution channel is closed; the cost (blocks can only reduce
completion) is honestly priced as INCONCLUSIVE, never as post-hoc corpus surgery.
Residual observe **D3c**: "resumes in-window" survives a second review still undefined —
the resume window/lease rules (v3b precedent: 21600 s wall budget, lease expiry) must be
a named freeze-record item.

### F5 (anti-circularity scope): partially addressed — observe

REV 2 now states the arm-direction-blind rule applies at "template selection, instance
derivation, and any difficulty-based replacement." But this sharpens rather than resolves
the REV 1 tension: §1 selects the convention-space family *because* it separates
("The convention-space task family (v3/v3b) separates"), while rule 5 says "diagnostic
arm outcomes may not select … templates." Both are true only if "arm-direction-blind"
means blind to *direction*, not to *existence of separation* — say so explicitly. And the
template-level-enrichment caveat still is not in the decision payload (§5.2 carries only
"the v3b confound and the construct boundary verbatim"). The construct boundary arguably
subsumes it; one sentence in the payload would close it cleanly. Observe **D5**.

### F6–F9 residuals

- §5 numbering and §2 rule separation: fixed ✓. "In-window": still undefined (→ D3c).
- **D7 (observe):** advisor-fallback pairs are "excluded from the primary analysis" but
  are receipt-backed — clarify whether they count in the ≥70% completion denominator
  (analysis N vs completion N can then diverge; exclusion is exogenous missingness, so no
  direction bias, but the denominator must be unambiguous at freeze).
- **D8 (observe):** session-level exclusivity (REV 1 F9) still absent from the AK 5092
  gate ("in-flight pair guard, per-pair receipt idempotency"). The pair guard plausibly
  contains the *consequence* of a duplicate session (second session cannot race an
  in-flight pair), but the v3b budget-waste mode (3 discarded executions) is unaddressed.

### Findings (delta), ranked

| # | Finding | Severity | Confidence |
|---|---|---|---|
| D1 | Primary test spec ambiguous/mislabeled: within-pair reading ≡ pooled exact McNemar (strata inert — numerically shown), across-arm reading rests on false within-stratum exchangeability (family/instance heterogeneity); "Exact … cluster-aware" claim unsupportable as written; freeze would bake the ambiguity into criterion text | **must-fix** | high |
| D2 | Co-primary guard (the real cluster protection) under-defined: no discordant-template minimum (2-cluster PASS path demonstrated at p=0.0386), tie rule undefined, "discordant template" undefined | **must-fix** | high |
| D3 | Freeze-record gaps: CP re-fit procedure, resume window/lease rules, simulation assumption grid (ICC/determinism are assumptions — v3/v3b has no repeated instances and the cross-run read is wheel-confounded) | observe (pre-freeze condition) | high |
| D4 | "First occurs at n_d≈33–35" omits the verified n_d=30 crossing (0.8034); conservative direction but should match cited facts | observe | high |
| D5 | Rule-5 vs §1 scope tension (direction-blind ≠ separation-blind) unresolved in wording; enrichment caveat absent from decision payload | observe | high |
| D6 | Futility false-stop at small n_d (≈11% at n_d=8) and it forecloses the extension remedy; no minimum-n_d activation rule | observe | high |
| D7 | Advisor-fallback pairs: completion-denominator ambiguity (receipt-backed but analysis-excluded) | observe | high |
| D8 | No session-level exclusivity in the AK 5092 gate (v3b budget-waste mode) | observe | medium |
| D9 | Positive: F3/F4 fully resolved; F2 honestly replaced by simulation + one-shot conservative-direction extension (no optional-stopping bias found); arithmetic and editorial fixes verified; blocker-grade false-PASS patterns from REV 1 are blocked by mandatory guard (iii) | observe (positive) | high |

**Blockers: none. Must-fix: D1, D2.** Both require document changes before the manifest
freeze (the freeze records criterion text; an ambiguous primary endpoint cannot be left
to analysis-time choice). Observes D3–D8 may stand as recorded pre-freeze conditions.

### Exact required changes (REV 3, minimal)

1. **(D1)** Specify the primary permutation exactly. Either: (a) within-pair arm-label
   sign flips — and state plainly that for the global summed-difference statistic this is
   distributionally identical to pooled exact McNemar (strata inert), so the cluster
   protection lives in guard (iii); or (b) a genuinely stratum-engaging statistic (e.g.,
   sum of stratum-mean differences with sign flips) with its own simulation-backed power.
   Delete or qualify "Exact … given within-stratum exchangeability" (false for families/
   instances within a stratum; unnecessary for the within-pair reading). Apply the same
   fix to the interim efficacy test.
2. **(D2)** Define the guard: template sign = sign of the summed within-pair differences
   over its 6 pairs; discordant template = sign ≠ 0; PASS requires **≥K discordant
   templates** (recommend K=4) **and** strict majority evidence-only; fewer than K
   discordant templates → INCONCLUSIVE regardless of pooled p (closes the demonstrated
   2-cluster PASS path). Mirror the definition in the FAIL clause.

### Coverage limits (delta pass)

- Re-read REV 2 of the design doc only; problem brief, evidence note, v3b results, and EC
  binding were not re-opened except where cited above (numbers re-verified from the REV 1
  session's computations and fresh recomputation).
- AK runtime state (5092/5095/5096, decision 137, evidence records) still not queried
  directly; AK 5092 hardening contents still uninspected.
- The Monte Carlo power simulation does not yet exist (it is a pre-freeze artifact); its
  adequacy is assessed as a *plan*, not as executed output. Same for enrollment order,
  corpus instance derivations, and the CP re-fit procedure.
- No formal proof was produced for reading-B's conservativeness (directional argument
  from family-mixing variance inflation only); the must-fix does not depend on it — the
  spec defect stands under both readings.

VERDICT: revise_rfc

---

## Delta re-review (REV 3) — 2026-08-26

**Input:** `g3-successor-campaign-design.md` REV 3, re-read in full. **Method:** finding-by-
finding verification; independent recomputation of the floored guard's edge cases (exact
McNemar p for at-floor patterns, majority thresholds, tie determinism); grep for residual
"stratified/permutation" language in criterion roles. Verdict logic per dispatch: D1 and
D2 resolved ⇒ `ready_for_adr`; observes may remain as recorded pre-freeze conditions.

### Structural checks (verified)

- Revision history accurately restates both prior rounds' findings (no strawmanning of
  the memo) ✓. Corpus arithmetic unchanged and correct (36 instances / 72 pairs / 144
  executions; interim 48; extension 96 / 192) ✓.
- **No residual "stratified permutation" in any criterion role:** the only three
  occurrences (lines 15, 78, 80) are the revision history and the D1 explanation of why
  it was dropped; §4 interim efficacy stop now reads "pooled exact McNemar p<0.001,"
  consistent with the new primary ✓.
- §1 adds the enrichment disclosure and marks it as traveling into the decision record;
  §5.2 lists it in the verbatim payload ("the v3b confound, the construct boundary, and
  the enrichment disclosure") — **D5 closed** ✓.

### D1 — resolved

Primary endpoint is now unambiguous and honestly labeled: "pooled pair-level exact
McNemar (two-sided) over all receipt-backed pairs," with the clustering concession
("makes independent-pairs assumptions indefensible") carried in §3, the mislabeled
permutation machinery removed with an accurate account of why (matching this review's
numerical finding), and cluster protection relocated to two explicitly scoped
instruments: the floored co-primary guard (necessary for PASS) and the design-effect
sensitivity ("required report, never sufficient for PASS") — the non-sufficiency is
stated verbatim, so the sensitivity cannot leak into the verdict ✓.

Wording nit **N1 (observe)**: "the design … does not rely on [pair independence] for the
PASS bar" slightly overclaims — condition (i) *is* the independence-based test; the
accurate statement is that the PASS bar does not rely on it *alone* (the guard carries
the cluster protection). One clause at freeze; does not reintroduce ambiguity into the
endpoint itself.

### D2 — resolved; one design-limit observe

Definitions are now fully determined at every edge:

- discordant template = "at least one evidence-only and at least one static-only pair
  over its 6 pairs" (operational, count-based) ✓;
- evidence-dominant = evidence-only pairs strictly outnumber static-only ✓;
- floor: d ≥ 4; majority = ⌊d/2⌋+1 (verified for d=4…12: 3,3,4,4,5,5,6,6,7) ✓;
- ties within a template (e.g., 3e/3s) count in d but in neither dominant count — every
  configuration resolves deterministically (checked: d=5 with 2 e-dom, 1 s-dom, 2 tied →
  needs 3 → fails; d=4 with 3 e-dom + 1 tied → 3 ≥ 3 → eligible) ✓;
- d < 4 ⇒ cannot PASS ⇒ INCONCLUSIVE (insufficient template dispersion) ✓;
- FAIL mirror stated (d ≥ 4, static-dominant majority) — symmetric, so static-side
  concentration is likewise confined to INCONCLUSIVE ✓.

Degenerate-pattern checks (computed): the round-2 demonstrated 2-cluster PASS path is
**blocked** (12 vs 0 discordant pairs from 2 templates: pooled p = 0.0005 but d = 2 < 4 →
INCONCLUSIVE) ✓. The pattern the dispatch names — exactly 4 discordant templates, 3
evidence-dominant — **remains PASS-eligible by design** (that is what a floor of 4
permits): minimal-margin variant 3×(4e/0s) + 1×(0e/3s) → n_d=15, pooled p = 0.0352, all
of (i)–(v) satisfiable; large-margin variant 18 vs 6 → p = 0.0227. This is the guard's
declared protection limit, not a defect: **N2 (observe)** — the mandated adversarial
simulation set ("all signal in 1–3 templates") should be extended at freeze to include
*exactly-at-floor* d=4 scenarios (both minimal- and large-margin) and clustered nulls
with ICC > 0, so the recorded type-I behavior covers the weakest cell the criterion
actually admits.

### D6, D8, and the simulation mandate

- **D6 — resolved.** "In-window" = "resume is allowed only while the frozen run
  wall-clock budget remains"; window frozen at freeze; window close ends the run and
  completion is judged then; <70% → INCONCLUSIVE (infrastructure). Determined ✓. Nit
  **N3 (observe)**: §5.3's manifest enumeration (instance digests, checker shas, wheel,
  criterion text, enrollment order, CP re-fit procedure, simulation model) does not name
  the wall-clock budget value — add it so "window frozen at freeze" is checkable.
- **D8 — resolved.** CP = frozen simulation model with discordance parameters re-estimated
  by method-of-moments from accumulated pairs; "procedure text frozen at freeze"; §5.3
  lists the CP re-fit procedure in the manifest ✓. Residual **N4 (observe)**: MoM
  estimates at n=48 (E[n_d]≈19 at p_d=0.4) are noisy; because the rule is one-shot and
  thresholded this is tolerable, but the freeze should record the estimator's behavior
  near the 0.80 boundary (and note the round-2 D3b gap persists structurally: CP ≥ 0.80
  at interim locks N=72 even if the frozen simulation showed power < 0.80 there — though
  in that regime low CP is the likelier outcome, partially self-correcting).
- **Joint-criterion simulation — closes the flagged gap.** REV 3 mandates Monte Carlo
  operating characteristics of the *joint* criterion (primary p + floored guard + family
  rule) under clustered DGMs, with adversarial concentration scenarios "that must be
  shown to be rejected or rendered INCONCLUSIVE by the floored guard," recording the
  power curve, type-I under concentration, and the ICC/determinism assumptions
  explicitly labeled as assumptions (correctly noting v3/v3b contains no repeated
  instances and the cross-run determinism read is wheel-confounded) ✓. This supersedes
  single-number power claims and is the right instrument. **N2** above extends its
  scenario set; **N5 (observe)**: record the power curve across an assumption *grid*
  (ICC × determinism), not only at point assumptions — round-2 D3a remains partially
  open in wording.
- Futility semantics now disclosed (n_d<8 ⇒ "insufficient information, not evidence of
  no effect") and extension-unavailability-after-any-stop stated as by-design ✓ — round-2
  D6 residual accepted as disclosed.

### New defects introduced by REV 3 (checked for)

**N6 (observe, pre-freeze condition): the DE sensitivity computation is not canonically
defined for an exact test.** "Pooled McNemar p re-scaled by the observed design effect
DE = 1+(m−1)ρ̂, m=6" — an exact test has no variance parameter to rescale; "re-scaled p"
has no standard meaning (candidate readings: exact test recomputed at effective
n_d/DE with observed proportions; asymptotic χ² deflated by DE). Because the report is
explicitly non-sufficient for PASS this cannot corrupt a verdict, but the manifest
freezes "criterion text," and a frozen-but-undefined advisory procedure invites
analysis-time improvisation. Pin the computation (and the ρ̂ estimator for binary
pair outcomes at template level) at freeze.

No other new defects found: FAIL symmetry, family-reversal and completion conditions,
INCONCLUSIVE-default (with the three labeled sub-types), single-variable requirement,
advisor-fallback exclusion, no-substitution rule, and AK 5092 hard gate are all carried
forward intact; arithmetic verified.

### Findings (round 3), ranked

| # | Finding | Severity | Confidence |
|---|---|---|---|
| N1 | "Does not rely on [independence] for the PASS bar" overclaims; (i) is still the independence-based test — say "not … alone" | observe | high |
| N2 | Adversarial simulation set covers 1–3-template concentration only; extend to exactly-at-floor d=4 (minimal + large margin) and clustered nulls ICC>0 — the at-floor PASS paths are computed and real | observe | high |
| N3 | Wall-clock budget value absent from the §5.3 manifest enumeration | observe | high |
| N4 | CP MoM re-fit noisy at n=48; record boundary behavior; structural D3b gap (CP≥0.80 locks N=72) persists, partially self-correcting | observe | medium |
| N5 | Record power curve across an ICC × determinism assumption grid, not point assumptions only (D3a wording still open) | observe | high |
| N6 | DE sensitivity "p re-scaled by DE" undefined for an exact test; pin computation + ρ̂ estimator at freeze (advisory-only, non-sufficient) | observe | high |
| N7 | Positive: D1/D2 resolved cleanly (2-cluster path blocked numerically; guard deterministic at every edge; FAIL mirrored); enrichment disclosure now travels into the decision payload; no residual mislabeled machinery anywhere in a criterion role; revision history restates prior findings accurately | observe (positive) | high |

**Blockers: none. Must-fixes: none.** D1 and D2 are resolved; N1–N6 are recorded
pre-freeze conditions (freeze-record contents and one wording clause), none requiring
revision of the accepted protocol's decision-relevant structure.

### Required at freeze (conditions, not document revisions)

1. (N2) Extend the joint-criterion simulation's adversarial set to exactly-at-floor d=4
   patterns and clustered nulls with ICC > 0; record type-I there.
2. (N6) Define the DE-adjusted sensitivity computation and the ρ̂ estimator precisely in
   the frozen criterion text.
3. (N3) Add the run wall-clock budget to the frozen manifest enumeration.
4. (N1) Apply the "not … alone" wording clause to §3.
5. (N4/N5) Record CP estimator boundary behavior and the assumption-grid power curve.

### Coverage limits (round 3)

- REV 3 of the design doc only; companion documents, v3b results, EC binding, and AK
  runtime (5092/5095/5096, decision 137, evidence records) not re-inspected this pass;
  AK 5092 hardening contents remain uninspected.
- The joint-criterion simulation, corpus derivations, enrollment order, and CP procedure
  text are pre-freeze artifacts assessed as *plans*; their executed adequacy is outside
  this pass and should be checked at the freeze review.
- Guard determinism was verified analytically over all edge configurations (tied
  templates, at-floor majorities), not by exhaustive enumeration of all 2^72 outcome
  tables; the analytic argument is closed-form (counts and strict inequalities), so this
  is sufficient.
- No repository state was mutated beyond appending this section to this memo.

VERDICT: ready_for_adr
