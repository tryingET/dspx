---
summary: "Independent policy review of the new exact-artifact Core/Forge publication channel."
read_when:
  - "Checking design review for the first protected-environment PyPI/GitHub release."
type: "review"
---

# Package-publication policy review

AK Decision 162; preparation task AK5785. Reviewed artifact:
`docs/rfc/20260919-package-publication.md`.
Independent read-only reviewer: `dispatch-1789815584138`.

## First pass: revise

Two design blockers were identified:

1. Specify which jobs have OIDC/repository-write permissions and prevent package
   installation/execution in those privileged jobs.
2. Require exact registry inventory, matching digests/sizes, unyanked state,
   approved-version installation and downloaded-byte identity, rather than only
   matching expected filenames.

Additional conditions concerned original-artifact retention, separate fresh
wheel/sdist environments, GitHub draft-first immutability and uncertain-write
reconciliation.

## Revised policy: ready_for_adr

The reviewer read the entire revised RFC and found both blockers closed, with no
remaining design blocker. Decision sections 5 and 7–10 now state these controls.
Historical FIDO false claims and signatures/nonces remain unchanged; the new
publication channel is distinct, not retroactive activation. Custom licensing is
explicit and does not claim standard Apache-2.0 or OSI approval.

Nonblocking follow-through: inspect GitHub release-immutability configuration and
report it without silently asserting it is enabled. Never overwrite already
published bytes even if the repository does not enforce immutability. Test
permission boundaries, artifact substitution, extra/yanked registry files,
wrong-version readback and interrupted-write recovery during implementation.

This is policy review only. No implementation tests, publication, external
configuration changes, PyPI ownership verification or legal enforceability
assessment were performed by the reviewer. It grants no publication authorization.

## Implementation review and confirmation

Independent reviewer `dispatch-1789817600191` inspected the implementation and
initially held landing for a stale package-check approval hash and missing direct
archive/CI/install/workflow tests. Added real archive fixtures and negative
contracts in `tests/test_release_publish_contracts.py`; registry/GitHub effect
state machines retain their separate mocked tests. The new tests exposed masked
registry failures through `tee`; explicit Bash pipefail now preserves those
failures, and read-only reconciliation also runs after failed uploads. The job
remains failed; no automatic write retry was introduced.

The reviewer confirmed both original landing blockers closed: 286 focused tests,
approval-hash check, focused Ruff and diff checks passed. No new blocker in the
bounded confirmation. Parent validation separately passed repo-wide `ci-quality`
(format, Ruff, ty, workflow contracts), native working-tree AK5785 scope, and
`just ci-package` with actual locked-dependency Core/Forge wheel installation.
Candidate sdists and ordinary unlocked Python 3.13/3.14 resolution still require
the release workflow, not the mocked install tests.

GitHub environment readback by the parent confirmed sole `tryingET` reviewer,
branch `main` only, and `can_admins_bypass=false`; the release clearance helper
requires those facts. Self-review remains intentionally permitted for this
single-owner policy. Read-only preflight cannot promise draft visibility; the
maintainer must inspect drafts before dispatch and the final writer rechecks.
Exact-source hosted CI, registry ownership and publication remain separate gates.
No version bump or upload is part of AK5785 infrastructure completion.

## Pending-publisher identity correction — AK5795

PyPI rejected the operator's second pending project because both used the same
owner/repository/workflow/environment tuple. `pypi-core` and `pypi-forge` now give
the two jobs distinct identities, with unchanged sole-owner/main-only/no-bypass
protections. The same manifest receives sequential Core and Forge approvals;
Forge independently rechecks Core registry bytes before staging its own files.
The old pending run 35442526631 was cancelled before upload; its successful wheel
and sdist installations on Python 3.13/3.14 remain evidence for its old source only.

Independent reviewer `dispatch-1789823290181` found no concrete blocker in the
bounded split: artifact custody, both approvals, permission isolation, Core
reverification and source/parent checks remain intact. This was static review,
not external configuration or publication approval. Parent verification passed
313 focused tests, repo `ci-quality`, native task scope and readback of both live
protected environments. New exact-source CI and release jobs are still required.
