---
summary: "Fail-closed partial dogfood evidence for owner-policy v003: currentness succeeded, but two confirmation windows ended without signing."
read_when:
  - "Checking task 4420 progress or why no v003 biometric signature/consume receipt exists yet."
  - "Preparing a later fresh payload after the unconfirmed v003 ceremony stop."
type: "evidence"
---

# Dogfood evidence — Owner-policy v003 shadow activation

## Outcome

`stopped_before_signing`

Decision 99 and owner-policy v003 currentness completed, but the required explicit operator confirmation did not arrive in either displayed confirmation window. No signature was produced, no nonce ledger was created, no nonce was consumed, and no shadow receipt exists. Both payloads and nonces are abandoned and will not be reused, edited, signed, or mechanically retried.

This is a fail-closed partial execution, not a successful shadow dogfood.

## Governance and immutable bytes

- Task: AK-4420, still open/deferred pending a new explicit ceremony instruction.
- Activation decision: 99, accepted and unblocked for authority-false execution only.
- Policy v003: commit `71c3b2ed4cf274cc39ec4d48dda9fe25759a4956`, blob `7a9214a6ed40c806a532e574a93fc064229bbfe5`, SHA-256 `f585d4125911a3f5a039739cb36b33d3318c833b710ae5aeea0bd0f9795b3e2c`.
- Selector v003:
  `dspx-core-owner-policy-selector-v1:git:402328b03f16d4c44ab2548315d4e74225683197:governance/release-signing/release-owner-policy-selector-v003.json:318f86dd5b4f4ce541dd812578ffe4a1e143ed63:d4b169475dae9048cee9aeff047eeb726081b1d44e8c48bd979e8fdaeaf3dc4b`.
- Exact-byte independent review: `ready_for_adr`, no blocker/high findings.
- Decision 99 ADR, implementation plan, and validation/rollout/rollback artifacts are recorded.

Policy v002 and selector v002 remain unchanged. V003 is enabled/current, but the existing consumer remains hard-wired authority-false. Package publication and sdist support remain false.

## Currentness evidence

The protected owner checkpoint advanced monotonically from version 2 to version 3 and selected the exact v003 selector above. File and parent ownership/modes remained owner-only.

Fail-closed checks passed without changing the checkpoint bytes:

- v002 downgrade rejected: `owner policy is below highest observed version`;
- same-version alternate-ref checkpoint fork rejected;
- duplicate v003 chain fork rejected;
- synthetic v002 -> v004 gap rejected.

Protected checkpoint SHA-256 after all negative checks: `f6d77313b84f23440981276edbcf851694307e0e136c49f7719cafec02173c6a`.

## Fresh evidence and prepare path

Read-only GitHub observations found the current trust-selector-bound evidence/custody pair from run `30659429735`:

- evidence artifact `8804579832`, provider digest `sha256:4eae75a84ef89d36ef695a2eba7454c00fa4af92bab2c508c3646e0b2b00685b`;
- receipt artifact `8804580826`, provider digest `sha256:a6a30642b4661f5081be9636251316a7c726d7e24510466d8d5ec25182af3f82`;
- custody expiry `2026-08-14T19:33:24Z` / artifact expiry `2026-08-14T19:33:27Z`;
- trust selector exactly `dspx-core-policy-selector-v1:git:c6170846054cf162462503d674da513ef74b160d:governance/release-signing/policy-selector-v002.json:87563d6685c2ea57eff74f133241eaaae1f0835b:ed9f25dfe20a3b957b429d262a6870b35f36745210cac27d79e07eb08d275984`.

Two deterministic pre-output failures occurred and created no payload:

1. pinned cosign v2.6.4 was absent from `PATH`;
2. the prior 90-day evidence receipt bound an older selector coordinate, so exact current-selector binding rejected it even though the policy blob matched.

The missing verifier was supplied in managed temporary storage from the official v2.6.4 release and checked against `cosign_checksums.txt` (`SHA-256 309779b0c4e409186b0a80daba99041fe2cf65a920ce645013901df6211895a9`). The current-selector-bound evidence pair then passed the trusted prepare surface.

## Unconfirmed expired payload

The complete canonical bytes and SHA-256 were displayed in the operator confirmation form.

- Payload SHA-256: `a54a6db42072a56c6cd3c18faddc29ed17b8d7752850d32e8216253cd2d76b3d`
- Issued: `2026-08-01T07:24:30Z`
- Expired: `2026-08-01T07:34:30Z`
- Authority ref: `ak-decision:99`
- Owner policy: version 3 and exact selector v003 ref
- Trust policy: version 2 and exact current selector ref
- Workflow run: `30659429735`, attempt 1
- Wheel SHA-256: `efc1ca6b03da6f4d31df2ff0dd989d3b79950e06dd0aa23d00311ebde056cc5d`

The confirmation form timed out after 600 seconds with no response. A direct peer follow-up also timed out. The payload expired during that wait.

## Second fresh confirmation stop

After the operator explicitly issued `prepare fresh payload`, task deferral 198 was released and AK-4420 was reclaimed. The trusted prepare surface reran current trust/owner policy, denylist, evidence, Sigstore, source, and paired-custody checks and created a distinct payload in a new owner-only scratch directory.

- Payload SHA-256: `aa205de0e85d0c1f44aef259512e387480cd9be2685bebf11a603978ecfc1b8c`
- Issued: `2026-08-01T12:59:11Z`
- Expiry: `2026-08-01T13:09:11Z`
- Nonce: `ed0eddd9edf3e5f440642395f382a8d10b5de3cdbac9e19ef9e2f5939b78df1d`
- Authority ref, policy/selector identities, workflow run, wheel, manifest, statement, source, and package identity matched the accepted first preparation except for the required fresh nonce/window.

The complete canonical bytes and hash were displayed in a new interactive confirmation form. That form timed out after 420 seconds without an explicit confirm/reject response. The signing gate therefore stopped immediately. This second payload and nonce are abandoned even if any lifetime remained at timeout; no signing or consumer command ran.

## Proved absence of effects

- Detached signature path does not exist.
- Nonce-ledger database path does not exist.
- No PIN, biometric data, private key handle, or askpass input was requested or recorded.
- No GitHub API/Actions mutation occurred; observations and artifact downloads were read-only.
- No consumer invocation occurred.
- No replay/consume result is claimed.
- `release_authority=false`, `package_publication=false`, and `sdist_supported=false` remain the only shipped outputs.

## Next legal move

A new explicit operator instruction and a coordinated immediate confirmation window are required before preparing another payload. Any later attempt must use a new nonce and validity window, redisplay all canonical bytes and SHA-256, and obtain confirmation before signing. It may then continue Phases 4–6 exactly once.

If continued activation is no longer desired, use the prepared forward-only rollback procedure: create a higher immutable disabled generation (expected v004 only after live-chain confirmation), never rewrite v003 or reset the checkpoint.
