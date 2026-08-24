---
summary: "S4b classification of GEPA 0.1.1 materialization, receipt, replay, and comparison evidence."
read_when:
  - "Before claiming real GEPA 0.1.1 candidate materialization or replay compatibility."
type: "evidence"
---

# GEPA 0.1.1 materialization and replay disposition

AK-4725 disposition: **`unsupported_real_materialization`**.

The exact target matrix passed 173 tests under DSPy/DSPy-AI 3.3.0, GEPA 0.1.1, and retained lock SHA-256 `3c1a67002a7b2a42afda6ff5bba6e2cb10e164badab5e81620504b05772034a9`. S2 removed the former guarded-smoke blocker: all nine refinement tests and all 29 candidate-materialization tests now pass.

That passing proxy is not the required S4b behavior. Bounded test/source audit found:

- refinement success tests replace `run_gepa_optimize` with `_fake_gepa`;
- candidate success uses synthetic `compiled.bin` optimizer payloads;
- receipt checks establish artifact integrity for those synthetic candidates;
- replay claims do not run deterministic regeneration, runtime reproduction, semantic reproduction, or quality-evaluation reproduction;
- comparison reaches `compared` over synthetic evidence, not actual GEPA 0.1.1 output;
- the real S4a optimizer node compiles/saves/loads/predicts but does not enter candidate materialization, refreshed behavior, receipt/replay, or comparison.

Therefore no passing node proves actual GEPA 0.1.1 output can be copied, freshly loaded by the behavior harness, materialized as a candidate, refreshed, receipt-bound, replay-checked, and compared. Integrity of fake or pickle payloads cannot substitute for that journey.

The lawful result is `unsupported_real_materialization`. S4a remains accepted compatibility-only. S4b is not accepted, GEPA remains outside the trusted-local production matrix, and S5 cannot consume S4b as a passing prerequisite. A successor must add one credential-free exact-target real-output journey; any discovered serialization/load/refresh/receipt/comparison defect must receive its own repair scope.

No provider/model/network call, dependency/lock change, production admission, release, publication, or activation occurred.
