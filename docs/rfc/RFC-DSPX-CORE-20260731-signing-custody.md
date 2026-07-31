---
summary: "Propose exact keyless signing for Core wheel evidence plus bounded public GitHub Actions evidence custody, while keeping release authorization and package publication separate."
read_when:
  - "You are reviewing or implementing Core release signer verification or CI evidence custody."
  - "You are deciding whether the Core wheel or sdist is a supported signed release subject."
type: "reference"
system4d:
  container:
    boundary: "Proposal-stage contract for Core evidence signing and public CI evidence custody."
    edges:
      - "docs/project/2026-07-31-problem-core-release-signing-custody.md"
      - "docs/project/2026-07-31-review-core-release-signing-custody-many-greats.md"
      - "docs/adr/20260731-core-release-signing-custody.md"
  compass:
    driver: "Make Core evidence authentic and inspectable without granting package release authority."
    outcome: "An exact signer, subject, threshold, revocation, custody, retention, and failure-semantics contract."
  engine:
    invariants:
      - "Evidence authenticity does not imply release approval."
      - "Public CI evidence disclosure does not imply package publication or release authority."
      - "Only the exact Core wheel is initially a supported signed release subject."
      - "Ambiguous signing, upload, or deletion effects fail closed or remain effect-indeterminate."
  fog:
    risks:
      - "OIDC policy drift can admit the wrong workflow identity."
      - "Public CI evidence can leak data if pre-upload validation is incomplete."
      - "The sdist can become an implied supported subject through careless predicate design."
---

# RFC-DSPX-CORE-20260731 — Core Release Signing and CI Custody

## Status

- review, revision 4
- date: 2026-07-31
- owner: DSPx release/governance owner
- reviewers: operator; governed `many-of-the-greats` review
- decision_deadline: owner acceptance before AK-4125 or AK-4126 implementation
- related_docs:
  - `docs/project/2026-07-31-problem-core-release-signing-custody.md`
  - `docs/project/developer_workflow.md`
  - `docs/project/product-posture.md`
  - `docs/project/2026-07-31-review-core-release-signing-custody-many-greats.md`
  - `docs/adr/20260731-core-release-signing-custody.md`

## Executive summary

Adopt DSSE/in-toto evidence statements signed through Sigstore keyless workload identity from one exact protected GitHub Actions workflow. One workload signature authenticates evidence; a separately bound 2-of-3 owner roster governs release authorization. Retain validated, strictly non-secret evidence as publicly downloadable GitHub Actions v4 artifacts for 14 days on ordinary trusted runs and 90 days for manually approved release-candidate runs. Keep the Core wheel as the only supported release subject. Represent the sdist only in a dedicated non-subject auxiliary-evidence collection until AK-4137 is separately triggered and completed.

## Problem statement

DSPx can generate and validate a local Core release-evidence bundle, but it cannot currently prove that a trusted workload produced the evidence or retain the bundle in CI under an owner-approved disclosure and custody policy. The missing policy spans signer identity, key custody, exact subjects, revocation, threshold authorization, provider, visibility, retention, deletion, access, and package-publication boundaries.

Signing or uploading without this decision would invent owner policy. Conflating a valid build signature or public evidence artifact with package release approval would be a category error.

## Goals / non-goals

### Goals

- authenticate exact Core build evidence to one exact workload identity;
- avoid long-lived CI signing keys;
- separate workload authenticity from owner release authorization;
- publish non-secret CI evidence for bounded inspection and incident response;
- preserve exact subject/material distinctions;
- fail closed on identity, digest, inclusion, roster, access, or policy drift.

### Non-goals

- authorize package-registry or GitHub Release publication;
- declare release readiness;
- create permanent archival custody;
- declare the sdist a supported distribution;
- claim reproducible dependency resolution or external dependency-artifact provenance.

### Invariants that must not break

- AK remains task, decision, evidence-reference, and transition authority.
- Local bundle generation remains explicit and no-replace.
- A signature authenticates a predicate; it does not approve release.
- Public CI evidence disclosure is not package publication or consumer support.
- Secrets, credentials, raw environment dumps, and secret-shaped fixtures never enter uploaded bundles.

## Current state evidence

- `scripts/ci/package-check.sh` can produce a local v3 release bundle.
- The bundle binds the exact wheel, sdist, installed proof, evidence envelope, two SBOMs, source state, and manifest.
- `docs/project/developer_workflow.md` states that signing, CI custody, package publication, readiness, and authority remain false.
- AK-4125 and AK-4126 are actively deferred until owner decisions.
- AK-4137 defers exact-sdist installation until support or signer-subject inclusion is declared, or a concrete defect is observed.
- The public GitHub repository `tryingET/dspx` now exists with repository ID `1318473695`, owner `tryingET`, and owner ID `260287438`.

