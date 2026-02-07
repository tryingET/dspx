DSPx: Provider-Agnostic DSPy Toolkit (Pi RPC First)
===================================================

[![CI](https://github.com/OWNER/REPO/actions/workflows/ci.yml/badge.svg)](https://github.com/OWNER/REPO/actions/workflows/ci.yml)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)
[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/downloads/)
[![ty](https://img.shields.io/badge/type--checking-ty-informational)](#type-checking)

DSPx is a provider-agnostic toolkit around DSPy. Current default posture is Pi RPC (`pi-rpc`), with additional providers (Codex/Claude/Gemini/OpenRouter/Stub/Multi) available as optional backends.

Canonical docs map
------------------
- Architecture: `docs/ARCHITECTURE.md`
- Vision/principles: `docs/VISION.md`
- Current status: `PROJECT_STATUS.md`
- Roadmap/next actions: `NEXT_STEPS.md`
- Monorepo layout + boundaries: `docs/MONOREPO_TRANSITION.md`
- Forge design + commands: `docs/FORGE.md`
- Server runtime/security: `docs/SERVER.md`
- OpenAPI tooling: `docs/OPENAPI_TOOLING.md`
- Native signature pipeline: `docs/SIGNATURE_NATIVE_PIPELINE.md`
- Policy defaults matrix: `docs/POLICY_DEFAULTS.md`
- Upstream contribution workflow (DSPy/MLflow): `docs/UPSTREAM_CONTRIBUTING_WORKFLOW.md`
- ADR index (decisions): `docs/adr/README.md`

Prerequisites
-------------
- Python 3.13+ (this project is initialized with 3.13)
- uv package manager (https://docs.astral.sh/uv/)
- For Pi RPC provider: `pi` CLI installed (`pi --version`)
- Optional legacy provider: Codex CLI installed/authenticated (`codex --version`, `codex login status`)

Configuration
-------------
- This repo ships `example.toml`. Copy it to a local `config.toml` and edit as needed:

  cp example.toml config.toml

- You can also point `DSPX_CONFIG` to any config path. The loader searches the nearest `config.toml` if none is set.
- Provider selection defaults to `DSPX_PROVIDER=pi-rpc`; override with `DSPX_PROVIDER=...` (or `dspx --provider ...`) to select another provider such as `openrouter`, `claude-cli`, `gemini-cli`, `codex-exec`, or `stub`.
- Secrets: `.env` is supported (git-ignored) and is loaded automatically by `just` recipes. Put `OPENROUTER_API_KEY=...` there if you use OpenRouter.

Files
-----
- `packages/dspx-core/src/dspx/`: core runtime package.
  - Providers/LM wrappers: `*_lm.py` (e.g., `codex_exec_lm.py`, `claude_cli_lm.py`, `gemini_cli_lm.py`, `multi_provider_lm.py`).
  - Core CLI entrypoint: `cli/dspx.py`.
  - Example CLIs: `cli/example_predict.py`, `cli/codegen.py`, `cli/vibegen.py`, `cli/viberefine.py`.
- `apps/forge/src/dspx_forge/`: Forge app package + CLI (`dspx-forge`).
- `scripts/`: repo automation/guardrails (`check_monorepo_boundaries.py`, compat smoke scripts).
- `docs/`: architecture, status, next steps, and operator guides.
- `~/programming/upstream/`: sibling upstream clones (recommended for `attachments`, `dspy`, `mlflow`, and patch workflows).

Project Template
----------------
For a reusable setup guide when starting new projects with DSPy + dspx CodexExec + attachments + MLflow, see:

- `~/programming/dspy-dspx-attachments-mlflow.md`

Architecture & Vision
---------------------
- This repo follows a layered design with clear seams for extension:
  - Core: config loader, MLflow tracing, typed DTOs, LM provider base + registry, tool registry
- Providers: Codex Exec, Claude CLI, Gemini CLI, Pi RPC, Multi‑provider, Stub LM
  - Also supported: OpenRouter (OpenAI-compatible HTTP API) via provider name `openrouter`
  - Pi RPC provider name: `pi-rpc` (long-lived `pi --mode rpc` subprocess)
  - Services: codegen, native signature generation, refine, module generation, mermaid workflows, agents
  - CLI: thin entrypoints delegating to services; unified `dspx` CLI available
- See docs/VISION.md (principles/roadmap), docs/ARCHITECTURE.md (multi‑view diagrams), and docs/OPENAPI_TOOLING.md (MVP details).
- Tutorials: docs/TUTORIAL_E2E.md (Mermaid + OpenAPI + CSV), docs/GEPA_FROM_MODULE_GEN.md (GEPA from module-gen).

Quick Start (uv)
----------------
1) Install deps and run the clean-clone smoke flow:

   just clean-clone-smoke

   (Equivalent explicit sequence: `uv sync`, `just dspx --help`, `just forge --help`, `just test`.)

   Tests run offline/deterministic by default (they force `DSPX_PROVIDER=stub` and `MLFLOW_ENABLE=0`).
   Live provider/network tests are opt-in via `DSPX_RUN_LIVE_TESTS=1`.

   Optional (OpenRouter): create `.env` (git-ignored) so Just recipes can load it:
   - `cp .env.example .env`

2) Verify Pi CLI is available:

   pi --version

3) Smoke the configured provider (from source):

   just dspx providers smoke --json

For legacy Codex-specific example flow, `just example` is still available but no longer the default posture.

Unified CLI (dspx)
------------------
- Signature (deterministic template):

  just dspx signature gen "Extract names" --template-version simple-v1 --class-name Sig_Names --outfile generated/sig.py

- Module generation (deterministic template):

  just dspx module-gen -n Summarizer -d "Summarizes text" -i text -o summary --template-version simple-v1 --outfile generated/module.py

- Codegen (deterministic template):

  just dspx codegen 'A CLI that prints "hello"' --language python --template-version simple-v1 --outfile generated/hello.py

- Mermaid workflows (multiple variants):

  just dspx mermaid gen -f path/to/diagram.mmd -n flow -v predict,cot,react

- Mermaid with signature‑per‑node (native generator):

  just dspx mermaid sig -f path/to/diagram.mmd -n flow --provider codex-exec

- Provider smoke (debugging provider config quickly):

  just dspx providers smoke --json

OpenRouter Provider
-------------------
- Create `.env` from `.env.example` (git-ignored) and set your key:

  cp .env.example .env
  # recommended: OPENROUTER_API_KEY=op://... (resolved via `op run`)

- Safer alternatives (avoid putting secrets on the command line):
  - File: `dspx --openrouter-api-key-file /path/key.txt ...`
  - 1Password CLI: `dspx --openrouter-api-key-op op://Vault/Item/field ...`
  - Prompt: `dspx --openrouter-api-key-prompt ...`
  - CI pipe: `printf %s "$OPENROUTER_API_KEY" | dspx --openrouter-api-key-stdin ...`

- 1Password CLI (recommended pattern): use `op run` to inject secrets as env vars:

  OPENROUTER_API_KEY="op://Vault/Item/field" op run -- dspx signature gen "..."

- Justfile shortcuts (recommended):
  - Ensure 1Password CLI `op` is installed and authenticated.
  - Run: `just openrouter-codegen "A python program that prints hello"`
  - Run: `just openrouter-signature "Extract names from text"`
  - Even simpler (no quotes/flags): `just or-codegen Write a python script that prints hello`

Pi RPC Provider
---------------
- Use pi as a provider (RPC mode, long-lived subprocess):

  DSPX_PROVIDER=pi-rpc just dspx providers smoke --json

- Live Pi RPC smoke (opt-in; defaults to `openai-codex` + `gpt-5.1-codex-mini`):

  DSPX_RUN_LIVE_TESTS=1 just pi-live-smoke

  # optional override
  DSPX_RUN_LIVE_TESTS=1 just pi-live-smoke openai-codex gpt-5.1-codex-max

- Common env knobs:
  - `DSPX_PI_BIN` (default: `pi`)
  - `DSPX_PI_PROVIDER`, `DSPX_PI_MODEL`, `DSPX_PI_THINKING`
  - `DSPX_PI_TIMEOUT` (seconds)
  - Safety defaults: `DSPX_PI_NO_TOOLS=1`, `DSPX_PI_NO_SESSION=1`, `DSPX_PI_DISABLE_RESOURCES=1`

OpenAPI Tools & Workflows
-------------------------
- Inspect operations in a local spec (JSON or YAML):

  dspx tools openapi ops path/to/spec.yaml

- Call a single operation with a host allowlist:

  dspx tools openapi call --spec path/to/spec.json --op ping --allow-host api.example.com

- Persist a mapping for a prefix (used by workflows):

  dspx tools openapi load -p gh --spec /abs/github.json --allow-host api.github.com
  dspx tools openapi env -p gh  # prints export commands

- Mermaid openapi nodes: label a node as `openapi:<prefix>.<operationId>`.
  - Upstream input supports JSON envelope: `{ "params": {...}, "body": {...}, "headers": {...}, "timeout": 10 }`.
  - The generated program auto‑registers the toolpack using env (`DSPX_OPENAPI_SPEC_<P>`) or a mapping file under `generated/openapi/<prefix>.json`.

Adapters: Datasets & Eval
-------------------------
- Train/test split from a CSV (prints JSON with output paths and counts):

  dspx adapters dataset split --csv data.csv --outdir splits --test-size 0.3

- Stratified split by label with group awareness; balance per-label by groups (not instances):

  dspx adapters dataset split \
    --csv data.csv \
    --outdir splits_g \
    --test-size 0.5 \
    --stratify-col label \
    --group-col session_id \
    --group-balance groups

- Three-way stratified split with ratios and default per-instance balancing:

  dspx adapters dataset split \
    --csv data.csv \
    --outdir splits_3 \
    --ratios 0.7,0.2,0.1 \
    --stratify-col label \
    --group-col session_id

- Evaluate predictions from a single CSV:

  dspx adapters eval run --csv preds.csv --truth-col y --pred-col yhat --metric accuracy

- Join two CSVs by id and evaluate ROC-AUC:

  dspx adapters eval run2 \
    --csv-true truth.csv \
    --csv-pred scores.csv \
    --id-col id \
    --truth-col y \
    --pred-col score \
    --metric roc_auc

Server (FastAPI) & Security
---------------------------
Run the optional HTTP server (`dspx-server`, FastAPI + Granian) to expose endpoints:

- Endpoints: `POST /signature`, `POST /module`, `POST /mermaid`
- Start (Granian): `granian --interface asgi --host 127.0.0.1 --port 33213 dspx.server.app:app`
- For Docker / remote access: bind `--host 0.0.0.0` and put auth + TLS in front (reverse proxy).
- Or with Just: `just start` (override via `just start host=0.0.0.0 port=33213`)

Auth (opt‑in):
- Single token: `export DSPX_SERVER_TOKEN='s3cr3t'`
- Multiple tokens: `export DSPX_SERVER_TOKENS='tok1,tok2'`
- Token file (one per line): `export DSPX_SERVER_TOKEN_FILE=/path/tokens.txt`
- Require auth (defaults to on when any token present): `export DSPX_AUTH_REQUIRED=1`
- Call with header: `Authorization: Bearer <token>`

Rate limiting (opt‑in):
- Enable: `export DSPX_RATE_LIMIT_ENABLED=1`
- Default cap: `export DSPX_RATE_LIMIT_DEFAULT='60/min,10/sec'`
- Per‑path caps (JSON): `export DSPX_RATE_LIMIT_PATHS='{"POST /module":"5/min"}'`
- Identity: `export DSPX_RATE_LIMIT_IDENTITY=token` (or `ip`)
- Trusted proxies (use X‑Forwarded‑For): `export DSPX_TRUSTED_PROXIES='10.0.0.0/8,192.168.0.0/16,127.0.0.0/8'` (CIDR list)

Metrics (opt‑in):
- Enable: `export DSPX_METRICS_ENABLED=1`
- JSON: `GET /metrics` (Prometheus text: `GET /metrics?format=prom`)

More docs: see docs/SERVER.md

Standardized error responses:
- 401: `{ "error": "unauthorized", "detail": "...", "status": 401 }`
- 429: `{ "error": "rate_limited", "detail": "limit exceeded", "status": 429 }`

Quick curl examples:

  # Signature (requires token if enabled)
  curl -sS -X POST http://localhost:33213/signature \
    -H "Authorization: Bearer $DSPX_SERVER_TOKEN" \
    -H 'Content-Type: application/json' \
    -d '{"prompt":"Echo signature","template_version":"simple-v1"}'

  # Module with per-path rate limit override
  export DSPX_RATE_LIMIT_ENABLED=1
  export DSPX_RATE_LIMIT_PATHS='{"POST /module":"1/sec"}'
  curl -sS -X POST http://localhost:33213/module \
    -H "Authorization: Bearer $DSPX_SERVER_TOKEN" \
    -H 'Content-Type: application/json' \
    -d '{"name":"M","description":"","inputs":[],"outputs":[]}'

Install, Update, Build
----------------------
- Dev install (editable, optional): `just dev-install` — exposes console scripts.
- Clean-clone smoke (used in CI): `just clean-clone-smoke`.
  - Runs: `uv sync`, `just dspx --help`, `just forge --help`, `just test`.
- Run commands without install:
  - Unified CLI: `just dspx ...` (runs from source via `uv run -m`).
  - Forge CLI: `just forge ...`.
  - Multi demo: `uv run -q python -m dspx.cli.multi_demo ...`.
- Package-scoped quality/test slices:
  - Core: `just lint-core && just typecheck-core && just test-core`
  - Forge: `just lint-forge && just typecheck-forge && just test-forge`
  - Forge/core wheel compat matrix: `just forge-core-compat-matrix`
    - `min` track expects tag `dspx-core-v<forge lower bound>` (e.g. `dspx-core-v0.1.0`).
- Update (editable install): `git pull` (code updates immediately).
- Update (uv tool install): `uv tool install --force .` in repo.
- Build packages:
  - all: `just build`
  - core only: `just build-core`
  - forge only: `just build-forge`
- Publish (PyPI): set `PYPI_TOKEN` then:
  - all artifacts in `dist/`: `just publish`
  - core only: `just publish-core`
  - forge only: `just publish-forge`

Type Checking
-------------
- Enforced in CI via `just typecheck` (runs `uvx ty check`).
- Local run: `just typecheck`
- Pre-commit uses ruff hooks by default; run ty manually or rely on CI.
- Excludes: `generated/` and `examples/` (plus external sibling clones outside this repo).


Release Cycle
-------------
- Default policy: independent package versioning (`dspx-core` and `dspx-forge` release separately).
- Suggest Semantic Versioning with lightweight cadence:
  - Patch on fixes/docs; minor on features; major for breaking changes.
- Forge runtime dependency is bounded to a compatible core range (currently `dspx-core>=0.1.0,<0.2.0`).
- Package-scoped release flow (recommended):
  - Core:
    - prep: `just release-core new=X.Y.Z`
    - tag: `just tag-core v=X.Y.Z` (creates `dspx-core-vX.Y.Z`)
    - publish: `just publish-core` (requires `PYPI_TOKEN`)
  - Forge:
    - prep: `just release-forge new=X.Y.Z`
    - tag: `just tag-forge v=X.Y.Z` (creates `dspx-forge-vX.Y.Z`)
    - publish: `just publish-forge` (requires `PYPI_TOKEN`)
- GitHub Actions release workflows:
  - `.github/workflows/release-core.yml` (trigger: `dspx-core-v*`)
  - `.github/workflows/release-forge.yml` (trigger: `dspx-forge-v*`)
- Coupled legacy helper remains available:
  - `just release new=X.Y.Z` / `just tag v=vX.Y.Z` / `just publish`

Customization
-------------
- Change model: set `CODEX_MODEL` env var or edit `model_flag` in `packages/dspx-core/src/dspx/cli/example_predict.py` (e.g., `gpt-5`).

Claude Code (Headless) Provider
-------------------------------
Use the `claude` CLI programmatically via `ClaudeHeadlessLM`.

Quick start:

  uv pip install -e .
  python -c "from dspx.claude_cli_lm import ClaudeHeadlessLM; import dspy; dspy.configure(lm=ClaudeHeadlessLM(output_format='text')); p=dspy.Predict('question -> answer'); print(p(question='Explain Python context managers').answer)"

Environment variables for the built-in registry factory:

- `CLAUDE_BIN` (default: `claude`)
- `CLAUDE_OUTPUT_FORMAT` (`text`|`json`|`stream-json`)
- `CLAUDE_APPEND_SYSTEM_PROMPT`
- `CLAUDE_ALLOWED_TOOLS` (comma or space separated)
- `CLAUDE_DISALLOWED_TOOLS` (comma or space separated)
- `CLAUDE_PERMISSION_MODE` (e.g., `acceptEdits`)
- `CLAUDE_MCP_CONFIG` (path to servers.json)
- `CLAUDE_PERMISSION_PROMPT_TOOL`
- `CLAUDE_RESUME` (session id)
- `CLAUDE_CONTINUE` (`1` to continue most recent)
- `CLAUDE_CWD` (working directory)
- `CLAUDE_USE_CLI_CWD` (`1` to pass `--cwd` to CLI)
- `CLAUDE_TIMEOUT` (seconds)

Registry name: `claude-cli`. You can select it via `DSPX_PROVIDER=claude-cli` with `provider_registry.create_from_env()`.

FunctAI Integration
-------------------
FunctAI builds on DSPy. You can pass any DSPy BaseLM—including `CodexExecLM` or `ClaudeHeadlessLM`—to FunctAI’s global configure:

  from functai import configure
  from dspx.codex_exec_lm import CodexExecLM
  from dspx.claude_cli_lm import ClaudeHeadlessLM

  # Use Codex Exec
  configure(lm=CodexExecLM(model_flag='gpt-4.1', auto_mode=True))

  # Or use Claude CLI headless with JSON output
  configure(lm=ClaudeHeadlessLM(output_format='json'))

No other changes are required; FunctAI forwards the LM into DSPy under the hood.

Default Codex flags
-------------------
The wrapper/example currently passes:
- `-m gpt-5`
- `-c model_reasoning_effort="minimal"`
- `--dangerously-bypass-approvals-and-sandbox`

You can adjust these by editing the `CodexExecLM(...)` arguments in `packages/dspx-core/src/dspx/cli/example_predict.py`.

Native signature generation
---------------------------
- DSPx signature generation/refinement no longer depends on external `vibe-dspy` code.
- Native generation is now **spec-first** (structured schema → deterministic code rendering), with fallback to deterministic templates when needed.
- Generation is provider-capability-aware (`json_mode` vs non-JSON providers) and supports bounded retries (`DSPX_SIGNATURE_MAX_ATTEMPTS`).
- Generated signatures run through validation gates (AST/compile/structure/smoke checks) before final selection.
- Refinement keeps structured feedback memory instead of raw prompt sprawl.
- `vibegen` / `viberefine` CLI command names are kept for continuity, but use native DSPx implementation.

Upstream clone: attachments
---------------------------
- Recommended location: `~/programming/upstream/attachments`
- Clone:

  mkdir -p ~/programming/upstream
  git clone https://github.com/MaximeRivest/attachments.git ~/programming/upstream/attachments

- Usage/import check:

  uv run env PYTHONPATH=~/programming/upstream/attachments/src python -c "import attachments; print('attachments ok')"

Submodules
----------
- This repository no longer tracks git submodules.
- Prefer sibling clones under `~/programming/upstream`.

Code Generator CLI
------------------
- Generate code (prints to stdout by default):

  just dspx codegen "Create a Python CLI that says hello"

- Language hint and write to file:

  just dspx codegen "CLI that prints 'Hello, world!'" --language python --outfile hello.py

- Environment variables to control Codex behavior:

  - `CODEX_MODEL` (default: `gpt-5`)
  - `CODEX_REASONING` (default: `minimal`)
  - `CODEX_BYPASS` (default: `1`, enable `--dangerously-bypass-approvals-and-sandbox`)

  Example with explicit model:

  CODEX_MODEL=gpt-4.1 just dspx codegen "CLI that prints 'Hello'" --language python --outfile hello.py

Mermaid → DSPy Programs
-----------------------
- Paste a Mermaid flowchart and generate multiple DSPy program variants (predict, CoT, ReAct) that execute the workflow end-to-end:

  just mermaid path/to/diagram.mmd name="my_flow" variants="predict,cot,react"

- Or via stdin:

  just mermaid-stdin name="my_flow"
  # paste the Mermaid, then Ctrl-D


License
-------
AGPL-3.0. See `LICENSE`.

- Output goes to `generated/workflows/<name or hash>/` as `program_<variant>.py` plus the original `workflow.mmd`.

- Extra variant: `clarity` (Constraints→Learn→Abduce→Robust-plan→Intervene→Trace→Yield). Example:

  just dspx mermaid gen -f path/to/diagram.mmd -n my_flow -v clarity

Native Signature CLI (legacy command names)
-------------------------------------------
- Generate a DSPy signature (native DSPx service):

  just vibegen "Count birds in an image and describe each"

- Wrap the signature into a runnable script that configures Codex Exec and save it:

  uv run -q python -m dspx.cli.vibegen --wrap-script -o generated/birds_sig.py "Count birds in an image and describe each"

- Control model/flags via env (same as the rest of this repo):
  - `CODEX_MODEL` (default: `gpt-5`)
  - `CODEX_REASONING` (default: `minimal`)
  - `CODEX_BYPASS` (default: `1`)

Interactive Refine
------------------
- Run refine with Codex Exec (interactive):

  uv run -q python -m dspx.cli.viberefine --attempts 3 "Extract topics and sentiment from support tickets"

- Non-interactive (accept first draft) and save to file:

  just viberefine "Extract topics and sentiment from support tickets" out="generated/tickets_sig.py"

- Wrap into runnable script that configures Codex Exec:

  uv run -q python -m dspx.cli.viberefine --non-interactive --wrap-script -o generated/tickets_script.py "Extract topics and sentiment from support tickets"

Tracing with MLflow
-------------------
- Install (already added to this project):

  uv add "mlflow>=2.18.0"

- Start server (recommended with a SQL backend):

  mlflow server --backend-store-uri sqlite:///mlflow.sqlite --host 127.0.0.1 --port 5000

- Enable tracing via env and run any script (example):

  uv run env MLFLOW_ENABLE=1 MLFLOW_TRACKING_URI=http://127.0.0.1:5000 MLFLOW_EXPERIMENT=DSPy \
    MLFLOW_RUN_NAME="local-test-$(date +%Y%m%d-%H%M%S)" \
    python -m dspx.cli.example_predict

- Or inside your script, after configuring providers:

  from dspx.tracing import enable_mlflow_from_env, ensure_run_from_env
  enable_mlflow_from_env()
  ensure_run_from_env()  # uses $MLFLOW_RUN_NAME if provided

- Read-only CLI metadata commands intentionally skip MLflow bootstrap so they stay
  offline/instant even if `config.toml` points to a remote tracking URI:
  - `dspx providers list`
  - `dspx providers capabilities`
  - `dspx tools openapi ops|describe|env|load`

Run naming
----------
- Set a run name via env to keep experiments organized:

  export MLFLOW_RUN_NAME="intent-context-$(date +%Y%m%d-%H%M%S)"

- Many scripts also call `mlflow.start_run(run_name=...)`. If both are set, the explicit `start_run` argument takes precedence over `MLFLOW_RUN_NAME`.
- Library behavior: `enable_mlflow_from_env()` will auto‑start a run using
  `MLFLOW_RUN_NAME` if no run is active yet. Scripts can still override by
  starting their own run explicitly.

Synology NAS (Docker) Example
-----------------------------
- Use a host port that doesn't conflict with Synology services, e.g., map 50000→5000:

  version: "3.9"
  services:
    mlflow:
      image: ghcr.io/mlflow/mlflow:3.3.1
      command: >
        mlflow server
        --host 0.0.0.0
        --port 5000
        --backend-store-uri sqlite:////mlflow/mlflow.db
        --artifacts-destination /mlflow/artifacts
      ports:
        - "50000:5000"
      volumes:
        - /volume1/mlflow:/mlflow

- Then point this project at the NAS:

- Update `config.toml` → `[mlflow].tracking_uri = "http://NAS_IP:50000"`
  - Or export `MLFLOW_TRACKING_URI=http://NAS_IP:50000`
  - Optionally set a run name prefix per machine/project:

    export MLFLOW_RUN_NAME="orgmem-intent-$(hostname)-$(date +%Y%m%d-%H%M%S)"

Config file (no more long env lines)
------------------------------------
- Project reads `config.toml` at startup and sets env vars automatically.
- Example (start from `example.toml` in the repo):

  [mlflow]
  enable = true
  tracking_uri = "http://192.168.1.10:50000"
  experiment = "DSPy"
  # Optional: you can continue to set `MLFLOW_RUN_NAME` via env for run naming

  [codex]
  model = "gpt-5"
  reasoning_effort = "minimal"
  bypass = true

Gemini (Headless) Provider
--------------------------
Use the `gemini` CLI programmatically via `GeminiCLILM` (non-interactive `-p`).

Quick start:

  python -c "from dspx.gemini_cli_lm import GeminiCLILM; import dspy; dspy.configure(lm=GeminiCLILM()); p=dspy.Predict('question -> answer'); print(p(question='What is a git worktree?').answer)"

Environment variables for the built-in registry factory:

- `GEMINI_BIN` (default: `gemini`)
- `GEMINI_MODEL` (forwarded in env; configure via settings.json or env)
- `GEMINI_CWD` (working directory for subprocess)
- `GEMINI_TIMEOUT` (seconds)
- `GEMINI_EXTRA_FLAGS` (space-separated additional CLI flags)

Registry name: `gemini-cli`.

Multi‑Provider Abstraction
-------------------------
Run multiple SDKs side‑by‑side without picking a single BaseLM.

- Registry name: `multi`
 - Env: `DSPX_MULTI_PROVIDERS="codex-exec,claude-cli,gemini-cli"`, `DSPX_MULTI_STRATEGY="sequential_first|parallel_first|collect_concat|collect_longest"`
- Python usage:

  from dspx.multi_provider_lm import MultiProviderLM
  from dspx.codex_exec_lm import CodexExecLM
  from dspx.claude_cli_lm import ClaudeHeadlessLM
  import dspy

  lm = MultiProviderLM(
      providers=[
          CodexExecLM(model_flag="gpt-5", auto_mode=True),
          ClaudeHeadlessLM(output_format="text"),
      ],
      strategy="sequential_first",  # or: parallel_first, collect_concat, collect_longest
  )
  dspy.configure(lm=lm)

Safety and side effects:
- Prefer `sequential_first` when providers can modify files (e.g., code‑editing tools).
- `parallel_first` can’t cancel already‑running CLI processes; they finish in background.
- For isolation, point each provider at separate CWDs and disable dangerous flags.

Aligned policy knobs:
- Set once, applied across providers where applicable:
  - `policy_bypass_permissions=True` → CodexExecLM: `dangerously_bypass=True`; ClaudeHeadlessLM: `permission_mode='acceptEdits'`.
  - `policy_allowed_tools`, `policy_disallowed_tools` → forwarded to Claude when available.
  - `policy_append_system_prompt` → forwarded to Claude.

Parallel variants:
- Shared workspace (2a): `MultiProviderLM(..., strategy='parallel_first', parallel_isolated=False, base_cwd=None)`.
- Isolated worktrees (2b): `MultiProviderLM(..., strategy='parallel_first', parallel_isolated=True, base_cwd='/path/to/repo', isolation_mode='git-worktree')`
  - Creates detached worktrees from `--worktree-commitish` (default `HEAD`) and cleans them up when done.
- Early abort on validation (2c): provide a validator and keep the first passing result; others are terminated when supported.
  - `MultiProviderLM(..., strategy='parallel_first', validator=my_ok, abort_others_on_validate=True)`
  - Works best with our CLI wrappers (`CodexExecLM`, `ClaudeHeadlessLM`) which expose `start/collect/terminate`.

Env configuration for `multi` registry:
- `DSPX_MULTI_PROVIDERS`: order of providers, e.g. `codex-exec,claude-cli,gemini-cli`
- `DSPX_MULTI_STRATEGY`: `sequential_first|parallel_first|collect_concat|collect_longest`
- `DSPX_MULTI_PARALLEL_ISOLATED`: `1` to mirror the workspace per provider
- `DSPX_MULTI_BASE_CWD`: base repo/workspace to mirror when isolated
- `DSPX_MULTI_ISOLATION_MODE`: `mirror` (default) or `git-worktree`
- `DSPX_MULTI_WORKTREE_COMMITISH`: commit/ref for worktree (default `HEAD`)
- `DSPX_MULTI_CLEANUP_ISOLATED`: `1` to auto-remove mirrored dirs/worktrees
- `DSPX_MULTI_POLICY_BYPASS`: `1` to enable cross-SDK bypass alignment
- `DSPX_MULTI_POLICY_ALLOWED_TOOLS`: tools list for Claude
- `DSPX_MULTI_POLICY_DISALLOWED_TOOLS`: tools list for Claude
- `DSPX_MULTI_POLICY_APPEND_SYSTEM_PROMPT`: extra system prompt for Claude

CLI demo with MLflow
--------------------
- Compare strategies and log results to MLflow:

  dspx-multi-demo "Refactor this module for clarity" \
    --providers codex-exec,claude-cli \
    --strategy parallel_first \
    --parallel-isolated \
    --isolation-mode git-worktree \
    --base-cwd /path/to/repo \
    --worktree-commitish HEAD \
    --validator json \
    --bypass \
    --mlflow

- Set MLflow env (optional): `MLFLOW_TRACKING_URI`, `MLFLOW_EXPERIMENT`, `MLFLOW_RUN_NAME`, `MLFLOW_ENABLE=1`.

Simple Modern uv
----------------
This repo follows a simple modern `uv` setup:

- Tasks via Justfile:
  - `just install` / `just dev-install` — sync deps or editable install.
  - `just upstream-link-dspy path=...` / `just upstream-link-mlflow path=...` / `just upstream-reset` — upstream sibling-clone workflow (no new submodules).
  - `just fmt` / `just lint` / `just typecheck` — ruff + ty.
  - `just test` / `just test-core` / `just test-forge` — marker-based pytest slices (`forge` vs non-`forge`).
  - `just build` / `just build-core` / `just build-forge` — build packages.
  - `just publish` / `just publish-core` / `just publish-forge` — publish artifacts.
  - `just release-core new=X.Y.Z` / `just release-forge new=X.Y.Z` — package-scoped release prep.
  - `just forge-core-compat-matrix` — wheel-based forge/core compatibility smoke.
  - `DSPX_RUN_LIVE_TESTS=1 just pi-live-smoke` — Pi RPC live smoke.
- Dev dependencies declared under `[dependency-groups.dev]` for uv.
- Console scripts defined in `pyproject.toml` under `[project.scripts]`.

- Your commands stay short:

Task Runner
-----------
- A Justfile is included for common commands:

  just            # list tasks
  just install    # uv sync
  just example    # run example_predict
  just vibegen "Make a signature..."
  just viberefine "Echo signature"
  just codegen "A Python CLI that prints 'ok'"
  just smoke      # run a small suite

  just dspx signature refine "Classify sentiment"

What gets logged
- DSPy predictions and steps (inputs/outputs, LM config, tools) appear under the selected experiment's Traces tab in the MLflow UI.
- This repo enables autologging automatically when `MLFLOW_ENABLE` is truthy, using settings from `MLFLOW_TRACKING_URI` and `MLFLOW_EXPERIMENT`.
- If `MLFLOW_ENABLE=0`, DSPx will not import or call MLflow (CI-safe: no accidental tracking-server HTTP retries).
- Replay/reproducibility should rely on local manifests/meta/cache artifacts; MLflow is the explainability sink, not the replay source of truth.

- Non-interactive runs: `auto_mode=True` adds `--full-auto` to avoid prompts.
- Extra flags: pass `extra_flags=["--json"]` or others in `CodexExecLM(...)`.
- Working directory: set `workspace="/path/to/project"` if Codex should run there.
- Inspect calls: `lm.history` stores the prompt, command, and return code.

Notes
-----
- The wrapper flattens chat-style messages into a plain prompt for the CLI.
- If Codex exits non-zero, the wrapper still returns captured stdout (or stderr). Set `strict=True` to raise on failures.
- Ensure your environment has the necessary permissions for code execution if Codex writes/executes files during `--full-auto` runs.
Project Layout
--------------
- `packages/dspx-core/src/dspx/`: core runtime/providers/services/tools/CLI
- `apps/forge/src/dspx_forge/`: Forge app CLI + workflow logic
- `docs/`: project docs (vision, status, next steps)
- `examples/`: curated, versioned examples and workflows
- `generated/`: local outputs (ignored); kept for CLI defaults
- `~/programming/upstream/`: sibling clones (`attachments`, `dspy`, `mlflow`, and other upstream patch checkouts)

Credits & upstream influences
-----------------------------
Thanks to upstream authors/projects that informed this repo and workflows:

- `vibe-dspy` — https://github.com/Archelunch/vibe-dspy
- `attachments` — https://github.com/MaximeRivest/attachments
- `ovllm` — https://github.com/MaximeRivest/ovllm
- `DSPy` — https://github.com/stanfordnlp/dspy
- `MLflow` — https://github.com/mlflow/mlflow
- `Codex CLI` — https://github.com/openai/codex
- `pi-mono` / `pi-coding-agent` — https://github.com/badlogic/pi-mono

We keep these acknowledgements even where integrations are now optional, replaced, or legacy.
