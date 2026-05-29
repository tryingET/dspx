---
summary: "DSPx generated-program activation packet boundary: evidence only until owner, decision, canonical binding, rollout owner, and rollback are explicit."
read_when:
  - "You are using `dspx program-promote activation-packet`."
  - "You need to know why a generated program remains blocked after Oracle/jury evidence exists."
  - "You are checking the authority/activation gates for generated DSPy/cognition programs."
---

# Generated program activation boundary

DSPx can produce activation evidence packets for generated DSPy/cognition programs, but those packets are not production activation authority.

Related DRY maps:

- [[oracle-backend-current-status]]
- [[generated-program-evidence-surface-boundaries]]
- [[program-gen-walkthrough]]

Canonical society-wide semantics live in governance-kernel:

- `~/ai-society/holdingco/governance-kernel/docs/core/definitions/generated-dspy-program-promotion-governance.md`
- `~/ai-society/holdingco/governance-kernel/docs/core/definitions/transition-passports/generated-cognition-program-production-activation.md`

## Hard boundary

`dspx program-promote activation-packet` may write a non-authoritative evidence packet. It must not:

- promote a generated program;
- deploy or route a generated program;
- mutate AK / society authority;
- mutate governance-kernel;
- mutate MLflow;
- mutate Oracle indexes;
- treat Oracle, MLflow, or DSPx jury output as approval.

## Rollout gate

A packet may reach `ready_for_rollout_preflight` only when all activation authority fields are explicit:

1. owning domain;
2. authority owner / delegated adjudicator;
3. required behavior evidence;
4. Oracle report when required;
5. jury/review evidence when required;
6. decision record with `outcome=promote`;
7. canonical binding ref;
8. rollout owner;
9. rollback plan.

If `rollout_owner` is missing, the packet stays `blocked` even if decision and canonical binding refs are present.

A non-empty `canonical_binding_ref` is not sufficient to claim rollout preflight. Until `dspx program-promote canonical-binding-verification` confirms the binding, the packet may only reach `ready_for_canonical_binding_verification`, not `ready_for_rollout_preflight`.

For Obsidian/PDF generated-program runtime activation, pass `--require-obsidian-review-adapter` with both target-aware candidate status and the Obsidian review-adapter receipt:

```bash
dspx program-promote activation-packet \
  --candidate-state <program_candidate_state.target_fidelity.json> \
  --obsidian-review-adapter-receipt <adapter-receipt.json> \
  --require-obsidian-review-adapter \
  ...
```

That evidence can prove review-packet admission, but it remains review-only. It does not satisfy jury/review evidence, domain decision, canonical binding, or rollout preflight by itself.

## Practical consequence

Oracle production-adjacent readiness on DS1621 improves the evidence substrate. Activation packets may cite shared Oracle publication preflight readiness and publication receipts as evidence only; they validate receipt target/backend posture, secret redaction, idempotency, record/publication consistency, source hash fields, preflight/receipt hash lineage when both are supplied, and non-authority posture before accepting a receipt. When a candidate-state sidecar also cites those Oracle publication artifacts, the activation packet cross-checks that the supplied refs agree instead of silently dropping them. The packet also exposes that check under `evidence_alignment.oracle_publication` so reviewers can see whether supplied/candidate-state publication IDs align. None of this changes the activation judge. A generated program still needs a domain-governed decision, canonical binding, rollout owner, and rollback plan before any production activation can be claimed.

Dogfood evidence for the DS1621 Oracle backend, backup, and authority gates is recorded in `docs/project/2026-05-09-oracle-production-readiness-gates-dogfood.md`. The authority dogfood intentionally remained blocked even with a shared Oracle publication receipt because review evidence, rollout owner, rollback plan, and canonical activation binding were not present.

Obsidian/PDF live-provider adapter dogfood is recorded in `docs/project/2026-05-09-obsidian-pdf-transition-live-adapter-dogfood.md`. That run used `dspy-lm-auth/codex/gpt-5.5` for generated behavior and materialized review-only proposal artifacts through the Obsidian adapter, but it still did not perform canonical production activation or mutate `Wiki/` / `Atlas/`.

The proposed next evidence layer is documented in `docs/rfc/RFC-DSPX-ADJ-20260509-meta-adjudication-orchestration.md`: a DSPx meta-adjudication layer that researches a generated program's target, selects and verifies a suitable jury, forms and verifies a program-specific adjudicator, publishes judging behavior to Oracle/Postgres as empirical memory, and later uses GEPA to improve judging behavior. That layer is still evidence-producing; it does not replace the domain/governance activation decision.

Current Obsidian/PDF dogfood evidence is recorded in `docs/project/2026-05-10-dogfood-obsidian-pdf-activation-packet.md`, `docs/project/2026-05-10-dogfood-obsidian-pdf-activation-blockers-resolved.md`, `docs/project/2026-05-10-review-bounded-obsidian-pdf-activation-many-greats.md`, `docs/project/2026-05-10-dogfood-obsidian-pdf-domain-decision.md`, and `docs/project/2026-05-10-dogfood-obsidian-pdf-canonical-binding.md`. The follow-up resolved the generated-program jury and refined-review evidence blockers, recorded AK decision `#40` and a matching domain decision sidecar, then verified the canonical binding and moved the packet to `ready_for_rollout_preflight`. Production remains unapplied until an explicit rollout preflight and rollout receipt are completed.
