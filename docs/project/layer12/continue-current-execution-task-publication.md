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

The spec digest is `sha256:7c4686dcdf26b085a595d1b381660a3191d650c8d26be1bb22a8adaa533142cc` under sorted, compact UTF-8 JSON (`ensure_ascii=false`, no NaN). The signature covers the complete publication object except its `signature` member. `signed_payload_digest` hashes those same canonical bytes.

## Independent pinning requirement

A consumer must provide every trust- or owner-sensitive input independently:

- expected DSPx owner and family identity;
- expected publication id, per-family epoch, current publication state, and optional withdrawal ref;
- expected scope and spec digests;
- expected AK wire identity and wire digest;
- expected signer key id, Ed25519 public key, lifecycle status, validity interval, and verification time.

The AK wire declaration and public key/lifecycle declaration embedded in the publication are evidence only. The verifier compares them to external pins, but never uses an embedded declaration to bootstrap trust. `declaration_is_trust_root` must be `false`; unknown fields and alternate trust-root flags are rejected.

Publication lifecycle is separately pinned from signer lifecycle. The signed fixture records epoch `1` and `state_at_signing=published`, while the current `published|withdrawn` state and withdrawal ref come from the external owner-local lifecycle pin. A current `withdrawn` pin rejects this publication even while the shared signing key remains active, so withdrawing one family epoch does not require revoking a key used by unrelated publications.

Canonical reconstruction is executable, not a declaration. `reconstruct_fixed_family_imports` consumes closed `layer12-fixed-family-import-v1` prior/current import records, required prior `layer12-fixed-family-epoch-high-watermark-v1` records, plus an optional closed `layer12-fixed-family-withdrawal-v1`. It returns `layer12-fixed-family-reconstruction-v1` without filesystem, AK, signing, or publication effects.

Reconstruction is cumulative and keyed by `(owner, family_id)`. Every imported family requires a high-water record; withdrawals remove the import but retain its per-family epoch/token/spec tombstone and the closed cumulative set of every used publication id. Feeding reconstruction output into the next call therefore rejects epoch reuse or regression and rejects reuse of a withdrawn publication id even at a higher epoch, while a strictly higher compatible epoch with a fresh id can advance the watermark. Per-family epochs must be strictly monotonic even when unrelated families are interleaved. Each unrelated family retains its own transition token and spec digest; later epochs for the same family must preserve that family contract. Duplicate coordinates, duplicate publication ids, conflicting same-epoch or same-family contract records, and non-monotonic histories fail closed. A withdrawal must match exactly one existing `(owner, family_id, epoch, publication_id)` and removes only that record; cross-family, missing-epoch, and conflicting-id withdrawals fail. All unrelated imports remain byte-equivalent canonical records in their original order, so this one-token family can never act as a global replacement snapshot.

The committed public key is safe only as deterministic fixture evidence. Its private key is derived in tests from the literal seed label `DSPx IW14b deterministic Ed25519 TEST FIXTURE ONLY v1`; it is not a production key and must never sign real publication material.

## Fail-closed invariants

The schema and verifier reject:

- zero, two, renamed, or otherwise different transition tokens;
- unknown or missing fields at every object boundary;
- publication-id, per-family epoch, owner, family, protocol, schema, scope, spec, AK-wire, signer, payload-digest, or signature drift;
- malformed Ed25519/base64 material or a signature made by a different key;
- revoked, inactive, not-yet-valid, expired, or publication-time-incompatible key lifecycle inputs;
- externally withdrawn publication state, missing withdrawal evidence, or withdrawal refs on a published state;
- missing/duplicate/regressed high-water tombstones, epoch or durable publication-id reuse after withdrawal, omitted/duplicate used-id history, duplicate/conflicting publication histories, non-monotonic per-family epochs, cross-family or non-matching withdrawals, and reconstruction attempts that globally replace or discard unrelated imports;
- embedded-key self-authorization or declarations marked as trust roots;
- affected-use publication or any true legality, selection, apply, promotion, activation, dogfood, or rollout flag.

A successful verifier result says only `verified=true` for owner-local artifact evidence and reports `authority_granted=false`. Any affected-use publication, AK acceptance, policy decision, or operational enablement requires a separate owner-authorized surface outside this contract.
