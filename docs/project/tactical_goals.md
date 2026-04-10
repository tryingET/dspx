---
summary: "Tactical goals for the single active strategic goal."
read_when:
  - "When planning sprints/weeks"
  - "When selecting the current active execution wave"
---

# Tactical Goals

Active strategic goal: `SG2` — turn receipts, replay, and Oracle evidence into the direct runtime and governance surface for empirical development of DSPy systems.

Active tactical goal: `unmaterialized`
Next tactical goal: `unmaterialized`

## Tactical ranking for `SG2` (Eisenhower-3D)

| ID | Status | Goal | Importance | Urgency | Difficulty | Why this was the right wave |
| --- | --- | --- | --- | --- | --- | --- |
| `TG26` | complete | Freeze the first human-governed promotion-eligibility contract for governance-only policy variants. | 5 | 5 | 3 | Completed via `AK-1047`, which froze `docs/adr/20260409-human-governed-promotion-eligibility-contract-v1.md` and grounded policy-variant nomination for future human review in candidate-assembly / execution-episode / receipt-bundle provenance without widening live authority. |
| `TG25` | complete | Establish the first explicit runtime spine for candidate assembly, execution episode, and receipt bundle semantics. | 5 | 5 | 3 | Completed via `AK-1085`, which bridged `dspx.synthesis` to explicit runtime-spine objects and gave replay, explain, Oracle, and later governance work a truthful bounded runtime backbone. |

## Tactical definitions of done

### `TG26` — Human-governed promotion-eligibility contract
Done when:
- DSPx names the first bounded contract that decides when governance-only policy-evaluation receipts may nominate a variant for human review toward live authority,
- the contract is grounded in explicit runtime-spine objects such as candidate assembly, execution episode, and receipt bundle evidence,
- the contract defines allowed evidence inputs, required review/audit artifacts, and explicit non-authority defaults,
- and the repo can materialize the first bounded follow-on slice without silently widening live ranking or promotion power.

### `TG25` — Runtime spine for empirical development
Done when:
- DSPx names and emits the first explicit runtime objects for candidate assembly, execution episode, and receipt bundle semantics,
- at least one bounded path emits those objects end-to-end without changing the visible CLI contract,
- and replay, explain, Oracle, and later governance work have a truthful runtime spine to consume instead of service-local ambiguity.

## Follow-on shape after `TG26`

- `AK-1047` froze `docs/adr/20260409-human-governed-promotion-eligibility-contract-v1.md` as the bounded human-governed nomination contract for future policy-variant review.
- The first truthful post-contract implementation step is a bounded receipt wave that emits `promotion_eligibility_nominations` from `governed_policy_evaluations` plus runtime-spine provenance.
- Keep that implementation step unmaterialized until a later direction-to-execution pass pins it in AK; do not invent the post-contract queue just to avoid an empty ready list.

## Recently completed tactical goals for `SG2`

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
- strategy/policy mutation without explicit governed evaluation and promotion-eligibility receipts,
- widening authority beyond governance-only evidence after `TG26` without a later contract or human-governed decision that explicitly promotes a named variant into live policy,
- guessing the post-contract implementation slice just to keep the queue non-empty,
- reopening the completed `TG26` promotion-eligibility contract wave without a new contract, surfaced regression, or operator pull,
- reopening the completed `TG25` runtime-spine wave without a new contract, surfaced regression, or operator pull,
- reopening the completed `TG24` runtime-boundary hardening wave without a new contract, surfaced regression, or operator pull,
- reopening the completed SG3 AK-native scope-snapshot chain without a new contract, surfaced regression, or operator pull,
- older provider/runtime and Oracle follow-ons (`AK-224`, `AK-235`–`AK-239`) that remain non-active backlog.
