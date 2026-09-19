---
summary: "Consumer-facing DSPx Core and Forge release changes, compatibility and limitations."
read_when:
  - "Upgrading DSPx packages or preparing release notes."
type: "reference"
---

# Changelog

## 0.3.0 — 2026-09-19

### Distribution

- Introduces the paired Core/Forge GitHub and PyPI distribution channel. Core
  provides `dspx` and `dspx-server`; optional Forge provides `dspx-forge`.
- Wheels and source distributions include the full custom Apache-based license
  and restrictive AI rider (`LicenseRef-Apache-2.0-with-AI-Rider`). This is not
  unmodified Apache-2.0 or an OSI-approved license. Review the license before use.
- The release manifest binds the source commit, package versions, four exact
  distribution hashes/sizes and the native AK scope evidence reference.
  Owner approval is separate from CI success and OIDC publishing identity.

### Runtime changes since Core 0.2.1

- Strengthens candidate-local receipt, replay, Oracle and generated-program
  evidence validation, including canonical manifest identities and complete
  readback-graph binding.
- Adds synthetic reader-intent integration and a bounded passage-pilot harness;
  these are not claims of real-book quality or production activation.
- Fixes generated-program import isolation and restores the hash-bound
  metric-honesty wrapper template used by optimization workflows.

### Compatibility and installation

- Requires Python `>=3.13,<3.15`. Forge 0.3.0 requires Core `>=0.3.0,<0.4.0`.
  This pre-1.0 minor release does not promise compatibility for internal APIs or
  historical experimental generated-program contracts. Keep validated prior pins
  when using those surfaces; do not treat older receipts as current approval.
- Base installation uses PyPI. The optional `oracle-embeddings` extra still needs
  the explicit CPU torch index; GPU, model, Postgres and live-provider paths are
  outside base-package release smoke coverage.
- The version-only release commit changes no runtime implementation or data
  schema. It publishes the preceding reviewed source; it is not a data migration.

### Validation limits and recovery

- Release clearance uses exact-source hosted CI, package smoke, native AK scope
  evidence and owner approval of exact artifact digests. The local hermetic
  `verify-full` gate was **not executed for this release**; no full-gate pass is
  inferred from hosted CI or historical receipts.
- The installed product journey is stub-backed plumbing proof. No live model,
  provider quality, semantic benchmark improvement, generated-program activation,
  independent approval quorum or historical FIDO activation is claimed.
- Publication is complete only after registry inventory/hash readback, fresh
  pinned PyPI installation and GitHub asset/tag verification. A workflow file or
  version bump alone is not evidence that this version is available.
- Keep original artifacts for interrupted-release recovery. Never replace public
  bytes or force tags. Bad releases require separately authorized advisories,
  yanks or a forward patch. Downgrade to a previously tested pin only after checking
  application data compatibility; automatic downgrade safety is not established.
