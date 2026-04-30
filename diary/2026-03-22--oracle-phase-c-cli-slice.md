---
summary: "Diary entry: 2026-03-22 — Oracle Phase C CLI Slice."
read_when:
  - "You need the historical implementation context captured in this diary entry."
  - "You are reviewing or extending work related to 2026-03-22 — Oracle Phase C CLI Slice."
type: "diary"
---

# 2026-03-22 — Oracle Phase C CLI Slice

## What I Did
- Added the first receipt-backed Oracle Phase C CLI surface: `dspx oracle branch`, `diff`, and `bisect`.
- Introduced `dspx.oracle_time_travel` to scan local receipts, group behavioral branches, compare lineage overlap, and find the first bad boundary in a branch.
- Added focused CLI tests that seed synthetic receipt v2 timelines and verify branch listing, branch detail, diff, and bisect JSON contracts.
- Documented the new Phase C slice in `docs/ORACLE_TIME_TRAVEL.md`.
- Re-ran the full validation path and restored a green `just verify-full` baseline.

## What Surprised Me
- The repo already had the receipt v2 metadata needed for Time Travel; the main gap was query/UX glue rather than storage.
- `just verify-full` initially surfaced unrelated typing drift in the provider-runtime worktree, but the fixes were small and let the full gate go green again.

## Patterns
- Receipt-backed history tools work best when they degrade gracefully: use lineage when available, but fall back to branch timeline ordering instead of failing hard.
- A minimal JSON contract makes new CLI slices testable before richer presentation layers exist.

## Crystallization Candidates
- If more Oracle subcommands are added, factor shared receipt-scan/report formatting into a broader Oracle service surface.
