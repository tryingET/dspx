---
summary: "Decision input: rebind the G3 frozen candidate from candidate-4 (bc43bb9) to candidate-5 = engineering-core main@cde7f14."
read_when:
  - "You are the decision-132 owner deciding the G3 candidate identity."
type: "decision-input"
---

# CANDIDATE-5 REBIND — DECISION INPUT — DRAFT

**Status: DRAFT INPUT for the decision-132 owner thread. A rebind is a pin,
not a verdict; adopting or rejecting it grades nothing.**

## What is being decided

Rebind the G3 program's frozen candidate identity:

- **From** candidate-4: engineering-core `bc43bb9` (v3-era freeze; predates
  the AK-5082 advise-surface fix).
- **To** candidate-5: engineering-core **main@cde7f142ebd07527d865eded4bbbadf9fda9409f**,
  wheel `engineering_core-0.10.0-py3-none-any.whl`,
  sha256 `921bff5ef60ee8dea112cdaf8825e809bb484f1e518a06080e853c7e52288ab0`.

## Why now (evidence, all diagnostic-labeled)

1. **The fix ships only on main.** AK-5082 (uniform falsification grammar,
   self-describing advise requests) landed on main@cde7f14. Candidate-4 does
   not contain it; a gate measuring candidate-4 would measure the known-broken
   advise surface.
2. **v3b (AK 5085, 10 pairs, 20 receipt-backed executions, frozen corpus
   digest 10e404ac, checkers frozen) on main@cde7f14:** glm evidence-arm
   conformance recovered on both v3-failure diagnostic pairs (A2 0→1, B2 0→1;
   family evidence rate 1/5→3/5); sol directive stability targets held
   (B1 1→1, B3 1→1; 4/5 v3 evidence-wins held, C1 regressed 1→0); separation
   4/10 tasks. n=1 per cell, no causal claim.
3. **Ship-quality drift is a live cost:** the accepted product surface is
   moving on main while the frozen candidate does not track it.

## Honest caveat (must survive into any decision record)

v3 vs v3b differ by **fix + wheel identity** (the v3b deviations — spec
strings, RELEASE_REF v1.0.0→v0.10.0, ref3b reference policy — are recorded in
`g3pilot-v3b-state.json`). The recovery read is therefore not single-variable.
Mitigation is prospective, not retroactive: the successor campaign design
(`g3-successor-campaign-design.md`) requires a single-variable design on the
bound candidate. Do not represent v3b as causal proof of the fix; represent it
as sufficient grounds for pinning.

## Revert path

Rebinding is metadata plus artifact identity: retain candidate-4's recorded
commit/wheel identity in the protocol manifest history; revert = repin to
bc43bb9 and re-freeze guidance bundles/checker pins against it (the v3 freeze
remains intact and reproducible). No campaign data is invalidated by either
direction; the stopped 5059 campaign is consumed per the G5 note either way.

## What this input does NOT request

No gate outcome, no promotion, no protocol amendment. Only the candidate
identity pin, so that any successor freeze targets shipped reality.
