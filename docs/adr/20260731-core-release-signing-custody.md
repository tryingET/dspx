---
summary: "Adopt exact Sigstore keyless Core wheel-evidence signing, separate 2-of-3 owner authorization, and bounded public GitHub Actions evidence custody."
read_when:
  - "You are implementing or verifying Core signing, release authorization, public CI evidence, or revocation policy."
  - "You are evaluating AK-4125, AK-4126, or the conditions that would trigger AK-4137."
type: "reference"
system4d:
  container:
    boundary: "Durable Core evidence-authenticity, owner-authorization, and public CI custody decision."
    edges:
      - "docs/rfc/RFC-DSPX-CORE-20260731-signing-custody.md"
      - "docs/project/2026-07-31-review-core-release-signing-custody-many-greats.md"
      - "docs/project/2026-07-31-core-release-signing-custody-implementation-plan.md"
  compass:
    driver: "Authenticate and disclose exact Core evidence without granting package release authority by implication."
    outcome: "One enforceable boundary for workload identity, subjects, current policy, threshold approval, and time-bounded evidence custody."
  engine:
    invariants:
      - "Workload authenticity and owner release authorization are separate predicates."
      - "The Core wheel is the only supported signed release subject in v1."
      - "Public CI evidence is non-confidential and does not authorize package publication."
      - "Release use requires current policy and currently available evidence plus receipt artifacts."
  fog:
    risks:
      - "GitHub/Sigstore identity or provider semantics may drift."
      - "Public evidence may disclose data if pre-upload validation fails."
      - "An unbound owner roster may be mistaken for release readiness."
---

# ADR 20260731 — Core Release Signing and CI Custody

## Status

- accepted
- date: 2026-07-31
- owner: DSPx release/governance owner
- reviewers: operator; governed `many-of-the-greats` review
- AK decision: `#88 Adopt exact keyless Core evidence signing and bounded public CI custody`
- related_docs:
  - `docs/project/2026-07-31-problem-core-release-signing-custody.md`
  - `docs/rfc/RFC-DSPX-CORE-20260731-signing-custody.md`
  - `docs/project/2026-07-31-review-core-release-signing-custody-attempt-1.md`
  - `docs/project/2026-07-31-review-core-release-signing-custody-attempt-2.md`
  - `docs/project/2026-07-31-review-core-release-signing-custody-attempt-3.md`
  - `docs/project/2026-07-31-review-core-release-signing-custody-many-greats.md`
  - `docs/project/2026-07-31-core-release-signing-custody-implementation-plan.md`
  - `docs/project/developer_workflow.md`
  - `docs/project/product-posture.md`

## Executive summary

DSPx adopts exact Sigstore keyless signing for Core wheel evidence from a dedicated protected workflow in public repository `tryingET/dspx`. One exact workload signature authenticates evidence. A separate, initially unbound 2-of-3 owner roster authorizes a future release. The wheel is the only supported signed subject; the sdist remains explicitly unsupported auxiliary evidence. Strictly non-secret evidence and a signed custody receipt may be disclosed through public GitHub Actions artifacts for 14 or 90 days. Package publication, release readiness, sdist support, and permanent archival custody remain unauthorized.

## Context

The repo already proves exact-wheel installation, payload identity, two SBOM scopes, local release-evidence envelopes, and optional local no-replace bundles. It did not have owner-authorized signer identity, revocation, threshold, CI disclosure, retention, deletion, or receipt policy.

The first three governed review attempts returned `revise_rfc`. Revision 4 closed exact Fulcio certificate mapping, fresh-live current-policy resolution, public-provider semantics, signed receipt retention, and current availability. The controlling review returned `ready_for_adr`. The operator accepted the recommendations and explicitly authorized creation of public repository `tryingET/dspx`.

## Decision drivers

- eliminate long-lived CI signing keys;
- authenticate one exact workflow and source state;
- keep machine authenticity separate from human release authority;
- sign only subjects backed by exact supported-install evidence;
- make public evidence disclosure explicit and non-secret;
- preserve current-policy revocation and anti-rollback truth;
- reject stale or deleted custody at release-use time;
- keep AK as decision and transition authority.

## Decision

### 1. Exact keyless workload identity

The trusted v1 workflow is:

- repository: `tryingET/dspx`, numeric ID `1318473695`;
- owner: `tryingET`, numeric ID `260287438`;
- workflow: `.github/workflows/core-release-evidence.yml@refs/heads/main`;
- trigger: `workflow_dispatch`;
- environment: `core-release-evidence`;
- runner: GitHub-hosted;
- OIDC issuer: `https://token.actions.githubusercontent.com`.

Offline verification uses the verified Fulcio certificate/Sigstore bundle. It checks URI SAN `2.5.29.17` and generic Sigstore OIDs `1.3.6.1.4.1.57264.1.8` through `.1.24` exactly as defined in RFC revision 4. Build Signer and Build Config URI/digest equality forbids reusable-workflow delegation. Source commit, run identity, repository/owner numeric IDs, public visibility, environment, trigger, workflow ref, and workflow digest must agree.

The workflow uses least privilege, immutable action revisions, and no package-publication permission. Signing stays disabled until protected `main` and the environment exist.

### 2. Subject and evidence scope

- `subject[]` contains exactly one Core wheel and SHA-256 digest.
- The installed proof, v3 envelope, two SBOMs, source state, manifest, and sdist digest live in `auxiliary_evidence[]` with exact roles and digests.
- The sdist role is `unsigned_unsupported_distribution_evidence`.
- The sdist cannot become a subject without AK-4137 completion and another owner decision.

