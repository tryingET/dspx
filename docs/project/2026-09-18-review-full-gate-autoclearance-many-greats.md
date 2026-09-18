---
summary: "Independent many-of-the-greats review of the AK-5511 full-gate deadlock and a proposed 'autoclearance'; outcome: contextual dominance — mechanical evidence clearance by exact-SHA green CI, human release authorization, local hermetic gate demoted to optional. Recommendation only; owner decisions pending."
read_when:
  - "You are deciding how to close AK-5511 or what gates a dspx-core release after 0.2.1."
  - "You are asked whether full verification may be cleared mechanically."
type: "reference"
---

# AK-5511 full-gate deadlock and "autoclearance" — MANY OF THE GREATS review

## Review identity

- reviewed question: whether the dspx full-verification gate should be cleared
  mechanically ("autoclearance"), the honest minimum to close AK-5511, and the
  interim gate for a dspx-core 0.3.0 release
- procedure: Prompt Vault `many-of-the-greats` (version 3)
- reviewer posture: independent, read-only subagent; no files, AK state, Docker
  objects or tests touched by the reviewer
- observed: 2026-09-18 at local HEAD `b69eae84`
- requested by: operator, in session ("call upon many-of-the-greats to resolve it
  once and for all ... with like autoclearance or something like that")
- outcome: `contextual_dominance`
- **authority: recommendation only.** Nothing here is adopted. The predicate in
  §Practical consequence 1, the AK-5511 rescoping in §2 and the release checklist
  in §3 each require the explicit owner decisions listed in §4. No AK task state,
  gate code path, release, tag or policy changed as a result of this review.

## Fact corrections recorded by the reviewer

1. At review time `main` was ahead of `origin/main` by one commit (`b69eae84`);
   the latest CI run (35352699243) was for `5c612519`.
2. CI on `main` has been red since 2026-08-25. None of the commits since
   `dspx-core-v0.2.1` has had a green mechanical gate.
3. Not all 85 failures of `run-1788935170` were sandbox-attributed. Per
   `diary/2026-09-07--evidence-full-verification.md`: three source-loader tests
   failed on a stale `model_roles.py` preledger pin (genuine); strict-docs failed
   on three diaries lacking front matter; 82 follow from `unshare -Urn` (UID 65534
   ancestors, loopback down) — "strongly supported, not counterfactually tested";
   `test-residual-serial` never ran.
4. The host-control / isolated-test split is already coded in
   `verify_full_isolation.py` and `verify_full_authority.py`; what is not admitted
   is running it.
5. `separately_disabled` is defined nowhere in the repository. It occurs seven
   times, all in AK-5511 prose, never in code, policy or schema. Its referent
   (apparently an AK or runner policy state outside this repo) is unverified.
6. Confirmed: `heavy-job status` shows `retained_run_count=3`, lock free; the
   AK-5511 claim lease expired 2026-09-12T05:29:38Z; no dspx Docker image exists;
   no manifest generator exists; `read_review` demands schema
   `dspx-full-local-custody-v3` with 11 exact keys.

## QUESTION

Should the dspx full-verification gate be cleared mechanically? What is the honest
minimum to close AK-5511? What should gate a dspx-core 0.3.0 release meanwhile?

## MODE 1 — MANY OF THE GREATS

### School 1: Hermetic custody (reproducible-build tradition)

- Core claim: a verification result means nothing unless every byte that
  influenced it is identified.
- Premises: the earlier gate ran with Just auto-loading `.env`, and an "offline"
  marker was mistaken for effect containment. A suite that can reach a provider, a
  home cache or a stale `.pth` hook can report green about something other than
  the source.
- Strongest case: the 88ab2223 dispatcher is the correct answer — `env -i`,
  `python -I -S -B`, per-file closure hashes, exact node inventory, skip-reason
  hashes, an immutable image ID.
- What it sees that others miss: a passing run is a claim about an environment,
  and unpinned environments lie silently. The three stale-pin failures are its
  vindication: a fail-closed pin caught real drift.

### School 2: Trunk-based CI as single source of truth

- Core claim: the only gate that matters runs on every commit, in minutes, and
  stops the line when red. A gate that does not run is folklore.
- Premises: verification value is frequency times fidelity, and frequency
  dominates.
- Strongest case: CI has been red for weeks and nobody stopped the line, while
  ~2,300 lines of dispatcher were written for a gate that has executed zero times.
- What it sees: `ubuntu-latest` already is the "compatible no-live isolation
  facility" the design says is not yet approved — ephemeral VM, read-only
  permissions and no secrets, native UID with root-owned ancestors, loopback up,
  no AK, no host model cache, frozen `uv.lock`, SHA-pinned actions.

### School 3: Least authority / capability security

- Core claim: separate planes by the authority each needs. Pytest needs no AK
  database, Docker socket, home directory or network; the scope check needs AK
  and nothing else.
- Strongest case: conflating the planes produced a gate needing an exclusive host
  runtime lock, a rootful Docker daemon and the owner's presence at once — hence
  unrunnable.
- What it sees: the AK-native stages verify workflow authority (is the diff inside
  the claimed task), not software correctness. Bundling them into "full
  verification" is a category error, and is why a correctness gate needs a live
  claim to run.

### School 4: Separation of duties / independent review

- Core claim: no actor certifies its own work.
- Premises: in an agent-operated repo the implementer can sincerely report
  success; external binding is the only defence.
- Strongest case: the independent `--review-sha256`, the rule that a form timeout
  is not consent, and the HOLD reviews that found seven real blockers are the
  system working.
- What it sees: "autoclearance" written by the agent that benefits from clearance
  is self-certification.

### School 5: Theory of constraints / lean flow

- Core claim: throughput is set by the constraint, here owner attention,
  serialized through five manual inputs each preceded by a separately dispatched
  review.
- Strongest case: every admission step waits days; the claim lease lapsed while
  waiting on a form; inventory piled up behind the constraint.
- What it sees: large batches are the risk. The longer the gate stays shut, the
  larger the release and the less any single full run can say about it. The gate
  manufactures the hazard it guards against.

### School 6: Policy-as-code attestation (SLSA / in-toto)

- Core claim: clearance is a predicate over signed facts, evaluated by a verifier
  that neither produced the facts nor benefits from the outcome. Humans write the
  policy once; machines evaluate it each time.
- What it sees: the repo already has this architecture. ADR 20260731 lets an exact
  workflow identity authenticate evidence while keeping owner release
  authorization a separate predicate. The custody-v3 manifest is a hand-rolled
  layout with no functionary to produce it — hence "no generator exists".

### School 7: Safety engineering / normalization of deviance

- Core claim: organizations fail by incrementally accepting anomalies. Two exist
  here: a red main tolerated for weeks, and a P0 gate permanently on HOLD so every
  commit ships past it anyway.
- What it sees: an always-closed gate trains everyone to route around it, which is
  worse than no gate. A controller with no feedback channel — zero executions —
  controls nothing, whatever its specification says.

## MODE 2 — CONFRONTATION

### Clash 1: a never-executed gate is zero evidence vs. a self-clearing gate is not a gate

- Fundamental contradiction: schools 1 and 4 measure a gate by what it would
  reject; schools 2 and 7 by what it has observed.
- Both halves are true and indict different objects. The dispatcher has rejected
  nothing real because nothing real has been presented; its evidentiary output is
  nil. "Self-clearing" is fatal only if the clearing party controls the
  predicate's inputs.
- Resolution lies in who evaluates. A predicate evaluated by GitHub's runner over a
  commit SHA cannot be talked into passing by the implementing agent; that is a
  gate in the full sense. A local script where the agent supplies
  `--owner-admitted` is not — `verify_full_isolation.py` itself labels that flag
  "manual execution opt-in, NOT authority proof".
- Residual tension: the workstation-only surface (AK scope, strict-docs through
  agent-scripts, hooks) is small, nameable, and not dismissible.

### Clash 2: does autoclearance collapse evidence and authorization?

- Only if defined sloppily. ADR 20260731 rejects a workflow replacing owner
  authorization in the same breath as it lets a workflow authenticate evidence.
- Mechanical clearance of evidence is therefore the repo's own doctrine. The
  current full gate is the ADR violator: it demands owner admission to *produce*
  evidence, putting authorization upstream of evidence.
- The admission does guard a heavy rootful Docker job on a shared workstation; it
  guards nothing on a hosted runner.
- Resolvable: evidence clearance becomes mechanical, authorization stays human.

### Clash 3: hermetic closure vs. the provisioning cost nobody will pay

- A complete per-file `.venv` inventory, exact node list and skip baseline,
  supplied independently by hand, must be regenerated on every dependency or test
  change; a manifest re-reviewed by a human on every test addition guarantees
  staleness. A generator run by the agent collapses the independence the hash was
  meant to supply.
- Locally irreducible. It dissolves on a hosted runner, where `uv.lock` plus
  `--frozen` plus action SHAs is the closure and `pytest --collect-only` on the
  runner is the node inventory. What is lost is byte-level interpreter custody — a
  real but modest loss for a library installed onto arbitrary interpreters.

### Clash 4: least authority vs. the AK-native tests

- The design forbids "test exclusion" as manufacturing a passing proxy. That
  conflates exclusion with reclassification under a recorded marker and a counted
  inventory. Reclassification with an explicit count is honest; silent skipping is
  not. Resolvable.

### Clash 5: flow vs. review

- Flow says delete the reviews; the record shows they found seven real defects.
  Neither yields. Reviews of *changes to the gate* stay. Reviews as a precondition
  to *each run* of the gate go.

## MODE 3 — INTEGRATION OR DECISION

- Chosen path: **Contextual Dominance**.
- Result: schools 2 and 6 govern "evidence that this commit's software is correct
  enough to release". School 3 governs the plane split that makes this possible.
  School 4 keeps two territories only: changes to the predicate, and release
  authorization. School 1's local dispatcher is demoted from gate to optional
  deep-assurance instrument. School 7 supplies the one non-negotiable rule: red
  main stops the line.
- Why this path is justified: the local gate's evidentiary yield is zero and its
  marginal cost unbounded; the hosted runner satisfies every isolation property
  the design lists for the "compatible no-live variant" without admission; the ADR
  already separates evidence from authorization; and most of the last full run's
  failures were artifacts of the first isolation attempt, which green CI will
  directly confirm or refute.
- What remains unresolved: byte-level toolchain custody is abandoned for release
  gating; whether the host-native AK stages pass at current HEAD is unknown and no
  hosted runner can show it; the referent of `separately_disabled` is unknown.

## PRACTICAL CONSEQUENCE

### 1. Verdict on autoclearance — adopt in bounded form

Predicate `evidence-clear(C)` for commit C on `main` is true iff all hold:

a. GitHub workflow `CI` concluded `success` for exactly SHA C on push to `main`,
   not re-run with changed inputs.
b. CI includes `quality`, all six `tests` shards, `coverage`, `package`, plus a new
   `runtime` job (replay-provenance, monorepo, module-synthesis, boundary-contract;
   strict-docs too if the checker can be vendored, else listed as host-only).
c. A collection-integrity step asserts the union of shard-collected node IDs equals
   `pytest --collect-only` under the offline marker — no duplicates, none missing.
d. Skips are emitted with reasons and compared to a checked-in skip baseline; any
   new skip fails.
e. `.github/workflows/ci.yml`, `scripts/ci/test-shard.sh`, the skip baseline and
   marker definitions are unchanged relative to the last owner-approved SHA for
   those paths; changing them requires an independent review recorded before the
   clearing run counts.

It **never** clears: release authorization, tagging, publishing, signing-roster or
trust-policy changes; AK task completion; any live/model/GPU/postgres test; AK
scope or provenance; anything about a commit other than C. A red or missing run is
"not clear", never "unknown, so proceed". An agent may read the predicate; it may
not assert it without the run URL and SHA.

### 2. Disposition of AK-5511

Close when: (i) CI is green on a pushed HEAD under (a), with (b)–(e) allowed to
follow in a new task; (ii) the three stale-pin source-loader failures and three
front-matter diaries are fixed or each recorded as an owned follow-up; (iii) one
host-native run of the AK stages only (`just task-scope-check` plus the task-5061
show through the AK gate wrapper) has been observed and recorded; (iv) a closing
note states plainly that no hermetic full run occurred and `run-1788935170` stands
as the last local full datum, at exit 1.

Move to a new P2 task "Optional hermetic local full run": Docker image
provisioning, the custody-v3 manifest and its generator, real container
cancellation/recovery proof, the residual-serial live/model plane. The 88ab2223
code stays in tree; bare `just verify-full` keeps exiting 2; docs stop calling it
"the final confidence gate" until it has run once.

The five manual inputs: `--owner-admitted` — drop as a gate concept; heavy-job
admission — keep, for the deferred local task only; reviewed manifest plus
independent hash — defer with the local task; live AK claim — keep, scoped to the
host-native AK stages and task closure only; the `separately_disabled` answer —
keep as an owner question, decoupled so it blocks only native full-profile
execution, and defined in writing in one place before it is asked again.

### 3. Interim gate for dspx-core 0.3.0

- [ ] `evidence-clear(C)` is true for release commit C.
- [ ] `main` was green for C and its parent; no fix merged in the same push as the
      release bump.
- [ ] `just ci-package` green (wheel install proof, SBOMs, v3 envelope per the ADR).
- [ ] The stale `model_roles.py` pin is resolved by an owner-visible commit, not an
      agent self-repin.
- [ ] The host-native AK scope check observed once at C, receipt path recorded.
- [ ] The changelog states the full local gate was not executed and carries the
      AK-5511 closing note.
- [ ] Owner release authorization given as a separate explicit act per the ADR, on
      the exact wheel digest.
- [ ] No live, model or provider claims in the release notes.

### 4. Ordered next actions

1. [agent-can-do-now] Land the remaining CI environment fixes.
2. [needs-owner-decision] Push the CI fixes and iterate until CI is green: yes/no.
3. [needs-owner-decision] Is a green GitHub CI run on the exact commit the
   release-evidence gate for 0.3.0, with local hermetic `verify-full` demoted to
   optional? yes/no.
4. [needs-owner-decision] What does `separately_disabled` refer to, and may it stay
   disabled and unasked while native full-profile execution is deferred?
5. [agent-can-do-now, after 3 = yes] Add the CI `runtime` job, the
   collection-integrity step and the skip baseline (predicate b–d).
6. [needs-independent-reviewer] Review action 5's diff and the marker
   reclassification — a single review, not one per run.
7. [needs-owner-decision] Re-claim AK-5511 under a fresh session (old lease dead):
   yes/no. Rescope its closure to §2 (i)–(iv) and create the P2 successor: yes/no.
8. [agent-can-do-now, after 7] Run the host-native AK stages once, fix the pin and
   front-matter items, write the closing note.
9. [needs-owner-decision] Release authorization for 0.3.0 on the exact digest.
10. [agent-can-do-now] Record an ADR (or amendment) stating the predicate; the
    "final confidence gate" wording is otherwise the normalization hazard.

### 5. Residual risks, blockers and reversal conditions

Blockers: red CI; the dead claim lease; the undefined `separately_disabled`; owner
decisions 3 and 7.

Residual risks (accepted if adopted): no byte-level custody of interpreter or
toolchain — trust rests on GitHub-hosted runners and PyPI through `uv.lock`
hashes; workstation-coupled guards are exercised only on a runner layout; live,
model and postgres tests remain unexecuted (as today, but now stated); the 82-case
attribution stays counterfactually untested until green CI tests it implicitly; a
large-batch release.

Reverse this recommendation if: CI cannot be made green without deleting or
skipping tests beyond the counted workstation reclassification; the runner proves
incompatible with the custody guards; dspx-core acquires consumers for whom
toolchain-byte custody is contractual; the repo stops being public or the runner
gains secrets; or CI-defining files are changed without review.

## Session follow-up (same day, not part of the independent review)

Action 1 was carried out red-green in the requesting session (commit `8e356b34`),
each group from a Given/When/Then scenario:

- the reading suite establishes its own admission posture and a private cache
  (`tests/reading_suite_posture.py`, specified by
  `tests/test_program_reading_suite_posture.py`). Root cause of the parallel
  failures: xdist workers shared `generated/cache` and overwrote the entry a
  candidate receipt is bound to;
- eight workstation-pinned full-gate tests are reclassified under a registered
  `workstation` marker with an exact checked-in inventory
  (`tests/test_ci_shard_selection.py`, `tests/fixtures/workstation-tests.txt`);
- generated top-level `module`/`signature` imports are isolated between tests
  (`tests/test_generated_module_isolation.py`);
- `host_scope` no longer writes bytecode into the repository it inspects
  (`tests/test_verify_full_host_scope_bytecode.py`).

Those changes touch `scripts/ci/test-shard.sh` and marker definitions, i.e. exactly
the paths predicate (e) would place under independent review. Also observed: the
~90 `tests/test_reading_pilot.py` cases skip unless
`READING_PILOT_ISOLATED_TESTS=1`, so they run neither in CI nor in a plain local
run — relevant to predicate (d).
