---
summary: "Diary entry: 2026-03-22 — Oracle Phase C Lineage Hardening."
read_when:
  - "You need the historical implementation context captured in this diary entry."
  - "You are reviewing or extending work related to 2026-03-22 — Oracle Phase C Lineage Hardening."
type: "diary"
---

# 2026-03-22 — Oracle Phase C Lineage Hardening

## What I Did
- Expanded `tests/test_oracle_time_travel_cli.py` to seed richer receipt v2 timelines, including:
  - multi-parent causal-chain overlap across branches,
  - runs with omitted `branch` metadata that must fall back to `main`,
  - bisect fallback when lineage metadata is partial and cannot identify a good ancestor.
- Added replay/explain invariance tests in `tests/test_run_receipts.py` to prove receipt verification stays green when lineage metadata is either absent or only partially populated.
- Re-ran targeted Oracle/receipt tests, `./scripts/ci/smoke.sh`, and the full `just verify-full` gate.
- Marked `DSPX-M2-02` done in `governance/work-items.json` and advanced the session handoff.

## What Surprised Me
- Replay/explain already ignored lineage fields cleanly; the missing piece was pinning that behavior in tests so future Phase C work cannot accidentally couple replay correctness to optional lineage metadata.
- The existing Oracle bisect implementation already had the right branch-timeline fallback semantics once the partial-lineage fixture existed.

## Patterns
- For receipt-evolution work, generate a valid receipt through the real CLI first, then patch only the experimental metadata you want to stress; this isolates lineage behavior from unrelated provenance mechanics.
- Phase C fixtures should always cover both "rich lineage" and "missing lineage" paths, because real receipts will continue to be heterogeneous for a while.

## Crystallization Candidates
- If more Time Travel behaviors are added, extract reusable receipt-fixture builders so branch/diff/bisect and replay/explain tests share the same lineage scenarios.
