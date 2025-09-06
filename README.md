Using DSPy with Codex Exec as the Active LM
===========================================

[![CI](https://github.com/OWNER/REPO/actions/workflows/ci.yml/badge.svg)](https://github.com/OWNER/REPO/actions/workflows/ci.yml)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)
[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/downloads/)
[![mypy](https://img.shields.io/badge/type--checking-mypy-informational)](#type-checking)

This example shows how to use the OpenAI Codex CLI's execution mode (`codex exec`) as the language model for a DSPy program, via a small wrapper `CodexExecLM`.

Prerequisites
-------------
- Codex CLI installed and authenticated (e.g., `codex --version`, `codex auth whoami`).
- Python 3.13+ (this project is initialized with 3.13)
- uv package manager (https://docs.astral.sh/uv/)

Configuration
-------------
- This repo ships `config.example.toml`. Copy it to a local `config.toml` and edit as needed:

  cp config.example.toml config.toml

- You can also point `DSPX_CONFIG` to any config path. The loader searches the nearest `config.toml` if none is set.

Files
-----
- `codex_exec_lm.py`: DSPy-compatible wrapper around `codex exec`.
- `claude_cli_lm.py`: DSPy-compatible wrapper around the `claude` CLI (headless mode).
- `gemini_cli_lm.py`: DSPy-compatible wrapper around the `gemini` CLI (headless `-p`).
- `multi_provider_lm.py`: Aggregate multiple providers under one LM (`MultiProviderLM`).
- `example_predict.py`: A runnable DSPy script using `Predict("question -> answer")`.
- `codegen.py`: CLI to generate code from a spec using DSPy + Codex Exec.
- `submodules/vibe-dspy`: Git submodule pointing to https://github.com/Archelunch/vibe-dspy
- `submodules/attachments`: Git submodule pointing to https://github.com/MaximeRivest/attachments
- `submodules/ovllm`: Git submodule pointing to https://github.com/MaximeRivest/ovllm
- `vibegen.py`: Adapter CLI that uses vibe-dspy's `SignatureGenerator` but configures DSPy to use Codex Exec.
- `viberefine.py`: Interactive refine CLI using vibe-dspy + Codex Exec. Lets you review/improve the generated signature with quick feedback.

Project Template
----------------
For a reusable setup guide when starting new projects with DSPy + dspx CodexExec + attachments + MLflow, see:

- `~/programming/dspy-dspx-attachments-mlflow.md`

Architecture & Vision
---------------------
- This repo follows a layered design with clear seams for extension:
  - Core: config loader, MLflow tracing, typed DTOs, LM provider base + registry, tool registry
  - Providers: Codex Exec, Claude CLI, Gemini CLI, Multi‑provider
  - Services: codegen, signature generation (vibe), refine, mermaid workflows, agents
  - CLI: thin entrypoints delegating to services; unified `dspx` CLI planned
- See docs/VISION.md for principles/roadmap, and docs/ARCHITECTURE.md for multi‑view diagrams. OpenAPI design in docs/OPENAPI_TOOLING.md.

Quick Start (uv)
----------------
1) Initialize (already done here, but safe to run):

   uv init

2) Add dependencies (already added):

   uv add dspy-ai

3) Verify Codex CLI works and you are logged in:

   codex --version
   codex auth whoami

4) Run the example via uvx (console script):

   uvx dspx-example

It configures DSPy to use Codex Exec with `gpt-5`, minimal reasoning effort, and bypassed approvals/sandbox. Codex may write and run code under the hood; the final answer prints to stdout.

Install, Update, Build
----------------------
- Dev install (editable): `uv pip install -e .` — exposes console scripts.
- Run commands without install: `uv run dspx-multi-demo ...` or
  `python -m dspx.cli.multi_demo ...`.
- Update (editable install): `git pull` (code updates immediately).
- Update (uv tool install): `uv tool install --force .` in repo.
- Build packages: `just build` (uses `uv build`, outputs to `dist/`).
- Publish (PyPI): set `PYPI_TOKEN` then `just publish`.

Type Checking
-------------
- Enforced in CI via `just typecheck` (runs `uvx mypy`).
- Local run: `just typecheck`
- Pre-commit uses ruff hooks by default; run mypy manually or rely on CI.
- Excludes: `submodules/`, `generated/`, and `examples/`.


Release Cycle
-------------
- Suggest Semantic Versioning with lightweight cadence:
  - Patch on fixes/docs; minor on features; major for breaking changes.
  - Tag releases: `just tag v=vX.Y.Z` and create GitHub Release.
  - Publish when ready: `just publish` (requires `PYPI_TOKEN`).
- Helper flow: `just release new=X.Y.Z` runs fmt/lint/typecheck/test, bumps
  version, and builds artifacts; then tag and publish.

Customization
-------------
- Change model: set `CODEX_MODEL` env var or edit `model_flag` in `example_predict.py` (e.g., `gpt-5`).

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

You can adjust these by editing the `CodexExecLM(...)` arguments in `example_predict.py`.

Submodule: vibe-dspy
--------------------
- Initialize after cloning:

  git submodule update --init --recursive

- Pull latest upstream changes later:

  git submodule update --remote --merge submodules/vibe-dspy

- Importing its code in this project (no packaging metadata in upstream):
  - Use PYTHONPATH to point to its `src` directory when running code:

  # install project console scripts
  uv sync && uv pip install -e .
  uvx dspx-example

  - Or set PYTHONPATH in your shell/session for convenience.

Submodule: attachments
----------------------
- Path: `submodules/attachments`
- Usage: library for rich prompt attachments and docs; importable by setting PYTHONPATH:

  uv run env PYTHONPATH=submodules/attachments/src python -c "import attachments; print('attachments ok')"

Submodule: ovllm
-----------------
- Path: `submodules/ovllm`
- Usage: utilities for DSPy workflows; importable via PYTHONPATH:

  uv run env PYTHONPATH=submodules/ovllm python -c "import ovllm; print('ovllm ok')"

Code Generator CLI
------------------
- Generate code (prints to stdout by default):

  uv run dspx-codegen "Create a Python CLI that says hello"

- Language hint and write to file:

  uv run dspx-codegen -l python -o hello.py "CLI that prints 'Hello, world!'"

- Environment variables to control Codex behavior:

  - `CODEX_MODEL` (default: `gpt-5`)
  - `CODEX_REASONING` (default: `minimal`)
  - `CODEX_BYPASS` (default: `1`, enable `--dangerously-bypass-approvals-and-sandbox`)

  Example with explicit model:

  uv run env CODEX_MODEL=gpt-4.1 dspx-codegen -l python -o hello.py "CLI that prints 'Hello'"

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

  uv run dspx-mermaid -f path/to/diagram.mmd -v clarity -n my_flow

Vibe-DSPy (Codex Exec) Adapter
------------------------------
- Generate a DSPy signature using vibe-dspy with Codex Exec as the LM:

  uv run dspx-vibegen "Count birds in an image and describe each"

- Wrap the signature into a runnable script that configures Codex Exec and save it:

  uv run dspx-vibegen --wrap-script -o generated/birds_sig.py "Count birds in an image and describe each"

- Control model/flags via env (same as the rest of this repo):
  - `CODEX_MODEL` (default: `gpt-5`)
  - `CODEX_REASONING` (default: `minimal`)
  - `CODEX_BYPASS` (default: `1`)

Interactive Refine
------------------
- Run refine with Codex Exec (interactive):

  uv run dspx-viberefine --attempts 3 "Extract topics and sentiment from support tickets"

- Non-interactive (accept first draft) and save to file:

  uv run dspx-viberefine --non-interactive -o generated/tickets_sig.py "Extract topics and sentiment from support tickets"

- Wrap into runnable script that configures Codex Exec:

  uv run dspx-viberefine --non-interactive --wrap-script -o generated/tickets_script.py "Extract topics and sentiment from support tickets"

Tracing with MLflow
-------------------
- Install (already added to this project):

  uv add "mlflow>=2.18.0"

- Start server (recommended with a SQL backend):

  mlflow server --backend-store-uri sqlite:///mlflow.sqlite --host 127.0.0.1 --port 5000

- Enable tracing via env and run any script (example):

  uv run env MLFLOW_ENABLE=1 MLFLOW_TRACKING_URI=http://127.0.0.1:5000 MLFLOW_EXPERIMENT=DSPy \
    MLFLOW_RUN_NAME="local-test-$(date +%Y%m%d-%H%M%S)" \
    dspx-example

- Or inside your script, after configuring providers:

  from dspx.tracing import enable_mlflow_from_env, ensure_run_from_env
  enable_mlflow_from_env()
  ensure_run_from_env()  # uses $MLFLOW_RUN_NAME if provided

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
- Example (see `config.toml` in repo):

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
  - `just fmt` / `just lint` / `just typecheck` — ruff + mypy.
  - `just test` — run pytest if present.
  - `just build` / `just publish` — build and publish packages.
  - `just release new=X.Y.Z` — fmt/lint/typecheck/test, bump version, build.
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

  uv run dspx-viberefine --non-interactive "Classify sentiment"

What gets logged
- DSPy predictions and steps (inputs/outputs, LM config, tools) appear under the selected experiment's Traces tab in the MLflow UI.
- This repo enables autologging automatically when `MLFLOW_ENABLE` is truthy, using settings from `MLFLOW_TRACKING_URI` and `MLFLOW_EXPERIMENT`.

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
- `src/`: source code (modules/packages)
- `docs/`: project docs (vision, status, next steps)
- `examples/`: curated, versioned examples and workflows
- `generated/`: local outputs (ignored); kept for CLI defaults
- `submodules/`: external utilities (vibe-dspy, attachments, ovllm)
