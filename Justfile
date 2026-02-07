set shell := ["bash", "-uc"]
set dotenv-load := true
set export

# List available tasks
default:
  @just --list

# Install workspace dependencies into the uv environment
install:
  # Sync uv environment (workspace deps)
  uv sync

# Install workspace packages in editable mode to expose console scripts (dev workflow)
dev-install:
  # Install core + forge app in editable mode
  uv pip install -e packages/dspx-core -e apps/forge

# Format code with ruff
fmt:
  uvx ruff format packages/dspx-core/src apps/forge/src docs

# Lint with ruff (all package code + docs)
lint:
  uvx ruff check packages/dspx-core/src apps/forge/src docs

# Lint core package only
lint-core:
  uvx ruff check packages/dspx-core/src

# Lint forge app package only
lint-forge:
  uvx ruff check apps/forge/src

# Type-check with ty (all package code)
typecheck:
  uvx ty check packages/dspx-core/src apps/forge/src

# Type-check core package only
typecheck-core:
  uvx ty check packages/dspx-core/src

# Type-check forge app package only
typecheck-forge:
  uvx ty check apps/forge/src

# Run tests (if present)
test:
  # Run only local tests (none by default); skip submodules' test suites
  if [ -d tests ]; then \
    uv run -m pytest -q tests; \
  else \
    echo "no local tests"; \
  fi

# Run core-focused test slice (exclude forge-marked tests)
test-core:
  if [ -d tests ]; then \
    uv run -m pytest -q tests -m "not forge"; \
  else \
    echo "no local tests"; \
  fi

# Run forge-focused test slice (explicit pytest marker)
test-forge:
  if [ -d tests ]; then \
    uv run -m pytest -q tests -m "forge"; \
  else \
    echo "no local tests"; \
  fi

# Forge/core wheel-compat smoke (latest core)
forge-core-compat mode="latest":
  bash scripts/forge_core_compat_smoke.sh "{{mode}}"

# Forge/core wheel-compat matrix (min + latest core)
forge-core-compat-matrix:
  just forge-core-compat latest
  just forge-core-compat min

# Clean-clone smoke flow for workspace packaging convergence
clean-clone-smoke:
  bash scripts/clean_clone_smoke.sh

# Monorepo boundary guardrail check
monorepo-check:
  uv run -q python scripts/check_monorepo_boundaries.py

# Run unified CLI from source (pass-through)
# Examples:
#   just dspx signature gen "Extract names" --template-version simple-v1
#   just dspx tools list
dspx *args:
  # Use bash to preserve argument boundaries reliably.
  bash -lc 'uv run --package dspx-core -q python -m dspx.cli.dspx "$@"' -- {{args}}

# Forge app CLI from monorepo app boundary
forge *args:
  bash -lc 'uv run --package dspx-forge -q python -m dspx_forge.cli "$@"' -- {{args}}

# OpenRouter wrapper (1Password `op run`)
# NOTE: We avoid variadic pass-through here because Just interpolation happens in a shell,
# and it will split multi-word args unless each arg is shell-escaped.
_op-preflight:
  if ! command -v op >/dev/null 2>&1; then echo "op CLI not found (install 1Password CLI)"; exit 2; fi

_openrouter-preflight:
  just _op-preflight
  if [ ! -f .env ]; then echo ".env not found (create one; see .env.example)"; exit 2; fi
  if ! rg -q '^OPENROUTER_API_KEY=' .env 2>/dev/null; then echo "OPENROUTER_API_KEY not set in .env (see .env.example)"; exit 2; fi

# Debug helpers (run in recipe environment)
openrouter-whoami:
  just _op-preflight
  op whoami

openrouter-env:
  just _openrouter-preflight
  # Do not print secrets; only show whether the key resolves and its length.
  op run -- bash -lc 'python - <<PY\nimport os\nk=os.getenv(\"OPENROUTER_API_KEY\") or \"\"\nprint(f\"OPENROUTER_API_KEY_set={1 if k else 0} len={len(k)}\")\nprint(f\"OPENROUTER_MODEL={os.getenv(\\\"OPENROUTER_MODEL\\\") or \\\"\\\"}\")\nPY'

