---
summary: "AK-5511 historical evidence archive locator and bounded cleanup result."
read_when:
  - "Resolving retained September 7 evidence paths after authorized cleanup."
type: "reference"
---

# September 7 evidence: archive custody and historical redirect

## Execution status

**Removed and verified at 2026-09-11T15:28:58.581Z.** Exactly 71 files (3,674,713 bytes) and three empty directories were removed. All 74 selected paths are absent.

Execution date: 2026-09-11 (UTC), not backdated to the evidence date.
AK-5511 scope entity version 8 permits this new locator. The supplied parent
dispatch authorizes phase 2 following independent review dispatch1789132510756
(conditional SHIP). It reports peer 01a086ae and the parent have no active or
intended readers/writers in these three trees, including children, and will
maintain cooperative quiescence through removal; forensic/review/archive children
are finished. This is an attributed coordination guarantee, not global inactivity
proof. Exact-task authority applies; effective routing is uninitialized.

No AK task/evidence mutation, session closeout, seal, release, or lifecycle closure
is performed or claimed. Caller acf6d5c6/session01a05bcc, frozen inventory revision
12 and O4 acceptance are parent-dispatch bindings, not independently revalidated
closeout state.

## Durable local locator

Archive directory (`A`):

`/home/tryinget/.local/state/dspx-evidence-archives/ak5511/2404c9334f4681199b0b2f968f084996b688162b9aacae8a8c7f042b922f17e3`

- Archive: `A/evidence.tar` (concatenate the exact directory above).
- Archive SHA-256: `2404c9334f4681199b0b2f968f084996b688162b9aacae8a8c7f042b922f17e3`.
- Checksum inventory: `A/SHA256SUMS`; SHA-256 `4e4c857a4c011a1d9eab6d4286669e0923c2cc41e323c240051cb138c2e5c46f`.
- Index: `A/INDEX.md`. Exact 74-row original-to-member map and 19 reference
  resolutions in five historical documents: `A/archive-map.json`, SHA-256
  `9a32ea61b76fa867d12ba2ddaaa43471df5dc33e7fe65c63fc7414961d2253e1`.
- Native source identities/metadata and per-file hashes: `A/manifest.json`.
- Historical receipt copy: `A/retention-receipt.json`; original
  `diary/2026-09-07--evidence-finalization.receipt.json` remains verbatim.
- New append-only per-file deletion journal (JSON array; each intent and result
  fsynced, never replacing the archive manifest):
  `/home/tryinget/.local/state/dspx-evidence-archives/ak5511/cleanup-tQwHK1ua/phase2receipt.json`.
- Fresh extraction/source verification, independent tar inspection, process
  observations, outside snapshots, and result proof are siblings of that journal.
- Prior independent review: `/home/tryinget/.local/state/pi-quests/tmp/dspx-ak5511-independent-review.sR9nxGRy/review-result.json`
  (scratch reference, not durable redundant custody).

## Explicit historical path map

Repository base (`R`): `/home/tryinget/ai-society/softwareco/owned/dspx`.
For each root below and every inventoried child `p`, the old absolute path
`R/<root>/p`, repo-relative `<root>/p`, or diary-relative basename plus `/p`
now resolves to `A/evidence.tar::<root>/p`. Directory entries map identically.
The archive member path does not gain another prefix.

| Original repo-relative root = archive member prefix | Files | Bytes |
| --- | ---: | ---: |
| `diary/2026-09-07--evidence-baseline-repair` | 16 | 1227230 |
| `diary/2026-09-07--evidence-full-verification` | 20 | 1056334 |
| `diary/2026-09-07--evidence-origin-repair` | 35 | 1391149 |
| Total | 71 | 3,674,713 |

Historical reference redirects (line numbers in the unchanged source):

- `diary/2026-09-07--evidence-baseline-repair.md`: line 85, `2026-09-07--evidence-baseline-repair/` → `A/evidence.tar::diary/2026-09-07--evidence-baseline-repair`; line 136, `2026-09-07--evidence-origin-repair/` → `A/evidence.tar::diary/2026-09-07--evidence-origin-repair`.
- `diary/2026-09-07--evidence-finalization.md`: line 96, `2026-09-07--evidence-baseline-repair/` → `A/evidence.tar::diary/2026-09-07--evidence-baseline-repair`; line 97, `2026-09-07--evidence-full-verification/` → `A/evidence.tar::diary/2026-09-07--evidence-full-verification`; line 98, `2026-09-07--evidence-origin-repair/` → `A/evidence.tar::diary/2026-09-07--evidence-origin-repair`.
- `diary/2026-09-07--evidence-finalization.receipt.json`: line 96, `2026-09-07--evidence-baseline-repair` → `A/evidence.tar::diary/2026-09-07--evidence-baseline-repair`; line 105, `2026-09-07--evidence-full-verification` → `A/evidence.tar::diary/2026-09-07--evidence-full-verification`; line 114, `2026-09-07--evidence-origin-repair` → `A/evidence.tar::diary/2026-09-07--evidence-origin-repair`; line 127, `2026-09-07--evidence-full-verification/full-run.log` → `A/evidence.tar::diary/2026-09-07--evidence-full-verification/full-run.log`.
- `diary/2026-09-07--evidence-full-verification.md`: line 26, `2026-09-07--evidence-full-verification/full-run.log` → `A/evidence.tar::diary/2026-09-07--evidence-full-verification/full-run.log`.
- `docs/project/2026-09-07-evidence-integrity-validation-continuation.md`: line 104, `2026-09-07--evidence-baseline-repair/` → `A/evidence.tar::diary/2026-09-07--evidence-baseline-repair`; line 105, `2026-09-07--evidence-full-verification/` → `A/evidence.tar::diary/2026-09-07--evidence-full-verification`; line 106, `2026-09-07--evidence-origin-repair/` → `A/evidence.tar::diary/2026-09-07--evidence-origin-repair`.

