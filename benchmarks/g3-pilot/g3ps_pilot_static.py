#!/usr/bin/env python3
"""Static-arm difficulty pilots (AK 5095 pre-freeze saturation guard).

One STATIC-only execution per template (instance a, fam-glm) to estimate
difficulty before freeze. Arm-direction-blind by construction (static arm
only, no guidance, no advisor). Templates whose pilot pass-rate exceeds 0.8
must be difficulty-re-targeted BEFORE freeze (design rule 2).
Writes docs/v1-proof/g3ps-static-pilots.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import g3ps_runner as runner  # noqa: E402
import g3ps_support as support  # noqa: E402

OUT = HERE.parents[1] / "docs/v1-proof/g3ps-static-pilots.json"


def main() -> None:
    results = {}
    for template in ("TA1", "TA2", "TA3", "TB1", "TB2", "TB3",
                     "TC1", "TC2", "TC3", "TC4", "TH1", "TH2"):
        task = support.task_for(f"{template}-a")
        pair_id = f"PILOT-{template}-a"
        print(f"[pilot] {template}: static arm", file=sys.stderr)
        outcome = runner.execute_arm(task, pair_id, "static",
                                     runner.load_state()["families"]["fam-glm"]
                                     if (runner.STATE_PATH.exists()) else "zai/glm-5.3:high",
                                     None, None)
        results[template] = {
            "y": outcome["y"],
            "duration_s": outcome["duration_s"],
            "problems": outcome["checks"]["acceptance"]["problems"][:4],
        }
        OUT.write_text(json.dumps({"schema": "dspx.g3ps-static-pilots/1",
                                   "arm": "static-only (no guidance, no advisor)",
                                   "model": "zai/glm-5.3:high",
                                   "results": results}, indent=1, sort_keys=True) + "\n")
    n_pass = sum(1 for v in results.values() if v["y"] == 1)
    print(json.dumps({"pass": n_pass, "total": len(results)}))


if __name__ == "__main__":
    main()