### 3. Separate release authorization

Authenticity requires one exact workload signature. Release authorization requires 2-of-3 distinct approvals from roster `dspx-core-release-owners-v1`:

1. DSPx release/governance owner;
2. Softwareco security owner;
3. Softwareco delivery owner.

The roster is not populated by this ADR. Each role must later bind to one distinct authenticated principal through an owner-authorized AK artifact. Approvals bind the exact wheel, manifest, signed statement, source commit, version, policy/roster versions, authority reference, and 72-hour expiry. Duplicate principals, missing bindings, drift, expiry, or withdrawal keep release authority false.

### 4. Current trust policy and revocation

Immutable policies live at `governance/release-signing/trust-policy-vNNN.json`. Canonical selector evidence uses:

`dspx-core-policy-selector-v1:git:<commit>:<path>:<blob-oid>:<file-sha256>`

Release-use verification freshly resolves all accepted repo-scoped selector decisions from live AK, requires one complete gapless monotonic supersession chain and unique tip, then verifies the exact Git blob. Saved AK output cannot prove freshness. Offline verification may report creation-policy validity only. Release use requires both creation-policy and current-policy validity; unavailable or ambiguous currentness fails closed.

Current deny entries invalidate affected runs, commits, statements, or manifests. Revocation is append-only policy, not artifact deletion. Compromised evidence is rebuilt and re-signed rather than overwritten.

### 5. Public bounded CI evidence custody

Validated non-secret evidence may be uploaded from the exact workflow as public GitHub Actions v4 artifacts:

- ordinary trusted run: 14 days;
- manually environment-approved release candidate: 90 days.

Repository/provider retention caps are preflighted. The bundle uses a strict member allowlist and secret-shaped-content rejection. It contains no credentials, raw environments, private prompts, local databases, or unrelated logs.

Other workflows may upload ordinary artifacts. Trust comes only from the exact signed custody receipt, never a name prefix. GitHub-authenticated users with public-repository read access may download the evidence; no confidentiality is promised. This disclosure is evidence publication, not package publication or release authority.

### 6. Signed custody receipt and current availability

After evidence upload, the same exact workload signs `dspx-core-ci-custody-receipt-v1` over artifact/provider identity, evidence and statement digests, repository/workflow/run identity, policy, visibility, retention, timestamps, and explicit non-authority flags. The receipt is a separate artifact with matching retention and workflow association. Before release authorization, its digest and custody facts must be attached to AK evidence for the exact release task.

Every release-use evaluation freshly confirms that both evidence and receipt artifacts exist, are downloadable, match provider digests, and are unexpired. Confirmed deletion/expiry or indeterminate provider observation ends current release-use custody while preserving historical facts.

## Alternatives considered

### Long-lived organizational signing key

Rejected for v1. It creates secret custody, rotation, and recovery burdens and weakens exact workload attribution.

### Keyless signature as release approval

Rejected. A workflow can authenticate evidence but cannot replace owner authorization.

### Wheel and sdist as co-subjects

Rejected. Exact-sdist install behavior is not proven or supported.

### Zero retention

Rejected for current operations because it prevents bounded inspection and incident response.

### Independent private/WORM custody

Deferred. It dominates for confidential or permanent release archives but requires another owner decision and infrastructure boundary.

## Consequences

### Positive

- Exact workload and repository identity are machine-checkable.
- No long-lived signing secret is required.
- Owner authority cannot be inferred from a CI signature.
- Sdist support cannot arise by implication.
- Public disclosure and its risks are explicit.
- Revoked, stale, deleted, or ambiguous evidence fails closed.

### Costs

- The verifier and workflow must implement a detailed certificate/policy/receipt contract.
- Public evidence requires aggressive content validation.
- Live AK and GitHub availability are required for release-use evaluation.
- Three role bindings and two distinct approvals remain prerequisites.

### Risks and mitigations

- Provider or certificate schema drift: disable signing until a new owner-accepted policy.
- Public data leakage: fail before upload, delete if observed, and deny the receipt/policy use.
- Local anti-rollback checkpoint corruption: define atomic/integrity-tested persistence before release use.
- Receipt artifact resolution ambiguity: persist or deterministically resolve the exact receipt artifact ID.

## Migration / rollout

Follow `docs/project/2026-07-31-core-release-signing-custody-implementation-plan.md`.

The first implementation stage is offline schemas, verification, policy selection, and adversarial tests. GitHub signing/upload remains disabled until protections, environment, retention, and roster preflight pass. Live dogfood is evidence-only and cannot release a package.

Rollback disables signing/upload, advances deny policy where necessary, preserves historical references, and keeps package release false.

## Architecture fitness functions / validation

- every Fulcio field and signed predicate value has positive and negative fixtures;
- exactly one wheel subject is accepted;
- the sdist is rejected as subject;
- selector forks, rollback, stale/offline authority, and blob drift fail closed;
- missing/duplicate roster bindings and approvals fail closed;
- public bundle allowlist and secret-shaped-content gates fail before upload;
- receipt upload, retention, deletion, expiry, digest drift, and effect-indeterminate cases are covered;
- signature/custody never satisfies release approval in tests or runtime state.

## Follow-up decisions / open questions

- Populate the three exact roster principal bindings through a separate owner-authorized artifact.
- Decide independent durable custody only if permanent or confidential evidence becomes necessary.
- Decide sdist support only after AK-4137's trigger and proof.
- Decide package publication separately; this ADR does not authorize it.

## Supersession

- supersedes: none
- superseded_by: none
