---
summary: "G5 consumption note: the 5059 campaign must be consumed as operator-stopped incomplete with null-signal observation; successor design referenced."
read_when:
  - "You are the decision-132 owner or reviewer consuming Gate G5 inputs."
type: "note"
---

# G5 CONSUMPTION NOTE — G3 campaign (AK 5059, decision 132) — DRAFT INPUT

**Status: DRAFT INPUT for the decision-132 owner thread. DSPx is the empirical
owner and supplies evidence, not gate verdicts.** Routing: decision 132
("Accept the G3 prospective evidence-calibration protocol"), created
2026-08-24; campaign task 5059; campaign results
`docs/v1-proof/g3-campaign-results.json`.

## Observation

The G3 production campaign terminated operator-stopped incomplete at 127/168
pairs: fam-gpt complete (84/84, both arms 77/84 = 0.9167); fam-grok 43/84
after an out-of-credits block and a mid-resume operator stop (holdingco 28,
softwareco 15, teachingco 0). Under the frozen criterion the study is
**not evaluable**: it did not reach its frozen N, and on completed pairs both
arms sit at or above 0.9167 success — a ceiling effect that leaves the arms
indistinguishable in every family and owner group. The campaign's own results
record: *"no PASS, no FAIL claimed; G5 must consume as operator-stopped
incomplete with null-signal observation."* No gate outcome may be asserted
from this campaign in either direction; the honest gate input is
**incomplete + null-signal**.

## Consequence for G5

G5 should consume the campaign exactly as recorded — incomplete, null-signal —
and treat the null as **instrument-limited, not candidate-exonerating**: a
corpus whose control arm passes ≥ 91.7% of pairs cannot measure guidance lift
at any N within budget. Separately, the post-campaign diagnostic line (v3,
AK 5081; v3b, AK 5085) built a convention-space task family that does
separate (6/10 and 4/10 task-level splits; glm evidence-arm recovery
0→1 on both diagnostic pairs after the AK-5082 advise-surface fix); these are
labeled diagnostic-only and carry no gate weight, but they are the calibration
basis for the proposed successor instrument. The successor path is authored in
`docs/v1-proof/g3-successor-campaign-design.md` (corpus promotion rules,
right-sized N with power calculation, pre-registered criterion, single-variable
design), gated on this owner thread's acceptance; candidate identity for any
successor run is subject to the rebind input in
`docs/v1-proof/g3-candidate-5-rebind-decision-input.md`. Until the owner
accepts a successor protocol, G5 remains open with this note as its recorded
input.
