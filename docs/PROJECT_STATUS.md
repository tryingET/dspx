Project Status
==============

Overview
--------
This repo demonstrates DSPy running on Codex Exec (codex CLI) with MLflow tracing and a growing toolchain for generating DSPy Signatures (via vibe-dspy) and code. The goal is an execution-aware LM backend with clean extension seams for providers, tools, modules, and optimizers.

What Works Today
----------------
- Codex Exec LM wrapper (`codex_exec_lm.py`):
  - Supports `--model`, reasoning effort via `-c model_reasoning_effort=...`, and `--dangerously-bypass-approvals-and-sandbox`.
  - Captures last agent message via `--output-last-message` for clean outputs.
  - Bridges to DSPy’s BaseLM; returns an OpenAI-like minimal response object.
- MLflow tracing (`tracing.py` + `config.toml`):
  - Autologging enabled via `enable_mlflow_from_env()`; configured through `config.toml` (or env).
  - Verified runs (experiment "DSPy") appear in MLflow UI (NAS Docker or local server).
- Config management (`config_loader.py`):
  - Reads `config.toml` at startup; populates MLflow and Codex env vars automatically.
- CLIs:
  - `example_predict.py`: simple Q&A with Codex Exec.
  - `codegen.py`: spec → code generator (code-only output; optional file write).
  - `vibegen.py`: uses vibe-dspy’s SignatureGenerator with Codex Exec.
  - `viberefine.py`: interactive/non-interactive refine loop; optional wrapped script output.
  - `agent_demo.py`: minimal ReAct agent demo with optional DSPy tools.
- Submodules:
  - `submodules/vibe-dspy` (signature generation utilities).
  - `submodules/attachments` and `submodules/ovllm` (optional utilities; importable via PYTHONPATH).
- MLflow in Docker:
  - `docker-compose.yml` for Synology NAS (host port 50000 → container 5000).

Mermaid → DSPy Generator (Alpha)
--------------------------------
- Generator CLI (`mermaid2dspy.py`) converts flowcharts into runnable DSPy programs.
- Variants emitted per workflow: `predict`, `cot`, `clarity` (and placeholder `react`).
- CLARITY implemented as first-class DSPy modules (`ClarityStep`, `ClarityDecision`).
- Phase specials in runtime:
  - Conversation nodes: build context from repo + DB + KB/Ontology, capture fixed intent via transcript acceptance.
  - INIT_6E nodes: synthesize 6E doc, extract normalized fields, persist to SQL (SQLite by default).
  - Intent nodes: forward the fixed intent captured during Conversation.
- Tools added for context:
  - `repo_summary`, `db_schema` (SQLite), `kb_summary`, `ontology_summary`.

6E Pipeline (Alpha)
-------------------
- SixE modules: `SixEWriter` (intent+context → 6E doc), `SixEExtractor` (6 fields), helpers.
- SQL store: `sixe` table with 6E columns + metadata; auto-created in SQLite (`SIXE_DB_URL`).
- Query with sqlite3 for quick inspection.

Recent Verifications
--------------------
- Ran traced examples for `example_predict`, `vibegen`, `viberefine`, and `codegen`.
- Confirmed MLflow auto-creates the "DSPy" experiment and logs traces.
- Generated runnable script in `generated/doc_qa_sig.py` with a working demo.

Registry & Provider Selection
-----------------------------
- Provider registry is implemented and integrated into services.
- Default provider is `codex-exec`; you can override with `DSPX_PROVIDER`.
- Codex provider auto-registers when needed (ensure_default_providers).

Known Gaps
----------
- Provider API and DTOs:
  - No `LMBase` abstraction yet; services directly rely on DSPy BaseLM-compatible classes.
  - No versioned request/response DTOs to stabilize contracts across layers.
- Tools & adapters:
  - No ToolRegistry yet; retrieval/storage/eval adapters are planned.
- Service layer:
  - Orchestration logic moved into `dspx/services`; CLIs are thin wrappers.
- Plugins and tools:
  - No plugin loader yet; submodules referenced manually via PYTHONPATH.
- Tests and CI:
  - No unit or e2e tests yet; no CI to guard interfaces or trace regressions.

Risks and Constraints
---------------------
- Codex Exec with `--dangerously-bypass-approvals-and-sandbox` is powerful but risky; ensure you run in a safe environment.
- Model availability depends on your OpenAI access; unsupported models will error.
- MLflow server ships without auth; keep it private or put it behind a reverse proxy.

Environment Snapshot
--------------------
- Python 3.13 (managed by uv)
- dspy-ai 3.0.2
- codex-cli 0.24.0
- mlflow 3.3.1 (server via Docker; tracing via `mlflow.dspy.autolog()`)
Tools
-----
- ToolRegistry with focused utilities:
  - Web/data: `web_search`, `web_fetch`, `web_scrape`, `data_preview`
  - Context: `repo_summary`, `db_schema` (SQLite), `kb_summary`, `ontology_summary`
- Justfile tasks for quick demos:
  - `just web-search "query"` / `just web-fetch url=...` / `just web-scrape url=... selector="..."`
  - `just data-preview path=/path/to/file.csv`

Limitations and Open Issues
---------------------------
- Mermaid parsing covers common flowchart syntax; subgraphs and chained edges need refinement.
- Decision routing uses label string inclusion; should restrict to explicit outgoing labels.
- ReAct variant is placeholder; real tools wiring and safety guards pending.
- Intent capture uses a transcript-file stub; live Discord/bot integration not wired yet.
- SQL store is SQLite-only; Postgres/SQLAlchemy integration pending.
- No unit/e2e tests yet; CI absent.
