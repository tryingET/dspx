---
summary: "Post-ADR implementation, validation, rollout, and rollback plan for exact Core keyless signing and bounded public GitHub evidence custody."
read_when:
  - "You are planning or executing AK-4125 or AK-4126 after Decision 88."
  - "You are configuring the Core release-evidence workflow, trust policy, roster, or custody receipt."
type: "reference"
system4d:
  container:
    boundary: "Post-ADR execution plan for Core signing and public CI evidence custody."
    edges:
      - "docs/adr/20260731-core-release-signing-custody.md"
      - "docs/rfc/RFC-DSPX-CORE-20260731-signing-custody.md"
  compass:
    driver: "Turn the accepted decision into testable, reversible implementation slices without claiming package release authority."
    outcome: "Offline proof first, provider configuration second, live evidence-only dogfood last."
  engine:
    invariants:
      - "No live signing or upload before offline contracts and provider preflight pass."
      - "No package release through this plan."
      - "AK-4137 remains deferred."
  fog:
    risks:
      - "Provider configuration may outrun verified code."
      - "Public upload may disclose data if fixtures are weaker than runtime inputs."
---

# Core Signing and CI Custody — Implementation Plan

## Authority

- accepted architecture: `docs/adr/20260731-core-release-signing-custody.md`
- AK decision: `#88`
- implementation tasks:
  - AK-4125 — signer, statement, trust policy, selector, authorization, and verifier;
  - AK-4126 — dedicated workflow, public artifact custody, receipt, retention, and provider effects;
- explicitly not activated: AK-4137 exact-sdist installation.

The decision deferrals may be resolved after ADR/AK acceptance. Task readiness still depends on ordinary AK admission and exact scope. Neither task may infer package publication authority.

## Phase 0 — Scope and prerequisites

1. Amend AK-4125 scope for the exact machine-readable policy/selector artifact paths before touching them.
2. Confirm `tryingET/dspx` numeric repository and owner IDs.
3. Inspect supported Sigstore/Fulcio bundle and verifier library versions.
4. Keep `.github/workflows/core-release-evidence.yml` absent or disabled until Phase 2.
5. Record the three roster roles but do not invent principal bindings.

Exit gate: implementation paths are scoped; no live signing/upload capability exists.

## Phase 1 — Offline contracts and adversarial verification

AK-4125 owns:

- canonical DSSE/in-toto statement schema;
- exact Fulcio generic OID extraction and matcher;
- wheel-only `subject[]` and typed `auxiliary_evidence[]`;
- immutable trust-policy and selector schemas;
- live-AK unique-tip selector resolution;
- creation/current policy verification;
- denylist and historical verification;
- roster binding and 2-of-3 approval schemas;
- atomic/integrity-tested highest-observed policy checkpoint;
- negative tests for every identity, subject, policy, roster, expiry, withdrawal, fork, rollback, and drift case.

No network signing occurs in this phase.

Exit gate: deterministic fixtures prove valid and invalid contracts; signature verification still cannot authorize release.

## Phase 2 — Custody workflow and receipt

AK-4126 owns:

- dedicated `.github/workflows/core-release-evidence.yml`;
- least permissions and immutable action revisions;
- protected-main, `workflow_dispatch`, and `core-release-evidence` environment preflight;
- 14/90-day retention-cap preflight;
- public bundle member allowlist and secret-shaped-content rejection;
- evidence upload with host-observed artifact identity;
- signed post-upload custody receipt;
- explicit persisted or deterministic receipt-artifact ID resolution;
- AK evidence attachment for the exact release task;
- provider observation before retry after ambiguous effects;
- current evidence/receipt existence, digest, downloadability, and expiry verification;
- deletion and workflow-run deletion semantics.

Signing/upload remains disabled until branch/environment protections and three distinct roster bindings exist. The unbound roster blocks release authorization even when evidence dogfood becomes available.

Exit gate: workflow static checks and mocked provider-effect tests pass; no package publication step exists.

## Phase 3 — Public evidence-only dogfood

1. Run from protected main through `workflow_dispatch` and the protected environment.
2. Build the exact Core wheel evidence bundle.
3. Prove pre-upload allowlist and secret-shaped-content gates.
4. Sign the statement and verify the exact certificate profile offline.
5. Upload public evidence with the selected 14-day dogfood class.
6. Generate, sign, upload, and verify the custody receipt.
7. Attach receipt digest and custody facts to AK evidence for the dogfood task.
8. Re-query live AK current policy and GitHub artifact availability.
9. Assert package release, readiness, and sdist support remain false.

Exit gate: receipt-backed public evidence is observable and current; no package release occurs.

## Validation plan

Minimum focused coverage:

- certificate SAN and OIDs `.1.8`–`.1.24`;
- Build Signer/Build Config equality;
- source commit/workflow digest binding;
- wrong repo/owner numeric IDs;
- pull request, fork, reusable workflow, tag, wrong branch, wrong environment, self-hosted runner;
- missing/extra/duplicate subjects and sdist-subject rejection;
- policy selector forks, gaps, cycles, rollback, multiple tips, stale/offline AK, and Git blob drift;
- roster role uniqueness, missing bindings, 2-of-3 threshold, expiry, withdrawal, and payload drift;
- public bundle allowlist and secret-shaped fixtures;
- provider retention cap, upload ambiguity, receipt ambiguity, deletion, expiry, digest drift, and unavailable current artifact;
- negative proof that signature/custody cannot set release authority.

Run repo-declared focused tests first, then `just check` and `just verify-full` when the package/workflow changes require the full gate.

## Rollout

1. Merge offline contracts and tests with signing disabled.
2. Configure public-repo branch and environment protections.
3. Bind three distinct roster principals through an owner-authorized AK artifact.
4. Enable evidence-only workflow dogfood.
5. Observe at least one full retention/expiry or controlled-deletion lifecycle before considering a package-release decision.

## Rollback and escape hatch

- Disable the dedicated workflow or its signing/upload job.
- Never delete history to conceal a compromised run.
- Add affected run/commit/statement/manifest digests to a higher accepted deny policy.
- Preserve historical receipts while marking current release use false.
- For ambiguous provider effects, stop and observe before any retry.
- Local bundle generation and validation remain available.
- Package publication stays false throughout rollback.

## Explicit nonclaims

Completion of this plan would establish authenticated, publicly disclosed, time-bounded Core evidence. It would not establish:

- package release approval;
- registry or GitHub Release publication;
- permanent archival custody;
- sdist support;
- production activation.
