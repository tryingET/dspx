DSPy + Codex Exec: Architecture Vision
======================================

Overview
--------
This codebase integrates DSPy with Codex Exec (codex CLI) to enable execution‑aware LM workflows, wrapped with MLflow tracing. The refactor vision organizes the project into clear layers so you can add models, tools, modules, and optimizers with minimal friction.

Layers
------
- Core:
  - `config_loader.py`: Loads config.toml → env (MLflow + Codex defaults); discovery via `DSPX_CONFIG` or nearest `config.toml` (walk-up from CWD).
  - `tracing.py`: MLflow autolog enablement (opt‑in via env/config)
  - LM Provider API (planned `LMBase`): small interface to unify providers
  - DTOs (planned): typed request/response contracts (versioned)
  - ProviderRegistry (planned): select providers by name at runtime
  - ProviderCapabilities (planned): feature flags (tool‑calling, code‑exec, JSON mode)
- Providers:
  - `codex_exec_lm.py`: CodexExecLM (codex exec, --full-auto or bypass)
  - OpenAI Responses (future), OSS/Ollama (future)
  - Instrumentation: optional verbose logs via `DSPX_CODEX_VERBOSE`, call history (durations, exit codes, output snippet)
- Services:
  - CodegenService: “spec → code” workflows (see `codegen.py` CLI)
  - SignatureService: vibe‑dspy adapter (see `vibegen.py`)
  - RefineService: interactive/non‑interactive refine (see `viberefine.py`)
  - AgentService (future): ReAct/agent orchestration with tools
  - OptimizeService (future): teleprompters/optimizers (BootstrapFewShot, MIPRO, Refine)
- Plugins & Tools (planned):
  - ToolRegistry: register functions/tools (retrieval, search, Python exec)
  - Adapters: retrieval (ColBERT/web), storage (S3/DB), evaluation/metrics
- CLI (thin):
  - `example_predict.py`, `codegen.py`, `vibegen.py`, `viberefine.py`
  - All load config, enable tracing, and delegate to services
- Integrations:
  - MLflow server/UI (local/remote/NAS)
  - `submodules/vibe-dspy` (signatures), `attachments`, `ovllm`
  - `codex` CLI (Codex Exec)
  - Optional explicit MLflow runs in downstream scripts for guaranteed tracking (params, artifacts, tags)

Why This Refactor
-----------------
Pros
- Clear separation of concerns enabling focused changes.
- Pluggable LM providers without touching service logic.
- Better testing: service logic testable with LM stubs; MLflow observability.

Cons (and Mitigations)
- More layers/indirection → use thin services and shared CLI mixins to reduce boilerplate.
- Provider flags leaking into services → isolate via `LMConfig` + `ProviderCapabilities` on the provider side.
- Sync/maintenance overhead → define DTOs (v1, v2…), add stub + e2e tests to guard contracts.

Extensibility Targets
---------------------
- Providers: Codex Exec, OpenAI Responses, OSS (Ollama), etc.
- Modules: dspy.Module implementations (Predict, chains, agents).
- Optimizers/Teleprompters: BootstrapFewShot, MIPRO, Refine, Compiler.
- Tools/Adapters: retrieval/search, Python exec, storage, evaluation/metrics.
- Programs/Agents: ReAct agents, planners, evaluators.

Roadmap (Incremental)
---------------------
1) Introduce `LMBase` + DTOs
   - Define minimal provider interface and typed request/response structures.
   - Adapt `CodexExecLM` to implement `LMBase` (keep DSPy BaseLM bridge small).

2) ProviderRegistry + Capabilities
   - Registry mapping provider names → factory functions.
   - Capabilities indicate tool‑calling, JSON mode, code‑exec, etc.

3) Move orchestration into Services
   - Extract logic from `codegen.py`, `vibegen.py`, `viberefine.py` into `services/`.
   - Keep CLIs thin; share common flags via a mixin/util.

4) Plugins & Tool Registry
   - Load tools/providers from a `plugins/` folder or Python entry points.
   - Enable optional packages (e.g., attachments/ovllm) without editing core.

5) Testing & CI
   - Unit tests for core/providers using stubs.
   - Golden e2e runs for codegen/signature/refine.
   - Optional smoke tests that post traces to MLflow (behind a toggle).

6) Additional Providers & Features
   - Add OpenAI Responses and OSS (Ollama) via the registry.
   - Add an AgentService with a small tool registry.
   - Add an OptimizeService wired to DSPy teleprompters.

Current State
-------------
- Codex Exec provider and CLIs are functional; MLflow tracing + config.toml are active.
- vibe‑dspy integration exists through adapter CLIs (`vibegen.py`, `viberefine.py`).
- Next steps are additive and backward compatible with current usage.
