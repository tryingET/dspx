---
summary: "Single-track review of the G3 prospective empirical protocol (decision 132)."
read_when:
  - "Assessing whether decision 132 is ready for ADR."
---

# Review — G3 prospective empirical protocol

**Mode:** bootstrap_single_track. **Outcome:** `ready_for_adr`.

Reviewed bytes: `docs/v1-proof/g3-protocol-manifest.json` validated by
`engineering-core/scripts/v1/calibration_manifest.py` (`status: pass`,
manifest digest `ea05ba3c…`, template digest `1ccb65fc…`).

## Checks

- Schema, sections, and accepted-stage freeze match the producer contract.
- Model identities are live Pi enabled models (`xai/grok-4.6`,
  `openai-codex/gpt-5.6-terra`), two distinct base families, not variants.
- Power numbers come from a seeded prospective simulation under declared
  assumptions, not from campaign output. Achieved power 0.8396 at SEPP 0.15.
- Equal owner weights; within-owner weights sum to one; safety set covers
  every owner × family cell.
- Forecasts bound to the advice surface before execution; no authority-claim
  fields; no raw cross-owner snapshot transfer.
- Campaign is not executed by this decision.

## Outcome

`ready_for_adr`. Residual work (campaign execution) is a later exact task and
is not a blocker for accepting the protocol freeze.
