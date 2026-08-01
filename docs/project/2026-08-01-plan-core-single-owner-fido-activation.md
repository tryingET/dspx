---
summary: "Post-ADR implementation plan for a forward-only enabled owner-policy successor, fresh FIDO ceremony, authority-false shadow dogfood, and separately governed authority-true transition."
read_when:
  - "Planning implementation after Decision 96 without conflating ADR acceptance with release activation."
  - "Preparing the immutable owner-policy successor or fresh YubiKey shadow ceremony."
type: "implementation_plan"
---

# Implementation Plan — Core single-owner FIDO activation

## Status and authority

Decision 96 is accepted and its ADR is recorded. This artifact supplies post-ADR implementation tracking; it does not itself authorize implementation, enable an owner policy, perform a signature, mutate GitHub, or make a consumer authoritative.

Current fixed baseline:

- ADR: `docs/adr/20260731-core-single-owner-fido-authorization.md`
- legal review closure: `docs/project/2026-08-01-followup-review-final-core-single-owner-fido-authorization.md`
- accepted selector evidence: `dspx-core-owner-policy-selector-v1:git:2839e8fcae8191667db5e2dae953af4f8dc4d27a:governance/release-signing/release-owner-policy-selector-v002.json:b733a20ad8c1bce866f35931dcc3a1ab960e5f0f:260e9e3a95bf2366cbb86bd28541d9fc4405b1d7ed775466aa6c5990fa109dba`
- owner policy v002: immutable and disabled
- current consumer result: `release_authority=false`
- package publication and sdist support: false

## Target of this plan

Produce one receipt-backed, non-publishing shadow dogfood of the accepted architecture using:

1. a new immutable **enabled** owner-policy generation;
2. a new exact Git-bound selector and lawful AK currentness lineage;
3. a fresh canonical approval payload displayed to the owner before signing;
4. a fresh YubiKey PIN/biometric SSHSIG with signed UP+UV flags;
5. the existing authority-false shadow consumer and durable nonce ledger;
6. explicit negative tests and forward-only rollback evidence.

The target stops at `shadow_verified_not_authorized`. Any authority-true behavior is a separate later decision/task and requires a new payload, nonce, signature, review, and transition.

## Non-goals

This plan does not:

- rewrite policy v002, selector v002, or any historical signature/evidence;
- create fake quorum or a second principal;
- permit a shadow receipt to stand in for release authority;
- reuse an expired, previously signed, or already reserved nonce;
- grant registry credentials, package publication, or sdist support;
- authorize an authority-true code path, package upload, or GitHub mutation;
- inspect, copy, or commit the FIDO private handle or PIN.

## Implementation sequence

### Phase 0 — Fresh authority and workspace preflight

A new exact AK task must scope every code/policy/test/doc mutation before work begins. Read back Decision 96 and require:

- state remains accepted/recorded or its lawful post-ADR successor;
- ADR and selector evidence refs match exactly;
- no newer owner-policy selector decision already controls the chain;
- policy v002 still has `authorization_enabled=false`;
- current consumer still hard-wires all authority/publication/sdist outputs false;
- repository and working tree identity are explicit;
- no private-key path or `.ontology/` path is in scope.

Abort on any mismatch. Do not mechanically retry an indeterminate AK, Git, signature, or ledger operation.

### Phase 1 — Author a forward-only owner-policy successor

Create a new owner-policy generation at the next valid immutable version (expected v003 only if live chain inspection confirms v002 is still latest). Do not edit v002.

The successor must:

- preserve the one-principal identity and exact pinned FIDO public key/fingerprint unless a separate key-rotation decision authorizes change;
- set `authorization_enabled=true` and `disabled_reason=null`;
- keep `package_publication=false` and `sdist_supported=false`;
- preserve UP+UV, namespace, lifetime, nonce, revocation, and concentration-risk invariants;
- identify immutable supersession lineage rather than claiming rollback by history rewrite.

Create a matching selector only after policy bytes are committed. Bind exact policy version/path, Git commit, blob OID, file SHA-256, accepting AK decision, and supersession fields. Validate the selector and policy through repo-owned tests and live resolver contracts before any ceremony.

### Phase 2 — Establish selector and AK currentness lawfully

Use a distinct activation decision/task for the new enabled generation. The decision must cite the exact selector ref from committed Git bytes and complete its own required review/artifact lifecycle. Do not treat Decision 96's accepted v002 selector evidence as approval of unknown v003 bytes.

