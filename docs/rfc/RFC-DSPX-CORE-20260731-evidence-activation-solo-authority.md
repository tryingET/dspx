---
summary: "Propose activating non-authoritative Core evidence custody for a solo operator without fabricating a release-owner quorum."
read_when:
  - "You are enabling Core evidence signing/custody or designing a future release-authorization consumer."
type: "rfc"
---

# RFC — Core Evidence Activation Under Solo Authority

## Question

May DSPx activate its exact keyless evidence-signing and bounded public-custody workflow while the operator is solo, the three-owner roster is deliberately unbound, and no owner-approval authentication adapter exists?

## Context

Decision 88 correctly separates workload authenticity from owner release authorization. Its rollout text nevertheless couples the first evidence-only dogfood to three distinct owner bindings. The current operator cannot truthfully supply three independent principals and explicitly declined to choose an owner-authentication mechanism now. Populating aliases, bots, accounts, or keys controlled by one person would create syntactic plurality rather than independent judgment.

The implemented workflow has no package-publication permission and every statement, receipt, and verifier keeps `release_authority=false`, `package_publication=false`, and `sdist_supported=false`.

## Many-of-the-greats confrontation

### Constitutional quorum

The 2-of-3 roster is the release constitution. Three genuinely distinct principals protect against unilateral intent, compromised credentials, and role collapse. A solo operator cannot satisfy it, and technical factors cannot be counted as people.

### Supply-chain empiricism

A live Sigstore signature and provider-observed custody receipt establish valuable empirical facts even when release authority is absent. Blocking evidence authenticity until an organization has three owners withholds a security control that does not itself release anything.

### Solo-builder operationalism

A solo project needs executable paths. The strongest lawful path is to dogfood the negative authorization state: authenticate and retain evidence, prove the future consumer remains blocked, and refuse fake quorum.

## Decision proposal

Use progressive assurance with two strictly separate planes.

### Evidence plane — may activate

The dedicated workflow may:

- validate immutable policy v1 and its Git-bound selector;
- validate the unbound roster's exact schema and disabled posture without requiring bindings;
- run only from protected `main` in `core-release-evidence`;
- keyless-sign the exact wheel-evidence statement;
- upload bounded public non-secret evidence and a signed custody receipt;
- verify exact workload identity and paired current availability;
- retain 14-day ordinary evidence and 90-day manually gated evidence;
- leave every release/publication/readiness claim false.

The 90-day required reviewer may be the same solo GitHub principal. That is an explicit same-principal deliberate-action control, not independent review or quorum.

### Release-authority plane — remains unavailable

No release-authorization consumer may return authority until a later accepted decision selects one of:

1. three genuinely independent owner principals and an authenticated 2-of-3 adapter; or
2. an explicit solo-owner policy version with one human principal, concentrated-risk acceptance, hardware-backed exact-payload authorization, revocation, replay protection, and technical controls described as a conjunction rather than a quorum.

Policy v1 and its accepted selector remain immutable. A future solo-owner policy must be a monotonic successor, never an edit or reinterpretation of v1.

## Future consumer boundary

A future consumer must combine, in order:

1. fresh current-policy resolution and deny checks;
2. exact Sigstore statement verification;
3. exact signed custody-receipt verification;
4. fresh paired evidence/receipt availability;
5. owner-registry and approval authentication from the later-selected adapter;
6. exact artifact-bound authorization with replay and expiry controls.

Until step 5 exists and passes, its only lawful result is `release_authority=false`. Package publication remains a separate owner surface even after authorization.

## Rollout

1. Remove only the evidence workflow's `--require-bindings` flag; retain exact roster validation.
2. Add a static contract test proving the workflow does not invoke release-approval evaluation and continues to deny publication.
3. Push the exact reviewed commit.
4. Configure protected environment and bounded retention.
5. Enable the repository variable only after preflight.
6. Run one 14-day canary, then one same-principal-reviewer-gated 90-day canary.
7. Stop and disable on any failed, ambiguous, or unobservable effect.
8. Record run, artifact, receipt, digest, expiry, and non-authority facts in AK and repo dogfood evidence.

## Rollback

Delete the enable variable, preserve run history, deny compromised identities through a later accepted policy, and never retry an effect-indeterminate upload mechanically.

## Nonclaims

This proposal does not bind release owners, authenticate human approvals, authorize a Core release, publish a package, support the sdist, create independent review, or provide permanent custody.