openrouter-codegen spec lang="python" template="v1":
  just _openrouter-preflight
  # Rely on Just's dotenv-load for `.env`; `op run` resolves any `op://...` env values.
  op run -- env DSPX_PROVIDER=openrouter uv run -q python -m dspx.cli.dspx codegen "{{spec}}" --template-version {{template}} --language {{lang}}

openrouter-codegen-timed spec lang="python" template="v1":
  just _openrouter-preflight
  # Total wall-clock time from command start to finish (printed to stderr).
  TIMEFORMAT=$'[openrouter] duration_s=%R\n'; \
  time op run -- env DSPX_PROVIDER=openrouter uv run -q python -m dspx.cli.dspx codegen "{{spec}}" --template-version {{template}} --language {{lang}}

openrouter-signature prompt template="v1":
  just _openrouter-preflight
  op run -- env DSPX_PROVIDER=openrouter uv run -q python -m dspx.cli.dspx signature gen "{{prompt}}" --template-version {{template}}

openrouter-signature-timed prompt template="v1":
  just _openrouter-preflight
  TIMEFORMAT=$'[openrouter] duration_s=%R\n'; \
  time op run -- env DSPX_PROVIDER=openrouter uv run -q python -m dspx.cli.dspx signature gen "{{prompt}}" --template-version {{template}}

# Friendly OpenRouter shortcuts (no flags, no quoting).
# These accept unquoted multi-word prompts by capturing the remainder.
or-signature prompt *more:
  P="{{prompt}} {{more}}"; P="${P% }"; \
  just openrouter-signature "$P" v1

or-codegen spec *more:
  S="{{spec}} {{more}}"; S="${S% }"; \
  just openrouter-codegen "$S" python v1

or-signature-timed prompt *more:
  P="{{prompt}} {{more}}"; P="${P% }"; \
  just openrouter-signature-timed "$P" v1

or-codegen-timed spec *more:
  S="{{spec}} {{more}}"; S="${S% }"; \
  just openrouter-codegen-timed "$S" python v1

# GEPA optimization (DSPy) — default provider is DSPX_PROVIDER (defaults to codex-exec)
gepa program train out val="" output_key="" auto="light" max_metric_calls="" metric="exact":
  if [ "{{val}}" != "" ]; then \
    VAL_ARGS="--val {{val}}"; \
  else \
    VAL_ARGS=""; \
  fi; \
  if [ "{{output_key}}" != "" ]; then \
    OUT_ARGS="--output-key {{output_key}}"; \
  else \
    OUT_ARGS=""; \
  fi; \
  if [ "{{max_metric_calls}}" != "" ]; then \
    BUDGET_ARGS="--max-metric-calls {{max_metric_calls}}"; \
    AUTO_ARGS=""; \
  else \
    BUDGET_ARGS=""; \
    AUTO_ARGS="--auto {{auto}}"; \
  fi; \
  uv run -q python -m dspx.cli.dspx optimize gepa --program "{{program}}" --train "{{train}}" --out "{{out}}" --metric {{metric}} $VAL_ARGS $OUT_ARGS $AUTO_ARGS $BUDGET_ARGS

# Deterministic GEPA demo using the stub provider (offline).
gepa-demo:
  MLFLOW_ENABLE=0 DSPX_PROVIDER=stub just gepa examples/gepa_demo_program.py examples/gepa_demo_train.csv generated/gepa_demo_optimized "" "" light 2

# GEPA smoke starting from `module-gen` output (offline; stub provider).
gepa-modulegen-smoke:
  TD="$(mktemp -d)"; \
  echo "[gepa-modulegen-smoke] dir=$TD"; \
  MLFLOW_ENABLE=0 uv run -q python -m dspx.cli.dspx module-gen \
    --name Student \
    --description "Answer a short question with a short answer" \
    --input question \
    --output answer \
    --template-version simple-v1 \
    --outfile "$TD/student.py" >/dev/null; \
  MLFLOW_ENABLE=0 DSPX_PROVIDER=stub \
    just gepa "$TD/student.py" examples/gepa_modulegen_train.csv "$TD/optimized" "" "" light 2 contains >/dev/null; \
  test -f "$TD/optimized/manifest.json"; \
  echo "[gepa-modulegen-smoke] ok out=$TD/optimized"

