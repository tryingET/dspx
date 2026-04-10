---
summary: "Tactical goals for the single active strategic goal."
read_when:
  - "When planning sprints/weeks"
  - "When selecting the current active execution wave"
---

# Tactical Goals

Active strategic goal: `SG2` — turn receipts, replay, and Oracle evidence into the direct runtime and governance surface for empirical development of DSPy systems.

Active tactical goal: `TG28`
Next tactical goal: `unmaterialized`

## Tactical ranking for `SG2` (Eisenhower-3D)

| ID | Status | Goal | Importance | Urgency | Difficulty | Why this is the right wave now |
| --- | --- | --- | --- | --- | --- | --- |
| `TG28` | active | Freeze the first human-governed review-decision contract for nominated governance-only policy variants. | 5 | 5 | 3 | `AK-1102` now emits the first bounded `promotion_eligibility_nominations` receipts, so SG2's next leverage is to freeze the explicit human review-decision contract that decides how nominated policy variants may be resolved toward future live authority without widening in-run behavior. |
| `TG27` | complete | Materialize the first promotion-eligibility nomination receipts for governance-only policy variants. | 5 | 5 | 3 | Completed via `AK-1102`, which emitted bounded `promotion_eligibility_nominations` receipts from governed policy-evaluation receipts plus candidate-assembly / execution-episode / receipt-bundle provenance without widening live authority. |

## Tactical definitions of done

### `TG28` — Human-governed review-decision contract
Done when:
- DSPx names the first bounded contract that decides how a promotion-eligibility nomination may be reviewed and resolved by humans toward future live authority,
- the contract is grounded in governed policy-evaluation receipts, promotion-eligibility nomination receipts, and explicit runtime-spine objects such as candidate assembly, execution episode, and receipt bundle evidence,
- the contract defines allowed review outcomes, required decision artifacts, and explicit non-authority defaults,
- and the repo can materialize the first bounded follow-on slice without silently widening live ranking or policy-activation power.

### `TG27` — Promotion-eligibility nomination receipts
Done when:
- DSPx emits bounded `promotion_eligibility_nominations` receipts from governance-only policy-evaluation receipts plus runtime-spine provenance,
- the nomination receipts record deterministic eligibility outcomes, required human-review artifacts, and explicit non-authority defaults,
- the receipts attach to bounded `module-gen` runtime metadata / persisted receipt metadata without widening live ranking, pruning, tie-breaking, or promotion behavior,
- and the repo closes the first post-contract implementation slice without inventing a larger governance workflow surface.

## Active operating decomposition for `TG28`

- `AK-1106` — freeze the first human-governed review-decision contract for nominated governance-only policy variants.
- Keep the slice bounded to the ADR/doc contract surface, the supporting tactical/operational/handoff/projection refresh, and the frozen task-scope snapshot.
- Ground the contract in the governed policy-evaluation receipts from `AK-593`, the promotion-eligibility nomination receipts from `AK-1102`, and the runtime-spine objects emitted by `AK-1085`.
- Keep the contract governance-only; do not widen live ranking, pruning, promotion blocking, or policy mutation authority.

## Recently completed tactical goals for `SG2`