## Options considered

### Option A — Long-lived hardware- or secret-backed organization key

- pros: stable organizational identity; conventional custody and revocation; independence from CI OIDC;
- cons: introduces secret storage, rotation, recovery, and operator access;
- risk: possession of one durable key may collapse build and release authority.

### Option B — Keyless CI signing with no separate owner threshold

- pros: no stored private key; exact workflow identity; transparent and automatable;
- cons: a compromised workflow could appear to authorize release;
- risk: evidence authenticity becomes confused with release approval.

### Option C — Keyless evidence signing plus separate owner release threshold

- pros: exact workload authenticity; no long-lived signing secret; explicit separation of machine evidence and owner authorization;
- cons: requires strict OIDC, roster, and predicate validation;
- risk: UI or docs may still collapse the predicates if wording is weak.

### Option D — Remain unsigned and ephemeral

- pros: no new trust or disclosure surface;
- cons: blocks authentic retained evidence and lawful progress on AK-4125/AK-4126;
- risk: repeated local-only evidence cannot support later review or incident analysis.

### Custody alternatives

- zero retention minimizes exposure but defeats inspection;
- bounded public GitHub Actions retention matches the public source repository but requires strict non-secret content policy;
- independent private WORM/registry custody is stronger for confidential or permanent evidence but is a separate future decision.

## Proposed direction

Choose Option C with bounded public GitHub Actions evidence custody.

## Exact signing identity

The offline verifier treats the Fulcio certificate and Sigstore bundle—not an unavailable raw OIDC token or unverified predicate copy—as the authenticated identity surface. After full chain, CT/Rekor inclusion, and bundle verification, every generic Fulcio extension below must equal the required value:

| Certificate field | OID | Required value |
|---|---|---|
| URI SAN | `2.5.29.17` | `https://github.com/tryingET/dspx/.github/workflows/core-release-evidence.yml@refs/heads/main` |
| OIDC issuer V2 | `1.3.6.1.4.1.57264.1.8` | `https://token.actions.githubusercontent.com` |
| Build Signer URI | `.1.9` | same URI as SAN |
| Build Signer Digest | `.1.10` | exact GitHub `job_workflow_sha` |
| Runner Environment | `.1.11` | `github-hosted` |
| Source Repository URI | `.1.12` | `https://github.com/tryingET/dspx` |
| Source Repository Digest | `.1.13` | exact source commit SHA |
| Source Repository Ref | `.1.14` | `refs/heads/main` |
| Source Repository Identifier | `.1.15` | `1318473695` |
| Source Repository Owner URI | `.1.16` | `https://github.com/tryingET` |
| Source Repository Owner Identifier | `.1.17` | `260287438` |
| Build Config URI | `.1.18` | same URI as SAN; equality with `.1.9` forbids reusable-workflow delegation |
| Build Config Digest | `.1.19` | exact GitHub `workflow_sha` |
| Build Trigger | `.1.20` | `workflow_dispatch` |
| Run Invocation URI | `.1.21` | `https://github.com/tryingET/dspx/actions/runs/<run_id>/attempts/<run_attempt>` with positive decimal IDs |
| Repository Visibility | `.1.22` | `public` |
| Deployment Environment | `.1.23` | `core-release-evidence` |
| Token Subject | `.1.24` | `repo:tryingET/dspx:environment:core-release-evidence` |

The `.1.N` values above abbreviate the common prefix `1.3.6.1.4.1.57264`. The verifier rejects missing, duplicated, malformed, or conflicting extensions and does not rely on deprecated GitHub-specific OIDs `.1.2`–`.1.6`. The signed statement's `source_commit_sha` must equal `.1.13`; its `workflow_file_sha256` must equal the SHA-256 of `.github/workflows/core-release-evidence.yml` read from that exact commit tree. Its run ID/attempt must equal `.1.21`. Repository and owner numeric IDs are therefore certificate-authenticated rather than signer-asserted predicate fields.

V1 prohibits reusable-workflow delegation, pull-request signing, tag-triggered signing, branch wildcards, and workflow execution from any ref other than protected `main`. The dedicated workflow must declare least privilege (`contents: read`, `id-token: write`, and no broader permission unless separately justified), use immutable full-commit action revisions, and perform no package publication. Repository transfer, numeric ID change, workflow-path change, environment change, ref-policy change, or workflow delegation requires a new policy version and owner decision before signing resumes.

