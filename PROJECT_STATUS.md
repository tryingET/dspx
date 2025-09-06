# Project Status

This document summarizes the current state of the repository, key
decisions, and readiness to begin implementation of the vision plan.

## Snapshot

- Baseline branch created: `version/vision-baseline` (frozen snapshot).
- Canonical Mermaid→signatures CLI: `dspx-mermaid-sig` maps to
  `dspx.cli.dspx_mermaid2dspy:main`.
- Duplicate/typo module removed: `src/dspx/cli/dspyx2_mermaid2dpsy.py`.
- Tests: local suite runs in ~3s (`just test`).
- Build: `uv build` succeeds; console scripts resolve.
- Docs: updated vision, architecture views, and OpenAPI toolpack design.

## Current Components

- Providers: CodexExecLM, ClaudeHeadlessLM, GeminiCLILM, MultiProviderLM.
- Services (implemented): SignatureService (vibe), RefineService (vibe),
  CodegenService, MermaidWorkflowService (variants + sig-per-node basis).
- CLIs: `dspx-vibegen`, `dspx-viberefine`, `dspx-mermaid`,
  `dspx-mermaid-sig`, `dspx-codegen`, example/tools/multi demos.
- Tracing: MLflow integration (opt-in via env). Disabled in tests.

## Documents

- `docs/VISION.md`: first-principles design, CTO layers, phased plan.
- `docs/ARCHITECTURE.md`: multi-view diagrams (layers, CLI, plugins,
  OpenAPI flow, DTOs).
- `docs/OPENAPI_TOOLING.md`: proposed OpenAPI toolpack (loader/caller,
  policies, CLI, roadmap).

## Readiness to Start Implementation Plan

- The repository is stable with a clear snapshot branch. The vision and
  architecture docs define the target state and phased plan with
  acceptance criteria.
- Next up: Phase 1 (LMBase + DTOs + StubLM), then Phase 2 (template
  library), and Phase 3 (ModuleService MVP).

## Risks & Dependencies

- External CLIs (codex/claude/gemini) availability and authentication.
- Network access and host allowlists for OpenAPI/Web tools.
- MLflow availability for tracing (optional; disabled in tests).
- Submodules are present but not required for fast tests.

## Success Criteria (short-term)

- Phase 1 unit tests run without external providers (StubLM only).
- DTOs are used across services; signatures remain compatible.
- Unified CLI skeleton planned and documented for Phase 4.
