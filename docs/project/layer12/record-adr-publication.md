---
summary: "TEST-only owner-local fixed-family publication for `record_adr` duplicate prevention."
read_when:
  - "Verifying the IW14b B6 record_adr fixture or accepted-ADR duplicate-prevention boundary."
type: "reference"
---

# `record_adr` owner-local publication

This deterministic IW14b B6 artifact publishes only DSPx owner-local TEST verification evidence for task key `B6-DSPx-publication`, task 4059, owner-execution authorization evidence 4856, and frozen six-path scope `sha256:789219a85ad06150d80ebcaccad934bd4a7fdb6d66fc83d1e7286a8a9f8f514a`. These identifiers authorize this bounded publication slice; they are not trust roots and do not authorize an ADR, decision, post-ADR, or successor transition.

- Family: `dspx.layer12.record-adr.v1`, coupled exactly and bidirectionally to `record_adr`; there is no generic or cross-token fallback.
- Publication: `dspx-iw14b-record-adr-owner-local-test-v1`, epoch 1.
- Key: distinct TEST fixture identity `dspx-iw14b-b6-record-adr-test-key-v1`; only public verification material and its deterministic signature are committed.
- Program: `dspx.generated.record_adr.v1`, with a closed two-module graph.
- Position boundary: the TEST evidence denies unknown decision/review/ADR/post-ADR Position fields, requires exactly one current source-bound decision and a legal `ready_for_adr` review closure, and fails closed on ambiguity or stale Position.
- Duplicate boundary: live Decision 50 already has its accepted ADR and current post-ADR continuation artifacts. This reusable family treats that posture only as a duplicate-prevention observation, not as an ADR-recording target or current lifecycle successor.
- Recordable boundary: a different current decision must have a legal `ready_for_adr` closure, no existing ADR, no post-ADR continuation, and separate exact ADR authorization before any mutation-capable surface could exist. This R0/R1 artifact remains blocked regardless.
- Mutation boundary: `availability=blocked_readiness_only`, `legal=false`, `effects=none`, `read_only=true`, `zero_mutation=true`, `allowed_mutations=[]`, and every ADR/decision/post-ADR/successor/apply flag is false.

The artifact does not record an ADR, mutate a decision or post-ADR plan, dispatch a successor, contact AK, or mutate another owner surface. It grants no AK trust or integration authority and no affected-use publication, apply, promotion, activation, dogfood, rollout, implementation-wave closeout, or strategic-frame closeout authority.

Reconstruction appends this ninth import to byte-identical B0–B5 eight-import history. An exact B6-only withdrawal returns those eight imports unchanged while retaining all nine epoch high-water marks plus the B6 used and withdrawn publication-id tombstone append-only. Replay or reuse of the withdrawn B6 identity/epoch fails closed **when the caller preserves and supplies that complete durable nine-watermark snapshot**. The pure verifier is stateless: discarding the B6 watermark makes the input indistinguishable from a legitimate pre-B6 eight-family snapshot, so durable monotonic snapshot retention remains the integrating owner's responsibility rather than authority supplied by this artifact.
