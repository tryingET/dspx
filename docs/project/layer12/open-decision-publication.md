---
summary: "TEST-only owner-local fixed-family publication for `open_decision`."
read_when:
  - "Verifying the IW14b B4 open_decision fixture or decision/successor boundary."
type: "reference"
---

# `open_decision` owner-local publication

This deterministic IW14b B4 artifact publishes only DSPx owner-local TEST verification evidence for task key `B4-DSPx-publication`, task 3915, authorization evidence 4429, and frozen six-path scope `sha256:170fc5f6509d43d65c95b4a29bbd85ec00089c38b7ba1d2c827848f25afc59bb`. Those identifiers authorize this bounded publication slice; they are not trust roots and do not authorize a decision transition.

- Family: `dspx.layer12.open-decision.v1`, coupled exactly and bidirectionally to the one token; there is no generic or cross-token fallback.
- Publication: `dspx-iw14b-open-decision-owner-local-test-v1`, epoch 1.
- Key: distinct, independently anchored TEST fixture key `dspx-iw14b-b4-open-decision-test-key-v1`; only public verification material is committed.
- Program: `dspx.generated.open_decision.v1`, with one closed two-module graph.
- Decision gate: `decision_currentness=required_not_available` and `explicit_decision_authorization_available=false`.
- Mutation boundary: `effects=none`, `read_only=true`, `zero_mutation=true`, `allowed_mutations=[]`, `open_decision_performed=false`, `decision_mutation_performed=false`, and `other_mutation_performed=false`.
- Successor boundary: every one of the six pre-existing transition tokens is explicitly `unavailable`, `all_successors_unavailable=true`, and `generated_program_dispatch_ready=false`.

The artifact does not open or mutate a decision, execute a successor, contact AK, dispatch the generated program, or mutate any owner surface. It grants no AK trust or integration authority and no affected-use publication, apply, promotion, activation, dogfood, rollout, or closeout authority.

Reconstruction appends this seventh import to byte-identical B0–B3 six-import history. An exact B4-only withdrawal returns those six imports unchanged while retaining the B4 epoch high-water mark and used publication-id tombstone append-only.
