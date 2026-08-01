---
summary: "Validation, shadow rollout, abort, and forward-only rollback contract for post-ADR Core single-owner FIDO activation."
read_when:
  - "Validating an enabled owner-policy successor or fresh authority-false YubiKey shadow dogfood."
  - "Handling replay, drift, revocation, or rollback after Decision 96."
type: "validation_rollout_rollback"
---

# Validation, rollout, and rollback — Core single-owner FIDO activation

## Scope and fixed boundary

This contract validates the post-ADR plan at `docs/project/2026-08-01-plan-core-single-owner-fido-activation.md`. It governs a future immutable enabled-policy successor and an authority-false shadow dogfood only.

Throughout this rollout:

```json
{
  "release_authority": false,
  "package_publication": false,
  "sdist_supported": false
}
```

Decision 96's recorded ADR does not authorize a fresh signature, enabled policy generation, GitHub mutation, authority-true result, or package publication by itself. Each mutation requires its own scoped AK task and applicable decision gates.

## Entry gates

Do not begin an enabled-policy slice unless all are true:

1. `ak decision passport 96 -F json` confirms the accepted ADR and exact v002 selector evidence.
2. A new activation task has explicit allowed/required/forbidden paths and guardrails.
3. A separate activation decision owns the exact future enabled-policy/selector bytes.
4. HEAD, working tree, selected commits, blobs, and SHA-256 values are explicit.
5. Policy v002 and selector v002 are unchanged.
6. The current shadow consumer and all receipts remain authority/publication/sdist false.
7. The owner-policy and trust-policy checkpoints are owner-only, non-symlink state paths with documented backup/restore posture.
8. The nonce-ledger parent is owner-only and the intended database identity is new or explicitly inspected.
9. No private FIDO handle, PIN, secret, or `.ontology/` path is in scope.

Failure of any entry gate is an abort, not a warning.

## Validation matrix

### A. Immutable policy and selector

Required assertions for the enabled successor:

- next version follows the live chain with no gap or fork;
- historical v002 bytes and refs remain unchanged;
- `authorization_enabled=true` pairs with `disabled_reason=null`;
- current pinned key is not listed as revoked;
- UP+UV, namespace, payload lifetime, nonce, repository, and owner identity are exact;
- `package_publication=false` and `sdist_supported=false` remain exact;
- selector policy locator resolves to the committed policy blob and SHA-256;
- selector supersession points to the prior accepted owner-policy decision/version;
- selector's accepting decision is accepted and eventually unblocked through AK, not inferred from prose;
- anti-rollback checkpoint accepts the new current generation and rejects downgrade/fork attempts.

### B. Canonical payload and ceremony

Required assertions before and immediately after signing:

- canonical JSON is duplicate-key-free and byte-stable;
- full bytes and SHA-256 were displayed before human approval;
- all policy/evidence/source/custody/run fields match independently derived current state;
- nonce is fresh 256-bit lowercase hexadecimal and absent from the ledger;
- issue/expiry times satisfy policy and trusted process time;
- exact SSHSIG namespace and pinned public key are used;
- OpenSSH cryptographic verification succeeds;
- strict parser reports both UP and UV set;
- signature counter is recorded only as telemetry;
- canonical payload hash is identical before signing, verification, and reservation/finalization.

Any changed field requires a new payload and signature. Never edit or resign the old bytes in place.

### C. Shadow consumer

Required positive path:

- all bounded artifacts/signature are staged once into one owner-only generation;
- nonce reservation commits as PENDING before signature/external verification;
- trust policy, owner policy, source, statement, denylist, and paired custody verify;
- fresh GitHub reads are read-only and complete;
- second currentness derivation matches the first;
- payload/custody remain unexpired at finalization;
- ledger schema, database identity, and parent identities remain exact;
- durable receipt commit succeeds;
- result is exactly `shadow_verified_not_authorized` and all three authority/publication/sdist booleans are false.

### D. Required negative paths

Each must fail closed with no authoritative receipt:

| Failure injection | Required result |
|---|---|
| replay same nonce/signature | already reserved/consumed; original receipt/tombstone unchanged |
| mutate any canonical payload field | payload mismatch/signature failure |
| trust or owner selector ref drift | selector binding/currentness failure |
| policy downgrade, chain gap, or fork | live resolver/checkpoint failure |
| disabled or revoked owner policy | authorization rejected |
| fingerprint/key/namespace/algorithm drift | authentication rejected |
| UP absent or UV absent | authentication rejected |
| expired payload, evidence, or custody | finalization rejected |
| wheel/manifest/statement/source/run drift | evidence binding rejected |
| artifact original swapped after staging | one coherent staged generation or fail closed |
| ledger DB entry/parent/symlink/schema replaced | reserve/finalize rejected |
| GitHub artifact absent, duplicated, expired, or digest-drifted | current custody rejected |

