---
summary: "AK-5511 scope-v6 bounded baseline repair: preservation/static checks pass; focused pytest failed once, corrected fixture not rerun."
read_when:
  - "Independently reviewing evidence8669 baseline characterization repair before authorizing further tests or commits."
---

# AK-5511 bounded baseline repair — observed 2026-09-09

**Implementation present, verification incomplete; HOLD. No commit or full-gate
pass.** Admission read from AK task5511 scope entity version6 and evidence8669.
Effective routing returned `AK_DIRECTION_ROUTING_UNINITIALIZED`; no route invented.
HEAD remained `92443fbee2ceb72c8844482215342ac76ed3211a` on main.
The existing design document was appended before code; its original content is
an exact prefix. This note and its sibling evidence directory are local projections,
not AK authority or independent implementation review.

## Implemented bounds

- Only source edit: `tests/test_dspy_lm_auth_lm.py` (final 1000 lines).
  Private fixture copies the required source/manifest/runner files and fixed
  v9/v10/code-semantics predecessors. The original runner is bound by a fixed
  complete-file hash; its 46-entry literal map is parsed without executing it.
  Every copied preledger source is checked against the historical pin or one of
  exactly three fixed current hashes. Exactly three full path/hash literals are
  replaced, once each, **only in the copied runner**. Arbitrary drift is not rehashed
  into a replacement pin. Existing source-only/origin/allowlist and post-preparation
  assertions remain, and rejection assertions now name the exact corrupted path.
- A separate historical runner test verifies its immutable hash, exact three
  current mismatches, and fail-closed rejection at `model_roles.py`.
- Exactly three admitted September3 diaries received only summary/read_when YAML
  frontmatter; each original file is an exact byte suffix. No historical body edits.
- Production runner, all46 bound source files, historical constants, lockfile,
  scope snapshot, existing reviewed gate tests, and all other pre-existing inputs
  are byte-identical. Before/after comparison covered **2786 unchanged files**;
  the only five existing files changed by this slice are the test, design and
  three diaries. New evidence files were written afterward.

**Synthetic current-source loader characterization is not historical verification,
production pin approval, a live-supported runtime, or new live eligibility.**
No provider invocation, production dispatch, saved-lineage replay or download was
requested. The tests use actual provider-free bootstrap inspection/import paths;
they do not mock the source loader and never call live entry functions.

## Execution and limits

One invocation, no pytest retry:

```bash
env -i HOME="$HOME" PATH="$PATH" LANG=C.UTF-8 TMPDIR="$TMPDIR" \
  UV_OFFLINE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  PYTHONDONTWRITEBYTECODE=1 MLFLOW_ENABLE=0 DSPX_PROVIDER=stub \
  unshare -Urn .venv/bin/python -B -m pytest -q tests/test_dspy_lm_auth_lm.py \
  -k 'bootstrap or source_loader or historical_repository_runner or candidate_contract_and_accepted_consumer or cli_gate4 or loaded_runtime_origin' \
  --basetemp=/home/tryinget/.local/state/pi-quests/tmp/ak5511-baseline-repair.jCmsRm/pytest
```

Observed **9 passed, 1 failed, 17 deselected**, 2.23s, exit1. Passing cases:
foreign runtime origin; contaminated startup; mutually exclusive CLI gates;
both exact-path preledger corruptions; post-preparation exact-path drift;
timestamp-valid malicious pyc ignored/source executed/cache untouched;
immutable historical runner rejection; accepted candidate/consumer bytes.

The positive stale-PYTHONPATH case failed at missing code-semantics JSON, before
its task-binding success, Gate4 allowlist/runtime-origin and Gate5 origin checks.
Inspection also identified the required v9 JSON. Both omitted dependencies were
added to the helper afterward, with an AST non-None type guard. **The final file
has not been executed**; the failed attempt is not final-source passing proof.
The five real temp-repository test copies agree on the tested-source hash below.
No indirect positive-path rerun or passing proxy was substituted.

Final-source explicit `.venv/bin/ruff check`, `ruff format --check`, and
`.venv/bin/ty check tests/test_dspy_lm_auth_lm.py` each exited0 under sanitized
offline environment; `git diff --check` was clean. Metadata parsed as exactly
summary plus nonempty read_when, and suffix equality was checked with byte
comparison. The custody-report assembly initially stopped on a wrong copy-count
assertion because Path.glob included pytest's `*current` symlink aliases; physical
`find -type f` subsequently identified five identical captured test copies. No
pytest or provider execution was repeated to repair this reporting discrepancy.
No full docs/runtime gate was run. Namespace success for nine cases proves neither
full-suite UID/permission compatibility nor live/network/model behavior. No syscall
audit is claimed. No AK mutations, staging, commit, push, full gate or retries.

## Exact custody hashes (SHA-256)

Sibling directory `2026-09-07--evidence-baseline-repair/` retains logs, diffs,
inventories, appended design bytes, and tested-source copy; `evidence-files.sha256`
binds those files. Full tracked diffs include pre-existing reviewed changes, not
just this implementation. `repair.diff` contains only the test and three diaries;
`design.append.txt` separately binds this slice's design additions.

