#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <slug> [date]" >&2
  echo "example: $0 mlflow-observability-rfc" >&2
  exit 2
fi

slug="$1"
date_part="${2:-$(date +%Y%m%d)}"
run_id="${date_part}-${slug}"

template_dir="docs/subagent-runs/_TEMPLATE"
run_dir="docs/subagent-runs/${run_id}"

if [[ ! -d "$template_dir" ]]; then
  echo "template not found: $template_dir" >&2
  exit 1
fi

if [[ -e "$run_dir" ]]; then
  echo "run already exists: $run_dir" >&2
  exit 1
fi

mkdir -p "$run_dir"
cp -R "$template_dir"/. "$run_dir"/

manifest="$run_dir/run.manifest.json"
if [[ -f "$manifest" ]]; then
  now_utc="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  task_title="${slug//-/ }"
  python3 - "$manifest" "$run_id" "$task_title" "$now_utc" <<'PY'
import json, sys
manifest_path, run_id, task_title, now_utc = sys.argv[1:]
with open(manifest_path, "r", encoding="utf-8") as f:
    data = json.load(f)

data["run_id"] = run_id
data["task_title"] = task_title
data["created_at"] = now_utc
data["updated_at"] = now_utc

with open(manifest_path, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
PY
fi

echo "$run_dir"
