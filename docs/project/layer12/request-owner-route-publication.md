---
summary: "TEST-only DSPx owner-local publication contract for the fixed request_owner_route family."
read_when:
  - "Verifying the IW14b B1 request_owner_route spec, fixture, program evidence, or withdrawal behavior."
---

# `request_owner_route` TEST fixed-family publication

## Boundary

This slice publishes deterministic **TEST evidence only** for exactly `request_owner_route` in family `dspx.layer12.request-owner-route.v1`. Its six-path task scope is pinned as `sha256:a96a880c99588b00a4c4c99e3035d10c792b02c91384f24ffb812438c0966583`.

Only `owner_local_artifact_publication` is true. A successful verification grants no AK trust or legality, affected-use publication, dispatch, selection, recommendation, apply, promotion, activation, dogfood, rollout, or closeout authority. The artifact does not call AK or send an owner route. Embedded AK-wire and signer declarations are evidence, never trust roots.

## Closed evidence

`request-owner-route-publication.v1.json` binds:

- a closed `program-intent-v2` evidence record for `dspx.generated.direction_controller.v1`;
- the exact six-signature graph: `ExtractLayer12PolicyFacts`, `DeriveLayer12StateVector`, `ProposeLayer12Transition`, `CritiqueAuthorityDrift`, `CritiqueTheaterTraps`, and `RepairLayer12IR`, including exact input/output fields and order;
- the sole verification sink `ak.direction_controller.verify`, with `apply_performed=false`;
- blocked Controls evidence: `legal=false`, `verdict=blocked`, `dispatch_ready=false`, and `owner_route_sent=false`;
- exactly two missing preconditions: `owner_route_destination_resolved` and `owner_route_dispatch_authorized`.

The ProgramIntent, module graph, and Controls rows each carry a canonical SHA-256 digest. The enclosing spec digest is `sha256:9c7fdfa7b13d13b803fecef1b57ed080a2b8462658f82b7f169521b84a4a893f`, so publication identity signs the complete closed evidence transitively.

## External pins and no fallback

The verifier now requires every caller to provide an exact transition-token pin. It accepts only the two owner-local fixed families implemented here and in B0, and the artifact token must equal the caller pin. It does not infer acceptance from an enum, dispatch through a generic controller, or fall back across tokens/families.

Owner, family, token, scope/spec digest, AK wire identity/digest, publication id/epoch/state, signer identity/public key/lifecycle, and verification time remain independent external pins. Co-substitution or lifecycle drift fails closed. B0 `continue_current_execution_task` semantics remain regression-bound and B0 rejects B1-only program evidence.

## Fixture and reconstruction

`fixtures/iw14b-request-owner-route-publication.v1.json` is signed using a deterministic Ed25519 key derived only in the focused test from `DSPx IW14b B1 request_owner_route deterministic Ed25519 TEST FIXTURE ONLY v1`. Publication/spec/docs contain the public key only; no private seed or production signing material is committed.

Reconstruction cumulatively retains B0 plus B1 as two independent `(owner, family_id)` records. Artifact-scoped B1 withdrawal removes only the exact B1 publication and retains byte-identical B0, while B1 epoch and publication-id history remain immutable in its high-water tombstone. Replay, regression, cross-family withdrawal, and durable publication-id reuse fail closed.

No real or external publication, route dispatch, AK mutation, activation, or production use is performed by this slice.
