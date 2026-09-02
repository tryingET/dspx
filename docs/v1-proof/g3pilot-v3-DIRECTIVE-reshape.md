---
summary: "Applied operator directive reshaping the G3 v3 pilot to ten tasks and twenty executions."
read_when:
  - "Auditing the G3 v3 pilot corpus, execution budget, or operator-directed reshape."
type: "reference"
---

# OPERATOR DIRECTIVE — v3 pilot reshape (AK 5081)

Status: **APPLIED**. Issued 2026-08-25T21:05Z by the operator via the controller session.
Received pre-freeze by the executing session (nothing had executed); corpus authored,
frozen (corpus_digest f465929048536586f69dabe0b57f7c1e804a9a2256966347099f729e4c4149c1),
calibrated, and run in exactly this shape: 10 tasks, 5 per family, static+evidence once
each in the assigned family, 20 total executions. Recorded as applied in
docs/v1-proof/g3pilot-v3-results.json (`operator_directives_applied`).
Applies BEFORE any v3 execution. If execution has already started, stop cleanly,
finish no further pairs, and apply this to the remainder.

## Reshape

The 10 tasks x 2 families x 2 arms = 40 execution design is superseded.

- **Total 10 tasks. 5 per family** (openai-codex/gpt-5.6-sol:high, zai/glm-5.3:high).
  NOT every task in both families.
- Each task runs **once per arm within its assigned family**: static + evidence = 2
  executions per task.
- **Total executions: 20.** That is the whole budget.
- Task allocation: pick the 10 strongest authored candidates; keep all four classes
  represented (recommended 3 x class A adoption/migrate/doctor, 3 x class B advise-loop,
  4 x class C lane-conformance; adjust by judgment).

## Unchanged

Every other rule from the original brief stands: specs + deterministic acceptance
checkers frozen before execution; arms differ ONLY by guidance presence; advisor
uniform (gpt-5.6-terra, fallback glm-5.3, record which); interleaved order; receipts
in the v2 shape plus `task_class` and `family`; stop conditions; checkers never
relaxed after seeing results.

## Closeout

Results JSON must state the reshaped design honestly (5 tasks per family, 20 total
executions) and quote the operator intent: "please do only 10 tasks, 5 per model".

If you (the pilot session) read this AFTER having frozen a 40-execution corpus:
re-freeze to the 10-task shape before executing. No pair executed under the old
shape may be counted.
