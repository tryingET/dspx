---
summary: "Native signature generation/refinement architecture: spec-first, validation-gated, capability-aware pipeline."
read_when:
  - "You are changing signature generation/refinement behavior or quality gates."
  - "You need rollout guidance from design through release/publish."
---

DSPx Native Signature Pipeline (Design → Plan → Implement → Validate → Promote → Publish)
============================================================================================

Scope
-----
- Applies to LM-backed signature generation and refine flows.
- Excludes deterministic template-only `simple-*` fast paths.

Design
------
1) Spec-first generation
- Stage A: model emits structured signature schema JSON.
- Stage B: deterministic renderer emits Python class code.

2) Capability-aware prompting
- If provider supports JSON mode: strict JSON-only contract.
- Else: tolerant JSON-extraction contract (still schema-first).

3) Validation-gated outputs
- AST parse + compile checks.
- Structural checks (Signature base class + InputField/OutputField presence).
- Smoke execution check (`exec` + subclass check).

4) Bounded retries with selection
- Generate N candidates (`max_attempts`).
- Score and select best valid candidate.
- Prefer non-fallback candidates.

5) Structured refinement memory
- Keep explicit feedback history and constraints.
- Feed memory into each refinement round instead of flat concatenation.

Plan (incremental)
------------------
Phase 1 (done):
- spec-first generator + deterministic renderer.
- provider-capability prompt strategy.
- validation/smoke checks + candidate scoring.
- bounded retries in generation.

Phase 2 (done):
- structured refinement memory model.
- non-interactive refine uses bounded retries.

Phase 3 (done):
- golden corpus regression tests for rendered signatures.
- pipeline unit tests for retries/spec parsing/validation.

Phase 4 (next):
- service-wide smoke/import checks for module/codegen/mermaid signatures.
- shared quality score contract across services.

Phase 5 (next):
- CI summary report for signature quality metrics (pass rate, fallback rate, retry depth).

Implementation details
----------------------
Key modules:
- `packages/dspx-core/src/dspx/services/signatures_service.py`
  - spec parsing/normalization
  - validation + scoring
  - retry/best-candidate selection
- `packages/dspx-core/src/dspx/services/refine_service.py`
  - structured refinement memory
  - non-interactive retry budget usage
- `packages/dspx-core/src/dspx/templates/signature_templates.py`
  - spec prompt formatting
  - deterministic spec renderer

Config knobs:
- `DSPX_SIGNATURE_MAX_ATTEMPTS` (default 1; bounded)
- `DSPX_BUDGET_SIGNATURE_MS` (budget + provider timeout propagation)

Verification / Validation
-------------------------
Required checks:
- Unit tests
  - `tests/test_signature_native_pipeline.py`
  - `tests/test_signature_golden_corpus.py`
  - `tests/test_refine_service_memory.py`
- Existing DTO/CLI/server tests must remain green.

Quality acceptance:
- Generated code parses and compiles.
- Contains at least one InputField and OutputField.
- Smoke execution confirms a discoverable `dspy.Signature` subclass.
- Golden corpus hashes unchanged unless intentional renderer change.

Promote
-------
Promotion gates:
1. local: format/lint/typecheck/tests green.
2. CI: core test slice green.
3. optional live: provider smoke (`DSPX_RUN_LIVE_TESTS=1`) still healthy.

Rollback posture:
- `simple-*` deterministic path remains unchanged.
- Native path falls back to deterministic signature template when generation is invalid.

Publish
-------
- Update docs and status files (`README.md`, `PROJECT_STATUS.md`, `NEXT_STEPS.md`).
- Release core package (`dspx-core`) using package-scoped flow:
  - `just release-core new=X.Y.Z`
  - `just tag-core v=X.Y.Z`
  - `just publish-core`
- Track post-release metrics:
  - fallback usage rate
  - average attempts used
  - signature validation pass rate
