# Project Status

This document summarizes the current state of the repository, key
decisions, and readiness against the vision plan.

## Snapshot

- Baseline branch created: `version/vision-baseline` (frozen snapshot).
- Unified CLI available: `dspx` (signature/module/codegen/mermaid/tools/adapters/cache) and
  `dspx-server` (FastAPI ASGI app served by Granian).
- Canonical Mermaid→signatures CLI: `dspx-mermaid-sig` maps to
  `dspx.cli.dspx_mermaid2dspy:main`.
- Tests: local suite runs in ~10–14s (`just test`) with 130 passing tests (3 skipped).
- Build: `uv build` succeeds; console scripts resolve.
- Docs: updated vision, architecture views, OpenAPI tooling (MVP), and new
  end‑to‑end tutorial `docs/TUTORIAL_E2E.md`.
- Configuration: consolidated example config `example.toml` (copy to `config.toml`); `config.toml` is git‑ignored.
- Examples: Mermaid sample updated to a pedagogical flow (Unterrichtsstörungen, DE) for a more practical demo.
- OpenRouter: provider available (`DSPX_PROVIDER=openrouter`) plus `.env.example` and Just recipes (`or-codegen`, `or-signature`, timed variants) designed to work with 1Password `op run` + `op://...` env references (no secrets in CLI flags).
- Tooling: `Justfile` includes `bench-mlflow` to run a single
  MLflow‑logged benchmark across providers. The task now exports
  `DSPX_RUN_GROUP` so all child CLI runs receive a consistent
  `run_group` tag in MLflow. Recipes were updated to run CLIs from
  source via `uv run -m` (no need to install console scripts with
  `uvx`). Server DX improved: `just start` now runs the FastAPI server
  with a bounded timeout (default 3s) on `127.0.0.1:33213`, plus
  helpers `start-timed` (short run), `start-forever` (no timeout), and
  `stop` (kill listeners on a port).

## Current Components

- Providers: CodexExecLM, ClaudeHeadlessLM, GeminiCLILM, OpenRouterLM, MultiProviderLM, Stub LM.
- Core: LMBase + ProviderCapabilities, DTOs (Signatures, Modules, Programs,
  Codegen, OpenAPI Call), ToolRegistry, typed descriptors for tools (`ToolDescriptor`) and
  typed OpenAPI operations (`OpenAPIOperationInfo`).
- Services: SignatureService (vibe + DTO), RefineService (vibe),
  CodegenService (DTO), ModuleService (MVP), MermaidWorkflowService
  (variants + sig‑per‑node; emits ProgramGraph/Artifact + manifest).
- Optimization: GEPA runner (`dspx optimize gepa`) that compiles a DSPy program/module and saves
  a loadable program directory (via `dspy.load`), with explicit IO (`--input/--output-key` or `io_spec()`),
  metric options (`exact|contains|f1`), per‑output weighting (`--output-weight` or `output_weights()`),
  and optional output normalization (`normalize_output(...)`). Reflection LM can be split from the
  student LM (`--reflection-provider`), defaulting to Codex Exec.
- OpenAPI Toolpack (MVP+): loader (JSON/YAML, URL with allowlists + cache),
  operation extraction (merged params, body schema, response schemas, tags),
  caller (host allowlist, basic validation), registry integration (dynamic tools),
  CLI (`tools openapi` with `ops --tags|--json`, `describe --json`, `call --dry-run`).
- Adapters (Phase 7 MVP+): dataset adapters (CSV/Parquet, MLflow artifact ref),
  eval metrics (accuracy, F1 binary, confusion, ROUGE‑1 F1, BLEU‑1, ROC‑AUC, per‑class precision/recall),
  macro/micro averaging for ROUGE/BLEU, stratified and group‑aware splits with
  group‑balancing modes (`instances|groups`) via `--group-balance`, local object store;
  Adapters CLI (`dspx adapters list`, `dspx adapters dataset describe`,
  `dspx adapters dataset split`, `dspx adapters eval run`, `dspx adapters eval run2`).
- Server: FastAPI app with `/signature`, `/module`, `/mermaid` endpoints; served by
  Granian; Bearer auth (env‑driven, tokens/file), rate limiting (per‑identity and global),
  trusted proxies for X‑Forwarded‑For, standardized JSON errors, structured logs; tested via ASGI TestClient.
  Default port is `33213`. Docs updated with quick `just start` usage
  and curl examples. Default bind host uses `127.0.0.1` to avoid
  occasional Granian "invalid IP address syntax" errors seen with
  `localhost` in certain environments.
- CLIs: `dspx` (signature/module/codegen/mermaid/tools/adapters, and `tools web fetch|scrape` with per‑call host allowlists), plus legacy demos;
  `dspx-server` launcher.
  Tools UX additions: `tools list --json` (capabilities/description/OpenAPI info),
  `tools describe [--json|--examples]`, `tools search [--tags] [--json]`, generic `--dry-run`
  for `tools run` and `tools openapi call` with redacted previews.