Existing narrative `.md` references still resolve to repository documents, not
tar members. This additive map supersedes only the current physical location of
the retained raw files. Historical bodies, hashes, failure findings, and receipt
claims are unchanged as history; they are not rewritten into retroactive passes.
In particular the retained full-run failure remains a failure.

## Bounded proof and limits

Fresh archive checksums and independent 74-member/71-payload inspection passed.
Post-removal archive checksum inventory and tar SHA-256 still match the pins.
The 2799-path before/after snapshot (tracked/nonignored untracked paths
plus explicit `.ontology`, excluding only the selected roots and this new doc)
is byte/metadata-equal, including `docs/_core`, historical documents, receipt,
`.gitignore`, and preexisting unrelated work. Outside Git status and the initially
empty staging index are unchanged before this document's commit.

Deletion journal SHA-256: `ba7f05e71ba19c67cae8e5e7dd8e87ced84498bb109a971490e69ff8eee29208`.
Result proof: `/home/tryinget/.local/state/dspx-evidence-archives/ak5511/cleanup-tQwHK1ua/result.json`.
Only this new locator is intended for the main-branch commit; validation/commit
proof is recorded separately in the same cleanup directory. No full runtime or
release gate is claimed for this custody-only change.

Checks cover the 71 regular files/74 entries, exact bytes, portable archive
metadata and fresh native source dev/inode/ctime/mode/owner/link metadata,
readable xattrs/extended ACLs, and no foreign entries. Exact nonrecursive unlinks
require immediate identity and digest rechecks; only the three empty directories
may be removed. Any drift or partial failure stops without retry.

The source and archive share a filesystem (device 50). This is machine-local
custody, **not redundant backup**, replication, public availability, historical
execution proof, or an immutable storage service. Checks exclude source atime;
portable archive metadata cannot retain native inode/device/ctime or directory
physical size. Process observations are current-UID, point-in-time and have
visibility denials; they cannot exclude future opens or uncooperative writers.
The check/unlink race is bounded by the supplied cooperative quiescent interval,
not an atomic filesystem transaction. No syscall-audit or global preservation
claim is made for workstation records, Pi history, other scratch or other owners;
this execution does not target them.

## Stop before commit: outside-state discrepancy

At 2026-09-11T15:30:34.284Z, the commit was withheld. Initial read-only inspection
showed one unrelated tracked modification and ten unrelated untracked paths
(historical-review / AK-5672 work). They were no longer dirty when the immediate
pre-mutation snapshot was captured; HEAD remained
`7a85b5c9d15da3986eaef1ac299c3f99dfbf62db`. The actor and cause are unestablished.

The 2,799-path preservation proof above applies only to the actual deletion
interval, not the entire session. It does not prove preservation of the unrelated
changes visible on initial inspection. No whole-session outside-state preservation
is claimed. Source removal and archive verification succeeded before this
discrepancy was recognized. No deletion retry or Git commit was attempted.

Stop evidence: `/home/tryinget/.local/state/dspx-evidence-archives/ak5511/cleanup-tQwHK1ua/stop-before-commit.json`.
The parent must reconcile that outside-state transition before authorizing the
locator commit. AK lifecycle/evidence and session closeout remain parent-owned.

## Parent reconciliation of the concurrent withdrawal

Fresh canonical-gated readback on September 11 identified the other owner operation:
AK-5672 is failed with an operator scope-correction result. Its evidence9227 records
archival and withdrawal of exactly the ten untracked historical-review files and
the two-line CLI registration seen in the initial observation. The recorded reason
is that the operator required a generated COMPASS-C program, not a DSPx extension.
That owner reports its archive at
`/home/tryinget/.local/state/compass-c/scope-corrections/AK5672-withdrawal.9kT5Wx5Y`,
SHA256 `109b216e47aff0a15613f9253c3ce00f60e79bd5c0c738cc946ca25eb490039a`,
and preservation of the foreign September7 evidence during its withdrawal.

This is attributed canonical owner evidence explaining the outside transition;
it is not an independently replayed withdrawal or a claim that this cleanup
preserved all state throughout both sessions. Our separate 2,799-path deletion-
interval check and 71-file archive/removal proof remain unchanged. The parent
therefore permits committing this locator only. No foreign files are restored,
deleted or reassigned, and the historical stop record is retained.
