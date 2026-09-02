---
summary: "Applied operator directive reshaping G3 v3b across both model families and correcting fixture refs."
read_when:
  - "Auditing the G3 v3b run design, family allocation, or released-pin fixture correction."
type: "reference"
---

# OPERATOR DIRECTIVE #2 — v3b reshape (AK 5085)

Issued 2026-08-26 by the operator via the controller session. Binding.
Applies immediately; you have not yet executed anything (verified: no receipts).

## 1. Reshape the run

Supersede the "glm only, all 10 tasks" design:

- **5 tasks per arm-slot, BOTH families**: re-run sol:high AND glm:high.
- Do NOT re-run all 10 tasks per family. Select **5 tasks per family** — keep
  all three classes represented per family and include the diagnostic
  must-haves: for glm {A2, B2} (the v3 failure pair) + 3 others covering A/C;
  for sol {B1 or B3} (a v3 evidence-win, to confirm it holds) + A1 + C1/C3,
  adjusting by judgment, recording the selection rationale.
- Total executions: 2 families x 5 tasks x 2 arms = **20**.
- Rationale (operator): single-family re-run risks family-specific bias in the
  recovery read; both families re-run on the same fixed wheel is the
  controlled comparison.

## 2. The version-pin incompatibility you found — resolve it by fixing the fixture refs, not the wheel

You correctly found `_pin()` gives `released-match` only when `ref ==
"v{__version__}"`, so a 0.10.0 wheel breaks class-A checkers that expect
released-match posture. Resolution: **use `--ref v0.10.0` (explicit released
pin, matching the wheel's real version) in the class-A fixtures/tasks** so the
checker's released-match expectation is honest for this wheel. Do NOT modify
advisor/adoption code, do NOT fake the pin posture, do NOT rebuild the wheel
with a different version. Record the ref used per task in the results. If any
checker turns out to hardcode a version string rather than the posture rule,
copy-and-fix the CHECKER input fixture (never the checker logic) and record
that as a v3b deviation with rationale.

Everything else stands: frozen corpus digest re-verified; checkers never
relaxed; interleaved; receipts v3 shape + family + run_label v3b; advisor
terraform identity uniform; stop conditions; cleanup. Closeout adds: per-task
v3-vs-v3b comparison for BOTH families, recovery verdict (glm A2/B2), sol
stability verdict (do v3 evidence-wins hold?), explicit n=1 non-claims.
