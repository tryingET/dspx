---
summary: "Compatibility landing page for the canonical project vision."
read_when:
  - "You followed an older reference to docs/VISION.md"
  - "You need the dated architecture references quickly"
---

# DSPx Vision

This path is retained as a compatibility entry point because older repo guidance and read-order docs still reference `docs/VISION.md`.

Canonical direction now lives in:
- [`docs/project/vision.md`](project/vision.md) — long-horizon product vision and current scope boundaries
- [`docs/project/strategic_goals.md`](project/strategic_goals.md) — top two strategic bets and which one is active
- [`docs/project/tactical_goals.md`](project/tactical_goals.md) — tactical waves for the active strategic goal
- [`docs/project/operational_goals.md`](project/operational_goals.md) — active operating slices with exact AK task IDs

Dated architecture references:
- [`docs/adr/20260322-provider-runtime-v4.md`](adr/20260322-provider-runtime-v4.md)
- [`docs/adr/20260322-synthesis-architecture-v7-v9.md`](adr/20260322-synthesis-architecture-v7-v9.md)

## Short version

DSPx is evolving toward a synthesis architecture where:
- **V7** ships explicit candidate generation/evaluation/selection/promotion,
- **V8** adds evidence-backed predictive ranking from receipts/Oracle history,
- **V9** governs how synthesis strategies and policies themselves evolve.

Implementation posture:
- architect the core so V9 remains possible,
- ship V7 behavior first,
- keep apps optional consumers of core,
- require receipts/evidence/policy boundaries before adding higher-order autonomy.
