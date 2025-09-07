# Project Status

This document summarizes the current state of the repository, key
decisions, and readiness against the vision plan.

## Snapshot

- Baseline branch created: `version/vision-baseline` (frozen snapshot).
- Unified CLI available: `dspx` (signature/module/codegen/mermaid/tools) and
  `dspx-server` (FastAPI ASGI app served by Granian).
- Canonical Mermaid→signatures CLI: `dspx-mermaid-sig` maps to
  `dspx.cli.dspx_mermaid2dspy:main`.
- Tests: local suite runs in ~8–9s (`just test`) with 48 passing tests.
- Build: `uv build` succeeds; console scripts resolve.
- Docs: updated vision, architecture views, OpenAPI tooling (MVP), and new
  end‑to‑end tutorial `docs/TUTORIAL_E2E.md`.

## Current Components

- Providers: CodexExecLM, ClaudeHeadlessLM, GeminiCLILM, MultiProviderLM, Stub LM.
- Core: LMBase + ProviderCapabilities, DTOs (Signatures, Modules, Programs,
  Codegen, OpenAPI Call), ToolRegistry.
- Services: SignatureService (vibe + DTO), RefineService (vibe),
  CodegenService (DTO), ModuleService (MVP), MermaidWorkflowService
  (variants + sig‑per‑node; emits ProgramGraph/Artifact + manifest).
- OpenAPI Toolpack (MVP+): loader (JSON/YAML, URL with allowlists + cache),
  operation extraction (merged params, body schema, response schemas, tags),
  caller (host allowlist, basic validation), registry integration (dynamic tools),
  CLI (`tools openapi` with `ops --tags`, `describe --json`).
- Adapters (Phase 7 MVP): dataset adapters (CSV/Parquet, MLflow artifact ref),
  eval metrics (accuracy, F1 binary), local object store; Adapters CLI
  (`dspx adapters list`, `dspx adapters dataset describe`).
- Server: FastAPI app with `/signature`, `/module`, `/mermaid` endpoints; served by
  Granian; smoke‑tested via ASGI TestClient.
- CLIs: `dspx` (signature/module/codegen/mermaid/tools/adapters), plus legacy demos;
  `dspx-server` launcher.
- Tracing: MLflow integration (opt‑in via env) with standardized tags
  (`service`, `template_version`, `provider`) and artifact/manifest logging.
- Caching/Repro: content‑hash caching for generation services; manifests and
  meta files alongside outputs; CLI `--no-cache`, `--cache-info`, cache keys in meta.

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
  Recent DX: `ops --tags`, `describe --json`, response schema printing.
- Phase 6 — Caching & Repro Metadata: DONE (cache + manifests/meta). Recent DX: CLI
  `--no-cache`, `--cache-info` and meta includes cache keys/paths.
- Phase 7 — Adapter Registry: DONE (MVP) — CSV/Parquet loaders, MLflow dataset ref,
  accuracy/F1 metrics, local object store, tests.
- Phase 8 — Server API (optional): PARTIAL (FastAPI app + Granian runner; endpoints for
  `/signature`, `/module`, `/mermaid`; smoke tests). Next: auth options, DTO polishing.
- Phase 9 — Policy, Safety, Sandboxing: PARTIAL (allowlists; more to do).
- Phase 10 — Plugins & Extension Points: NOT STARTED.

## Risks & Dependencies

- External CLIs (codex/claude/gemini) availability and authentication.
- Network access and host allowlists for OpenAPI/Web tools.
- MLflow availability for tracing (optional; disabled in tests).
- Submodules present but not required for fast tests.
- Granian presence for running `dspx-server` (not required for tests).

## Success Criteria (near-term)

- Stable, deterministic tests without external providers (currently ~9s locally).
- DTOs and manifests adopted across services; CLIs documented.
- Next: harden server API (Phase 8), stronger policy (Phase 9), and plugin basics (Phase 10).
