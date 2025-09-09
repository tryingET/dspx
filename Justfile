set shell := ["bash", "-uc"]

# Load .env if present
export := "$(test -f .env && set -a && . ./.env && set +a; env)"

# List available tasks
default:
  @just --list

# Install project dependencies into the uv environment
install:
  # Sync uv environment (project deps)
  uv sync

# Install project in editable mode to expose console scripts (dev workflow)
dev-install:
  # Install project in editable mode to expose console scripts
  uv pip install -e .

# Format code with ruff
fmt:
  uvx ruff format src docs

# Lint with ruff
lint:
  uvx ruff check src docs

# Type-check with mypy
typecheck:
  uvx mypy --exclude '^(submodules/|generated/|examples/)' src

# Run tests (if present)
test:
  # Run only local tests (none by default); skip submodules' test suites
  if [ -d tests ]; then \
    uv run -m pytest -q tests || true; \
  else \
    echo "no local tests"; \
  fi

# Build distributables (wheel + sdist)
build:
  uv build

# Publish to PyPI (requires PYPI_TOKEN)
publish:
  if [ -z "${PYPI_TOKEN:-}" ]; then echo "PYPI_TOKEN not set"; exit 1; fi
  uv publish --token "$PYPI_TOKEN"

# Set project version in pyproject.toml
version new="":
  if [ -z "{{new}}" ]; then echo "usage: just version new=1.2.3"; exit 1; fi
  NEW="{{new}}" perl -0777 -pe 's/^(version\s*=\s*")[^"]+(\")/$1$ENV{NEW}$2/m' -i pyproject.toml
  echo "set version to {{new}}"

# Tag the current commit as a release version
tag v="":
  if [ -z "{{v}}" ]; then echo "usage: just tag v=v1.2.3"; exit 1; fi
  git tag "{{v}}"
  echo "created tag {{v}}"

# One-shot release helper: fmt, lint, test, build
release new="":
  if [ -z "{{new}}" ]; then echo "usage: just release new=1.2.3"; exit 1; fi
  just fmt
  just lint
  just typecheck
  just test
  just version new={{new}}
  just build
  echo "Now: just tag v=v{{new}} && just publish (requires PYPI_TOKEN)"

# Install console scripts as a uv tool and run via `uvx` (global-ish)
tool-install:
  # Install console scripts as a uv tool (global-ish via uvx)
  uv tool install .

# Start MLflow server via Docker Compose
mlflow-up:
  docker compose up -d

# Stop MLflow server
mlflow-down:
  docker compose down

# Run the DSPy + Codex Exec example (from source)
example:
  uv run -q python -m dspx.cli.example_predict

# Generate a DSPy signature using vibe-dspy (from source)
vibegen prompt:
  uv run -q python -m dspx.cli.vibegen "{{prompt}}"

# Refine a DSPy signature (non-interactive) and optionally write to file (from source)
viberefine prompt out="generated/refined_sig.py":
  uv run -q python -m dspx.cli.viberefine --non-interactive -o "{{out}}" "{{prompt}}"

# Generate code from a spec (prints or writes a file) from source
codegen spec lang="python" out="generated/codegen_out.py":
  uv run -q python -m dspx.cli.codegen -l "{{lang}}" -o "{{out}}" "{{spec}}"

# Quick smoke run: example + gen/refine/codegen
smoke:
  just example
  just vibegen "Create a DSPy signature that extracts person names from text"
  just viberefine "Echo signature for smoke"
  just codegen "A Python CLI that prints 'smoke ok'" python generated/smoke_cli.py

# Run minimal ReAct agent with optional tools (from source)
agent question tools="retrieve_stub" iters="3":
  uv run -q python -m dspx.cli.agent_demo --tools "{{tools}}" --iters {{iters}} "{{question}}"

# Web search via DuckDuckGo (from source)
web-search query k="5":
  uv run -q python -m dspx.cli.tools_demo search -k {{k}} "{{query}}"

