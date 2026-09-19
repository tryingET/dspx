---
summary: "Propose a protected-environment, exact-artifact Core/Forge publisher for the first DSPx PyPI release."
read_when:
  - "Reviewing the first Core/Forge PyPI publication boundary or its implementation."
type: "rfc"
---

# DSPx paired package publication

## Owner request and scope

On 2026-09-19 the operator selected DSPx Core/Forge (not engineering-core), GitHub
release artifacts plus PyPI trusted publishing, and protected GitHub `pypi`
environment approval after inspecting exact artifact hashes. They selected
Apache-2.0 while retaining the existing restrictive rider from their other repos,
and will register pending trusted publishers without sharing a token.

The rider was found in `tryingET/pi-extensions` LICENSE at
`3ac629343fa9c2c14810cf4c796964b16a76fe0e` and matching Compass-C LICENSE. Preserve
it verbatim. This is custom, source-available Apache-based licensing, not
unmodified Apache-2.0 or an OSI-approved license claim. Use
`LicenseRef-Apache-2.0-with-AI-Rider`, include the full base license and rider in
both wheels/sdists, and retain third-party licensing separately. Legal
enforceability is not assessed by this implementation.

AK5785 prepares infrastructure at the current package versions. A separate
release-version task bumps both packages to 0.3.0, updates Forge's compatible Core
range and uv.lock, and obtains exact-commit CI clearance after the infrastructure
parent is green. This is a paired first release, not a commitment to perpetual
lockstep versioning. No provider/model execution or production activation is in
scope. No upload occurs before exact-manifest owner approval.

## Decision proposed

1. Introduce `.github/workflows/release.yml`, manually dispatched on protected
   `main` for its exact `github.sha`. Build and validation jobs are read-only;
   registry upload has a separate protected-environment job. Serialize releases
   with cancellation disabled. Do not give PR workflows publishing authority.
2. Verify successful first-attempt push-to-main `CI` evidence for the exact source
   commit and its first parent, including all required jobs. Native AK scope
   evidence for the release commit is separately recorded by the operator-side
   task and referenced in the dispatch. CI evidence is not owner permission.
3. Build once through the existing package journey, retain exactly Core/Forge
   wheel+sdist files, and bind their names, sizes, SHA-256, package versions,
   compatibility bounds and source commit in one manifest. Keep the existing Core
   evidence nonclaims unchanged; it is not a publication approval.
4. Install the exact retained wheels and sdists outside the checkout using normal
   registry dependency resolution; smoke Core alone, then Core+Forge. Check
   Python 3.13 and 3.14 because metadata advertises both. Failure blocks upload.
   These are base-package checks; embedding-model, GPU, Postgres and live-provider
   behavior are not claimed. Document the optional CPU torch index requirement.
5. Store the candidate files as same-run Actions artifacts, publish their manifest
   hashes in the job summary, and hand their immutable artifact ID and manifest
   digest to downstream jobs. Retain original candidate artifacts for 90 days;
   expiry or missing bytes blocks recovery, never authorizes a silent rebuild.
   No rebuild after artifact testing.
6. Require `pypi` environment approval by GitHub user `tryingET` (260287438), with
   protected-branch restriction. The owner reviews the run/source, all four file
   hashes, and native AK scope evidence before approving. This is explicitly a
   concentrated single-owner decision, not independent quorum or FIDO proof.
7. Publish Core before Forge using SHA-pinned PyPA trusted publishing with
   job-level `id-token: write`, no registry token/password, and PEP 740
   attestations. Reconcile registry file hashes before upload: identical files
   may be retained; different bytes under an existing name/version fail closed.
   Stage only missing expected files. Reconcile again after each package upload.
   Require exact per-version registry inventory equality (no additional files),
   matching digests/sizes and all files unyanked; unknown observations fail closed.