Signing remains disabled until the public repository has protected `main`, the `core-release-evidence` environment, and the roster bindings described below. Absence or drift fails closed.

## Signature and subject contract

- format: canonical DSSE/in-toto statement with a Sigstore verification bundle;
- custody: ephemeral GitHub OIDC token and Fulcio certificate; no long-lived CI private key;
- transparency: valid inclusion proof and pinned trust-root digest are mandatory;
- `subject[]`: exactly one entry—the exact Core wheel name and SHA-256 digest;
- `auxiliary_evidence[]`: installed proof, v3 evidence envelope, exact-wheel SBOM, resolved-environment SBOM, source commit/tree state, bundle manifest, and sdist digest;
- each auxiliary item has an exact role and digest; the sdist role is `unsigned_unsupported_distribution_evidence`;
- the sdist is forbidden from `subject[]` until AK-4137 is triggered, completed, and followed by a new owner decision;
- authenticity threshold: one valid signature from the exact trusted workload identity;
- interpretation: authenticity does not satisfy owner release authorization.

## Release-authorization threshold contract

Roster version `dspx-core-release-owners-v1` contains three non-interchangeable roles:

1. `role:dspx-release-governance-owner`;
2. `role:softwareco-security-owner`;
3. `role:softwareco-delivery-owner`.

Before the first release authorization, an owner-authorized AK artifact must bind each role to exactly one authenticated principal identifier. One principal cannot occupy or approve for multiple roles. Missing, expired, ambiguous, or duplicate bindings keep release authority false.

A release authorization requires 2-of-3 distinct role approvals. Every approval binds:

- roster version;
- policy version;
- exact wheel SHA-256;
- bundle-manifest SHA-256;
- signed-statement SHA-256;
- source commit SHA;
- intended package version;
- approval creation time and 72-hour expiry;
- authenticated principal and role;
- decision/release task authority reference.

An approval may be withdrawn before the release transition. Any withdrawal, expiry, artifact drift, policy drift, or principal/role ambiguity invalidates the threshold. Approval records are authority inputs; they are not embedded as a claim that the CI signer itself authorized release.

The accepted ADR and AK decision establish this threshold policy but do not populate the three principal bindings. Release authorization stays disabled until a separately owner-authorized roster-binding artifact exists.

## Revocation and historical verification

Each immutable policy version is a checked-in machine-readable artifact at `governance/release-signing/trust-policy-vNNN.json`. It records a monotonic positive integer `policy_version`, effective time, exact OIDC/certificate matcher, pinned Sigstore trust-root digest, roster version, and denied workflow-run IDs, commit SHAs, statement digests, and manifest digests.

Each policy version has a canonical selector JSON committed to Git. Its accepting repo-scoped AK decision uses an `evidence_ref` with this exact grammar:

`dspx-core-policy-selector-v1:git:<commit>:<path>:<blob-oid>:<file-sha256>`

The selector binds repository `tryingET/dspx`, repository ID `1318473695`, positive integer `policy_version`, exact policy path/commit/blob OID/SHA-256, accepting AK decision ID, and either null predecessors for v1 or exact `supersedes_decision_id` plus `supersedes_policy_version`.

For every release-use evaluation, the verifier performs fresh live resolution from the configured owner-approved AK runtime with `ak decision list --limit 100000 --machine` and `ak decision get <id> --machine`. The list call must succeed with a supported schema and return fewer than the requested limit, or completeness is unproven. Candidate selectors must have exact DSPx repo scope, `state=adr_accepted`, `outcome=accepted`, and the evidence-ref grammar above.

Accepted selectors are valid history only when they form one gapless, strictly increasing supersession chain. The unique chain tip is current. Duplicate versions, forks, missing predecessors, inconsistent embedded decision IDs, cycles, or multiple tips fail closed. A newly accepted selector becomes current immediately; future-dated early acceptance is forbidden. The verifier resolves the bound commit/path locally, requires the tree entry to equal the bound blob OID, reads that blob rather than the working tree or network `main`, and verifies both Git OID and SHA-256.

Rules:

- policy versions and selectors are append-only; corrections create a higher accepted version;
- saved AK output is replay evidence, not authenticated freshness;
- a fresh offline verifier may report creation-policy validity only and must report `current_policy_unavailable`;
- release use requires successful fresh live AK resolution and also rejects a tip below the verifier's previously persisted highest accepted version;
- missing policy blob, hash/OID mismatch, invalid supersession, or unavailable live selector keeps release use false;
- a current deny entry invalidates matching evidence even if it was valid when created;
- historical verification reports both creation-policy and current-policy validity; release use requires both;
- identity/trust-root drift disables signing until a higher owner-accepted policy exists;
- compromised evidence is denied and rebuilt/re-signed; signatures and artifacts are never overwritten;
- no automated deletion substitutes for a revocation record.

