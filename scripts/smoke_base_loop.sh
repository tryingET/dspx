#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

OUT_DIR="${DSPX_SMOKE_BASE_DIR:-}"
if [ "$#" -gt 0 ] && [ -n "${1:-}" ]; then
  OUT_DIR="$1"
fi

if [ -z "$OUT_DIR" ]; then
  OUT_DIR="$(mktemp -d "${TMPDIR:-/tmp}/dspx-smoke-base.XXXXXX")"
else
  mkdir -p "$OUT_DIR"
  OUT_DIR="$(cd "$OUT_DIR" && pwd)"
fi

PROGRAM_DIR="$OUT_DIR/program"

export DSPX_CACHE_DIR="$OUT_DIR/cache"
export DSPX_CACHE_ENABLE=1
export DSPX_PROVIDER=stub
export MLFLOW_ENABLE=0

printf '[smoke-base] root=%s\n' "$ROOT"
printf '[smoke-base] out=%s\n' "$OUT_DIR"
printf '[smoke-base] provider=%s mlflow=%s cache=%s\n' "$DSPX_PROVIDER" "$MLFLOW_ENABLE" "$DSPX_CACHE_DIR"

printf '[smoke-base] signature gen\n'
uv run --package dspx-core -q python -m dspx.cli.dspx signature gen \
  "Classify support tickets" \
  --template-version simple-v1 \
  --class-name TicketSig \
  --outfile "$OUT_DIR/ticket_sig.py"

printf '[smoke-base] module-gen\n'
uv run --package dspx-core -q python -m dspx.cli.dspx module-gen \
  --name TicketClassifier \
  --description "Classify support ticket urgency" \
  --input ticket_text \
  --output urgency \
  --template-version simple-v1 \
  --use-signature \
  --outfile "$OUT_DIR/ticket_module.py"

cp examples/program_gen/ticket_intent.yaml "$OUT_DIR/intent.yaml"

printf '[smoke-base] program-gen\n'
uv run --package dspx-core -q python -m dspx.cli.dspx program-gen \
  --intent "$OUT_DIR/intent.yaml" \
  --outdir "$PROGRAM_DIR"

printf '[smoke-base] generated eval harnesses\n'
(
  cd "$PROGRAM_DIR"
  uv run --project "$ROOT" --package dspx-core -q python eval_smoke.py
  uv run --project "$ROOT" --package dspx-core -q python eval_jury.py
  uv run --project "$ROOT" --package dspx-core -q python eval_promotion.py
  uv run --project "$ROOT" --package dspx-core -q python eval_examples.py
)

printf '[smoke-base] authority adapter plan (planned_not_exported; no AK call)\n'
uv run --package dspx-core -q python -m dspx.cli.dspx adapters authority agent-kernel-plan \
  --manifest "$PROGRAM_DIR/manifest.json" \
  --external-ref AK-EXAMPLE \
  --out "$PROGRAM_DIR/ak-export-plan.json"

printf '\n[smoke-base] ok\n'
printf '[smoke-base] generated directory: %s\n' "$OUT_DIR"
printf '[smoke-base] signature: %s\n' "$OUT_DIR/ticket_sig.py"
printf '[smoke-base] module: %s\n' "$OUT_DIR/ticket_module.py"
printf '[smoke-base] program manifest: %s\n' "$PROGRAM_DIR/manifest.json"
printf '[smoke-base] program receipt: %s\n' "$PROGRAM_DIR/manifest.json.meta.json"
printf '[smoke-base] authority export plan: %s\n' "$PROGRAM_DIR/ak-export-plan.json"
printf '[smoke-base] adapter receipt: %s\n' "$PROGRAM_DIR/ak-export-plan.json.meta.json"
