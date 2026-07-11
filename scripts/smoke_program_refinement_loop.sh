#!/usr/bin/env bash
# ---
# summary: "Smoke-test local program refinement from Oracle evidence through candidate comparison."
# read_when:
#   - "Changing refinement proposals, promotion decisions, second-candidate generation, or comparison."
# ---
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

OUT_DIR="${DSPX_SMOKE_PROGRAM_REFINEMENT_DIR:-}"
if [ "$#" -gt 0 ] && [ -n "${1:-}" ]; then
  OUT_DIR="$1"
fi

if [ -z "$OUT_DIR" ]; then
  OUT_DIR="$(mktemp -d "${TMPDIR:-/tmp}/dspx-smoke-program-refinement.XXXXXX")"
else
  mkdir -p "$OUT_DIR"
  OUT_DIR="$(cd "$OUT_DIR" && pwd)"
fi

export OUT_DIR

PROGRAM_DIR="$OUT_DIR/program"
PROGRAM_V2_DIR="$OUT_DIR/program-v2"
ORACLE_DIR="$OUT_DIR/oracle"
REFINEMENT_DIR="$OUT_DIR/refinement"
PROMOTION_DIR="$OUT_DIR/promotion"

mkdir -p "$ORACLE_DIR" "$REFINEMENT_DIR" "$PROMOTION_DIR"
cp examples/program_gen/ticket_intent.yaml "$OUT_DIR/intent.yaml"

export DSPX_CACHE_DIR="$OUT_DIR/cache"
export DSPX_CACHE_ENABLE=1
export DSPX_PROVIDER=stub
export MLFLOW_ENABLE=0
export DSPX_ORACLE_EMBEDDING_BACKEND=mock

printf '[smoke-program-refinement] root=%s\n' "$ROOT"
printf '[smoke-program-refinement] out=%s\n' "$OUT_DIR"
printf '[smoke-program-refinement] provider=%s mlflow=%s cache=%s oracle_backend=%s\n' \
  "$DSPX_PROVIDER" "$MLFLOW_ENABLE" "$DSPX_CACHE_DIR" "$DSPX_ORACLE_EMBEDDING_BACKEND"

printf '[smoke-program-refinement] program-gen\n'
uv run --package dspx-core -q python -m dspx.cli.dspx program-gen \
  --intent "$OUT_DIR/intent.yaml" \
  --outdir "$PROGRAM_DIR" >/dev/null

find "$PROGRAM_DIR" -maxdepth 1 -type f -print0 | sort -z | xargs -0 sha256sum \
  > "$OUT_DIR/program.before.sha256"

printf '[smoke-program-refinement] oracle index/report in temp CoordinateIndex\n'
uv run --package dspx-core -q python -m dspx.cli.dspx oracle index \
  --from-program-evidence \
  --path "$PROGRAM_DIR" \
  --index-path "$ORACLE_DIR/coordinates.db" \
  --json > "$ORACLE_DIR/index-result.json"

uv run --package dspx-core -q python -m dspx.cli.dspx oracle program-evidence report \
  --index-path "$ORACLE_DIR/coordinates.db" \
  --json > "$ORACLE_DIR/program-evidence-report.json"

printf '[smoke-program-refinement] propose/review/decide request_more_evidence\n'
uv run --package dspx-core -q python -m dspx.cli.dspx program-refine propose \
  --manifest "$PROGRAM_DIR/manifest.json" \
  --oracle-report "$ORACLE_DIR/program-evidence-report.json" \
  --out "$REFINEMENT_DIR/refinement_proposal.json" \
  --json > "$REFINEMENT_DIR/propose.stdout.json"

uv run --package dspx-core -q python -m dspx.cli.dspx program-promote review \
  --manifest "$PROGRAM_DIR/manifest.json" \
  --oracle-report "$ORACLE_DIR/program-evidence-report.json" \
  --refinement-proposal "$REFINEMENT_DIR/refinement_proposal.json" \
  --out "$PROMOTION_DIR/promotion_review_refined.json" \
  --json > "$PROMOTION_DIR/review.stdout.json"

uv run --package dspx-core -q python -m dspx.cli.dspx program-promote decide \
  --review "$PROMOTION_DIR/promotion_review_refined.json" \
  --outcome request_more_evidence \
  --decided-by local_operator \
  --rationale "Generate one bounded second candidate for observed mismatch." \
  --out "$PROMOTION_DIR/promotion_decision_record.json" \
  --json > "$PROMOTION_DIR/decide.stdout.json"

printf '[smoke-program-refinement] generate-and-compare\n'
uv run --package dspx-core -q python -m dspx.cli.dspx program-refine generate-and-compare \
  --manifest "$PROGRAM_DIR/manifest.json" \
  --refinement-proposal "$REFINEMENT_DIR/refinement_proposal.json" \
  --decision-record "$PROMOTION_DIR/promotion_decision_record.json" \
  --outdir "$PROGRAM_V2_DIR" \
  --comparison-out "$REFINEMENT_DIR/candidate_comparison.json" \
  --workflow-out "$REFINEMENT_DIR/generate_and_compare_result.json" \
  --json > "$REFINEMENT_DIR/generate-and-compare.stdout.json"

python - <<'PY'
import json
import os
from pathlib import Path

root = Path(os.environ.get("OUT_DIR", ""))
if not root:
    raise SystemExit("OUT_DIR missing")
workflow = json.loads((root / "refinement" / "generate_and_compare_result.json").read_text())
comparison = json.loads((root / "refinement" / "candidate_comparison.json").read_text())
index_result = json.loads((root / "oracle" / "index-result.json").read_text())
assert index_result["indexed"] == 1
assert index_result["errors"] == 0
assert workflow["schema_version"] == "program-refinement-generate-and-compare-result-v1"
assert workflow["status"] == "materialized_and_compared"
assert workflow["effect"]["local_second_candidate_generated"] is True
assert workflow["effect"]["local_comparison_written"] is True
assert workflow["effect"]["third_candidate_generated"] is False
assert workflow["non_authority"]["program_gen_automation"] is False
assert workflow["non_authority"]["winner_selection"] is False
assert comparison["schema_version"] == "program-refinement-candidate-comparison-v1"
assert comparison["status"] == "compared"
assert comparison["effect"]["local_comparison_only"] is True
assert comparison["effect"]["new_candidate_generated"] is False
assert comparison["non_authority"]["oracle_promotion"] is False
assert "behavior_comparison" in comparison
PY

find "$PROGRAM_DIR" -maxdepth 1 -type f -print0 | sort -z | xargs -0 sha256sum \
  > "$OUT_DIR/program.after.sha256"
diff -u "$OUT_DIR/program.before.sha256" "$OUT_DIR/program.after.sha256"

test -f "$PROGRAM_V2_DIR/manifest.json"
test -f "$REFINEMENT_DIR/candidate_comparison.json"
test ! -f "$PROGRAM_DIR/eval_behavior.py"
test ! -f "$PROGRAM_V2_DIR/eval_behavior.py"

printf '\n[smoke-program-refinement] ok\n'
printf '[smoke-program-refinement] generated directory: %s\n' "$OUT_DIR"
printf '[smoke-program-refinement] source manifest: %s\n' "$PROGRAM_DIR/manifest.json"
printf '[smoke-program-refinement] second candidate manifest: %s\n' "$PROGRAM_V2_DIR/manifest.json"
printf '[smoke-program-refinement] comparison: %s\n' "$REFINEMENT_DIR/candidate_comparison.json"
printf '[smoke-program-refinement] workflow result: %s\n' "$REFINEMENT_DIR/generate_and_compare_result.json"