The activation decision may become current only when AK reports its accepted/unblocked state and the selector chain is complete, monotonic, and fork-free. The live resolver must:

- resolve the exact v002 -> v003 chain;
- reject missing/gapped/forked/supersession drift;
- advance the owner-policy anti-rollback checkpoint monotonically;
- reject any attempt to resolve a lower generation afterward;
- return the exact enabled v003 selector/policy identity.

Unblocking an enabled-policy decision does not make the existing consumer authoritative: the shadow consumer remains hard-wired false.

### Phase 3 — Prepare one fresh exact payload

After fresh policy, trust, evidence, source, denylist, custody, and GitHub-read currentness checks, run the non-publishing prepare surface to derive one new canonical payload.

Before signing, display to the owner:

- the full canonical JSON bytes, not a summary;
- SHA-256 of those exact bytes;
- repository name and numeric ID;
- trust- and owner-policy versions plus full selector refs;
- owner-key fingerprint;
- wheel, manifest, and signed-statement digests;
- source commit and package version;
- workflow run/attempt;
- purpose, nonce, issue time, expiry time, and AK authority ref.

The owner must confirm the displayed bytes/hash and refuse if any field is unexpected. Payload lifetime must remain within policy and leave enough time for signing and shadow consumption. A timeout or interruption means prepare a new nonce; never extend or edit signed bytes.

### Phase 4 — Fresh YubiKey biometric ceremony

Use the dedicated FIDO public-key identity and exact SSHSIG namespace. The human performs the normal PIN/biometric interaction and physical touch for the displayed payload.

Immediately verify:

- normal `ssh-keygen -Y verify` succeeds over the exact canonical bytes;
- strict SSHSIG parsing finds the pinned ED25519-SK key;
- signed user-presence and user-verification bits are both set;
- fingerprint, namespace, algorithm, reserved fields, and signature structure match policy;
- the payload remains unexpired.

Record only safe public evidence: payload hash/fields, public key fingerprint, flags, counter telemetry, commands/receipts, and timestamps. Never record PIN, biometric data, private key handle, or credential secrets.

### Phase 5 — Authority-false shadow dogfood

Use a newly created owner-only nonce-ledger directory and the existing staged-input consumer. The attempt must:

- reserve the nonce durably before external signature verification;
- use one staged generation for all bounded artifacts and the detached signature;
- independently resolve current trust/owner policy and exact evidence/custody;
- verify the payload and fresh FIDO signature;
- repeat currentness and expiry checks;
- commit the exact durable receipt before returning;
- return only `shadow_verified_not_authorized` with `release_authority=false`, `package_publication=false`, and `sdist_supported=false`.

The shadow receipt, enabled owner policy, and valid owner signature are evidence for the path. They do not authorize a release.

### Phase 6 — Negative proof and evidence closure

Using separate generated fixtures or the consumed payload where safe, prove fail-closed behavior for:

- replay of the consumed nonce;
- payload, selector, fingerprint, namespace, key, wheel, statement, source, run, or manifest drift;
- absent UP or UV;
- expired payload or custody;
- disabled/revoked/superseded policy;
- trust/owner selector fork, gap, downgrade, or checkpoint rollback;
- GitHub artifact absence/digest/expiry drift;
- staged-input replacement and ledger entry/parent/schema redirection.

Attach machine-checkable receipts to the activation task/decision. Record the shadow result as false and stop.

### Phase 7 — Separate authority-true proposal

Only after successful shadow evidence may a new scoped decision/task propose an authority-true consumer transition. That later proposal must:

- identify the exact code diff that can return true;
- prove the durable receipt commit remains the linearization point;
- define credential separation and non-publication behavior;
- obtain fresh independent review and its own validation/rollout/rollback evidence;
- use a **new** canonical payload, nonce, expiry window, and YubiKey signature;
- keep package publication and sdist support false unless separately decided by their owner surface.

No artifact from Phases 1–6 mechanically authorizes Phase 7.

## Ownership and handoff

- AK owns tasks, decisions, evidence, selector acceptance, and lifecycle transitions.
- DSPx owns local generation, verification, shadow replay, and empirical receipts.
- Git owns immutable policy/selector bytes only after commit; working-tree files are not authority.
- Prompt Vault owns reusable ceremony/review procedures if one is introduced.
- ROCS owns ontology semantics if new controlled vocabulary is proposed.
- Package registry credentials/publication remain outside this plan.
