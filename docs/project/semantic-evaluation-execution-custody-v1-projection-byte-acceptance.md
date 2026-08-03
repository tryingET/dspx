---
summary: "Decision 105 exact synthetic projection-byte acceptance record and successor non-authorization."
read_when:
  - "Checking whether Decision 105 produced accepted immutable projection bytes."
  - "Checking the prerequisite boundary before any Decision 106 work."
type: "acceptance_record"
status: "accepted"
decision_id: 105
implementation_task_id: 4607
acceptance_task_id: 4614
---

# Decision 105 projection-byte acceptance

## Gate decision

**ACCEPTED**, limited to the exact synthetic no-network projection bytes and identities recorded below.

This acceptance establishes only that Decision 105 has produced one constructible, schema-valid, immutable projection from the accepted internal DSPx custody primitive. It does not authorize Decision 106, ROCS consumption, runtime or CLI wiring, provider/model/network use, publication, adoption, promotion, governance action, or production activation. The ROCS/Decision 106 owner must separately authorize any successor work.

## Accepted implementation identity

- implementation commit: `cc6c80678482e0ff46cd4252f4bd5cebfe78bab1`
- implementation tree: `ab35a0844aa3892eff76100038ebb693da44e832`
- canonical branch at generation: `main` / `origin/main`
- custody source SHA-256: `5ba7c0cab7471f5d29f6e0e8505bb336ad24b356ce2998a16dec11261e7b580e`
- custody test SHA-256: `e25b1e97a9159ac4f210fef2660d2f91e86f85b7ea93e81ac1bb6cbaff6b1c7c`
- projection schema SHA-256: `d42569781d23c625627d92a9f37ea9c26211c92c403b0dcdb45b0360c386c532`

The implementation was accepted for this identity by:

| Concern | Review identity | Outcome |
|---|---|---|
| DSPx owner boundary | `dispatch-1785746076380` | ACCEPT |
| lifecycle/crash/idempotency | `dispatch-1785746076381` | ACCEPT |
| projection/evidence | `dispatch-1785746076382` | ACCEPT |
| store security | `dispatch-1785746076383` | ACCEPT |

## Accepted projection identity

- attempt ID: `3a7cf8f1-726b-4435-965b-8a7443815ae9`
- terminal reason: `observed_return`
- exact projection byte length: `1810`
- exact projection SHA-256: `43cb523b3787726956f331ea0917fd55757cf317a13815cd6f0f97c8b9eb7206`
- terminal seal SHA-256: `ae5879bca4aa9182f50ba6f783af2f7ea43171a5e70a27b5e2a488bcda2259b4`
- verification manifest SHA-256: `895088932e697e4b181c1e3280cc234f4b489011f488a6310289ff3498a671b5`
- local verification root at acceptance: `/home/tryinget/.local/state/pi-quests/tmp/dspx-d105-4607-cc6c8067.dB3a4A`

The following single JSON line is the exact 1810-byte UTF-8 projection preimage. The Markdown fence delimiters and surrounding newlines are not part of the accepted bytes.

```json
{"attempt_id":"3a7cf8f1-726b-4435-965b-8a7443815ae9","attempt_kind":"original","candidate_coordinate":{"candidate_receipt_digest":"f1afbaf70f69bcde2dc6ac289bae2d2e8860792ba19eabeb0b225a802c72340e","source_manifest_digest":"1cf4c998d5fd0e521521ea0687e9481bc71991074de413f1340bf04fd0e688d6"},"effect_inventory_version":"dspx-semantic-evaluation-execution-effect-inventory-v1","episode_evidence_manifest_digest":"0010113601470a67193b0306eb3d4274d36d40913c5cfc83ef5b031e9de90ffb","episode_id":"decision105-synthetic-projection-gate-1","evaluation_request_digest":"9f4c067bf1934f5430db1370cade817ef6b0f1f0800a81477fcf4f1bed36e69e","input_coordinate":{"disclosure_posture":"digest_only_no_raw_access_right","normalized_input_digest":"8ac0d9d1d9aa37ebfb14df0bfc0791ebe4433a5b8ab45cd8314bf32117e404e9"},"non_authority":{"ak_mutation":false,"currentness":false,"deterministic_verdict":false,"executed_identity":false,"external_authority":false,"governance":false,"promotion":false,"publication":false,"semantic_meaning":false},"outcome_evidence":{"normalized_return_digest":"dc9403c3bdfeae78390e72cf8534500475794c78524607e2e6bb550a36fba1f5","observation_kind":"return","sanitized_failure_digest":null},"receipt_digest":"bfa3eab22ca7ff62ee631442686241da769678d935f91411fdbbe4eaca1f2cdf","runtime_observation":{"attempt_start_digest":"eb490b9946475e6fae0ed9945cf15a0109cb260c3d5b6d8015f4bbaea4b7eb38","configured_model":null,"configured_provider":null,"configured_runtime_digest":"8630c6ffbe76bb005c70aff98042eb860b67fbbae469caa5d6b1adc572848991","executed_model_identity":null,"executed_provider_identity":null,"outcome_kind":"return"},"schema_version":"dspx-semantic-evaluation-evidence-projection-v1","source_receipt_digest":null,"state_trace_digest":"f01a409428f2126abc676e12db0fa0f3f48a01361c5f6338280debb0a16d0d6e"}
```

## Conformance evidence

Observed validation for the accepted implementation identity:

- focused custody suite: `27 passed`;
- Ruff and Ty focused checks: passed;
- full offline suite: `2919 passed, 4 skipped`;
- residual live/network/model/GPU/Postgres selection: `5 skipped`;
- DSPx runtime replay, monorepo, module-synthesis, and documentation boundary gates: passed;
- exact Draft 2020-12 schema validation and code/schema differential review: passed;
- no provider, model, network, publication, runtime wiring, CLI wiring, Oracle publication, AK mutation, or governance effect occurred during generation.

A skipped task-scope helper was not treated as scope proof. AK task 4607's frozen scope and the cumulative Git diff independently showed only the projection schema, internal custody module, and focused tests. Task 4614 is limited to this acceptance record.

## Boundary and nonclaims

The accepted bytes record only DSPx-mediated local validation, durable start, direct return observation, local evidence sealing, and fixed non-authority fields. They do not prove provider-side call cardinality, provider retries, executed provider/model identity, protected-data custody, network or process isolation, semantic correctness, ROCS compatibility, publication/currentness, promotion, governance, or external authority.

Decision 98 B0 remains frozen and unrelated. Rejected Decision 105 implementation commits remain negative evidence only and are not revived by this acceptance.

## Forward gate

Decision 105's immutable projection-byte prerequisite is satisfied only for the exact identities in this record. Decision 106 remains blocked until its ROCS owner independently verifies this canonical record, explicitly authorizes its own scoped task, and begins its own strict lifecycle. Decision 107 remains blocked until Decisions 105 and 106 expose accepted interfaces.
