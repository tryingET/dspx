---
summary: "Install DSPx packages and operate the owner-approved exact-artifact GitHub/PyPI publisher."
read_when:
  - "Installing DSPx Core or Forge outside the workspace."
  - "Preparing, approving, or recovering a paired package release."
type: "guide"
---

# DSPx package releases

## Installation and compatibility

DSPx Core provides `dspx` and `dspx-server`; Forge adds `dspx-forge` and depends
on Core. Python 3.13 and 3.14 are the advertised base-package versions. Releases
are alpha: test upgrades in a fresh environment and retain your previous pin.

Once 0.3.0 is published and registry readback passes, install with:

```sh
python -m pip install 'dspx-core==0.3.0'
dspx --help
# Optional application; resolves its compatible Core dependency from PyPI:
python -m pip install 'dspx-forge==0.3.0'
dspx-forge --help
```

These commands are not a statement that publication has already happened. Check
[PyPI Core](https://pypi.org/project/dspx-core/) and
[PyPI Forge](https://pypi.org/project/dspx-forge/) for available versions and
[GitHub releases](https://github.com/tryingET/dspx/releases) for exact assets.
Base installation does not install optional embedding/GPU/Postgres extras or
establish live-provider quality. The `oracle-embeddings` extra pins a CPU torch
build from `https://download.pytorch.org/whl/cpu`; PyPI alone cannot resolve that
extra. Prefer an explicit named torch index in an application dependency manager,
not an unrestricted extra-index fallback. Optional extras are not release smoke
coverage.

Licensing is custom Apache-based with an additional restrictive AI rider, named
`LicenseRef-Apache-2.0-with-AI-Rider`. Read the full
[LICENSE](https://github.com/tryingET/dspx/blob/main/LICENSE) before redistribution
or use. This is not an unmodified Apache-2.0 or OSI-approved license claim.
Third-party dependencies retain their own terms.

## Prepare and approve

Authority: AK Decision 162 and the
[publication ADR](../adr/20260919-package-publication.md). The CI evidence policy
is [ADR 20260918](../adr/20260918-ci-evidence-clearance.md); the local hermetic
full gate remains separate, not silently counted as run.

1. Land publisher infrastructure under AK5785, then wait for first-attempt green
   push CI. In a separate release task, update both package versions, Forge's Core
   dependency range, lockfile, changelog and any runtime version contract.
2. Push the exact release commit to protected `main`, wait for its first-attempt
   green CI, run the native AK task-scope check at that SHA and record AK evidence.
3. Register PyPI pending publishers with owner `tryingET`, repository `dspx`,
   workflow `release.yml`: use environment **`pypi-core` for `dspx-core`** and
   **`pypi-forge` for `dspx-forge`**. PyPI rejects two pending project names with
   an identical publisher identity; the environment distinguishes these identities.
   Replace any old pending registration using `pypi` before registering the corrected
   identity. No long-lived PyPI token is needed. Name availability is not ownership.
4. Ensure both GitHub environments require sole user `tryingET` (260287438),
   permits only branch `main` and has administrator bypass disabled. Self-review
   is permitted because this is explicitly a single-owner release decision.
5. Dispatch **Publish approved DSPx packages** on `main` with the committed
   version and native scope evidence reference `AK-evidence:<id>`.
6. The read-only candidate job builds once and displays the source SHA, manifest
   SHA-256 and four file hashes. Read-only Python 3.13/3.14 jobs separately install
   wheels and sdists with ordinary base dependency resolution.
7. The owner reviews those exact hashes and AK evidence, then approves `pypi-core`
   in the run UI. After Core publishes, approve `pypi-forge` against the same
   manifest. These are sequential approvals, not independent quorum. Agents must
   not approve or bypass either gate on the owner's behalf.
8. Separate OIDC writers publish Core then Forge. Forge rechecks Core's registry
   bytes before uploading its own files. Subsequent read-only jobs
   install pinned versions from PyPI. Only then does the GitHub writer create
   complete drafts with the same bytes and publish them. Verify both channels and
   record URLs, source, manifest digest and final installation results in AK.

No candidate package code executes in publishing jobs. Registry hashes and
artifact manifests are verified without installing distributions there. The
GitHub read-only preflight can see published releases and tags, but cannot promise
visibility of drafts; inspect drafts with maintainer credentials before dispatch.
The final writer independently checks conflicts. Repository release immutability
is reported when observable, never assumed. Published bytes are never overwritten.

## Failure and recovery

Treat each channel independently: publication is not an atomic operation across
Core, Forge and GitHub. A failed upload may have partially succeeded. Read-only
registry reconciliation runs even after a failed upload when staging succeeded;
the failed upload still leaves the job failed. Do not automatically retry writes.

Keep the original same-run candidate artifact and manifest (90-day retention).
Reconcile registry names, sizes, digests and yanks plus GitHub draft/tag/assets
before an explicit resume. Rerun only failed publication/readback jobs, never a
successful candidate build after a partial upload. Obtain fresh environment
approval. Missing or expired original artifacts block recovery; rebuilding does
not authorize different bytes under the same version. No force tags, asset
replacement, deletion or automatic unpublishing is supported.

For a bad public version, stop new dispatches and use separately owner-authorized
yanking/advisories or a forward patch. Downgrade only to a previously tested pin;
this release process does not prove persisted data or generated artifacts are
backward-compatible. Preserve original receipts and consult the relevant data
contract before reverting applications that have already written state.