AK-4125 must amend its scope for the exact machine-readable policy and selector paths before implementation. The accepted ADR chooses this locator and resolution contract; it does not claim policy v1 has already been implemented or selected.

## CI evidence custody and disclosure contract

- provider: GitHub Actions artifacts v4 in public repository `tryingET/dspx`;
- trusted workflow: `.github/workflows/core-release-evidence.yml` under the exact signer identity above;
- recognition, not global ACL: other workflows may upload ordinary artifacts, but evidence is trusted only when its signed custody receipt proves the exact workflow identity, artifact digest, and policy version;
- visibility: GitHub-authenticated users with repository read access may download workflow artifacts; because the repository is public, the policy treats the evidence as publicly disclosed and promises no confidentiality;
- anonymous download is neither required nor relied upon;
- meaning: public evidence disclosure is not package publication, release readiness, support, or release authority;
- ordinary trusted-run retention: request 14 days;
- manually environment-approved release-candidate retention: request 90 days;
- provider cap: preflight the repository/organization Actions retention maximum; if it is lower than the requested class, fail before upload rather than silently shorten custody;
- upload: the trusted-evidence name prefix is `dspx-core-evidence-`; name alone grants no trust;
- untrusted, pull-request, fork, reusable-workflow, or non-main contexts cannot produce trusted evidence receipts;
- download authorization follows GitHub's repository-read and Actions-artifact rules, not a DSPx-specific private ACL;
- early deletion is allowed to authenticated GitHub principals with the provider permission required to delete Actions artifacts or workflow runs; deleting a workflow run may delete its associated artifacts;
- the v1 trusted workflow has no deletion permission and does not delete artifacts;
- pre-upload gate: exact bundle validation, manifest validation, deterministic secret-shaped-content rejection, and an allowlist of bundle members;
- bundle content: no credentials, tokens, raw environment dumps, private prompts, local databases, or unrelated logs;
- upload or deletion timeout/partial response: record `effect_indeterminate`, query provider state by run/artifact identity before retry, and never claim success mechanically;
- no overwrite: changed evidence receives a new artifact identity.

GitHub artifact custody is operational and time-bounded, not WORM or permanent archival custody. Independent durable custody requires another owner decision.

Confirmed deletion or expiry means provider-observed absence of the evidence or receipt artifact by exact artifact ID and workflow run after a successful provider response. Confirmed absence immediately ends current release-use custody; signatures and historical evidence references remain factual but cannot authorize a new release. A timeout, 5xx/transport failure, insufficient authorization, partial response, or missing post-delete observation is `effect_indeterminate`; release use remains false until an explicit provider observation resolves it.

## Post-upload custody receipt

After `actions/upload-artifact@v4` returns, the workflow constructs `dspx-core-ci-custody-receipt-v1` containing:

- evidence artifact ID, URL, provider digest, name, and visibility;
- evidence bundle and manifest SHA-256 digests;
- signed-statement digest and Sigstore bundle digest;
- repository and owner numeric IDs;
- workflow run ID, run attempt, commit SHA, environment, and policy version;
- upload observation time and computed expiry time;
- retention class (`trusted_run_14d` or `release_candidate_90d`);
- explicit `evidence_publication_only=true` and `package_release_authority=false`.

The same exact workload identity signs this receipt after the evidence upload. The signed receipt is uploaded as a separate `dspx-core-custody-receipt-<evidence-artifact-id>` artifact with the same requested retention days and workflow-run association as the evidence artifact. The receipt records both requested retention and provider-observed expiry; an earlier observed expiry fails the selected class.

Receipt upload has the same effect-indeterminate rule as evidence upload. If receipt upload is ambiguous, the workflow queries provider state before any retry. If no valid signed receipt is observed, custody is unproven even when the evidence artifact appears in the provider UI. Before any release-authorization threshold can be evaluated, an owner-authorized step must attach the receipt digest, evidence artifact ID/digest, expiry, and current-policy reference to AK evidence for the exact release task. The receipt artifact's own ID is transport metadata and is not recursively included in the receipt.

An attached receipt is historical upload evidence, not proof of current availability. Every release-use evaluation must freshly confirm that both referenced artifact IDs still exist, remain downloadable under expected GitHub semantics, retain matching provider digests, and have not expired. Confirmed deletion/expiry or an indeterminate availability check keeps the 2-of-3 release threshold unsatisfied.

