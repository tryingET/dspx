---
summary: "Adopt bounded evidence autoclearance: a green GitHub CI run on the exact commit clears release evidence mechanically; release authorization stays human; the local hermetic verify-full becomes optional deep assurance."
read_when:
  - "You are deciding whether a commit has enough verification evidence to release."
  - "You are changing CI sharding, skips, markers, or any file listed in governance/ci-gate-approval.json."
  - "You are about to call just verify-full a release gate."
type: "reference"
system4d:
  container:
    boundary: "What counts as verification evidence for a DSPx commit, and what that evidence never authorizes."
    edges:
      - "docs/project/2026-09-18-review-full-gate-autoclearance-many-greats.md"
      - "docs/project/2026-09-07-evidence-integrity-closing-note.md"
      - "docs/adr/20260731-core-release-signing-custody.md"
      - "scripts/ci/ci_evidence_predicate.py"
      - "governance/ci-gate-approval.json"
  compass:
    driver: "Replace a gate that never ran with one that runs on every commit, without letting the agent that benefits from clearance assert it."
    outcome: "One machine-checkable evidence predicate evaluated by a party that neither wrote the change nor gains from the result."
  engine:
    invariants:
      - "Evidence clearance is mechanical; release authorization is a separate explicit human act."
      - "A red, missing or re-run-with-changed-inputs run is not clear — never unknown, so proceed."
      - "An agent may read the predicate; it may not assert it without the run URL and exact SHA."
      - "Files that define the gate cannot change without a visible same-commit edit to the approval record."
  fog:
    risks:
      - "No byte-level custody of interpreter or toolchain; trust rests on GitHub-hosted runners and uv.lock hashes."
      - "Workstation-pinned and opt-in tests are outside the predicate and can rot unnoticed."
      - "A skip baseline can be widened by the same change that needs the skip."
      - "Deleting a test, or swapping which tests carry live/network/model/gpu/postgres, is visible only in the diff."
      - "The approval record is tamper-evidence, not authentication: nothing proves who wrote approved_by."
---

# ADR 20260918 — CI Evidence Clearance ("bounded autoclearance")

## Status

Accepted by the accountable owner in session on 2026-09-18, following the independent
[many-of-the-greats review](../project/2026-09-18-review-full-gate-autoclearance-many-greats.md).
Implemented under AK-5755. Refines, and does not replace,
[ADR 20260731](20260731-core-release-signing-custody.md).

## Context

From 2026-08-25 to 2026-09-18 `main` had no green mechanical gate. CI was red, and the
local full gate — rebuilt in `88ab2223` as a fail-closed hermetic dispatcher demanding
owner admission, heavy-job admission, a hand-reviewed `dspx-full-local-custody-v3`
manifest with an independently supplied hash, a live AK claim and an operator ruling —
executed zero times. Over a hundred commits accumulated behind it. A gate that never
runs yields no evidence and trains everyone to route around it.

ADR 20260731 already separates *workload authenticity of evidence* from *owner release
authorization*. The local gate inverted that by requiring owner admission in order to
*produce* evidence.

## Decision

**Predicate `evidence-clear(C)`** holds for commit `C` on `main` if and only if:

1. GitHub workflow `CI` concluded `success` for exactly SHA `C` on a push to `main`,
   and was not re-run with changed inputs.
2. That run included `quality`, `runtime`, all six `tests` shards, `coverage` and
   `package`.
3. **Collection integrity:** the shards partition the offline suite exactly — every
   node id `pytest --collect-only` yields under the offline marker expression is
   collected by exactly one shard (`just ci-collection-integrity`). The number of
   tests *outside* the offline selection must equal the approved
   `excluded_node_count`, so marking a red test `live` changes an approved number.
   It is a count, not an inventory: only the workstation nodes are listed by id, so a
   net-zero swap among the other excluded tests, or deleting a test outright, is
   visible only in the diff.
   An empty collection is never accepted.
4. **Outcome baseline:** every skip, xfail and xpass a shard reports is listed, by test
   file, exact reason and reviewed maximum count, in
   `tests/fixtures/ci-skip-baseline.txt`. An unlisted outcome, or more of a listed one
   than reviewed, fails the shard. The itemised rows must add up to pytest's own totals
   line; a log without one fails closed.
