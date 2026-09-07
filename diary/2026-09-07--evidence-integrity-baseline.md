---
summary: "AK-5511 bounded implementation baseline: saved-byte positives, explicit provenance limits, runtime boundary repairs and visible validation blockers."
read_when:
  - "Reviewing the evidence-integrity implementation or coordinating its auth repin."
---

# Evidence-integrity implementation baseline

Authority: exact AK-5511 scope snapshot and the reviewed Misegraph implementation
plan. This is a technical baseline, not task completion, acceptance or release.
No original evidence writes, model/network calls, credential access, consumed
attempt replay, target/fork edits, auth repin or AK task mutation were performed.

Canonical API, module/interpreter observations and hash vectors:
[implementation contract](../docs/project/2026-09-07-evidence-integrity-design.md).
The standalone fixed-current-code verifier uses stdlib-only isolated Python,
explicit captured-byte aliases, existing v1 hash domains and finite historical
profiles; it does not import orchestration or historical executable code.

Observed dogfood: Espresso and imported-vLLM return verified connected byte
closures, but retain injected quality, unknown acceptance and review_eligible=false.
Copilot has journal-only proof, not an invented import binding. Originals are
rehash-checked by the positive tests; negative modifications use separate scratch.

Runtime repairs: explicit execution repository; per-check preflight claims;
shared streaming stdout caps/duplex I/O and child-group cleanup. Name-only provider
classification no longer grants live. Generic registry one-shot tests remain in
the foundry suite. Existing acceptance APIs and current owner pins are unchanged.

Validation observations:
- Focused closure/provenance: 50 passed with Espresso and Copilot selected.
- Imported-vLLM closure/boundaries: 40 passed.
- Foundry-wide: 569 passed, 2 failed (current fork/pin disagreement; unchanged
  metric-honesty test incorrectly assuming all retained documents predate the field).
- Offline verify-fast passed. CI-quality format/lint/workflow passed; nine type
  diagnostics remain on unchanged test lines. Targeted new verifier/runtime/CLI
  type checks pass. Full suite/full gate and independent implementation review
  remain unproven; no green gate or lifecycle closeout is inferred.

Coordination: parent must review the implementation and provision its pinned
interpreter/runtime/capsule independently of evidence. AK-5512 repinning waits for
parent's reviewed exact commit. Deterministic-authored acceptance, future pre-jury
binding, authenticated output capture and target recommendation eligibility are
separate owner decisions, not hidden prerequisites claimed solved here.