| Artifact | SHA-256 |
|---|---|
| Full tracked diff before | `e837a04dbb4778f3d856480871b073ea953f3f76be19123d5b205b93d8b8546a` |
| Full tracked diff after | `e53e3ea8d0c2e971b9a2464b35eed281cf21c4e48ab491f38364cdf14501f952` |
| Repair test/diaries diff | `25e1c22af115705e24e0d28ab4089c35e9082b26cb34fabb0de552762f5be28e` |
| Design append | `c6fc2556b435ccd8047d6b1a21d6957f609a442152e6091b5f64d7da47e90a2a` |
| Tested source (retained temp copy) | `a69a3d519f9e8ffa8d75fa7437fa8b16bb849271a348ce2fda3b06f5bec938f7` |
| Final test source (not rerun) | `9aa4ccff89845e274e7fdc70c4f3bfd079ba5009bfac9ae6ed49edc965bfbc2c` |
| Pytest log | `5ff693a9e748c9af6a64ed39eac9584f4e2157ba31ea4dfe11eba1129bfed9ea` |
| Production runner before/after | `f593be0834cb370806a8b5c18ac5a157e6438cf1fcaa7628ee920e47c6e868c6` |
| Protected-file inventory before/after | `88f619999f2dacfb89f43f1a53aff91f2ba90c007b632bb199f2f37b838d2d77` |
| 46 current preledger source inventory | `f7b5b3d169e42ca74096d10b150518195774f22cd958f90a745df7b59647dd68` |

Exact historical diary suffixes:

| September3 diary ending | Preserved bytes | SHA-256 |
|---|---:|---|
| child-retention-and-xai-timeout.md | 6218 | `d5e0e3ba1607967223bd93c40b5f487deab0bce9f5592753dfb0a94fb48dd2ec` |
| fresh-subprocess-and-split.md | 7197 | `cadaa65cef04bc2de5caa3d44def195845523b1d4594ea8d51cb81e774c14e16` |
| preflight-and-catalog.md | 6122 | `e584d2c853d557fa043dae619fdcb48a47c061e59ed1558c06242af45f53afc4` |

All three historical source hashes were independently recovered via read-only
`git show 6ea779d0f1af7e8adb2f0a7a4bc499c450b1f890:<exact-path>` and matched the
runner literals. The design table preserves historical/current pairs and records
source-change lineage `c617826c` / `c9a52177`. No production repin occurred.

## Stop / next action

Stop for separate independent implementation review. Owner/controller must
explicitly authorize focused final-source revalidation before this repair can be
called passing; no commit before that review. The earlier full gate remains HOLD
and requires separate compatible no-live posture/admission, not an implicit retry.


## Dated review and foreign-origin repair addendum — 2026-09-09

This addendum preserves the entire earlier note, including the **9-pass/1-fail**
attempt and then-unexecuted correction, as an exact prefix. Those remain historical
facts, not the current final-source status.

Independent review `dispatch1788937030933` issued **bounded SHIP** on prior source
`9aa4ccff89845e274e7fdc70c4f3bfd079ba5009bfac9ae6ed49edc965bfbc2c`:
**10 passed / 17 deselected**, plus five separately labelled scratch probes.
The reviewer found a pre-existing false-green: the foreign-module test could reject
ordinary `dspx.__cached__` without reaching the backend. Review receipt and prior
pytest/adversarial logs are retained under `2026-09-07--evidence-origin-repair/`.
These are reviewer observations, not fresh executions of those prior probes here.

Parent adopted the minimal correction and explicitly authorized deterministic
focused regression reruns. The scoped design decision was appended before code.
Only `tests/test_dspy_lm_auth_lm.py` changed source: the old broad-cache/foreign
matcher was replaced with Gate4/Gate5 parametrized actual-loader subprocess tests.
Each establishes a passing baseline, changes only the backend's `__file__`, checks
both the exact production diagnostic and the raising frame's backend-relative path
and module identity, restores that origin, and passes again using the unchanged
manifest. No cached attributes, runtime inputs, module allowlists or unrelated
modules are cleared. Unused test imports, including duplicate stdlib-only imports
in the existing subprocess text, were removed; all its assertions remain.
The file remains **1000 lines**. Synthetic characterization grants no new live
eligibility and does not repin production or historical bytes.

### Final-source execution and attribution

Final source SHA-256:
`df5191a4d26295ce0cff1e9adaed9138beed7dae5065b230c7fe3cb2c36dcdf9`.
Focused pytest **11 passed / 17 deselected**, exit0, 4.22s. The prior ten-case
selection now has two precise foreign-origin cases in place of the one defective
case. All other loader/immutable-candidate checks remain selected. Gate4 and Gate5
both reject `packages/dspx-core/src/dspx/services/program_oracle_semantic_backend.py`
after a passing real source-only baseline. Two additional final-source scratch
counterfactuals omitted only the origin mutation: each test then correctly failed
with `foreign backend origin accepted`, rather than passing on an earlier cache
failure. These are negative-test characterizations, not extra full-gate cases.

