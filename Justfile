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
