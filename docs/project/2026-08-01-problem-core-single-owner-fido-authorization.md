---
summary: "Tier 1 problem brief for honest single-owner, hardware-authenticated DSPx Core release authorization without fake quorum or publication authority."
read_when:
  - "Reviewing the problem that Decision 96 and its single-owner FIDO authorization RFC are intended to solve."
  - "Checking the Tier 1 artifact chain before recording the Core single-owner authorization ADR."
type: "problem_brief"
---

# Problem Brief — Core single-owner FIDO authorization

## Status and authority

This is the Tier 1 trigger/problem artifact for Decision 96. AK Decision 96 owns current lifecycle truth. The RFC and ADR describe the proposal and accepted architecture; they do not independently authorize a release, enable an owner policy, or publish a package.

## Trigger

DSPx has one real owner, `tryingET` / GitHub user ID `260287438`. Core evidence signing and custody are live, but exact-wheel release authorization remains a separate authority boundary. The historical 2-of-3 owner-policy shape is deliberately disabled because multiple accounts, roles, or credentials controlled by one human do not create independent principals or judgment.

The project therefore needs an authorization design that can:

- name the one real principal honestly;
- authenticate one exact, short-lived payload with a hardware-backed FIDO SSH key requiring user presence and verification;
- bind approval to immutable Git/AK-selected policy lineage and current release evidence;
- consume one nonce durably and fail closed under replay, expiry, revocation, artifact substitution, or ledger redirection;
- preserve a hard separation between exact-wheel release authority and package publication.

## Problem statement

Without an accepted explicit single-owner model, DSPx must choose between two unacceptable states:

1. retain a disabled release-authorization path indefinitely even when evidence and custody are valid; or
2. pretend that aliases, recovery credentials, technical checks, or repeated actions by the same owner constitute an independent quorum.

The architecture must instead acknowledge concentration risk while making the technical authorization conjunction exact and auditable. A valid owner signature alone is insufficient: authorization also depends on current immutable policy selectors, current denylist and kill-switch state, exact signed evidence, clean source identity, paired custody, trusted time, and durable single-use consumption.

## Evidence that this is not local noise

- The original owner policy remains disabled because hardware-backed approval and the trusted consumer path were incomplete.
- Initial structured review required explicit SSHSIG UP/UV enforcement, immutable selector lineage, durable nonce consumption, and independent evidence derivation.
- A fresh follow-up review rejected commit `5f03e1b4` because mutable artifact originals could be reopened across verification seams and SQLite operations could reconnect through a replaceable path.
- Commit `2839e8fcae8191667db5e2dae953af4f8dc4d27a` repaired both seams with one-read owner-only staging, a retained verified ledger connection/identity, in-transaction schema checks, and deterministic replacement tests.
- The repair passed 26 focused consumer tests, the 94-test authorization/signing/custody/workflow set, Ruff, workflow contracts, and pre-push validation. The final structured review found zero blocker/high findings in the repaired scope.

## Why this is Tier 1

This decision changes the durable boundary among human authority, authentication, immutable policy selection, release evidence, replay state, and future exact-wheel authorization. It also records an explicit concentration-risk posture and constrains later rollout. Those are architecture and governance commitments, not a local implementation detail.

## Decision requested

Decide whether DSPx should adopt the RFC's explicit concentrated single-owner model with:

- one named human principal;
- FIDO ED25519-SK SSHSIG authentication with signed UP+UV requirements;
- full immutable trust- and owner-selector binding to accepted AK authority;
- one coherent staged artifact/signature generation per attempt;
- a crash-safe, path-identity-bound nonce ledger;
- a non-publishing consumer and separate future activation ceremony.

## Non-goals and guardrails

This decision does **not**:

- create independent quorum;
- enable owner policy v002 or create an enabled successor;
- perform a PIN/biometric signing ceremony;
- authorize `release_authority=true` in the current shadow consumer;
- authorize package publication or sdist support;
- prove payload inspection, host integrity, authenticator model/non-exportability, GitHub identity, or independent judgment;
- unblock post-ADR rollout without the required implementation and validation/rollout/rollback artifacts.

## Artifact chain

- Evidence: `docs/project/2026-08-01-core-single-owner-fido-shadow-repair.md`
- RFC: `docs/rfc/RFC-DSPX-CORE-20260731-single-owner-fido-authorization.md`
- Prior review attempts:
  - `docs/project/2026-08-01-review-core-single-owner-fido-authorization.md`
  - `docs/project/2026-08-01-review-core-single-owner-fido-authorization-followup.md`
- Final review closure: `docs/project/2026-08-01-followup-review-final-core-single-owner-fido-authorization.md`
- ADR: `docs/adr/20260731-core-single-owner-fido-authorization.md`
