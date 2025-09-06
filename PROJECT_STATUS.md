# Project Status

This document summarizes the current state of the repository, key
decisions, and readiness against the vision plan.

## Snapshot

- Baseline branch created: `version/vision-baseline` (frozen snapshot).
- Unified CLI available: `dspx` (signature/module/codegen/mermaid/tools).
- Canonical Mermaid→signatures CLI: `dspx-mermaid-sig` maps to
  `dspx.cli.dspx_mermaid2dspy:main`.
- Tests: local suite runs in ~4s (`just test`) with 35 passing tests.
- Build: `uv build` succeeds; console scripts resolve.
- Docs: updated vision, architecture views, and OpenAPI tooling (MVP).

## Current Components

- Providers: CodexExecLM, ClaudeHeadlessLM, GeminiCLILM, MultiProviderLM, Stub LM.
- Core: LMBase + ProviderCapabilities, DTOs (Signatures, Modules, Programs,
  Codegen, OpenAPI Call), ToolRegistry.
- Services: SignatureService (vibe + DTO), RefineService (vibe),
  CodegenService (DTO), ModuleService (MVP), MermaidWorkflowService
  (variants + sig‑per‑node; emits ProgramGraph/Artifact + manifest).
- OpenAPI Toolpack (MVP): loader (JSON/YAML, URL with allowlists + cache),
  operation extraction (merged params, body schema), caller (host allowlist,
  basic validation), registry integration (dynamic tools), CLI (`tools openapi`).
- CLIs: `dspx` (signature/module/codegen/mermaid/tools), plus legacy demos.
- Tracing: MLflow integration (opt‑in via env) + guarded logging for services
  and OpenAPI calls. Disabled in tests.
- Caching/Repro: content‑hash caching for generation services; manifests and
  meta files alongside outputs.

## Documents

- `docs/VISION.md`: first-principles design, CTO layers, phased plan.
- `docs/ARCHITECTURE.md`: multi-view diagrams (layers, CLI, plugins,
  OpenAPI flow, DTOs).
- `docs/OPENAPI_TOOLING.md`: OpenAPI toolpack MVP (loader/caller, URL+cache,
  policies, CLI, roadmap).

## Implementation Progress vs. Plan

- Phase 1 — Contracts & Abstractions: DONE (LMBase, DTOs v1, StubLM).
- Phase 2 — Template Library: DONE (signatures/codegen/module templates + tests).
- Phase 3 — ModuleService (MVP): DONE.
- Phase 4 — Unified CLI (skeleton): DONE (`dspx`).
- Phase 5 — OpenAPI Toolpack (MVP): DONE (loader/caller/registry/CLI, YAML+URL support,
  basic validation and caching). Mermaid nodes can call OpenAPI ops via labels.
- Phase 6 — Caching & Repro Metadata: DONE (cache + manifests/meta).
- Phase 7 — Adapter Registry: NOT STARTED.
- Phase 8 — Server API (optional): NOT STARTED.
- Phase 9 — Policy, Safety, Sandboxing: PARTIAL (allowlists; more to do).
- Phase 10 — Plugins & Extension Points: NOT STARTED.

## Risks & Dependencies

- External CLIs (codex/claude/gemini) availability and authentication.
- Network access and host allowlists for OpenAPI/Web tools.
- MLflow availability for tracing (optional; disabled in tests).
- Submodules present but not required for fast tests.

## Success Criteria (near-term)

- Stable, deterministic tests (<5s) without external providers.
- DTOs and manifests adopted across services; CLIs documented.
- Next: adapters (Phase 7), server API (Phase 8), and stronger policy (Phase 9).