8. Verify ordinary installation from PyPI, not just a local wheel path. Use only
   the selected public registry for base installation. A failed readback leaves
   the release partial/unverified; do not call it complete or retry uploads
   blindly. Pin both approved versions and record installed versions and downloaded
   distribution hashes. Use separate fresh environments for wheel versus sdist
   candidate tests so wheels cannot mask source-build failure. Only read-only
   registry visibility polling is automatic.
9. Publish component GitHub releases from the same tested bytes. Create draft
   releases with all assets before publishing, verify asset/source identity, then
   publish; never depend on adding files after immutable release publication.
   Existing releases/tags must match the exact expected source and assets before
   a no-op can be accepted. Inspect repository release-immutability configuration
   and final published asset/tag identity. After an interrupted GitHub API write,
   read back the exact tag/release/assets before resuming; conflicting or unknown
   effects stop. Only missing assets in a matching draft may be completed.
   No unpublish, delete, force-tag or overwrite recovery.
10. Build, install and registry-install readback jobs have neither OIDC nor
    repository-write permissions. Only the protected registry publisher receives
    `id-token: write`. Only the GitHub release writer receives `contents: write`,
    and it depends on successful exact-manifest approval, registry publication and
    readback. Each writer verifies artifact ID, manifest digest and complete file
    inventory before mutation; neither executes candidate packages or installs
    their dependencies. Registry JSON/hash-only checks are safe in a writer job;
    package execution belongs in the separate read-only jobs.

## Relationship to previous authority

This proposes a new explicit package-publication channel for Core and Forge,
including sdists only after their new install checks pass. For this channel,
protected environment approval of the displayed exact manifest is the owner's
publication authorization. It replaces neither historical evidence nor its claim
meaning. Decisions 88/96/99 and their immutable files remain unchanged: the FIDO
consumer still returns authority/publication false and no old signature, receipt
or nonce is reused. This proposal does not activate that consumer's authority-true
path. Its separate approval mechanism must be accepted explicitly, not inferred
from the old shadow rollout or a green CI badge.

## Account and infrastructure setup

Register two PyPI pending publishers: project `dspx-core` / `dspx-forge`, owner
`tryingET`, repository `dspx`, workflow filename `release.yml`, environment `pypi`.
A 404 does not reserve a name. Registration needs the owner's authenticated PyPI
account; no bootstrap token is necessary. Create the matching GitHub environment
and read back its reviewer and branch protections. Do not approve it on behalf of
the operator. The environment is an actual permission gate, not an assertion in
a version-controlled JSON file.

## Validation and failure handling

Freeze tests for wrong source/version/filenames, missing/extra artifacts, digest
mismatch, license/rider absence, Forge bounds, failed/rerun/wrong-SHA CI, missing
shards, and conflicting/partial registry inventory. Review code independently,
including any changed CI gate-file hashes in the same commit. Run repo-declared
CI checks and the exact-source CI evidence contract; optional hermetic full-gate
execution remains separate.

Publication is not atomic across two packages and GitHub. Report each observed
terminal effect independently. Preserve the original artifacts and failures;
resume a failed publication job only after reconciling the unchanged artifact
manifest and obtaining fresh environment approval. Do not rebuild differing bytes
under an already-uploaded version. If the channel must be stopped, disable future
dispatch/publication; preserve tags, artifacts, receipts and historical failures.
A bad published version needs owner-directed deprecation/yank or a forward fix,
not hidden replacement.

## Alternatives

- Reuse raw token-based `just publish*`: rejected as the new normal path because it
  does not bind the tested bytes, source clearance or exact human approval.
- Complete the FIDO consumer's authority-true transition first: operator selected
  the simpler protected-environment package channel instead. Old claims remain
  false; no fake FIDO authorization is created.
- Introduce Release Please and publishing in one step: preparation automation can
  follow the first proven publisher. It is not permission to bypass uv lock/bounds
  reconciliation, and is not required to ship this explicit first release.
