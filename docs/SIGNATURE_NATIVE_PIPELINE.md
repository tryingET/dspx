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
- provider-shaped corpus cases (pi-rpc/openrouter/codex/claude/gemini) for parser/renderer drift detection.

Phase 4 (next):
- service-wide smoke/import checks for module/codegen/mermaid signatures.
- shared quality score contract across services.

Phase 5 (done):
- quality event telemetry (`generated/cache/signature/quality_runs.jsonl` by default).
- CLI quality aggregation + promotion gates (`dspx signature quality-summary`).
- run-summary emission hooks for `signature gen` / `signature refine` (`--summary`, `--summary-json-out`).

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
- `packages/dspx-core/src/dspx/services/signature_quality.py`
  - quality event log append/read
  - aggregate metrics + gate evaluation
- `packages/dspx-core/src/dspx/services/signature_quality_corpus.py`
  - provider-corpus event synthesis
  - strict corpus gate profile used by CI
- `packages/dspx-core/src/dspx/templates/signature_templates.py`
  - spec prompt formatting
  - deterministic spec renderer

Config knobs and CLI controls:
- `DSPX_SIGNATURE_MAX_ATTEMPTS` (default 1; bounded)
- `dspx signature gen --max-attempts N` for a per-run native retry budget
- `dspx signature gen --input FIELD --output FIELD` for explicit repeatable IO field names; these are validated as non-overlapping Python identifiers, render directly on deterministic `simple-*` runs, are passed as native-generation constraints on LM-backed runs, and are preserved in run summaries/receipts
- `dspx signature gen --constraint TEXT --feedback TEXT` for explicit native-generation guidance without changing prompt text
- `DSPX_BUDGET_SIGNATURE_MS` (budget + provider timeout propagation)
- `DSPX_SIGNATURE_QUALITY_ENABLE` (default `1`; set `0` to disable JSONL event logging)
- `DSPX_SIGNATURE_QUALITY_LOG` (override log file path; default `generated/cache/signature/quality_runs.jsonl`)

Verification / Validation
-------------------------
Required checks:
- Unit tests
  - `tests/test_signature_native_pipeline.py`
  - `tests/test_signature_golden_corpus.py`
  - `tests/test_signature_provider_corpus.py`
  - `tests/test_signature_quality_summary.py`
  - `tests/test_signature_quality_corpus.py`
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
2. CI: core test slice green + provider-corpus quality gate artifact.
   - build deterministic corpus log:
     - `uv run -q python scripts/build_signature_provider_quality_log.py --out generated/ci/signature_provider_quality.jsonl`
   - evaluate gates:
     - `dspx signature quality-summary --log-path generated/ci/signature_provider_quality.jsonl --run-kind signature-gen --json --fail-on-gate --max-fallback-rate 0.10 --max-attempts-p95 1.0 --min-validation-pass-rate 1.0 --min-smoke-pass-rate 1.0`
   - publish artifact: `signature-quality-summary` + PR-facing step summary.
3. default quality gate report (runtime telemetry log):
   - `dspx signature quality-summary --json --fail-on-gate`
   - default thresholds:
     - `fallback_rate <= 0.25`
     - `attempts_p95 <= 3.0`
     - `validation_pass_rate >= 0.90`
     - `smoke_pass_rate >= 0.90`
4. optional live: provider smoke (`DSPX_RUN_LIVE_TESTS=1`) still healthy.

Rollback posture:
- `simple-*` deterministic path remains unchanged.
- Native path falls back to deterministic signature template when generation is invalid.

Publish
-------
- Update docs and status files (`README.md`, `PROJECT_STATUS.md`, and the project direction stack under `docs/project/`).
- Release core package (`dspx-core`) using package-scoped flow:
  - `just release-core new=X.Y.Z`
  - `just tag-core v=X.Y.Z`
  - `just publish-core`
- Track post-release metrics:
  - fallback usage rate
  - attempts-used distribution (p95 + histogram)
  - signature validation pass rate
  - signature smoke pass rate