- Tracing: MLflow integration (opt‑in via env) with standardized tags
  (`service`, `template_version`, `provider`, optional `run_group`) and artifact/manifest logging. `run_group` is populated from `DSPX_RUN_GROUP` (now exported by `bench-mlflow`) and applied consistently via `ensure_run_with_standard_tags()` across CLIs (including Mermaid SIG).
  Per‑service budgets recorded via `service.budget_ms` tag and
  `service.duration_ms`/`service.budget_exceeded` metrics.
  dspy traces: `mlflow.dspy.autolog` configured to attach spans to the active named run
  (no implicit run creation), with stable run naming in CLI (`signature-*`, `codegen-*`, `module-*`, `mermaid-*`).
  MLflow hard-disable: `MLFLOW_ENABLE=0` now prevents `mlflow` imports/calls entirely (no default HTTP tracking fallback, no accidental network retries). A concrete observability fix plan lives in `docs/MLFLOW_OBSERVABILITY_PLAN.md`.
  Signature refine now has MLflow parity: a dedicated `signature-refine` run name with standard tags,
  params/metrics, and artifact logging gated by `mlflow.active_run()` (no implicit runs unless configured).
- Caching/Repro: content‑hash caching for generation services; manifests and
  meta files alongside outputs; CLI `--no-cache`, `--cache-info`, cache keys in meta;
  Cache management CLI: `dspx cache info|list|show|clear`.

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
  Recent DX: `ops --tags`, `describe --json`, response schema printing, and
  validation for enums/arrays/shallow nested objects.
- Phase 6 — Caching & Repro Metadata: DONE (cache + manifests/meta). Recent DX: CLI
  `--no-cache`, `--cache-info` and meta includes cache keys/paths.
- Phase 7 — Adapter Registry: DONE (MVP+) — CSV/Parquet loaders, MLflow dataset ref,
  accuracy/F1/confusion/ROUGE‑1/BLUE‑1 metrics, dataset split CLI, stratified and group‑aware splits
  with group‑balancing options (`instances|groups`), ROC‑AUC and per‑class precision/recall,
  macro/micro averaging for ROUGE/BLEU; local object store; tests.
- Phase 8 — Server API (optional): DONE (MVP+) — FastAPI app + Granian runner; endpoints for
  `/signature`, `/module`, `/mermaid`; Bearer auth (env), rate‑limit options (per‑path, identity/global),
  trusted proxies (XFF), standardized JSON errors, basic structured logging; tests and docs.
- Phase 9 — Policy, Safety, Sandboxing: IN PROGRESS
  - Implemented: env‑driven policy engine for tool/provider allow/deny; optional max timeout clamp;
    HTTP method allow/deny and guarded mutation (POST/PUT/PATCH/DELETE) enforcement;
    provider gating in registry; tool enforcement wrapper in registry; root CLI policy flags;
    optional sandbox worktree for Codex provider (`DSPX_SANDBOX_WORKTREE=1`).
    Web tools now enforce per‑call host allowlists with CLI integration (`dspx tools web fetch|scrape --allow-host`).
  - Implemented: per‑service budgets with MLflow tagging/metrics; CLI `--budget-ms` for signature/module/codegen.
  - Implemented: run naming + `mlflow.dspy.autolog(create_run=False)` to attach traces to named runs; simple duration traces added to mermaid and non‑DTO signature paths.
  - Implemented (new): destructive‑op confirmation in CLI for mutating OpenAPI/tools
    (policy‑aware with `--yes` and `--allow-network-mutate`), capability category gating for
    tools via registry wrapper + descriptors, dry‑run previews for OpenAPI/tools with redacted URLs,
    typed descriptors (`ToolDescriptor`) and typed OpenAPI operations (`OpenAPIOperationInfo`),
    and server‑side confirmation gate for mutating endpoint `/mermaid` controlled by
    `DSPX_CONFIRM_MUTATIONS` + `X-DSPX-Confirm` header. Token redaction hardened (URL userinfo,
    Cookie/Set-Cookie, token/key/secret/password headers) and applied to previews/outputs.
  - Remaining: stronger sandbox isolation options; capability gating for `code.exec` in providers;
    optional parent/child nested runs for workflow‑level grouping; further redaction coverage and
    audit trails; unify descriptors across any remaining tool paths.
- Phase 10 — Plugins & Extension Points: NOT STARTED.

## Risks & Dependencies

- External CLIs (codex/claude/gemini) availability and authentication.
- 1Password CLI (`op`) for resolving `op://...` references in `.env` when using OpenRouter recipes.
- OpenRouter API availability and networking (only required when the provider is selected).
- Network access and host allowlists for OpenAPI/Web tools.
- MLflow availability for tracing (optional; disabled in tests).
- Submodules present but not required for fast tests.
- Granian presence for running `dspx-server` (not required for tests).

## Success Criteria (near-term)

- Stable, deterministic tests without external providers (currently ~10–14s locally).
- DTOs and manifests adopted across services; CLIs documented.
- Next: stronger policy (Phase 9), plugins (Phase 10), richer adapter features,
  and optional distributed rate limiting. Expand descriptor usage and server tooling endpoints.