An initial version of this follow-up also passed 11/17 (4.01s) and two omitted-origin
probes; it was then simplified within the new test to retain the file's 1000-line
budget. The final source and both probes were explicitly rerun, not inferred from
that earlier result. Both execution versions and source hashes are retained.
Final explicit-file ruff check, ruff format --check, and ty check each exited0;
`git diff --check` was clean.

Final pytest command (installed tools, no sync/download):

```bash
scratch=/home/tryinget/.local/state/pi-quests/tmp/ak5511-origin-repair.vcy0HJ
env -i HOME="$HOME" PATH="$PATH" LANG=C.UTF-8 TMPDIR="$scratch" \
  UV_OFFLINE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  PYTHONDONTWRITEBYTECODE=1 MLFLOW_ENABLE=0 DSPX_PROVIDER=stub \
  unshare -Urn .venv/bin/python -B -m pytest -q -p no:cacheprovider \
  tests/test_dspy_lm_auth_lm.py \
  -k 'bootstrap or source_loader or historical_repository_runner or candidate_contract_and_accepted_consumer or cli_gate4 or loaded_runtime_origin' \
  --basetemp="$scratch/pytest-final"
```

The counterfactual script used the same sanitized network-isolated environment
and pinned this final test hash; it altered subprocess code only in memory and
wrote fixture copies only in owned scratch. No provider/model call, download,
saved-attempt replay, full gate, AK operation, staging or commit occurred.

### Custody and remaining boundary

| Artifact | SHA-256 |
|---|---|
| This follow-up's test-only delta | `97aaf8298dcca0112f78a63d009aafae32b0c8a4b7f01bf794aa893d379c8a63` |
| Full tracked diff before | `e53e3ea8d0c2e971b9a2464b35eed281cf21c4e48ab491f38364cdf14501f952` |
| Full tracked diff after | `99e224d4e16d19a29345faa0dabb34f1b8075b5b419201212c5ef3c764122903` |
| Final pytest log | `33329cb1000456856c769c3b93be0973d857693a3da5b5568c23ae3b988ea84f` |
| Final counterfactual log | `f5663215cb358e41575512c32396d41bbf9453c87261be94e4fb2b5459c42744` |
| Production runner, unchanged | `f593be0834cb370806a8b5c18ac5a157e6438cf1fcaa7628ee920e47c6e868c6` |

The retained before/after inventory and `preservation.json` bind this slice's
mutation limits. All46 production preledger sources and the runner are unchanged;
existing reviewed gate tests, three September3 headers/bodies and earlier receipt
files are untouched. Historical suffixes retain their exact earlier byte counts
and hashes. Design and this diary change only by appending; the original failed
attempt is not rewritten. Full tracked diffs include prior work, not just this
follow-up. New scoped evidence is separately checksummed.

**Stop for final independent implementation review; no commit.** The earlier
bounded SHIP does not review this follow-up. Focused tests and traceback attribution
do not prove a full-suite isolation posture, live/model behavior, historical
execution, or release eligibility. Full-gate HOLD is unchanged and requires
separate compatible no-live posture and authorization.


## Final independent SHIP consumed — 2026-09-09

Final re-review `dispatch1788937030933` issued **SHIP for the bounded correction**
on `df5191a4d26295ce0cff1e9adaed9138beed7dae5065b230c7fe3cb2c36dcdf9`.
The actual final source independently produced **11 passed / 17 deselected**,
exit0, 3.95s. Four separate counterfactual characterizations passed: for each
Gate4/Gate5, omitting the backend-origin mutation fails with `foreign backend
origin accepted`; mutating only another module fails the backend attribution
assertion despite the same production diagnostic. These expected child exit1
results are negative-test characterizations, not extra pytest/full-gate passes.

Inspected review: `/home/tryinget/.local/state/pi-quests/tmp/ak5511-origin-rereview.ie6TnY/review.md`,
SHA-256 `87cbc95128db5853754292068a1a525c0e5032eb55e005991ebbd1373d5a0d23`.
Independent pytest log: `84393489da39cf1a1de236e56c2303d991b0d32d1a3274b121d6eac9dcb17306`;
counterfactual log: `7c08d2d1754d739aa7679b065c64ebe5775a20ff21b3b0bdded52ef285491223`.
These hashes were checked during finalization, not inferred from prose. No blocking
review finding remains; private traceback-local coupling is an explicit, optional
maintenance risk, not grounds to weaken wrong-reason rejection checks.

Fresh finalization reran the same accepted selection: **11 passed / 17 deselected**,
exit0, 4.12s, plus package/test typechecks and scoped format/lint. Native strict docs
metadata passed; all three historical September3 bodies remain exact HEAD suffixes.
The original 9-pass/1-fail attempt and every earlier byte above remain intact.
Production runner and all46 preledger sources still equal HEAD; synthetic success
is not production pin approval or historical/live eligibility.

The pending-review/no-commit stop above is superseded only by this final SHIP and
controller's bounded main-commit authorization. Full-gate HOLD remains. Current
inventory and remaining gates: `diary/2026-09-07--evidence-finalization.md`; compact
command/hash receipt: `diary/2026-09-07--evidence-finalization.receipt.json`.
