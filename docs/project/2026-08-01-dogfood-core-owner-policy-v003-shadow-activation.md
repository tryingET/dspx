---
summary: "Completed owner-policy v003 authority-false shadow dogfood with exact mechanical display, YubiKey Bio UP+UV, durable nonce consumption, and replay rejection."
read_when:
  - "Checking task 4420 completion evidence for the v003 biometric authority-false shadow ceremony."
  - "Confirming that the successful shadow receipt granted no release authority or publication capability."
type: "evidence"
---

# Dogfood evidence — Owner-policy v003 shadow activation

## Outcome

`shadow_verified_not_authorized`

Decision 99 and owner-policy v003 completed one mechanically displayed, explicitly hash-confirmed, hardware-backed authority-false shadow ceremony. OpenSSH and the strict ED25519-SK parser proved user presence and user verification. The durable ledger committed one shadow receipt, and the single intentional replay was rejected.

The result explicitly reports `release_authority=false`, `package_publication=false`, and `sdist_supported=false`. This is successful shadow-path dogfood, not release authorization or package publication. The four earlier payloads remain abandoned and were never signed or consumed.

## Governance and immutable bytes

- Task: AK-4420, claimed for final evidence, independent review, and closeout after successful shadow consumption.
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

## Third fresh confirmation stop

After a coordinated operator-ready event, the trusted prepare surface produced another distinct payload and reran the accepted live checks.

- Payload SHA-256: `fb1715e013781258bb0f198bbc9586899414b1dbe46af789ff4489dc7ff5bef6`
- Issued: `2026-08-01T13:20:05Z`
- Expiry: `2026-08-01T13:30:05Z`
- Nonce: `aae4606a5fafd73ffc0d4be7ea504f25745bbfc8765f40d1d6544a665e470bf2`

The canonical bytes and hash were relayed to the controller, but no exact-payload confirmation returned before expiry. No signing, ledger, or consumer command ran. The payload and nonce are abandoned.

## Fourth fresh display-integrity stop

After the operator again reported immediate readiness, the trusted prepare surface produced a fourth distinct payload.

- Canonical-file payload SHA-256: `5fb9ee2a1bfeb79c086c57bd7daa92c04923a6e53fc0d16e657ffa207e69216f`
- Issued: `2026-08-01T14:26:18Z`
- Expiry: `2026-08-01T14:36:18Z`
- Nonce: `dd141433a15bd71752b8fc17b986dd3bbc33bdfc5f7570d65a139d13b95c3043`
- Canonical-file source commit: `c6170846054cf162462503d674da513ef74b160d`

The controller detected that its displayed JSON altered `source_commit_sha`; those displayed bytes therefore did not hash to the canonical-file SHA-256. Exact-byte informed confirmation was impossible. The signing gate stopped fail-closed immediately, and an operator stop notification was sent. No signing, ledger, or consumer command ran. This payload and nonce are abandoned even if the canonical file itself remained unmodified.

A future attempt must transmit canonical payload bytes mechanically from the file and recompute the hash over the exact displayed byte sequence; manual field copying is not an acceptable ceremony transport.

## Successful mechanical-display ceremony

After the operator explicitly replied `GO`, deferral 201 was released and AK-4420 was claimed. A dedicated Ghostty terminal generated one new payload, mechanically printed the canonical file with `cat`, computed its hash with `sha256sum`, and required the exact input `CONFIRM <computed-hash>`. The script recomputed the file hash after confirmation and refused to sign on any mismatch.

Canonical approval evidence:

- Payload SHA-256: `58b93f6689bf51ad714ced215349c449902ff1a62deae045c4f3d1774a54ef43`
- Signature SHA-256: `7cc8790d58724c575cb24a3f19ffb1f49e093bc804b5985844f518e33f0ab023`
- Issued: `2026-08-01T14:44:00Z`
- Expired: `2026-08-01T14:54:00Z`
- Nonce: `af6f1b860d7b32ac58e1d219559302438233d62b7455444c2f13d37cfabe8ca0`
- Authority ref: `ak-decision:99`
- Source commit: `c6170846054cf162462503d674da513ef74b160d`
- Workflow run: `30659429735`, attempt 1
- Evidence artifact: `8804579832`
- Custody receipt artifact: `8804580826`
- Wheel SHA-256: `efc1ca6b03da6f4d31df2ff0dd989d3b79950e06dd0aa23d00311ebde056cc5d`

The operator entered the authenticator PIN only in the direct terminal and used an enrolled YubiKey Bio finger. No PIN, private key handle, or biometric material was captured. OpenSSH verification succeeded. The strict parser reported ED25519-SK flags `5`, `user_presence=true`, `user_verification=true`, and counter telemetry `8` for the pinned public fingerprint.

## Durable authority-false consume

The trusted consumer reserved the fresh nonce before external verification and durably committed this exact receipt at `2026-08-01T14:48:54Z`:

- Schema: `dspx-core-release-authorization-shadow-receipt-v1`
- Status: `shadow_verified_not_authorized`
- Linearization point: `durable_nonce_receipt_commit`
- Receipt SHA-256: `bfdad15d71a76693084520b582e17431d5be23feb06bf15af53b9e9c3833aa42`
- `release_authority=false`
- `package_publication=false`
- `sdist_supported=false`

The new ledger parent and database were owner-only modes `0700` and `0600`. A read-only post-commit query found exactly one `committed` row whose embedded receipt matched all authority-false fields. The single intentional replay exited nonzero with `authorization nonce is already reserved or consumed`; it was not retried.

## Negative matrix and quality gates

The isolated release test matrix passed `150` tests, including exact-payload drift, expiry, absent UP/UV, disabled/revoked policy, selector downgrade/fork/gap, evidence and custody drift, coherent staged input replacement, and ledger entry/parent/symlink/schema replacement. Scoped Ruff and repository workflow-contract checks also passed. These fixtures did not mutate the protected checkpoints or committed live ledger.

## Proved absence of effects in the four stopped attempts

For each of the four abandoned attempts described above:

- Detached signature path does not exist.
- Nonce-ledger database path does not exist.
- No PIN, biometric data, private key handle, or askpass input was requested or recorded.
- No GitHub API/Actions mutation occurred; observations and artifact downloads were read-only.
- No consumer invocation occurred.
- No replay/consume result is claimed.
- `release_authority=false`, `package_publication=false`, and `sdist_supported=false` remain the only shipped outputs.

## Completion boundary and next legal move

AK-4420 may close after independent post-run review confirms this evidence and the committed receipt. Do not reuse the successful payload, nonce, or signature.

This result does not authorize an authority-true consumer, package publication, registry credentials, or sdist support. Any authority-true proposal requires a separate decision/task, exact implementation review, validation and rollback artifacts, and a new payload, nonce, signature, and durable consumption ceremony.

If v003 must later be disabled, use the prepared forward-only rollback procedure: create a higher immutable disabled generation only after checking the live chain, never rewrite v003 or reset the checkpoint/ledger.
