---
summary: "Target synthesis architecture for DSPx: V9-compatible core, V7-first implementation posture."
read_when:
  - "You are changing module generation, synthesis runtime boundaries, or higher-order automation posture."
  - "You need dated references for V7, V8, and V9 architecture terms."
---

ADR 20260322 — Synthesis Architecture V7-V9
===========================================

Status
------
Accepted

Context
-------
DSPx has reached the point where its next architectural wave is no longer provider plumbing alone.

The repo now has:
- provider/runtime explicitness good enough to run real mixed-provider optimize proofs,
- replay/explain receipts and provenance checks,
- Oracle Phase C foundations for behavioral history,
- a strong core-first boundary.

But `module-gen` is still effectively template-first, and the architecture needed to move from deterministic scaffolds toward evaluated/promoted synthesis is only implicit.

We need a durable reference for three terms that were previously discussed but not recorded in a date-stamped repo decision:
- **V7**
- **V8**
- **V9**

Decision
--------
Adopt the following target architecture vocabulary and implementation posture.

## Implementation posture

DSPx will **architect the synthesis core for V9 compatibility while implementing V7 behavior first**.

That means the first implementation slices must make these seams explicit now:
- synthesis intent/request contracts,
- structured intermediate representations (IR),
- candidate records and lineage,
- evaluation contracts,
- named/versioned selection and promotion policies,
- evidence/receipt recording for candidate outcomes.

It does **not** mean shipping V8 or V9 behavior immediately.

## V7 — operational synthesis runtime

V7 is the first operational synthesis architecture.

A V7-capable DSPx flow can:
- generate one or more candidate artifact specs,
- render artifacts deterministically from those specs,
- evaluate candidates through explicit checks,
- select the best passing candidate through a named policy,
- promote the selected artifact through an explicit boundary,
- record enough evidence to explain why that artifact won.

The first repo-local V7 consumer should be `module-gen`.

## V8 — predictive / evidence-aware synthesis

V8 adds a predictive layer on top of V7.

A V8-capable DSPx flow can:
- retrieve receipts, replay outputs, and Oracle history as evidence,
- estimate which candidates are most promising before expensive execution,
- prune or rank candidate work using priors/uncertainty instead of brute force alone.

V8 depends on V7 because predictive ranking is only trustworthy when candidate/evaluation receipts already exist.

## V9 — governed self-evolving synthesis

V9 adds governed self-evolution on top of V8.

A V9-capable DSPx flow can:
- propose changes to synthesis strategies or policies,
- evaluate those strategy/policy variants against explicit evidence,
- promote or reject them under governance rather than silent prompt drift.

V9 does **not** mean uncontrolled self-modification. Promotion boundaries, receipts, and policy review remain mandatory.

Consequences
------------
Positive:
- DSPx now has durable, dated references for V7/V8/V9 terminology.
- Module generation can evolve into the first real synthesis-runtime consumer without baking strategy/policy/evidence into one opaque service.
- V8 and V9 can be added later without a conceptual rewrite if V7 records the right contracts now.

Costs / tradeoffs:
- More architecture must be explicit up front: IR, evaluation records, policy versions, promotion receipts.
- The first V7 slices may feel slower than ad-hoc code generation because they optimize for future-proof seams rather than maximum immediacy.
- Higher-order autonomy is deliberately constrained until evidence and governance surfaces are real.

Consequences for near-term implementation
-----------------------------------------
Near-term work should prioritize:
1. synthesis contracts and package layout,
2. module-spec prompting/normalization/rendering,
3. candidate workspace + promotion shell,
4. `module-gen` integration through a one-candidate V7 path,
5. later extension to multi-candidate selection and optimize/replay evaluation.

It should explicitly defer:
- predictive Oracle priors for candidate ranking,
- strategy/policy self-evolution,
- uncontrolled auto-promotion beyond narrow governed cases.
