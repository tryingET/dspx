set shell := ["bash", "-uc"]

# Load .env if present
export := "$(test -f .env && set -a && . ./.env && set +a; env)"

default:
  @just --list

install:
  # Sync uv environment
  uv sync

mlflow-up:
  docker compose up -d

mlflow-down:
  docker compose down

example:
  uv run python -m example_predict

vibegen prompt:
  uv run python -m vibegen "{{prompt}}"

viberefine prompt out="generated/refined_sig.py":
  uv run python -m viberefine --non-interactive -o "{{out}}" "{{prompt}}"

codegen spec lang="python" out="generated/codegen_out.py":
  uv run python -m codegen -l "{{lang}}" -o "{{out}}" "{{spec}}"

smoke:
  just example
  just vibegen "Create a DSPy signature that extracts person names from text"
  just viberefine "Echo signature for smoke"
  just codegen "A Python CLI that prints 'smoke ok'" python generated/smoke_cli.py

agent question tools="retrieve_stub" iters=3:
  uv run python -m agent_demo --tools "{{tools}}" --iters {{iters}} "{{question}}"

mermaid file name="" variants="predict,cot,react":
  uv run python -m mermaid2dspy -f "{{file}}" -n "{{name}}" -v "{{variants}}"

mermaid-stdin name="" variants="predict,cot,react":
  echo "Paste Mermaid, then Ctrl-D:" && uv run python -m mermaid2dspy -n "{{name}}" -v "{{variants}}"