# HTTP GET a URL and print metadata (from source)
web-fetch url:
  uv run -q python -m dspx.cli.tools_demo fetch "{{url}}"

# Fetch and extract text; optional CSS selector (from source)
web-scrape url selector="":
  uv run -q python -m dspx.cli.tools_demo scrape --selector "{{selector}}" "{{url}}"

# Preview CSV/JSON/Parquet schema + head (from source)
data-preview path nrows="5":
  uv run -q python -m dspx.cli.tools_demo preview --nrows {{nrows}} "{{path}}"

# Generate DSPy programs from a Mermaid flowchart (from source)
mermaid file name="" variants="predict,cot,react":
  uv run -q python -m dspx.cli.mermaid2dspy -f "{{file}}" -n "{{name}}" -v "{{variants}}"

# Paste Mermaid to stdin and generate programs (from source)
mermaid-stdin name="" variants="predict,cot,react":
  echo "Paste Mermaid, then Ctrl-D:" && uv run -q python -m dspx.cli.mermaid2dspy -n "{{name}}" -v "{{variants}}"


# Mermaid → DSPy with signature-per-node program (vibe-dspy, from source)
dspx-mermaid file name="" provider="":
  if [ "{{provider}}" != "" ]; then \
    DSPX_PROVIDER={{provider}} uv run -q python -m dspx.cli.dspx_mermaid2dspy -f "{{file}}" -n "{{name}}" ; \
  else \
    uv run -q python -m dspx.cli.dspx_mermaid2dspy -f "{{file}}" -n "{{name}}" ; \
  fi

# Benchmark CLI flows with MLflow enabled (one example per type)
# Usage: just bench-mlflow
bench-mlflow:
  bash -lc 'set -e; export DSPX_RUN_GROUP="cli-bench-$(date +%Y%m%d-%H%M%S)"; export MLFLOW_ENABLE="${MLFLOW_ENABLE:-1}"; echo "[bench] run_group=$DSPX_RUN_GROUP"; \
    SIG="Summarize a middle school science passage into 3 key points."; \
    if uv run -q python -m dspx.cli.dspx signature gen --provider codex-exec --template-version v1 --budget-ms 30000 "$SIG" >/dev/null 2>&1; then echo "provider=codex-exec kind=signature rc=0"; else echo "provider=codex-exec kind=signature rc=$?"; fi; \
    if uv run -q python -m dspx.cli.dspx signature gen --provider claude-cli --template-version v1 --budget-ms 30000 "$SIG" >/dev/null 2>&1; then echo "provider=claude-cli kind=signature rc=0"; else echo "provider=claude-cli kind=signature rc=$?"; fi; \
    SPEC="A Python CLI that prints 10 random fraction addition practice problems for grade 6"; \
    if uv run -q python -m dspx.cli.dspx codegen --provider codex-exec --template-version v1 --budget-ms 240000 "$SPEC" >/dev/null 2>&1; then echo "provider=codex-exec kind=codegen rc=0"; else echo "provider=codex-exec kind=codegen rc=$?"; fi; \
    if CLAUDE_MODEL=sonnet uv run -q python -m dspx.cli.dspx codegen --provider claude-cli --template-version v1 --budget-ms 240000 "$SPEC" >/dev/null 2>&1; then echo "provider=claude-cli kind=codegen rc=0"; else echo "provider=claude-cli kind=codegen rc=$?"; fi; \
    if uv run -q python -m dspx.cli.dspx module-gen --name LessonSummarizer --description "Summarize middle school readings into key points" --input text --output summary --budget-ms 30000 >/dev/null 2>&1; then echo "provider=none kind=module rc=0"; else echo "provider=none kind=module rc=$?"; fi; \
    WF=examples/workflows/sample_flow/workflow.mmd; \
    if uv run -q python -m dspx.cli.dspx mermaid gen --file "$WF" --name bench --variants predict,cot >/dev/null 2>&1; then echo "provider=none kind=mermaid-gen rc=0"; else echo "provider=none kind=mermaid-gen rc=$?"; fi; \
    export DSPX_POLICY_ENFORCE_NETWORK_MUTATE=0; export DSPX_BUDGET_SIGNATURE_MS=60000; \
    if CODEX_TIMEOUT=60 uv run -q python -m dspx.cli.dspx mermaid sig --file "$WF" --name benchsig --provider codex-exec >/dev/null 2>&1; then echo "provider=codex-exec kind=mermaid-sig rc=0"; else echo "provider=codex-exec kind=mermaid-sig rc=$?"; fi; \
    if CLAUDE_TIMEOUT=60 uv run -q python -m dspx.cli.dspx mermaid sig --file "$WF" --name benchsig --provider claude-cli >/dev/null 2>&1; then echo "provider=claude-cli kind=mermaid-sig rc=0"; else echo "provider=claude-cli kind=mermaid-sig rc=$?"; fi; \
    echo "[bench] done. Group: $DSPX_RUN_GROUP"'

