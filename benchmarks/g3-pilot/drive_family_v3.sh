#!/usr/bin/env bash
# G3 v3 pilot family driver (DIAGNOSTIC SCREEN ONLY; AK 5081).
# Runs one family's pairs sequentially in frozen execution order; the two
# families run in parallel (interleaved). Honors the 6h wall budget deadline.
set -u
FAM="$1"
DEADLINE="$2"
cd /home/tryinget/ai-society/softwareco/owned/dspx
LOG="$TMPDIR/g3pilot-v3-5081/logs/${FAM}.log"
mkdir -p "$(dirname "$LOG")"
echo "[driver] family=$FAM deadline=$DEADLINE start=$(date -u +%H:%M:%SZ)" >> "$LOG"
for PAIR in $(python3 - "$FAM" <<'PY'
import json, sys
state = json.load(open("docs/v1-proof/g3pilot-v3-state.json"))
fam = sys.argv[1]
for pid in state["execution_order"]:
    if pid.endswith("-" + fam):
        print(pid)
PY
); do
  echo "[driver] $(date -u +%H:%M:%SZ) starting $PAIR" >> "$LOG"
  python3 benchmarks/g3-pilot/g3p3_runner.py run --pair "$PAIR" --deadline "$DEADLINE" >> "$LOG" 2>&1 || echo "[driver] $PAIR exited nonzero" >> "$LOG"
done
echo "[driver] $(date -u +%H:%M:%SZ) family=$FAM stream done" >> "$LOG"