# GEPA smoke starting from `module-gen` output (live; Codex Exec; opt-in).
gepa-modulegen-live:
  if [ "${DSPX_RUN_LIVE_TESTS:-0}" != "1" ] && [ "${DSPX_RUN_LIVE_TESTS:-0}" != "true" ] && [ "${DSPX_RUN_LIVE_TESTS:-0}" != "yes" ]; then \
    echo "set DSPX_RUN_LIVE_TESTS=1 to run live Codex GEPA smoke"; exit 0; \
  fi; \
  if ! command -v codex >/dev/null 2>&1; then echo "codex CLI not found"; exit 2; fi; \
  if ! (codex login status >/dev/null 2>&1 || codex auth whoami >/dev/null 2>&1); then echo "codex not authenticated (codex login status)"; exit 2; fi; \
  TD="$(mktemp -d)"; \
  echo "[gepa-modulegen-live] dir=$TD"; \
  MLFLOW_ENABLE=0 uv run -q python -m dspx.cli.dspx module-gen \
    --name Student \
    --description "Answer a short question with a short answer" \
    --input question \
    --output answer \
    --template-version simple-v1 \
    --outfile "$TD/student.py" >/dev/null; \
  DSPX_PROVIDER=codex-exec \
    just gepa "$TD/student.py" examples/gepa_modulegen_train.csv "$TD/optimized" "" "" light 2 contains >/dev/null; \
  test -f "$TD/optimized/manifest.json"; \
  echo "[gepa-modulegen-live] ok out=$TD/optimized"

# Pi RPC live smoke (opt-in) with recommended provider/model defaults.
pi-live-smoke provider="openai-codex" model="gpt-5.1-codex-mini" thinking="" timeout="90":
  if [ "${DSPX_RUN_LIVE_TESTS:-0}" != "1" ] && [ "${DSPX_RUN_LIVE_TESTS:-0}" != "true" ] && [ "${DSPX_RUN_LIVE_TESTS:-0}" != "yes" ]; then \
    echo "set DSPX_RUN_LIVE_TESTS=1 to run live Pi RPC smoke"; exit 0; \
  fi; \
  if ! command -v pi >/dev/null 2>&1; then echo "pi CLI not found"; exit 2; fi; \
  DSPX_PI_LIVE_PROVIDER="{{provider}}" \
  DSPX_PI_LIVE_MODEL="{{model}}" \
  DSPX_PI_LIVE_THINKING="{{thinking}}" \
  DSPX_PI_LIVE_TIMEOUT="{{timeout}}" \
    uv run -m pytest -q tests/test_pi_rpc_provider_live.py -rs

# GEPA optimization pinned to Codex Exec
codex-gepa program train out val="" output_key="" auto="light" max_metric_calls="20":
  DSPX_PROVIDER=codex-exec just gepa "{{program}}" "{{train}}" "{{out}}" "{{val}}" "{{output_key}}" {{auto}} {{max_metric_calls}}

codex-gepa-timed program train out val="" output_key="" auto="light" max_metric_calls="20":
  TIMEFORMAT=$'[codex-gepa] duration_s=%R\n'; \
  time just codex-gepa "{{program}}" "{{train}}" "{{out}}" "{{val}}" "{{output_key}}" {{auto}} {{max_metric_calls}}

# Build distributables (wheel + sdist) for all workspace packages
build:
  uv build --all-packages

# Build distributables for core package only
build-core:
  uv build --package dspx-core

# Build distributables for forge package only
build-forge:
  uv build --package dspx-forge

# Publish all artifacts in dist/ to PyPI (requires PYPI_TOKEN)
publish:
  if [ -z "${PYPI_TOKEN:-}" ]; then echo "PYPI_TOKEN not set"; exit 1; fi
  uv publish --token "$PYPI_TOKEN"

# Publish core artifacts only (requires PYPI_TOKEN)
publish-core:
  if [ -z "${PYPI_TOKEN:-}" ]; then echo "PYPI_TOKEN not set"; exit 1; fi
  if ! ls dist/dspx_core-* >/dev/null 2>&1; then echo "no core artifacts in dist/ (run just build-core)"; exit 1; fi
  uv publish --token "$PYPI_TOKEN" dist/dspx_core-*

