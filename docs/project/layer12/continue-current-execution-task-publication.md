---
summary: "Closed DSPx owner-local publication contract for the one-token continue_current_execution_task Layer-12 family."
read_when:
  - "Verifying or changing the IW14b fixed-family spec, signed fixture, external pins, or authority boundary."
---

# `continue_current_execution_task` fixed-family publication

## Purpose and boundary

DSPx publishes one owner-local family/spec artifact for exactly one transition token:

```text
continue_current_execution_task
```

The publication is evidence that the DSPx-owned family/spec bytes were signed. It is not publication to affected users and does not establish AK wire truth, AK legality, policy selection, recommendation, apply, promotion, activation, dogfood, or rollout authority. No code in this slice calls or imports `layer12_controller`, calls AK, writes an AK repository or database, selects a policy, or performs publication/signing effects.

The six-file IW14b slice is bound to task-scope digest `sha256:46e7861e08304ee1fa2ececa5ab460137dcf3fd2eae40f7055b8252b7fa04393`.

## Artifacts

- `continue-current-execution-task-publication.v1.json` is the closed family/spec.
- `layer12-fixed-family-publication.v1.schema.json` closes both spec and publication shapes.
- `fixtures/iw14b-continue-current-execution-task-publication.v1.json` is deterministic test evidence signed by a test-only Ed25519 fixture key.
- `program_layer12_fixed_family_publication.py` is a pure verifier. It neither signs nor publishes.

The spec digest is `sha256:acbfc92dff83c76e99135d073a1bd58bea7db185ed2955eceb893b3fa19f486f` under sorted, compact UTF-8 JSON (`ensure_ascii=false`, no NaN). The signature covers the complete publication object except its `signature` member. `signed_payload_digest` hashes those same canonical bytes.

## Independent pinning requirement

A consumer must provide every trust- or owner-sensitive input independently:

- expected DSPx owner and family identity;
- expected scope and spec digests;
- expected AK wire identity and wire digest;
- expected signer key id, Ed25519 public key, lifecycle status, validity interval, and verification time.

The AK wire declaration and public key/lifecycle declaration embedded in the publication are evidence only. The verifier compares them to external pins, but never uses an embedded declaration to bootstrap trust. `declaration_is_trust_root` must be `false`; unknown fields and alternate trust-root flags are rejected.

The committed public key is safe only as deterministic fixture evidence. Its private key is derived in tests from the literal seed label `DSPx IW14b deterministic Ed25519 TEST FIXTURE ONLY v1`; it is not a production key and must never sign real publication material.

## Fail-closed invariants

The schema and verifier reject:

- zero, two, renamed, or otherwise different transition tokens;
- unknown or missing fields at every object boundary;
- owner, family, protocol, schema, scope, spec, AK-wire, signer, payload-digest, or signature drift;
- malformed Ed25519/base64 material or a signature made by a different key;
- revoked, inactive, not-yet-valid, expired, or publication-time-incompatible key lifecycle inputs;
- embedded-key self-authorization or declarations marked as trust roots;
- affected-use publication or any true legality, selection, apply, promotion, activation, dogfood, or rollout flag.

A successful verifier result says only `verified=true` for owner-local artifact evidence and reports `authority_granted=false`. Any affected-use publication, AK acceptance, policy decision, or operational enablement requires a separate owner-authorized surface outside this contract.
