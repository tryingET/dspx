---
summary: "Tactical goals for the single active strategic goal."
read_when:
  - "When planning sprints/weeks"
  - "When selecting the current active execution wave"
---

# Tactical Goals

Active strategic goal: `SG2` — turn receipts, replay, and Oracle evidence into the predictive/governance substrate for V8 and V9.

Active tactical goal: `TG24`
Next tactical goal: `TG25`

## Tactical ranking for `SG2` (Eisenhower-3D)

| ID | Status | Goal | Importance | Urgency | Difficulty | Why this is the right wave now |
| --- | --- | --- | --- | --- | --- | --- |
| `TG24` | active | Harden receipt-bearing runtime boundaries so server, multi-provider, replay/explain, and SG2 evidence surfaces persist trustworthy artifacts and fail closed under drift. | 5 | 5 | 3 | The working tree already carries concrete repo-local edits across server artifact persistence, mutation confirmation, multi-provider isolation/policy restoration, strict boundary validators, and SG2 receipt parsing, while AK had no live slice for that wave. |
| `TG25` | next | Freeze the first explicit human-governed promotion-eligibility contract for moving named governance-only policy variants toward future live-authorized policy. | 5 | 4 | 4 | SG2 still needs an explicit bridge beyond governance-only receipts, but that bridge should sit on hardened receipt/runtime surfaces instead of today’s partially implicit boundary behavior. |

## Tactical definitions of done

### `TG24` — Receipt-bearing runtime boundary hardening
Done when:
- server-generated signature/module/mermaid runs persist stable artifacts and receipts or degrade cleanly without lying about persistence,
- multi-provider orchestration preserves request/policy isolation semantics and fail-closed winner/capability behavior under dirty-worktree and async edge cases,
- receipt/explain/openapi/rate-limit/evidence parsers reject malformed boundary inputs instead of silently coercing them.

### `TG25` — Governed promotion-eligibility contract
Done when:
- DSPx names the first bounded contract that decides when governance-only policy-evaluation receipts may nominate a variant for human review toward live authority,
- the contract defines allowed evidence inputs, required review/audit artifacts, and explicit non-authority defaults,
- the repo can materialize the first bounded follow-on slice without silently widening live ranking/promotion power.

## Active operating decomposition for `TG24`

- `AK-707` (done) — persist server-generated signature/module/mermaid artifacts and receipts, enforce confirmation gates across all mutating server endpoints, and return stable artifact references/manifest paths.
- `AK-708` (ready) — harden multi-provider orchestration with dynamic capability aggregation, request-message preservation, policy override restoration, dirty-worktree-safe git-worktree isolation, and hung-loser cleanup.
- `AK-709` (after `AK-708`) — tighten SG2 receipt parsing, MLflow explain artifact matching, OpenAPI numeric strictness, rate-limit token parsing, and adjacent regression coverage.

## Recently completed tactical goals for `SG2`

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
- jumping directly from governance-only evaluation receipts to a live-authority promotion contract while `TG24` runtime-boundary hardening is still incomplete,
- live predictive ranking from Oracle priors,
- live candidate pruning or promotion blocking from prior-backed signals,
- strategy/policy mutation without explicit governed evaluation receipts,
- widening authority beyond governance-only receipt emission before a later contract explicitly promotes a named variant into live policy,
- reopening the completed SG3 AK-native scope-snapshot chain without a new contract, surfaced regression, or operator pull,
- older provider/runtime and Oracle follow-ons (`AK-224`, `AK-235`–`AK-239`) that remain non-active backlog.
