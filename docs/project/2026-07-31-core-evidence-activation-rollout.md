---
summary: "Validation, rollout, dogfood, and rollback contract for solo-operated Core evidence custody."
read_when:
  - "You are configuring or running the first live Core evidence canaries."
type: "procedure"
---

# Core Evidence Activation — Validation, Rollout, and Rollback

## Authority boundary

This procedure activates evidence authenticity and public bounded custody only. It cannot authorize or publish a package. The release-owner roster stays unbound and disabled.

## Preflight

1. Confirm exact repository/owner IDs and authenticated GitHub target.
2. Confirm protected `main`, `core-release-evidence`, and provider maximum retention of at least 90 days through an authenticated repository-admin API call.
3. Write `DSPX_CORE_RELEASE_RETENTION_CAP_DAYS=90` and `DSPX_CORE_RELEASE_90D_REVIEW_CONFIGURED=true` only after observing those exact provider facts. These non-secret assertions bridge facts that the restricted Actions token cannot read; they do not create release authority.
4. Confirm policy/selector/roster validation passes with the roster unbound and authorization disabled.
5. Confirm focused tests, workflow contract, full readiness gate, and clean scoped Git status.
6. Push the exact reviewed main commit and confirm remote equality.
7. Configure the environment reviewer as a same-principal deliberate-action control; do not describe it as independent review.

## Rollout

1. Re-observe the provider settings, confirm the two assertion variables still match, then set `DSPX_CORE_RELEASE_SIGNING_ENABLED=true` only after preflight.
2. Dispatch one `trusted_run_14d` workflow.
3. Observe provider state to terminal completion; do not retry failed or indeterminate upload effects.
4. Download and verify evidence and receipt artifacts.
5. Dispatch one `release_candidate_90d` workflow.
6. Approve its environment deployment only through the configured authenticated principal and record same-principal posture.
7. Repeat download and verification.
8. Leave the variable enabled only after both canaries are verified successful; otherwise delete it.

## Verification evidence

Record:

- source/workflow commit and run attempt;
- run URL and terminal conclusion;
- evidence and receipt artifact IDs, provider digests, creation and expiry;
- exact signed statement and Sigstore verification result;
- paired current-availability result from one complete provider observation;
- explicit false release authority, package publication, and sdist support;
- environment reviewer and same-principal non-independence posture;
- final enable-variable state.

## Stop conditions

Stop and delete the enable variable if:

- repository, owner, ref, workflow, environment, or runner identity drifts;
- policy, selector, trust root, certificate, DSSE bytes, or deny checks fail;
- pre-upload disclosure scan fails;
- provider effect is indeterminate;
- evidence or receipt is absent, duplicated, expired, or digest-drifted;
- the workflow requests package-write permission or emits authority claims.

## Future release consumer

A future release consumer remains a decision-gated design. Its current lawful behavior is fail-closed because no owner-authentication adapter exists. Do not implement a permissive placeholder or bind aliases to the v1 roster.
