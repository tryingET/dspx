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
  uv run mypy --exclude '^(submodules/|generated/)' src

# Run tests (if present)
test:
  uv run -m pytest -q || true

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

# Run the DSPy + Codex Exec example
example:
  uvx dspx-example

# Generate a DSPy signature using vibe-dspy (Codex Exec configured)
vibegen prompt:
  uvx dspx-vibegen "{{prompt}}"

# Refine a DSPy signature (non-interactive) and optionally write to file
viberefine prompt out="generated/refined_sig.py":
  uvx dspx-viberefine --non-interactive -o "{{out}}" "{{prompt}}"

# Generate code from a spec (prints or writes a file)
codegen spec lang="python" out="generated/codegen_out.py":
  uvx dspx-codegen -l "{{lang}}" -o "{{out}}" "{{spec}}"

# Quick smoke run: example + gen/refine/codegen
smoke:
  just example
  just vibegen "Create a DSPy signature that extracts person names from text"
  just viberefine "Echo signature for smoke"
  just codegen "A Python CLI that prints 'smoke ok'" python generated/smoke_cli.py

# Run minimal ReAct agent with optional tools
agent question tools="retrieve_stub" iters="3":
  uvx dspx-agent --tools "{{tools}}" --iters {{iters}} "{{question}}"

# Web search via DuckDuckGo
web-search query k="5":
  uvx dspx-tools search -k {{k}} "{{query}}"

# HTTP GET a URL and print metadata
web-fetch url:
  uvx dspx-tools fetch "{{url}}"

# Fetch and extract text; optional CSS selector
web-scrape url selector="":
  uvx dspx-tools scrape --selector "{{selector}}" "{{url}}"

# Preview CSV/JSON/Parquet schema + head
data-preview path nrows="5":
  uvx dspx-tools preview --nrows {{nrows}} "{{path}}"

# Generate DSPy programs from a Mermaid flowchart
mermaid file name="" variants="predict,cot,react":
  uvx dspx-mermaid -f "{{file}}" -n "{{name}}" -v "{{variants}}"

# Paste Mermaid to stdin and generate programs
mermaid-stdin name="" variants="predict,cot,react":
  echo "Paste Mermaid, then Ctrl-D:" && uvx dspx-mermaid -n "{{name}}" -v "{{variants}}"


# Mermaid → DSPy with signature-per-node program (vibe-dspy)
dspx-mermaid file name="" provider="":
  if [ "{{provider}}" != "" ]; then \
    DSPX_PROVIDER={{provider}} uvx dspx-mermaid-sig -f "{{file}}" -n "{{name}}" ; \
  else \
    uvx dspx-mermaid-sig -f "{{file}}" -n "{{name}}" ; \
  fi