## Verification contract

Fail closed on:

- any OIDC claim mismatch;
- missing branch/environment protection prerequisites;
- missing/invalid transparency inclusion or trust root;
- wrong, missing, duplicated, or unexpected `subject[]` entry;
- sdist represented as a supported release subject;
- auxiliary-evidence role or digest drift;
- malformed, replaced, or stale verification bundles;
- denied run, commit, statement, or manifest under current policy;
- missing/duplicate roster bindings or approvals;
- approval payload, expiry, withdrawal, or distinct-principal failure;
- missing or invalid post-upload custody receipt;
- missing, deleted, expired, digest-drifted, or effect-indeterminate evidence/receipt artifacts at release-use time;
- stale, incomplete, forked, or unavailable current-policy selector resolution;
- any attempt to treat signature/custody as package publication or release approval.

## Affected contracts / interfaces

- `.github/workflows/core-release-evidence.yml` for trusted identity, keyless signing, public upload, and custody receipt;
- `scripts/ci/core_release_*.py` for statement, trust-policy, approval, and receipt validation;
- `scripts/ci/package-check.sh` for explicit signing/custody gates;
- release tests for identity, subject/material, roster, revocation, retention, disclosure, and failure semantics;
- product/developer posture docs for truthful claim boundaries.

No implementation is authorized by this RFC alone.

## Rollout / migration plan

1. Record owner acceptance through ADR and AK decision; resolve only AK-4125/AK-4126 decision deferrals.
2. Implement offline statement, policy, roster, approval, and custody-receipt fixtures without network effects.
3. Add adversarial tests for identity, subject, trust-root, denylist, approval, and sdist-role drift.
4. Configure protected `main`, environment, and three distinct roster bindings; signing remains disabled until all exist.
5. Add the dedicated GitHub workflow with public 14/90-day non-secret evidence upload.
6. Dogfood on a non-package-release candidate run.
7. Require a separate 2-of-3 release authorization before any package release; package publication remains a separate owner transition.

Rollback:

- disable signing/upload steps;
- retain local bundle validation;
- issue a new denylist policy version for affected evidence;
- preserve audit references without overwriting artifacts;
- keep package release/publication claims false.

## Validation plan

- focused release-evidence unit and adversarial tests;
- workflow static validation and permissions inspection;
- exact OIDC fixture tests for every accepted/rejected claim;
- exact wheel-only subject and sdist-auxiliary-role tests;
- roster uniqueness, 2-of-3 binding, expiry, withdrawal, and drift tests;
- trust-policy version and current-denylist tests;
- public-content allowlist and secret-shaped-content rejection tests;
- post-upload receipt binding tests;
- live dogfood only after branch/environment/roster preflight;
- negative proof that signature/custody cannot satisfy package release approval.

## Risk register

| Risk | Trigger | Mitigation | Rollback |
|---|---|---|---|
| Wrong workload identity accepted | OIDC policy too broad | exact immutable IDs, path, ref, event, environment, and workflow hash | disable signing; new policy version |
| Signature read as approval | UI or docs collapse predicates | separate authenticity and 2-of-3 authority records | keep release state false |
| Sdist support implied | sdist appears as subject | exactly one wheel subject; dedicated auxiliary role | reject statement |
| Secret-bearing artifact disclosed | pre-upload gate fails or is bypassed | deterministic allowlist and secret-shaped-content rejection | stop upload; delete if observed; deny receipt |
| Upload/delete outcome ambiguous | provider timeout or partial response | effect-indeterminate plus provider observation before retry | stop workflow |
| Public artifact treated as package publication | wording or automation drifts | explicit evidence-publication flags and separate release transition | disable upload |
| Roster is unbound | exact principals absent | release authority remains false | no release transition |

## Open questions

None for architecture closure. Exact principal bindings and runtime artifact schemas are bounded implementation prerequisites and cannot enable signing or release until owner-reviewed and validated.

## Decision requested

Approve the exact keyless identity, wheel-only subject, auxiliary sdist role, versioned revocation policy, role-bound 2-of-3 authorization, public non-secret GitHub evidence disclosure, 14/90-day retention, and post-upload custody-receipt contract; or return the RFC for revision.

## Follow-through

If the latest governed review returns `ready_for_adr`, record the durable ADR and accepted AK decision. Only then resolve AK-4125 and AK-4126's decision deferrals. Their implementation remains fail-closed until the GitHub protections, policy artifact, roster bindings, and tests exist. AK-4137 remains deferred unless a later owner decision promotes the sdist to a supported signed subject or a concrete defect is observed.