5. **Gate approval:** every gate-defining file — the workflow, `Justfile`,
   `pyproject.toml`, `tests/conftest.py`, the shard, package and predicate scripts, the
   two inventories and the two specs that enforce them — hashes to the digest recorded
   in `governance/ci-gate-approval.json` (`just ci-gate-approval`). The check is driven
   by the gate set, not by the record's own keys, and rejects placeholder reviewers.
   Changing a gate file therefore requires changing the record in the same commit,
   where it is visible. **This is tamper-evidence, not authentication:** the repository
   has no required reviews, CODEOWNERS or signed approvals, so nothing proves who wrote
   `approved_by`. Deliberately outside the set: `uv.lock` (churns on every dependency
   bump; `--frozen` already makes drift fail) and the record itself (it cannot hash
   itself and is visible in the diff).

Conditions 1 and 2 have no automated evaluator. Check them by hand against the run:
`gh run view <id> --json conclusion,event,headSha,headBranch,attempt,jobs` must show
`success`, `push`, the exact SHA, `main`, and `attempt` 1.

Reclassified tests are counted, never silently dropped: workstation-pinned tests carry
the `workstation` marker and are inventoried exactly in
`tests/fixtures/workstation-tests.txt`.

### What it never clears

Release authorization, tagging, publishing, signing-roster or trust-policy changes; AK
task completion; any `live`, `network`, `model`, `gpu` or `postgres` test; AK task scope
or provenance; strict docs metadata (host-only, because its checker lives outside this
repository); and anything about a commit other than `C`.

### Review of the gate itself

Independent review applies to *changes to the predicate* — the files in the approval
record — once per change. It is not a precondition of each evaluation. That keeps
separation of duties where it protects something and removes it where it only taxed
running the gate.

### The local hermetic gate

`just verify-full` stays in tree and keeps exiting 2 without admission. It is an
optional deep-assurance instrument (AK-5754), not a release gate, and no document may
call it the final confidence gate until it has executed once.

## Alternatives considered

- **Keep the hermetic gate mandatory.** Strongest custody claim, zero executions, and a
  manifest that must be re-reviewed by hand whenever a test or dependency changes. A
  generator run by the implementing agent would collapse the independence the hash was
  meant to supply. Rejected as a gate; retained as an instrument.
- **Require both.** Keeps every release blocked on the same unprovisioned work.
- **Unbounded autoclearance** (green CI also authorizes release). Rejected: it collapses
  the evidence/authorization separation ADR 20260731 exists to keep.

## Consequences

- Verification evidence exists for every pushed commit, produced by a party the
  implementing agent cannot talk into passing.
- Byte-level interpreter and toolchain custody is given up for release gating.
- Workstation-coupled guards are exercised on a runner layout, not the real host.
- Live, model, GPU and postgres tests remain unexecuted — as before, but now stated.
- Red `main` stops the line. Tolerating it for weeks is the normalization of deviance
  this decision exists to end.

## Interim release checklist (dspx-core 0.3.0)

- [ ] `evidence-clear(C)` for the exact release commit; record the run URL and SHA.
- [ ] `main` green for `C` and its parent; no fix in the same push as the version bump.
- [ ] `just ci-package` green per ADR 20260731.
- [ ] Host-native AK scope check observed once at `C`, receipt path recorded.
- [ ] Changelog states that the local hermetic gate was not executed.
- [ ] Separate, explicit owner release authorization on the exact wheel digest.
- [ ] No live, model or provider claims in the release notes.

## Reversal conditions

Hardening not yet done: CODEOWNERS plus a required review on the gate set, or an
owner-signed approval record, would turn condition 5 from evidence into control.

Revisit if CI cannot stay green without deleting or skipping tests beyond the counted
reclassification; if hosted runners prove incompatible with the custody guards; if
dspx-core gains consumers for whom toolchain-byte custody is contractual; if the
repository stops being public or the runner gains secrets; or if gate-defining files
are found changed without a recorded review.
