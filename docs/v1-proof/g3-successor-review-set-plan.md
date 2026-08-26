---
summary: "Review set plan for the G3 successor protocol decision: single bootstrap track (current_track), independent dispatched reviewer, three-pass adversarial review with computational verification."
read_when:
  - "You are auditing the review closure of the G3 successor protocol decision."
type: "review-set-plan"
---

# Review set plan — G3 successor campaign protocol

- **Mode:** bootstrap_single_track (single active track `current_track`).
- **Reviewed artifact (RFC):** `docs/v1-proof/g3-successor-campaign-design.md`
  (through REV 3).
- **Reviewer:** independent dispatched reviewer session (reviewer profile;
  no authorship role in the protocol; separate context from the author).
- **Method:** adversarial three-pass review with independent computational
  verification (exact-McNemar power recomputed by enumeration from first
  principles; v3b descriptive statistics recomputed from `corpus_table`; EC
  git facts verified on disk; guard edge cases checked numerically).
  Full memos: `g3-successor-review-memo.md` (REV 1 verdict `revise_rfc`,
  blocker F1 + must-fixes F2–F5; REV 2 delta verdict `revise_rfc`, must-fixes
  D1–D2; REV 3 delta verdict **`ready_for_adr`**, observes N1–N6 recorded as
  pre-freeze conditions).
- **Companion inputs reviewed:** `g3-successor-problem-brief.md`,
  `g3-successor-evidence-note.md`, `g3pilot-v3b-results.json`,
  engineering-core `2026-08-26-v1-g3-successor-binding.md` (AK 5096).
- **Coverage limits (stated by reviewer):** AK runtime and AK-5092 contents
  not inspected; simulation/corpus/enrollment/CP artifacts are plans to be
  re-checked at the freeze review.
