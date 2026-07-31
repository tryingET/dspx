---
summary: "Final governed many-of-the-greats review of Core signing and public CI evidence custody revision 4; outcome ready_for_adr."
read_when:
  - "You are evaluating ADR legality or implementing the accepted Core signing/custody boundary."
  - "You need the controlling review outcome for the Core signing/custody RFC."
type: "reference"
system4d:
  container:
    boundary: "Controlling review attempt for Core release signing and public CI evidence custody."
    edges:
      - "docs/rfc/RFC-DSPX-CORE-20260731-signing-custody.md"
      - "docs/project/2026-07-31-review-core-release-signing-custody-attempt-1.md"
      - "docs/project/2026-07-31-review-core-release-signing-custody-attempt-2.md"
      - "docs/project/2026-07-31-review-core-release-signing-custody-attempt-3.md"
      - "docs/adr/20260731-core-release-signing-custody.md"
  compass:
    driver: "Adjudicate incompatible signing, authorization, subject, and custody schools before ADR acceptance."
    outcome: "One explicit ADR-readiness result with residual risks separated from blockers."
  engine:
    invariants:
      - "Workload authenticity and owner release authorization remain distinct predicates."
      - "Current release use requires current policy and current artifact availability."
  fog:
    risks:
      - "Proposal completeness may be mistaken for implementation evidence."
---

# Core Signing and CI Custody Review — Final MANY OF THE GREATS Attempt

## Review identity

- reviewed artifact: `docs/rfc/RFC-DSPX-CORE-20260731-signing-custody.md`, revision 4
- procedure: Prompt Vault `many-of-the-greats` (`text_ok`)
- dispatch: `dispatch-1785511748742`
- reviewer posture: independent, read-only
- prior immutable attempts:
  - attempt 1: `revise_rfc`
  - attempt 2: `revise_rfc`
  - attempt 3: `revise_rfc`
- outcome: `ready_for_adr`
- legal next move: record the durable ADR and accepted repo-scoped AK decision; only afterward resolve AK-4125/AK-4126 decision deferrals

## MODE 1 — Strongest schools

### Exact workload sovereignty

A keyless signature from one exact protected workflow should authenticate build evidence. Ephemeral identity avoids durable CI key custody and binds the evidence to repository, workflow, source commit, trigger, environment, and transparency material.

### Durable organizational-key sovereignty

A release identity should survive CI providers and repository migrations. Hardware-backed organizational keys offer independent custody and conventional revocation, but introduce long-lived secret management and blur build identity with organization authority.

### Owner authorization sovereignty

A machine can prove what produced evidence; it cannot decide that the organization intends to release it. Release authority requires distinct human-owner principals and exact artifact-bound approvals.

### Subject minimalism

Only an artifact with exact supported-install proof belongs in `subject[]`. The Core wheel qualifies. Treating the sdist as a subject would silently expand the support contract and trigger AK-4137.

### Atomic release-set completeness

Every artifact published under one package version should be co-subject so a valid wheel cannot lend trust to an unaudited sibling. This school dominates only if a later owner decision includes the sdist in package publication.

### Bounded public CI evidence

A public-source project can disclose strictly non-secret evidence through time-bounded Actions artifacts for inspection and incident response. This is cheap and operational, but mutable and non-archival.

### Independent immutable custody

Release evidence should survive independently of the signer and resist administrative deletion. This dominates for permanent consumer-facing release archives, not the current bounded evidence-only phase.

## MODE 2 — Confrontation

- Workload identity and owner authority cannot control one predicate. Revision 4 resolves this by requiring one exact workload signature for authenticity and a separate 2-of-3 owner threshold for release authorization.
- Wheel-only subject scope and atomic wheel+sdist scope are irreconcilable until exact-sdist support exists. Revision 4 chooses wheel-only and gives the sdist a dedicated unsupported auxiliary role.
- Public Actions custody and immutable archival custody solve different time horizons. Revision 4 requires fresh provider availability for release use and refuses to call Actions WORM or permanent.
- Historical receipt validity and current custody are not equivalent. Revision 4 requires both a signed historical receipt and fresh existence/downloadability/digest/non-expiry checks.

## MODE 3 — Integration or decision

- chosen path: **True Synthesis** for authenticity versus authorization; **Contextual Dominance** for subject scope and custody horizon
- result: accept the exact Fulcio generic-extension matcher, wheel-only subject, current-live AK policy selector, fail-closed role roster, public 14/90-day evidence custody, signed post-upload receipt, and current-availability checks
- why justified: each mechanism governs a distinct predicate and no weaker mechanism is allowed to impersonate a stronger one
- unresolved: principal roster bindings, branch/environment configuration, trust-policy artifacts, code, tests, and live artifacts remain implementation prerequisites—not decision blockers

## Prior-blocker closure

- exact Fulcio OIDs and same-workflow binding: closed;
- fresh-live unique AK selector chain and anti-rollback behavior: closed at proposal stage;
- public artifact recognition/access/deletion semantics: closed;
- receipt retention, effect handling, AK attachment, and current availability: closed;
- role roster: fail-closed while unbound;
- sdist: remains non-subject; AK-4137 remains deferred;
- lifecycle: ADR/AK acceptance precedes deferral resolution and implementation.

## Residual implementation risks

1. Persist or deterministically resolve the receipt artifact ID; do not rely on name alone.
2. Define and test atomicity, integrity, bootstrap, and recovery for the local highest-observed policy-version checkpoint.
3. Verify GitHub branch/environment/retention settings before enabling signing or upload.

These are implementation obligations, not RFC blockers.

## Outcome

`ready_for_adr`

No signing, custody, release authorization, package publication, or sdist support is proven by this review.
