---
summary: "AK-5754: the hermetic verify-full gate ran for the first time: all 13 container stages pass in discovery after seven defects were fixed; the first official execute passed 5 stages and stopped at the hook guard (fixed since); no passing receipt yet."
read_when:
  - "You want to run, re-provision or debug the optional hermetic local full run."
  - "heavy-job refuses admission with 'process-reference scan incomplete'."
type: "reference"
---

# Hermetic gate — first real execution (AK-5754), observed 2026-09-18

The hermetic `verify-full` dispatcher is an **optional deep-assurance instrument, not a
release gate** ([ADR 20260918](../adr/20260918-ci-evidence-clearance.md)). Until today
none of its stages had executed outside `--plan`.

## What ran, and what did not

**Discovery runs — observations, not gate evidence.** Each stage's exact command ran in
the dispatcher's exact container posture (`--user=1000:1000 --network=none --read-only
--cap-drop=ALL --security-opt=no-new-privileges --pids-limit=1024 --memory=12g
--cpus=16`, the closed `fixture_environment()`, the `STARTUP` identity/capability/network
assertions), but with **live read-only mounts** instead of the custody copy, and outside
the dispatcher. At `eb014199`:

| Stage | Result |
|---|---|
| workflow, direction-static, governance, replay, monorepo, strict-docs, package-ty, test-ty | pass |
| module-corpus | pass |
| hooks (`prek run --all-files`, offline, reviewed caches read-only) | pass, zero rewrites |
| offline (`-n 16 --dist load`) | 4579 passed, 98 skipped, 0 failed, 140 s |
| residual | 3 skipped (live/model/postgres opt-ins), 0 failed |
| membership | the gate's own `validate_membership` accepts the merged reports |

**Not run:** the official `--prepare` and `--execute`, therefore also the two host stages
inside the dispatcher (`hostscope`, `host-task5061`), the custody copy, the Docker
intent journal, container reconciliation and cancellation/recovery. No receipt exists.

## Official run — PASSED

Three owner-authorized `heavy-job` admissions (ADR-0019 / Decision 160 age deferral of
the same three named terminal runs), all `heavy_job_result=success`:

1. `--prepare` at `2f029478` — succeeded. A read-only pre-check then showed `--execute`
   would fail `hostscope`: AK-5754 had no task scope. One was authored and frozen
   (`22f8c597`), which changed HEAD and invalidated that manifest and copy.
2. `--prepare` at `22f8c597` + `--execute` — passed `workflow`, `direction-static`,
   `governance`, `hostscope`, then stopped fail-closed at `hook rewrote source bytes`.
   The ruff hook was caching into the source tree; fixed in `af91c808`.
3. `--prepare` + `--execute` at `6fead7bf`, with this note's own edit as the uncommitted
   in-scope slice — **`ok: verify-full`, exit 0, 220 s.**

### The passing receipt

`receipt.json` SHA-256 `4502b7f86ca1efd12a2cd7b5982497fce794fb6f0ade8063ae321bf97be31f3c`,
manifest SHA-256 `a5780e9f3c4baf65c472572b4ffe02df4df437f7876075d2d8298d53a2a8b86b`,
reviewed-closure digest `533328e6dd93…`, HEAD `6fead7bf`.

| | |
|---|---|
| status | `passed` |
| stages | 15/15 — every stage in `STAGES` |
| hostscope | task 5754, `working-tree` mode |
| host-task5061 | native integration, task 5061 |
| membership | 4683 collected = 4680 offline + 3 residual, disjoint and complete; 101 skips; 0 collector skips |
| containers | every one reconciled and removed; no unsettled host effects |

This is the first passing hermetic receipt in the repository's history. It is **not** a
release gate and clears nothing: the release-evidence predicate remains exact-SHA green
CI ([ADR 20260918](../adr/20260918-ci-evidence-clearance.md)), and release authorization
remains a separate human act.

The 2.4 GB job directory is retained for inspection, as the gate's contract requires.

## Scope stage: the gate validates *uncommitted* work

`host_scope` calls `check_task_scope(mode="auto")`, and `auto` resolves to
**working-tree** when the tree is dirty and **head** when it is clean. In head mode the
slice is every commit from the task's first scope artifact through HEAD, so when another
task lands in between — AK-5756 did — that task's files are judged against this task's
scope and the stage fails:

```
packages/dspx-core/src/dspx/services/optimize_service.py: falls outside attested task scope
```

That is the over-approximation already recorded for AK-5511, not a new defect: the gate
is built to validate the work in front of you, before it is committed. The custody-v3
manifest binds dirty worktree bytes and explicit deletion tombstones precisely for that.
Run the gate with the task's changes uncommitted; a clean tree on a shared main is the
unsupported mode.

Independent of that, **commits should carry provenance notes**. The restricted host Git
view admits exactly `git notes show --ref=refs/notes/...`, and
`committed_files_for_task_provenance` uses those notes to include a task's already
committed group. The convention lapsed in this repository after 2026-08-24 and this
session's commits initially had none; they were added afterwards with
`~/ai-society/core/agent-scripts/scripts/git-note-provenance.sh`.

## Defects the first real run found

Unit tests with synthetic venvs and fake command results could not find these:

1. Closure rejected a `PUBLIC KEY` `.pem` shipped in a locked wheel (litellm).
2. Package identity was parsed from the whole METADATA file; `distro`'s README body
   contains `Name: Antergos Linux`, which overrode the header.
3. Inside the gate `TMPDIR=/fixture/tmp`, so the gate's own unit tests were rejected by
   its guard against mounting over `/fixture`.
4. The audit hook denied a synthetic `<tmp>/agent-kernel/` fixture by path text alone.
5. **Thread budget.** numpy starts one thread per *host* core (64) regardless of
   `--cpus`; threads count against `--pids-limit=1024`; 16 workers x 64 = 1024, so forks
   failed with `EAGAIN` before any test ran. At 12 workers it surfaced as subprocess
   timeouts and a `degraded` runtime status. The closed environment now caps the pools.
6. The ruff hook cached into the source tree, tripping the hook-rewrite guard (above).
7. Tests assumed a writable `/tmp`, an unset oracle-index override and a host scratch
   root. The image also lacked a passwd entry for UID 1000 (44 failures), `ssh-keygen`,
   `/usr/bin/python3` and `cue`.

## Provisioned

- Image: `scripts/ci/verify-full-image/Dockerfile` (Arch base; git, just, node, uv, cue,
  openssh, python; user `tryinget` UID 1000). Built locally as
  `sha256:f04d8830e787f453df01e18caff4ff682e242934c211aa1d138bb2660a4fc158`. Python,
  the venv, prek, hook caches and docs tooling are mounted from the closure, not baked in.
- Generator: `scripts/ci/verify_full_manifest.py` reuses the verifier's `inventory`,
  `validate_closure` and `validate_membership`, and derives the node/skip baseline from a
  discovery run's reports (`--from-reports`). 14 closure rows, ~34,700 members, 2,830
  source files, 4,680 nodes, 101 skips. The dispatcher's `read_review` accepts it.
- **Custody caveat.** The manifest and its hash are produced by the party that runs the
  gate. That is self-attested custody, not the independent review the v3 schema
  envisaged; the generator prints this. The manifest binds exact bytes: any commit, any
  `.pyc` written into `.venv`, or any prek cache change invalidates it — regenerate
  immediately before `--prepare`, and export `PYTHONDONTWRITEBYTECODE=1` in between.

## `heavy-job` admission needs an owner-authorized age deferral

`--prepare` must run under the workstation wrapper. A plain `heavy-job run` exits 74:
`retained-run enforcement failed: process-reference scan incomplete` for
`run-1788137699…`, `run-1789025931…`, `run-1789118712…`.

**This is deliberate workstation policy, not a defect** (an earlier revision of this note
said otherwise; that was wrong). Those runs are past the 72 h age limit, so the wrapper
must clean them before admitting new work. Cleanup requires that every kernel-protected
same-UID process present now is in the run's recorded `protected_process_baseline`
(`pid:start-time`): a protected process that appeared after the run might hold a
reference to its scratch and cannot be inspected. After a reboot every protected process
is new, so cleanup cannot be proven safe. Workstation ADR-0011 rejects rebasing
baselines, copying current identities into old metadata and a reboot-based proof, and
routes any change of those semantics through the owner decision membrane.

The sanctioned route is workstation ADR-0019 / Decision 160: name the aged terminal runs
and defer only their age debt for one invocation. Nothing old is deleted or rewritten and
every other gate still applies. Each invocation needs the workstation owner's
authorization; the owner gave it in session on 2026-09-18 for the single DSPx
`--prepare` below. Nothing was worked around and no wrapper code was changed.

## Official run procedure

```
IMG=$(docker image inspect dspx-verify-full:local --format '{{.Id}}')
# 1. discovery at the exact HEAD -> reports; 2. generate; 3. prepare; 4. execute
/usr/bin/python3 -I -S -B scripts/ci/verify_full_manifest.py --image "$IMG" \
  --out <manifest> --logs <fresh> --from-reports <offline/reports> <residual/reports>
heavy-job run --label dspx-verify-full-prepare --task <id> \
  --defer-retained-ages <aged-run>,<aged-run>[,...] --retention-decision 160 -- /bin/sh scripts/ci/verify-full.sh \
  --prepare --owner-admitted --heavy-job-admitted --review <manifest> \
  --review-sha256 <sha> --prepared <fresh> --logs <fresh>
/bin/sh scripts/ci/verify-full.sh --execute --owner-admitted --review <manifest> \
  --review-sha256 <sha> --prepared <prepared> --job <fresh> --logs <fresh> \
  --expected-task <claimed task id> --claimant <claimant>
```

`--execute` requires the claimant to hold a live AK claim on `--expected-task`, and all
paths must be fresh, absolute, disjoint, and outside both the repository and `/tmp`.
