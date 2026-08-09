---
summary: "Exact-target S4a GEPA 0.1.1 compile/save/load compatibility evidence."
read_when:
  - "Before claiming GEPA 0.1.1 compile/save/load compatibility."
type: "evidence"
---

# GEPA 0.1.1 compile/save/load compatibility proof

AK-4724 disposition: **`accepted_compatibility_only`**.

The proof ran credential-free under the accepted Gate A target: CPython 3.13.12, DSPy/DSPy-AI 3.3.0, GEPA 0.1.1, and retained lock SHA-256 `3c1a67002a7b2a42afda6ff5bba6e2cb10e164badab5e81620504b05772034a9`.

Nine focused nodes passed across `test_optimize_gepa_stub.py`, metric hooks, MLflow tracing, and the provider-runtime-metadata optimizer node. The core node used real `dspy.teleprompt.gepa.GEPA`, a credential-free stub program, compile, whole-program save, `dspy.load(..., allow_pickle=True)`, and prediction. It did not substitute the fake refinement helper used by candidate-materialization tests.

Observed support is narrow: exact-environment construction, compile, save, same-process pickle-enabled load, and prediction. No live provider/model/network call occurred. No canonical dependency, source, lock, release, publication, or activation mutation occurred.

Nonclaims:

- no fresh-process or cross-environment portability;
- no deterministic rebuild or runtime replay;
- no semantic improvement or quality claim;
- no candidate materialization/receipt/comparison proof (S4b is separate);
- no non-pickle production path;
- no trusted-local Core production admission.

Pickle-backed whole-program artifacts remain compatibility evidence only and are explicitly excluded from the trusted-local production matrix.
