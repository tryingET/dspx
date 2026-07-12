---
summary: "TEST-only owner-local fixed-family publication for `close_implementation_wave`."
read_when:
  - "Verifying the IW14b B2 close_implementation_wave owner-local publication, fixture, or authority boundary."
type: "reference"
---

# `close_implementation_wave` owner-local publication

This deterministic IW14b B2 artifact publishes only DSPx owner-local verification evidence for task key `B2-DSPx-publications`, task 3836, authorization evidence 4231, and scope `sha256:8783fc9276dafc434003277b6a690b92fe466a8249a4e0e50f82071dc30b98ca`.

- Family: `dspx.layer12.close-implementation-wave.v1` (exact token-to-family pairing; no fallback)
- Publication: `dspx-iw14b-close-implementation-wave-owner-local-test-v1` at epoch 1
- Key: distinct TEST fixture key `dspx-iw14b-b2-close-implementation-wave-test-key-v1`; only public verification material is committed
- Program: `dspx.generated.close_implementation_wave.v1` with a distinct closed module graph and blocked Controls evidence
- Controls: `legal=false`, `dispatch_ready=false`, `transition_action_performed=false`
- Authority: only `owner_local_artifact_publication=true`; every affected-use, AK legality, apply, promotion, activation, dogfood, and rollout flag remains false

No dispatch, apply, transition, external publication, AK trust mutation, or task completion is performed or authorized. Withdrawal reconstruction is owner/family/epoch exact and retains unrelated publications plus durable high-watermark history.