# Publish forge artifacts only (requires PYPI_TOKEN)
publish-forge:
  if [ -z "${PYPI_TOKEN:-}" ]; then echo "PYPI_TOKEN not set"; exit 1; fi
  if ! ls dist/dspx_forge-* >/dev/null 2>&1; then echo "no forge artifacts in dist/ (run just build-forge)"; exit 1; fi
  uv publish --token "$PYPI_TOKEN" dist/dspx_forge-*

# Set core package version in package pyproject.toml
version-core new="":
  if [ -z "{{new}}" ]; then echo "usage: just version-core new=1.2.3"; exit 1; fi
  NEW="{{new}}" perl -0777 -pe 's/^(version\s*=\s*")[^"]+(\")/$1$ENV{NEW}$2/m' -i packages/dspx-core/pyproject.toml
  echo "set dspx-core version to {{new}}"

# Set forge package version in package pyproject.toml
version-forge new="":
  if [ -z "{{new}}" ]; then echo "usage: just version-forge new=1.2.3"; exit 1; fi
  NEW="{{new}}" perl -0777 -pe 's/^(version\s*=\s*")[^"]+(\")/$1$ENV{NEW}$2/m' -i apps/forge/pyproject.toml
  echo "set dspx-forge version to {{new}}"

# Set both package versions (legacy coupled helper)
version new="":
  if [ -z "{{new}}" ]; then echo "usage: just version new=1.2.3"; exit 1; fi
  just version-core new={{new}}
  just version-forge new={{new}}
  echo "set dspx-core + dspx-forge versions to {{new}}"

# Tag the current commit for a core release
tag-core v="":
  if [ -z "{{v}}" ]; then echo "usage: just tag-core v=1.2.3"; exit 1; fi
  git tag "dspx-core-v{{v}}"
  echo "created tag dspx-core-v{{v}}"

# Tag the current commit for a forge release
tag-forge v="":
  if [ -z "{{v}}" ]; then echo "usage: just tag-forge v=1.2.3"; exit 1; fi
  git tag "dspx-forge-v{{v}}"
  echo "created tag dspx-forge-v{{v}}"

# Tag the current commit as a generic release version (legacy helper)
tag v="":
  if [ -z "{{v}}" ]; then echo "usage: just tag v=v1.2.3"; exit 1; fi
  git tag "{{v}}"
  echo "created tag {{v}}"

# One-shot helper for core package release prep
release-core new="":
  if [ -z "{{new}}" ]; then echo "usage: just release-core new=1.2.3"; exit 1; fi
  just monorepo-check
  just lint-core
  just typecheck-core
  just test-core
  just version-core new={{new}}
  just build-core
  echo "Now: just tag-core v={{new}} && just publish-core (requires PYPI_TOKEN)"

# One-shot helper for forge package release prep
release-forge new="":
  if [ -z "{{new}}" ]; then echo "usage: just release-forge new=1.2.3"; exit 1; fi
  just monorepo-check
  just lint-forge
  just typecheck-forge
  just test-forge
  just version-forge new={{new}}
  just build-forge
  echo "Now: just tag-forge v={{new}} && just publish-forge (requires PYPI_TOKEN)"

# One-shot release helper for coupled versioning (legacy)
release new="":
  if [ -z "{{new}}" ]; then echo "usage: just release new=1.2.3"; exit 1; fi
  just fmt
  just lint
  just typecheck
  just test
  just version new={{new}}
  just build
  echo "Now: just tag v=v{{new}} && just publish (requires PYPI_TOKEN)"

# Install workspace console scripts as uv tools (global-ish via uvx)
tool-install:
  uv tool install packages/dspx-core
  uv tool install apps/forge

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

# MLflow smoke: signature refine should create a `signature-refine` run with standard tags and code artifacts.
mlflow-smoke-signature-refine:
  TD="$(mktemp -d)"; \
  echo "[mlflow-smoke-signature-refine] dir=$TD"; \
  export MLFLOW_ENABLE=1; \
  export MLFLOW_TRACKING_URI="file:$TD/mlruns"; \
  export MLFLOW_EXPERIMENT="DSPxSmoke"; \
  export DSPX_PROVIDER=stub; \
  uv run -q python -m dspx.cli.dspx signature refine \
    --attempts 1 \
    --outfile "$TD/refined_sig.py" \
    "Reply with the single word: hello" >/dev/null; \
  DSPX_EXPECT_OUTFILE="refined_sig.py" uv run -q python scripts/smoke_mlflow_signature_refine.py

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
