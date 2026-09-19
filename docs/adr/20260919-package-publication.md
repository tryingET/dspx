---
summary: "Accept an independently reviewed protected-environment exact-artifact publisher for DSPx Core/Forge, separate from historical FIDO shadow evidence."
read_when:
  - "Implementing or authorizing DSPx Core/Forge package publication."
type: "reference"
---

# ADR — Core/Forge package publication

AK Decision 162 records runtime status. Owner intent is the 2026-09-19 explicit
selection of DSPx GitHub+PyPI release, custom Apache-based licensing with the
existing restrictive rider, and owner approval through protected GitHub `pypi`
environment rather than activating the FIDO authority-true path first.

Accept the boundary and sequencing in
[the reviewed RFC](../rfc/20260919-package-publication.md), after the
[independent policy review](../project/2026-09-19-release-publication-review.md)
closed both design blockers. Implementation remains subject to code review and
exact-source validation.

### Implementation correction: distinct pending publisher identities

The operator's PyPI registration attempt exposed a provider constraint: two pending
project names cannot share one publisher identity. AK5795 therefore separates the
original `pypi` job into `publish-core` / `pypi-core` and `publish-forge` /
`pypi-forge`, still using owner `tryingET`, repo `dspx`, workflow `release.yml`.
Both environments retain the sole owner reviewer, main-only branch restriction
and disabled administrator bypass. The same manifest is reviewed twice, first
for Core and then for Forge; this adds a gate, never bypasses approval or creates
independent quorum. Forge rechecks Core's exact registry bytes before uploading.
The binding contract below applies to each environment. The old waiting run was
cancelled before any publisher ran. No package version/dependency/runtime changed.

## Binding publication contract

- Exact source and parent CI clearance plus host-native AK scope evidence precede
  approval. Existing evidence nonclaims remain unchanged.
- Build once; test the exact Core/Forge wheels and sdists in fresh environments,
  including normal base dependency resolution on advertised Python versions.
- The protected single-owner environment approves one displayed source/manifest
  and its four distribution hashes. OIDC publishing identity is not that approval.
- Writers revalidate same-run immutable artifact ID, manifest digest and complete
  inventory. They neither install nor execute candidate packages. Readback jobs
  have no OIDC or repository-write permission.
- PyPI completion requires exact filename/size/hash inventory, no unexpected
  yanks, pinned installed versions and registry-derived distribution-byte proof.
- Publish Core before Forge; then verify installation; create complete draft
  GitHub releases and verify before publishing the same bytes. Verify final tags
  and assets; never overwrite published bytes regardless of repository settings.
- Unknown or partial effects remain explicit. Reconcile original bytes before
  resuming; retention expiry does not authorize a silent rebuild. No automatic
  delete, unpublish, force-tag, or blind upload retries.

## What remains unchanged

Decisions 88, 96 and 99, their selectors/policies, FIDO consumer and historical
receipts are immutable. Their authority/publication false claims stay false. This
ADR accepts a separate package-publication approval channel; it does not activate
the FIDO consumer or claim independent quorum. It grants no DSPy-program production
activation, semantic-quality result, live-provider proof, or global consumer pin
upgrade. Existing source-index-only optional extras remain separately documented.

## Rollout and rollback

AK5785 lands reviewed infrastructure first without a version bump or upload. A
separate versioned release task requires green parent/source CI, current native
scope proof, PyPI account setup and final exact-manifest owner approval. Stop
future dispatch on regression; preserve artifacts and failure receipts. Address a
bad public version through separately authorized forward correction or yank,
never replacement of history. The owner's account retains PyPI and GitHub recovery.
