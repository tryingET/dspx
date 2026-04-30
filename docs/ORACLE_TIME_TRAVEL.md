---
summary: "Guide to Oracle time-travel behavior and usage."
read_when:
  - "You are using Oracle time-travel features."
  - "You need historical behavior replay context."
type: "guide"
---

# Oracle Time Travel CLI (Phase C slice)

DSPx now ships a first receipt-backed Oracle Phase C workflow for inspecting
behavioral history from local `*.meta.json` files.

## Commands

```bash
# List known behavioral branches
just dspx oracle branch --path generated --json

# Inspect one branch timeline
just dspx oracle branch feature-x --path generated --json

# Compare two branches through shared lineage IDs and branch-local runs
just dspx oracle diff feature-x feature-y --path generated --json

# Find the first bad boundary in a branch
just dspx oracle bisect feature-x --path generated --json
```

## Receipt contract used by this slice

The CLI reads local receipt v2 metadata and uses these fields when present:

- `branch` — groups runs into behavioral branches
- `parent_run_id` — immediate parent link for branch navigation
- `causal_chain` — ordered lineage for diff/bisect context
- `outcome` — marks the bad side of a bisect boundary (`failure` and `partial`
  by default)

When lineage is partial or absent, the commands fall back to branch-timeline
ordering instead of failing.

## Output contracts

- `dspx oracle branch --json`
  - returns `{ "branches": [...] }` with per-branch counts, outcome totals, run
    kinds, time window, and lineage-link count
- `dspx oracle branch <name> --json`
  - returns `{ "branch": ..., "summary": ..., "runs": [...] }`
- `dspx oracle diff <left> <right> --json`
  - returns branch summaries plus `shared_lineage_ids`, branch-only run IDs, and
    run-kind overlap
- `dspx oracle bisect <branch> --json`
  - returns `status`, `method`, `last_good_run`, `first_bad_run`, and a
    `candidate_window`