Failed attempts after reservation retain PENDING tombstones. Do not delete or recycle them to make a retry pass.

## Rollout stages

### Stage 0 — Offline/static

Land future policy/selector/test changes with authorization outputs still false. Run focused release suites, workflow contracts, Ruff/typecheck where applicable, task-scope validation, and pre-push gates. Review exact Git bytes and selector ref independently.

### Stage 1 — Currentness only

After the future activation decision is lawful, resolve the enabled generation through AK/Git/anti-rollback surfaces without signing. Confirm the consumer remains authority-false and the resolver rejects v002 downgrade.

### Stage 2 — Fresh ceremony

Display one fresh canonical payload and hash, obtain PIN/biometric/touch SSHSIG, and verify exact bytes plus UP+UV. No package or GitHub mutation occurs.

### Stage 3 — One shadow consume

Consume once against a new protected ledger, commit the false receipt, and immediately prove replay rejection. Publish no package and return no authority.

### Stage 4 — Observation hold

Freeze mutation. Review receipts, negative tests, policy currentness, checkpoint state, and residuals. A failed or ambiguous observation does not graduate; it triggers forward rollback.

### Stage 5 — Separate authority-true gate

Not part of this rollout. It requires a new decision/task, implementation diff, review closure, validation/rollback pack, and fresh payload/signature.

## Abort conditions

Abort immediately if any of these occurs:

- selector/policy bytes do not match their committed blob/digest;
- AK decision/currentness state is incomplete, stale, or ambiguous;
- v002 history changes;
- enabled successor changes publication or sdist flags;
- displayed payload differs from bytes passed to `ssh-keygen` or the consumer;
- UP/UV cannot be proven from signed details;
- clock, custody, GitHub observation, or denylist currentness is unavailable;
- nonce/ledger identity is not new and exact;
- any consumer path can return true before the separately accepted authority transition;
- any command has indeterminate effect.

For an indeterminate signature or ledger result, preserve files/receipts, do not retry mechanically, and require operator review plus a new nonce.

## Forward-only rollback and revocation

Immutable policy and anti-rollback semantics prohibit rewriting v003 to disable it or resetting the checkpoint to v002.

Rollback is a **new higher immutable generation** (expected v004 only if v003 is live and no newer generation exists) with:

- `authorization_enabled=false`;
- a specific non-empty `disabled_reason`;
- the affected fingerprint in `revoked_fingerprints` when key compromise/loss is suspected;
- `package_publication=false` and `sdist_supported=false`;
- a new exact selector, supersession link, Git binding, and accepted AK rollback decision;
- monotonic checkpoint advancement to that disabled generation.

Rollback actions:

1. stop ceremonies and consumer invocations;
2. preserve ledger, payload, signature, staged-failure, AK, and Git evidence;
3. create/claim a scoped rollback task and decision;
4. land the disabled/revoking successor without changing history;
5. advance its selector through lawful review/currentness;
6. verify the live resolver selects the new disabled generation and rejects v003/v002 downgrade;
7. rerun disabled/revoked negative tests;
8. record incident/rollback evidence and reassess the FIDO key.

A local checkpoint deletion, ledger deletion, nonce deletion, force-push, selector rewrite, or policy rewrite is not rollback.

## Authority-true separation

A successful shadow dogfood does not widen authority. The later authority-true transition must independently prove:

- accepted implementation code can return true only after durable receipt commit;
- all currentness, revocation, replay, expiry, staging, and ledger identity gates remain present;
- the process has no package-registry credential and keeps publication/sdist false;
- rollback is ready before transition;
- a fresh payload, nonce, expiry interval, and YubiKey signature are used;
- the prior shadow payload/nonce/signature are not reused;
- AK records the exact decision, evidence, and transition receipt.

## Required evidence packet

The future shadow slice must close with:

- task scope/contract/guardrail readback;
- exact policy and selector refs, commits, blobs, and digests;
- activation-decision passport and governance receipts;
- canonical payload bytes plus SHA-256 and safe display confirmation;
- SSHSIG public verification receipt with UP, UV, flags, counter telemetry, and namespace;
- shadow authorization receipt and durable ledger identity;
- replay and negative-test receipts;
- current trust/owner/custody observations;
- validation commands and commit/push identity;
- explicit statement that release authority, package publication, and sdist support remain false;
- rollback decision/task or prepared forward-only rollback procedure reference.
