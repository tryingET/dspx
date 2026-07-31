---
summary: "Activate exact Core evidence signing/custody independently from unavailable release-owner quorum."
read_when:
  - "You are enabling or verifying the Core release-evidence workflow under solo operation."
type: "decision"
---

# ADR 20260731 — Core Evidence Activation Under Solo Authority

## Status

- accepted
- date: 2026-07-31
- owner: DSPx operator
- AK decision: `#91 Activate Core evidence custody without fabricating owner quorum`
- reviewed artifact: `docs/rfc/RFC-DSPX-CORE-20260731-evidence-activation-solo-authority.md`
- review: `docs/project/2026-07-31-review-core-evidence-activation-solo-authority.md`

## Context

Decision 88 accepted exact keyless Core evidence signing, bounded public custody, and a separate initially unbound 2-of-3 release-owner roster. Its rollout coupled live evidence dogfood to roster bindings. The operator is currently solo and cannot truthfully supply three independent principals or an owner-authentication adapter.

The workflow has no package-publication permission. Its statements, receipts, and verifiers explicitly deny release authority and package publication.

## Decision

Activate the evidence plane independently from the release-authority plane.

The workflow validates trust policy, selector, and the exact unbound disabled roster, but does not require roster bindings before producing evidence. It may sign and retain exact public non-secret Core evidence for 14 days, or for 90 days behind a GitHub environment deliberate-action gate.

The same solo GitHub user may operate the 90-day environment gate. This is not independent review, an owner quorum, or release authorization.

The release-authority plane remains unavailable. No fake bindings are created. No future consumer may return release authority until a later accepted decision selects and implements an authenticated owner model. Policy v1 remains immutable. A possible solo-owner policy must be a new monotonic version with explicit concentration risk; multiple technical factors remain one human principal.

## Consequences

- Live Sigstore/provider dogfood can establish evidence authenticity and current custody.
- Empty roster and missing owner-auth adapter continue to block release authority.
- Live artifacts remain public, time-bounded, wheel-only evidence.
- Package publication remains a separate unauthorized transition.
- The enable variable is an operational switch, not authority.

## Fitness functions

- static workflow contract proves roster validation remains but `--require-bindings` is absent;
- workflow permissions remain `contents: read`, `actions: read`, and `id-token: write` only;
- no publish action or registry credential exists;
- live runs verify exact DSSE, certificate identity, receipt, and paired availability;
- failed or indeterminate effects disable the switch before any retry;
- all outputs preserve false release/publication/sdist claims.

## Rollback

Delete `DSPX_CORE_RELEASE_SIGNING_ENABLED`, preserve historical evidence, advance deny policy if compromise is observed, and do not erase or mechanically retry ambiguous runs.

## Supersession

This decision narrows Decision 88's rollout prerequisite for the evidence plane only. It does not supersede Decision 88's release threshold, policy v1, selector v1, subject scope, or publication boundary.
