---
summary: "Accepted G3 prospective empirical protocol for engineering-core v1 Gate G3: paired evidence-vs-static design, frozen grok-4.6 and gpt-5.6-terra families, declared-assumption power analysis, equal owner weights, harm stops, and a fail-closed safety set."
read_when:
  - "Executing, reviewing, or changing the engineering-core v1 G3 campaign."
  - "Selecting models, sample size, calibration thresholds, or harm stops for that campaign."
---

# ADR — Accept the G3 prospective evidence-calibration protocol

## Status

Accepted under AK decision `132` (architecture, repo-scoped to `softwareco/owned/dspx`).

## Decision

Accept `docs/v1-proof/g3-protocol-manifest.json` as the frozen prospective protocol
for engineering-core v1 Gate G3, validated fail-closed by the producer harness
`engineering-core/scripts/v1/calibration_manifest.py` (cross-repo dogfood).

- Schema: `engineering-core.v1.g3/1`, `protocol_stage: accepted`
- Template digest: `1ccb65fc071f645b6840398189ad01f218540ec2b2a50a6e7727f5055d82b952`
- Manifest digest: `ea05ba3cd118e7ebb2cb37a2df8736dd0c0ebfd9784eb8edb5c86a3542ff5fa0`

Binding properties:

- **Treatment contrast:** evidence-advice arm vs static-baseline arm on the same
  task, model, tools, and budget except the declared evidence-advice slot.
- **Model families (from the live Pi enabled-model list, not Radius-only):**
  `xai/grok-4.6` and `openai-codex/gpt-5.6-terra`. Variants of one base do not
  count as diversity. The same frozen set is used in every positive owner group.
- **Power:** declared-assumption paired design, seed `20260824`. SEPP = 0.15
  absolute success-rate lift (owner-decision-cost prior). Analytic n_confirm = 126
  before 10% attrition inflation → 144 confirm pairs (24 per owner×family cell)
  plus 24 disjoint development pairs. Monte Carlo (20 000 sims) achieved power
  0.8396 under H1. Sensitivity at +20% pair variance requires 168 confirm pairs
  and is recorded, not silently adopted.
- **Weighting:** equal top-level weight per owner group (holdingco, teachingco,
  softwareco). Within each owner, baseline × model weights sum to one.
- **Calibration:** Brier + 10-bin ECE; forecasts emitted by the advice surface
  before execution; reference is disjoint-development prevalence; forecasts hidden
  from outcome reviewers.
- **Harm / safety:** cell and owner-marginal −5 pp stops; aggregate cannot waive
  a cell stop; one insufficient-evidence safety case in every owner × family cell.
- **Privacy:** no raw cross-owner snapshot transmission; transfers empty at freeze.
- **Authority:** empirical output grants no release, rollout, or doctrine authority.
  Owner dispositions, outcomes, receipts, and governance decisions remain distinct.

## Consequences

- No confirmatory, development-arm, forecast, or analysis output may be produced
  until this protocol is the accepted decision record (now true).
- Any change to a frozen field requires a fresh accepted empirical decision, a
  held-out corpus, and affected reruns. Failed studies stay in lineage.
- Campaign execution remains a later exact DSPx task; this ADR does not run it.

## Rollback

Withdrawing this decision leaves G3 unaccepted; no campaign output exists to
relabel. The manifest and this ADR remain historical.