# Start the FastAPI server (Granian)
# Usage (positional args):
#   just start                 # 3s on 127.0.0.1:33213 (default)
#   just start 10              # 10s on 127.0.0.1:33213
#   just start 5 0.0.0.0 33213 # 5s on 0.0.0.0:33213
start secs="3" host="127.0.0.1" port="33213":
  if [ "{{secs}}" != "" ]; then \
    echo "Starting DSPx server on http://{{host}}:{{port}} for {{secs}}s ..."; \
    timeout {{secs}}s env UV_LINK_MODE=copy uv run -q granian --interface asgi --host {{host}} --port {{port}} dspx.server.app:app || code=$?; \
    if [ "${code:-0}" -eq 124 ]; then echo "Timed out after {{secs}}s (expected)."; exit 0; elif [ "${code:-0}" -ne 0 ]; then echo "Server exited with code ${code:-0}."; exit "${code:-0}"; fi; \
  else \
    echo "Starting DSPx server on http://{{host}}:{{port}} ..."; \
    env UV_LINK_MODE=copy uv run -q granian --interface asgi --host {{host}} --port {{port}} dspx.server.app:app; \
  fi

# Start the FastAPI server but stop it after a short timeout
# Usage (positional params):
#   just start-timed                    # 3s on 127.0.0.1:33213
#   just start-timed 5                  # 5s on 127.0.0.1:33213
#   just start-timed 3 0.0.0.0 33213    # 3s on 0.0.0.0:33213
start-timed secs="3" host="127.0.0.1" port="33213":
  echo "Starting DSPx server on http://{{host}}:{{port}} for {{secs}}s ..."
  timeout {{secs}}s env UV_LINK_MODE=copy uv run -q granian --interface asgi --host {{host}} --port {{port}} dspx.server.app:app || code=$?
  if [ "${code:-0}" -eq 124 ]; then \
    echo "Timed out after {{secs}}s (expected)."; \
    exit 0; \
  elif [ "${code:-0}" -ne 0 ]; then \
    echo "Server exited with code ${code:-0}."; \
    exit "${code:-0}"; \
  fi

# Stop any process listening on the DSPx port (best-effort)
stop port="33213":
  PIDS=$(lsof -t -i TCP:{{port}} -sTCP:LISTEN 2>/dev/null || true)
  if [ -n "$PIDS" ]; then \
    echo "Stopping PIDs: $PIDS on :{{port}}"; \
    kill -TERM $PIDS || true; \
    sleep 1; \
    kill -0 $PIDS 2>/dev/null && kill -KILL $PIDS || true; \
  else \
    echo "No listeners on :{{port}}"; \
  fi

# Run server without timeout (explicit)
start-forever host="127.0.0.1" port="33213":
  echo "Starting DSPx server on http://{{host}}:{{port}} (no timeout) ..."
  env UV_LINK_MODE=copy uv run -q granian --interface asgi --host {{host}} --port {{port}} dspx.server.app:app
