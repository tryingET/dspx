Project Status
==============

Overview
--------
This repo provides a thin, extensible SDK around multiple headless CLI
providers and DSPy, with MLflow tracing and utilities for program
generation. The goal is an execution‑aware LM backend with clean seams
for providers, tools, modules, and optimizers — now including a
multi‑provider orchestration layer and a first consensus reducer.

What Works Today
----------------
- Multi‑provider orchestration (`multi_provider_lm.py`):
  - Strategies: `sequential_first`, `parallel_first`, `collect_concat`,
    `collect_longest`.
  - Isolation: mirror copies or git worktrees (detached) per provider,
    with auto‑cleanup; fallback to mirror if git not available.
  - Policy alignment: single bypass knob maps to provider‑specific
    flags (`dangerously_bypass`, `permission_mode=acceptEdits`).
  - Early abort: validator gate cancels other providers when a passing
    result arrives (for async‑capable wrappers).
- Consensus reducer (MVP):
  - `HeuristicReducer` combines JSON parse success (optional
    requirement), keyword coverage, and log‑scaled length. Used to pick
    a winner when no early validator succeeds.
- Provider wrappers:
  - Codex Exec (`codex_exec_lm.py`):
    - Supports `--model`, reasoning effort via `-c model_reasoning_effort=...`, and `--dangerously-bypass-approvals-and-sandbox`.
    - Captures last agent message via `--output-last-message` for clean outputs.
    - Bridges to DSPy’s BaseLM; returns an OpenAI-like minimal response object.
    - Async control: `start/collect/terminate` with process‑group kill.
    - Diagnostics: warns if CLI missing with install/auth hints.
  - Claude Code (`claude_cli_lm.py`):
    - Headless `-p` with `--output-format {text,json,stream-json}`.
    - Allowed/disallowed tools, resume/continue, MCP config.
    - Async control + diagnostics on missing CLI.
  - Gemini CLI (`gemini_cli_lm.py`):
    - Headless `-p`; extra flags/env forwarded.
    - Async control + diagnostics on missing CLI.
- Provider registry & selection:
  - Built‑ins: `codex-exec`, `claude-cli`, `gemini-cli`, and `multi`.
  - `DSPX_PROVIDER` selects; env‑driven factories configure defaults.
- Demo & tooling:
  - `dspx-multi-demo`: compare sequential/parallel, isolation, and
    validator/reducer choices; logs to MLflow.
- MLflow tracing (`tracing.py` + `config.toml`):
  - Autologging enabled via `enable_mlflow_from_env()`; configured through `config.toml` (or env).
  - Verified runs (experiment "DSPy") appear in MLflow UI (NAS Docker or local server).
  - Downstream scripts may also start explicit runs (`mlflow.start_run`) and log params/artifacts for guaranteed visibility.
- Config management (`config_loader.py`):
  - Reads `config.toml` at startup; populates MLflow and Codex env vars automatically.
  - Discovery order: `DSPX_CONFIG` env → nearest `config.toml` by walking up from the current working directory.
- CLIs (console scripts):
  - `dspx-example`, `dspx-codegen`, `dspx-vibegen`, `dspx-viberefine`,
    `dspx-agent`, `dspx-mermaid`, `dspx-mermaid-sig`, `dspx-multi-demo`.
- Submodules:
  - `submodules/vibe-dspy` (signature generation utilities).
  - `submodules/attachments` and `submodules/ovllm` (optional utilities; importable via PYTHONPATH).
- MLflow in Docker:
  - `docker-compose.yml` for Synology NAS (host port 50000 → container 5000).

Mermaid → DSPy Generator (Alpha)
--------------------------------
- Generator CLI (`src/dspx/cli/mermaid2dspy.py`) converts flowcharts into
  runnable DSPy programs.
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

Dev Workflow (uv)
-----------------
- Justfile commands:
  - `just dev-install` (editable install), `just install` (sync deps)
  - `just fmt`/`just lint` scoped to `src/` and `docs/`
  - `just typecheck` excludes `generated/` and `submodules/`
  - `just build` creates wheels/sdist with `uv build`
  - `just tool-install` installs console scripts via `uv tool install .`

Known Gaps
----------
- Reducers: heuristic MVP shipped; judge‑based reducer and consensus
  workflows TBD.
- Type checks: project types still need refinement (some Optional and
  container typing improvements); third‑party libs lack stubs.
- CI: no GitHub Actions yet (lint/typecheck/build, publish on tag).
- Tests: no unit/e2e tests yet; demo relies on CLIs.
- Tooling: plugin loader and fuller ToolRegistry are pending.

Risks and Constraints
---------------------
- Codex Exec with `--dangerously-bypass-approvals-and-sandbox` is powerful but risky; ensure you run in a safe environment.
- Model availability depends on your OpenAI access; unsupported models will error.
- MLflow server ships without auth; keep it private or put it behind a reverse proxy.

Environment Snapshot
--------------------
- Python 3.13 (managed by uv)
- dspy-ai 3.x
- codex-cli 0.24.x
- mlflow 3.x (server via Docker; tracing via `mlflow.dspy.autolog()`)
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
- Config precedence can surprise if multiple parent folders contain a `config.toml`. Set `DSPX_CONFIG` for strict control.
