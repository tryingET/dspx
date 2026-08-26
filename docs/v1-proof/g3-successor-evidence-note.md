---
summary: "Evidence note: v3b results, 5059 campaign facts, EC candidate-5 binding — the factual basis for the successor protocol acceptance."
read_when:
  - "You are reviewing or deciding the G3 successor campaign protocol."
type: "evidence-note"
---

# Evidence note — G3 successor protocol (DSPx-side conditioned acceptance)

## Primary evidence items

1. **5059 campaign (stopped)** — `docs/v1-proof/g3-campaign-results.json`:
   127/168 pairs (fam-gpt 84/84 complete; fam-grok 43/84 after out-of-credits
   block + operator stop). Both arms ≥ 0.9167 on completed pairs; frozen
   criterion not evaluable; recorded instruction: consume as
   operator-stopped incomplete with null-signal observation.
2. **v3 diagnostic (AK 5081)** — `g3pilot-v3-results.json` (commit e25fe943):
   10 pairs, 20 executions, 6/10 task-level splits; established the
   convention-space family separates arms; glm evidence-arm failures on A2/B2.
3. **v3b diagnostic (AK 5085)** — `g3pilot-v3b-results.json` (commit 5516ee65,
   AK evidence 7839 pass): 10 pairs, 20 receipt-backed executions on frozen
   corpus (digest 10e404ac) + frozen checkers, wheel = engineering-core
   main@cde7f14 (0.10.0, sha 921bff5e…). Outcomes: glm evidence recovery
   A2 0→1, B2 0→1 (family evidence rate 1/5→3/5); sol stability B1 1→1,
   B3 1→1, 4/5 v3 evidence-wins held (C1 regressed 1→0); separation 4/10.
   n=1 per cell; diagnostic-only labels intact; two operational incidents
   (429 stall; duplicate-session race) contained and ledgered in the results
   file with honest budget reconciliation (24 executor invocations, 20
   receipt-backed).
4. **EC binding (the condition)** — engineering-core AK 5096 (done, evidence
   7841), commit `145c889`,
   `docs/project/2026-08-26-v1-g3-successor-binding.md`: candidate-5 =
   main@cde7f142ebd07527d865eded4bbbadf9fda9409f (wheel sha 921bff5e…) bound
   to the G3 successor instrument; G3 reopened; G0–G4 frozen records stay
   candidate-4; operator acceptance "accept both" recorded 2026-08-26.
5. **Incident disclosure (137)** — AK evidence 7840: superseded-with-no-outcome
   decision 137 was the product of an erroneous state-machine probe that
   executed a real transition; this decision replaces 137's intent with the
   correct conditioned shape, per cross-session agreement with the
   engineering-core session (which independently verified the state).

## Verification basis

All digests in items 2–4 re-verified this session (corpus digest, module
shas, wheel sha, EC commit). The design under acceptance is
`docs/v1-proof/g3-successor-campaign-design.md` (amended: anti-circularity
clauses + split governance routing), committed in softwareco/owned/dspx.

## What this evidence does NOT establish

- No causal isolation of the AK-5082 fix (confounded with wheel identity in
  v3→v3b).
- No general capability claim about either model family.
- No gate verdict of any kind: G3 consumption is a future owner fan-in act.
