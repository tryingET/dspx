Using DSPy with Codex Exec as the Active LM
===========================================

This example shows how to use the OpenAI Codex CLI's execution mode (`codex exec`) as the language model for a DSPy program, via a small wrapper `CodexExecLM`.

Prerequisites
-------------
- Codex CLI installed and authenticated (e.g., `codex --version`, `codex auth whoami`).
- Python 3.13+ (this project is initialized with 3.13)
- uv package manager (https://docs.astral.sh/uv/)

Files
-----
- `codex_exec_lm.py`: DSPy-compatible wrapper around `codex exec`.
- `example_predict.py`: A runnable DSPy script using `Predict("question -> answer")`.
- `codegen.py`: CLI to generate code from a spec using DSPy + Codex Exec.
- `submodules/vibe-dspy`: Git submodule pointing to https://github.com/Archelunch/vibe-dspy
- `submodules/attachments`: Git submodule pointing to https://github.com/MaximeRivest/attachments
- `submodules/ovllm`: Git submodule pointing to https://github.com/MaximeRivest/ovllm
- `vibegen.py`: Adapter CLI that uses vibe-dspy's `SignatureGenerator` but configures DSPy to use Codex Exec.
- `viberefine.py`: Interactive refine CLI using vibe-dspy + Codex Exec. Lets you review/improve the generated signature with quick feedback.

Architecture & Vision
---------------------
- This repo is evolving toward a layered design with clear seams for extension:
  - Core: config loader, MLflow tracing, LM provider base + registry
  - Providers: Codex Exec today; OpenAI Responses / OSS next
  - Services: codegen, signature generation (vibe), refine, agents/optimizers (future)
  - CLI: thin entrypoints delegating to services
- See docs/VISION.md for the full refactor plan, pros/cons, and roadmap.

Quick Start (uv)
----------------
1) Initialize (already done here, but safe to run):

   uv init

2) Add dependencies (already added):

   uv add dspy-ai

3) Verify Codex CLI works and you are logged in:

   codex --version
   codex auth whoami

4) Run the example via uv:

   uv run python example_predict.py

It configures DSPy to use Codex Exec with `gpt-5`, minimal reasoning effort, and bypassed approvals/sandbox. Codex may write and run code under the hood; the final answer prints to stdout.

Customization
-------------
- Change model: set `CODEX_MODEL` env var or edit `model_flag` in `example_predict.py` (e.g., `gpt-5`).

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

    uv run env PYTHONPATH=submodules/vibe-dspy/src python -m example_predict

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

  uv run python -m codegen "Create a Python CLI that says hello"

- Language hint and write to file:

  uv run python -m codegen -l python -o hello.py "CLI that prints 'Hello, world!'"

- Environment variables to control Codex behavior:

  - `CODEX_MODEL` (default: `gpt-5`)
  - `CODEX_REASONING` (default: `minimal`)
  - `CODEX_BYPASS` (default: `1`, enable `--dangerously-bypass-approvals-and-sandbox`)

  Example with explicit model:

  uv run env CODEX_MODEL=gpt-4.1 python -m codegen -l python -o hello.py "CLI that prints 'Hello'"

Mermaid → DSPy Programs
-----------------------
- Paste a Mermaid flowchart and generate multiple DSPy program variants (predict, CoT, ReAct) that execute the workflow end-to-end:

  just mermaid path/to/diagram.mmd name="my_flow" variants="predict,cot,react"

- Or via stdin:

  just mermaid-stdin name="my_flow"
  # paste the Mermaid, then Ctrl-D

- Output goes to `generated/workflows/<name or hash>/` as `program_<variant>.py` plus the original `workflow.mmd`.

- Extra variant: `clarity` (Constraints→Learn→Abduce→Robust-plan→Intervene→Trace→Yield). Example:

  uv run python -m mermaid2dspy -f path/to/diagram.mmd -v clarity -n my_flow

Vibe-DSPy (Codex Exec) Adapter
------------------------------
- Generate a DSPy signature using vibe-dspy with Codex Exec as the LM:

  uv run python -m vibegen "Count birds in an image and describe each"

- Wrap the signature into a runnable script that configures Codex Exec and save it:

  uv run python -m vibegen --wrap-script -o generated/birds_sig.py "Count birds in an image and describe each"

- Control model/flags via env (same as the rest of this repo):
  - `CODEX_MODEL` (default: `gpt-5`)
  - `CODEX_REASONING` (default: `minimal`)
  - `CODEX_BYPASS` (default: `1`)

Interactive Refine
------------------
- Run refine with Codex Exec (interactive):

  uv run python -m viberefine --attempts 3 "Extract topics and sentiment from support tickets"

- Non-interactive (accept first draft) and save to file:

  uv run python -m viberefine --non-interactive -o generated/tickets_sig.py "Extract topics and sentiment from support tickets"

- Wrap into runnable script that configures Codex Exec:

  uv run python -m viberefine --non-interactive --wrap-script -o generated/tickets_script.py "Extract topics and sentiment from support tickets"

Tracing with MLflow
-------------------
- Install (already added to this project):

  uv add "mlflow>=2.18.0"

- Start server (recommended with a SQL backend):

  mlflow server --backend-store-uri sqlite:///mlflow.sqlite --host 127.0.0.1 --port 5000

- Enable tracing via env and run any script (example):

  uv run env MLFLOW_ENABLE=1 MLFLOW_TRACKING_URI=http://127.0.0.1:5000 MLFLOW_EXPERIMENT=DSPy \
    python -m example_predict

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

Config file (no more long env lines)
------------------------------------
- Project reads `config.toml` at startup and sets env vars automatically.
- Example (see `config.toml` in repo):

  [mlflow]
  enable = true
  tracking_uri = "http://192.168.1.10:50000"
  experiment = "DSPy"

  [codex]
  model = "gpt-5"
  reasoning_effort = "minimal"
  bypass = true

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

  uv run python -m viberefine --non-interactive "Classify sentiment"

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
- `generated/`: generated examples (git-tracked for demo)
- `submodules/`: external utilities (vibe-dspy, attachments, ovllm)
