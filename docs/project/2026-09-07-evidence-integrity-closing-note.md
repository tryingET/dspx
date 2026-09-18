---
summary: "AK-5511 closing note (2026-09-18): closed under the owner-adopted bounded autoclearance decision; no hermetic local full run ever executed; separately_disabled defined and ruled non-applicable to DSPx."
read_when:
  - "You need to know how and on what evidence AK-5511 was closed."
  - "You meet the term separately_disabled, or are about to run the native full-profile gate."
type: "reference"
---

# AK-5511 closing note — observed 2026-09-18

This filename follows the task's admitted September 7 path prefix, not the closing date.

## What was decided, and by whom

On 2026-09-18 the owner, in session, answered three explicit questions raised by the
independent many-of-the-greats review
([review](2026-09-18-review-full-gate-autoclearance-many-greats.md)):

1. **Autoclearance — adopt in bounded form.** A green GitHub `CI` run on the exact
   commit SHA mechanically clears release *evidence*. Release *authorization* stays
   an explicit human act. The local hermetic `verify-full` is demoted from gate to
   optional deep-assurance instrument. Implementation of the full predicate
   (runtime job, collection-integrity check, skip baseline, ADR) is AK-5755.
2. **AK-5511 — re-claim, rescope, close.** The `evidence-repair` session's lease
   expired 2026-09-12; the task was released with `ak task unclaim 5511` and claimed
   by `claude-code:86921cdd:ak5511-closure`.
3. **`separately_disabled` — dissolve it if possible.** It was; see below.

## What did NOT happen — stated plainly

**No hermetic local full run ever executed.** The fail-closed dispatcher landed in
`88ab2223` has run zero times beyond `--plan`. No Docker image, closure or
`dspx-full-local-custody-v3` manifest was ever provisioned, and no generator for one
exists. The last local full datum remains `run-1788935170-066132954db9cde8`:
**exit 1, 4067 passed / 85 failed / 5 skipped**, residual serial tests not executed.
Nothing here retroactively repairs that run. That work is AK-5754 (P2), explicitly
not a release gate.

Live, model, GPU and postgres tests remain unexecuted. The ~90
`tests/test_reading_pilot.py` cases skip unless `READING_PILOT_ISOLATED_TESTS=1`, so
they run neither in CI nor in a plain local run.

## Evidence the closure rests on

- **Green CI on the pushed HEAD.** Run `35358539756` concluded `success` for
  `b5db19dd` on push to `main`: quality, core-0..3, forge, slow, package smoke and
  the coverage ratchet. It is the first green run on `main` since 2026-08-25. The
  preceding run `35352699243` (`5c612519`) failed with 14 failures, 25 errors and
  22 type diagnostics; all were runner-environment assumptions and were fixed
  spec-first in `b69eae84` and `8e356b34`.
- **The six genuine failures of the last full run are fixed at HEAD.** The three
  September 3 diaries carry front matter and the strict docs check passes. The three
  source-loader tests pass (28/28 in `tests/test_dspy_lm_auth_lm.py`, and in CI);
  the production runner pin is unchanged — the repair was test-side in `097b57f8`.
- **The 82-case isolation attribution is now counterfactually tested.** Those
  Soomfon ancestor-guard, ledger, local-catalog and permission-negative tests pass
  on a runner with native UID, root-owned ancestors and loopback up. They were
  artifacts of `unshare -Urn`, not host regressions.
- **Host-native AK stage, observed once.** Through
  `agent-kernel/scripts/ak-runtime-gate.sh`: `task list -s claimed` resolves 5511 to
  the closing claimant, and `task show 5061` returns `done`.
- **Scope.** Each of the ten AK-5511 commits, checked individually with
  `check_task_scope.py --task-id 5511 --mode head --range <c>^..<c>`, touches zero
  out-of-scope paths. Eight are `ok`; `6690520e` and `0938c5cf` report only that the
  required design path did not appear *in that single docs-only commit*.

### Accepted gap, recorded rather than worked around

`just task-scope-check task_id=5511 mode=auto` **fails**. Its range runs from the
first AK-5511 scope artifact through HEAD and therefore includes other tasks'
commits (the AK-5681 reading pilot, the 2026-09-18 CI repairs), which it judges
against AK-5511's scope. This is the limitation already recorded in the
[validation continuation](2026-09-07-evidence-integrity-validation-continuation.md).
No scope manifest, snapshot or provenance note was altered to manufacture a pass.
The design document was not edited for closure: it sits exactly at the repository's
800-line markdown budget.

The done-contract item "repo-declared full validation" is satisfied under decision 1
by exact-SHA green CI, not by `just verify-full`. "Independent adversarial review" is
satisfied for the implementation by the September reviews recorded in the design and
diary, and for the closure logic by the many-of-the-greats review above.

## `separately_disabled` — definition and ruling

**Definition.** `separately_disabled` is a field of
`agent-kernel/policy/ak-runtime-access.json`, whose declared `authority_scope` is
"Operator startup/access projection only". As of its `updated_at`
2026-09-05T19:32:08Z it lists four **agent-kernel-internal** surfaces left switched
off after the August AK WAL-safe incident:

- `current_validation_profiles` — agent-kernel's own `static-hook`,
  `full-disposable` and `deep-disposable` engine validation lanes
  (`agent-kernel/docs/project/2026-08-09-wal-safe-incident-custody-validation-contract.md`);
- `legacy_checked_out_hook_activation`;
- `dirty_checkout_install`;
- `session_closeout_runtime_modes`.

`ak-runtime-gate.sh` does not read the field; only a static shape check does.

**Ruling: it does not apply to DSPx.** The DSPx gate makes exactly two AK calls, both
reads through the exclusive runtime gate — the path the same policy marks
`installed_pin_reads: allowed` under `status: normal`. DSPx `verify-full` is not an
agent-kernel validation profile, activates no AK hook, installs nothing into AK and
is not a session-closeout mode. The earlier "owner applicability determination"
request arose from the words "validation profiles" and asked the owner to adjudicate
a category confusion; the form then timed out, which was correctly not treated as
consent. No owner determination is needed for DSPx reads through the gate. Should
DSPx ever invoke an agent-kernel validation profile or closeout mode, re-read the
then-current policy first. This is the single place the term is defined for DSPx.

## Disposition of the five manual gate inputs

| Input | Disposition |
|---|---|
| `--owner-admitted` | Dropped as a gate concept; the code itself labels it "NOT authority proof". |
| Heavy-job admission | Kept, for AK-5754 only — a genuine shared-resource control. |
| Reviewed custody manifest + independent hash | Deferred with AK-5754. |
| Live AK claim | Kept, scoped to host-native AK stages and task closure. |
| `separately_disabled` answer | Dissolved above; not a DSPx input. |

Bare `just verify-full` still exits 2 by design. Documents that call it the final
confidence or release gate are superseded by decision 1 until it has run once; the
wording cleanup rides with AK-5755's ADR.

## What this closure does not grant

No release, tag, publish, signing-roster or trust-policy action; no consumer-trust
activation; no production repin. A dspx-core 0.3.0 release still requires
`evidence-clear(C)` for the exact release commit and a separate explicit owner
authorization on the exact wheel digest, per
[ADR 20260731](../adr/20260731-core-release-signing-custody.md).
