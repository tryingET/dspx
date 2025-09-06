# Next Steps

This document outlines actionable next steps aligned with the phased
implementation plan in `docs/VISION.md`.

## Phase 1 — Contracts & Abstractions

Goal: introduce minimal, testable interfaces and data contracts so
services can run with a stub LM.

- Deliverables
  - `dspx/core/lm_base.py` with `LMBase` and `ProviderCapabilities`.
  - `dspx/core/dtos.py` with v1 DTOs:
    - SignatureGenRequest/Result
    - ModuleSpec/ModuleArtifact
    - ProgramGraphSpec/ProgramArtifact
    - OpenAPICallRequest/Result (skeleton)
  - `dspx/providers/stub_lm.py` simple deterministic LM for tests.

- Changes
  - Refactor services to accept `LMBase` where applicable.
  - Keep existing behavior; add optional code paths using DTOs.

- Acceptance
  - Unit tests using StubLM (no external providers) pass in <2s.
  - Services import DTOs without breaking existing CLIs.

## Phase 2 — Template Library

Goal: centralize prompts/templates for signatures and codegen.

- Deliverables
  - `dspx/templates/` with versioned templates + selection API.
  - Golden tests for signature/codegen outputs with StubLM.

- Acceptance
  - Services consume templates; tests stable and deterministic.

## Phase 3 — ModuleService (MVP)

Goal: generate reusable DSPy modules from ModuleSpec.

- Deliverables
  - `dspx/services/module_service.py` with `run_generate`.
  - DTO mapping from ModuleSpec → ModuleArtifact (optionally via
    SignatureService).
  - Unit tests using StubLM and templates.

- Acceptance
  - Module skeleton code is produced and passes smoke tests.

## Phase 4 — Unified CLI (skeleton)

Goal: user-friendly command surface with consistent flags.

- Deliverables
  - `dspx/cli/dspx.py` (Typer) with:
    - `signature gen|refine`
    - `module gen`
    - `mermaid gen|sig`
  - Backward-compatible shims from existing scripts.

- Acceptance
  - CLI smoke tests <3s; help text documents shared flags.

## Phase 5 — OpenAPI Toolpack (MVP)

Goal: safe, typed access to OpenAPI operations as tools.

- Deliverables
  - `dspx/tools/openapi/{loader,caller}.py` + CLI commands.
  - Host allowlists, timeouts, redaction; MLflow metadata.

- Acceptance
  - Load GitHub spec; call a read-only op; logs redact tokens.

## Day-to-Day Checklist

- Run `just test` before and after changes; target <3s locally.
- Keep docs in sync (VISION/ARCHITECTURE/NEXT_STEPS) with major changes.
- Prefer small, scoped PRs per phase/sub-phase; include acceptance notes.