- `TG27` — materialized the first promotion-eligibility nomination receipts on `synthesis_diagnostics.promotion_eligibility_nominations`, deriving bounded nomination receipts from governed policy-evaluation receipts plus runtime-spine provenance without changing live V7 ranking, tie-breaking, pruning, or promotion behavior.
- `TG26` — froze the first human-governed promotion-eligibility contract for governance-only policy variants as `docs/adr/20260409-human-governed-promotion-eligibility-contract-v1.md`, defining how governed policy-evaluation receipts plus runtime-spine provenance may nominate a named variant for explicit human review toward future live authority without changing live V7 behavior.
- `TG25` — established the first explicit runtime spine for candidate assembly, execution episode, and receipt bundle semantics via `AK-1085`, giving later governance work a truthful bounded runtime backbone.
- `TG24` — closed the receipt-bearing runtime-boundary hardening wave via `AK-707`/`AK-708`/`AK-709`, persisting trustworthy server artifacts, hardening multi-provider isolation/capability boundaries, and tightening SG2 receipt/explain/openapi/rate-limit parsing without widening live policy authority.
- `TG23` — materialized the first governance-only ranking/promotion evaluation receipts on `synthesis_diagnostics.governed_policy_evaluations`, evaluating named bounded variants against shadow predictive-ranking evidence plus trusted current metadata without changing live V7 ranking, tie-breaking, pruning, or promotion behavior.
- `TG22` — froze the first governed policy-evaluation contract that consumes shadow predictive-ranking evidence as `docs/adr/20260330-synthesis-evidence-governed-policy-evaluation-contract-v1.md`, defining the bounded evaluation inputs, variant surfaces, receipt payload, and promotion-authority limits before the first governed receipt wave.
- `TG21` — materialized the read-only shadow predictive-ranking advisory on live module metadata and persisted receipts, comparing a bounded prior-aware shadow preference against the trusted V7 winner without changing live ranking, tie-breaking, pruning, or promotion behavior.
- `TG20` — froze the first offline/shadow predictive-ranking contract after the read-only counterfactual advisory.
- `TG19` — materialized the read-only candidate-prior counterfactual advisory on live module metadata and persisted receipts before any predictive-ranking authority widened.
- `TG18` — froze the next post-readiness SG2 contract as the read-only candidate-prior counterfactual advisory contract.
- `TG17` — materialized the read-only candidate-prior readiness advisory on live metadata and persisted receipts.
- `TG16` — froze the next post-divergence SG2 contract as the read-only candidate-prior readiness advisory contract.
- `TG15` — materialized the read-only candidate-prior divergence explanation on live metadata and persisted receipts.
- `TG14` — froze the next post-audit SG2 contract as the read-only candidate-prior divergence-explanation contract.
- `TG13` — materialized the read-only post-selection candidate-prior audit on live metadata and persisted receipts.
- `TG12` — froze the first post-selection candidate-prior audit contract.
- `TG11` — materialized read-only candidate winner priors for the current deterministic `module-gen` variants.
- `TG10` — froze the first evidence-backed candidate-prior contract before predictive ranking.
- `TG9` — materialized the first read-only historical convergence advisory from SG2 evidence.
- `TG8` — froze the first post-diagnostics SG2 contract before predictive ranking began.
- `TG7` — threaded the v1 evidence bundle into module-synthesis diagnostics.
- `TG6` — materialized the v1 evidence retrieval bundle for ranked module synthesis.
- `TG5` — froze the first evidence-substrate contract for ranked synthesis.

## Recently completed tactical goals for `SG1`

- `TG1` — froze the synthesis target architecture in dated, referenceable docs.
- `TG2` — landed a V9-compatible module synthesis runtime MVP inside the existing `module-gen` surface.
- `TG3` — extended the MVP to true V7 candidate selection and evidence-backed promotion.
- `TG4` — hardened the module synthesis pipeline with quality gates and corpus coverage.

## Defer/until-later notes

The following remain intentionally out of the active tactical wave until the lifecycle promotes them:
- live predictive ranking from Oracle priors,
- live candidate pruning or promotion blocking from prior-backed signals,
- strategy/policy mutation without explicit governed evaluation, promotion-eligibility, and review-decision receipts,
- widening authority beyond governance-only evidence before `TG28` freezes the first explicit human review-decision contract and a later contract or human-governed decision explicitly promotes a named variant into live policy,
- guessing the post-`TG28` tactical wave just to keep the queue non-empty,
- reopening the completed `TG27` nomination-receipt wave without a new contract, surfaced regression, or operator pull,
- reopening the completed `TG26` promotion-eligibility contract wave without a new contract, surfaced regression, or operator pull,
- reopening the completed `TG25` runtime-spine wave without a new contract, surfaced regression, or operator pull,
- reopening the completed `TG24` runtime-boundary hardening wave without a new contract, surfaced regression, or operator pull,
- reopening the completed SG3 AK-native scope-snapshot chain without a new contract, surfaced regression, or operator pull,
- older provider/runtime and Oracle follow-ons (`AK-224`, `AK-235`–`AK-239`) that remain non-active backlog.
