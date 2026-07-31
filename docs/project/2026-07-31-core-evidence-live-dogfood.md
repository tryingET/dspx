---
summary: "Receipt-backed live dogfood of Core policy-v2 evidence signing and 14/90-day public custody."
read_when:
  - "You need current live Core signature/custody evidence or activation nonclaims."
type: "evidence"
---

# Core Evidence Signing and Custody — Live Dogfood

## Scope and authority

This dogfood activated only keyless evidence authenticity and bounded public GitHub artifact custody. It did not authorize or publish a package. The release-owner roster remained empty and disabled, no owner-authentication adapter was selected, and every signed receipt kept package release authority and package publication false.

The `core-release-evidence` environment used `tryingET` (GitHub user ID `260287438`) as a required reviewer with self-review permitted. This was a same-principal deliberate-action gate, not independent review or a release quorum.

## Decisions and policy

- Decision 91: activate the evidence plane without fabricating three owner principals.
- Decision 92: accept immutable trust policy v2 after live Fulcio `.1.24` drift.
- Decision 93: accept the exact Git-bound v2 selector superseding Decision 90/policy v1.
- Current policy: `governance/release-signing/trust-policy-v002.json`.
- Current selector: `governance/release-signing/policy-selector-v002.json`.

Policy v2 exactly matches the observed numeric-ID-bound Fulcio token subject:

`repo:tryingET@260287438/dspx@1318473695:environment:core-release-evidence`

Policy v1 and selector v1 remain immutable historical artifacts.

## Adversarial dogfood progression

Each failed run stopped and the enable variable was deleted before a code or policy correction. No failed or indeterminate upload was mechanically retried.

| Run | Commit | Observed result |
|---|---|---|
| `30658434219` | `34379d71` | Restricted Actions token could not read repository-admin retention settings; no upload. |
| `30658647807` | `6dad2f90` | Shallow checkout could not resolve immutable policy-v1 history; no upload. |
| `30658784801` | `78d76203` | Real Sigstore/Rekor signature exposed exact Fulcio `.1.24` drift; no artifact upload. |
| `30659429735` | `c6170846` | Evidence and receipt uploaded; final pair check rejected bare upload-action digest format. Offline fresh observation later proved both artifacts current. |
| `30659729944` | `d4efd764` | Evidence uploaded; GitHub's exposed expiry was one second below created-at plus 14 days, so receipt creation failed closed. |
| `30660107470` | `9090e20a` | 90-day evidence uploaded; provider expiry-start skew was 96 seconds, above the initial 60-second bound, so receipt creation failed closed. |

These runs are retained as evidence of fail-closed behavior. They are not successful custody canaries.

## Successful 14-day canary

- run: [`30659977281`](https://github.com/tryingET/dspx/actions/runs/30659977281)
- source commit: `9090e20a68c9cfddb0bc9155c9ef4e625679223f`
- conclusion: `success`
- evidence artifact: `8804782861`
- evidence provider digest: `sha256:f795a2a6658c2cd926588b159b08122df92fc5d0b0a5afe8df9893a86e9179d1`
- receipt artifact: `8804783816`
- receipt provider digest: `sha256:9e3e8dd4e56acf618c53c6571059347bbbc36889b3ee27e4c7390f1c50b11620`
- expiry: 2026-08-14
- downloaded public-upload preflight: passed
- fresh paired availability: `status=current`, `release_use_custody=true`

## Successful 90-day canary

- run: [`30660312181`](https://github.com/tryingET/dspx/actions/runs/30660312181)
- source commit: `1ac2868b40108c1748404bdb4408fc0b241f8748`
- conclusion: `success`
- evidence artifact: `8804911840`
- evidence provider digest: `sha256:c18117d9df7d2e33956f41c821721ee1ae08b4436b20c82b090f563063f96db6`
- receipt artifact: `8804913752`
- receipt provider digest: `sha256:166622eceab6f1ad09d486b4e415bf0cc9f80dc25d6fc1513dcbd060cad388dc`
- expiry: 2026-10-29
- downloaded public-upload preflight: passed
- fresh paired availability: `status=current`, `release_use_custody=true`

The provider computes expiry from upload initiation but exposes a later `created_at`. The implementation permits at most five minutes of this observed start-time skew; larger shortfalls still fail closed.

## Live verification

Both successful jobs passed:

- protected repository/workflow/environment preflight;
- exact immutable policy/selector/roster validation;
- clean commit-bound bundle creation;
- bounded nested archive disclosure scan;
- exact keyless Sigstore signing and pinned-root verification;
- evidence upload and complete provider observation;
- signed receipt creation and verification;
- receipt upload and complete provider observation;
- exact paired evidence/receipt ID, digest, expiry, and current-availability verification.

Downloaded artifacts were rechecked locally. Both public upload sets passed non-secret preflight, both signed receipts retained policy version 2, and both fresh complete provider observations returned current paired custody.

## Final provider posture

- `DSPX_CORE_RELEASE_SIGNING_ENABLED=true` remains enabled after both verified canaries, as explicitly selected by the operator.
- provider retention assertion: `DSPX_CORE_RELEASE_RETENTION_CAP_DAYS=90`.
- 90-day reviewer assertion: `DSPX_CORE_RELEASE_90D_REVIEW_CONFIGURED=true`.
- protected environment required reviewer: `tryingET`, same principal as operator.

## Remaining release-authority blockers

Evidence activation is complete. Package release authority remains unavailable because:

1. three genuinely independent v1 owner principals do not exist;
2. no owner-approval authentication mechanism has been selected;
3. no release-authorization consumer has been authorized to return true;
4. package publication remains a separate undecided owner transition;
5. the sdist remains unsupported auxiliary evidence.

Do not satisfy these blockers with aliases, bots, additional credentials, or technical factors controlled by the same person.
