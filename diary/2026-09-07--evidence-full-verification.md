---
summary: "AK-5511 independent full-gate attempt failed: baseline contract failures and incompatible namespace semantics; no retry or repair."
read_when:
  - "Reviewing the September 9 AK-5511 full validation receipt or planning a separately authorized successor attempt."
---

# AK-5511 independent full verification — observed 2026-09-09

## Decision / exact receipt

**FAIL: the actual full gate returned 1. Full validation remains unsatisfied.**
No SHIP, release, lifecycle completion, repair, commit, push, or retry is claimed.

- Root: `/home/tryinget/ai-society/softwareco/owned/dspx`, branch `main`.
- HEAD before/after: `92443fbee2ceb72c8844482215342ac76ed3211a`.
- Reviewed tracked diff SHA-256 before/after gate:
  `8c6d8dff527d8863fee000678816ed0c6a1a13567a068b579863a24c244631b9`.
- New gate test SHA-256:
  `8201456a74e98bd166bd06546d54dae8b2df0a68459ea9d9804b1a8befeda456`.
- Wrapper observation window: `2026-09-09T06:26:06Z`–`06:28:25Z`.
- Runner: `run-1788935170-066132954db9cde8`, task `5511`,
  label `ak5511-verify-full`, exit **1**, `scratch_cleanup=removed`.
- Admission: named-run age-only deferral, Decision **154**,
  retained run `run-1788137699-9655c994d9827ead`.
- Runner manifest timestamps: admission `06:26:10Z`, completion `06:28:15Z`.
- Exact preserved output: `2026-09-07--evidence-full-verification/full-run.log`;
  SHA-256 `0c1edeacde139bcd600893e7df0415554ef45f38475bbff24f80ecb8c07737c1`.
- Sibling evidence directory preserves argv, tool PATH, before/after inventories,
  reviewed diff, status, timestamps, exit, and owner runner failure record.

## Preflight and execution variant

Read the target ancestry, local engineering notes/compact policy, workflow,
AK-5511 live task/scope (claimed, version 5), and Decision154 passport (accepted,
unblocked). AK listed only task5511 as claimed in DSPx. Direction list read;
effective-routing show returned `AK_DIRECTION_ROUTING_UNINITIALIZED` (no canonical
cutover row), not an invented route. The explicit dispatched task remained the
execution binding. Upstream remote engineering retrieval was not attempted.

Read installed runner help and implementation of the age-deferral path. It performs
normal locking, twice-validated retained census, headroom and readable-current-UID
reference inspection. No guard override, test mode, waiting, old cleanup,
displacement, or worker-scan skip was used. Initial status was free. Admission
reported **7 kernel-protected processes outside reference inspection**; this is
an explicit visibility limit, not proof those processes were inactive. The host
runner was not put inside the namespace.

Executed once, from DSPx root:

```bash
env -i HOME="$HOME" PATH="$PATH" LANG=C.UTF-8 TMPDIR="$TMPDIR" \
  UV_OFFLINE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  PYTHONDONTWRITEBYTECODE=1 MLFLOW_ENABLE=0 DSPX_PROVIDER=stub \
  heavy-job run --label ak5511-verify-full --task 5511 \
  --defer-retained-age run-1788137699-9655c994d9827ead \
  --retention-decision 154 -- unshare -Urn just verify-full
```

The actual `just verify-full` and all repository selections were unchanged.
`env -i` removed ALL inherited live opts, credentials, policy overrides, pytest
selection overrides, runner overrides, including Oracle VLLM/Postgres/BERT opts.
The runner replaced TMPDIR with its own home-backed scratch. No ancestor `.env`
was present. Pinned hook repositories and both prepared hook environments were
already cached; offline `uvx prek --version` succeeded. No hooks-install, sync,
remote install, model download or live-provider validation was requested.

`sentence_transformers` was absent via `find_spec` both directly and under the
sanitized `uv run --no-sync` interpreter, without importing that library. That
absence protects the three dependency-gated real-embedding cases **on this
installation only**. Network isolation alone would not prevent cached inference.
Reviewed other selected embedding tests use mock/fake backends.

## Passing evidence — observed

- Workflow, direction-document, governance-declaration and AK-5511 working-tree
  scope checks passed. Governance output is a declaration, not lifecycle proof.
- All five cached hook checks passed; no file rewrites observed.
- Both package and complete-test `ty` checks passed.
- Replay success and intentionally corrupted cache-code hash rejection passed.
- Monorepo boundaries passed.
- Module synthesis: 3 corpus runs, selection integrity and receipt coverage 1.0,
  quality gates PASS. Generated JSONL bytes matched their pre-run contents.
- Full offline xdist pool: **4067 passed, 85 failed, 5 skipped**, 5 warnings,
  120.25 seconds. No subset was substituted for the full-gate invocation.
- Independent source inspection confirmed the reviewed Oracle gate rejects
  non-exact flags/bypass/restrictive policy before HTTP and does not grant policy;
  effect-counted local tests cover default/malformed flags, deny-over-allow,
  unavailable fake HTTP, and permitted fake success. BERT tests use fake module
  imports and cover collection, malformed opt-ins, empty/mismatched inputs,
  options, argument order, F1 aggregation and macro delegation.
- Earlier 101-pass/2-skip and 38-negative-mutant results remain prior-review
  evidence supplied by dispatch, not newly rerun independent results.

## Confirmed discrepancies — high confidence

1. Runtime docs strict check fails on three unchanged, out-of-slice diaries
   lacking front matter/read_when:
   `2026-09-03--implementation-foundry-jury-child-retention-and-xai-timeout.md`,
   `2026-09-03--implementation-foundry-jury-fresh-subprocess-and-split.md`, and
   `2026-09-03--implementation-foundry-jury-preflight-and-catalog.md`.
2. Three source-loader tests fail before their intended positive/drift/pyc
   assertions because the preledger pin for `model_roles.py` is stale relative
   to both HEAD and worktree. Runner pin:
   `a7a4dc03afcbc2726d62ab4b11b951bf8d32c069652d34423c3ec08e751015a2`;
   actual HEAD/worktree:
   `30c8f3c935e9a59b03f386d6f1525b2fa66bc36735ef611c3b75ae97b1cef8c2`.
   Fail-closed rejection is observed; this does not authorize updating the pin.
3. **The chosen namespace variant is incompatible with full-suite assumptions.**
   A read-only diagnostic confirmed host UID1000 becomes namespace UID0, while
   host-root-owned `/` and `/home` appear UID65534. Private-path walkers accept
   only `{0, geteuid()}` ancestors. Logs show 43 Soomfon and 25 ledger failures
   at those ancestor guards. Namespace loopback was DOWN; 12 fake local catalog
   tests report transport/credential-probe failures. Two permission-negative
   tests did not raise (candidate unreadability and journal privacy).
   The ownership/link facts are confirmed; attribution of every individual
   failure to this variant is strongly supported, **not counterfactually tested**.
   These 82 failures must not be presented as 82 demonstrated host regressions.

## Coverage gaps / untested risks

- Offline branch failure prevented `test-residual-serial`; its live/model/network/
  GPU/Postgres selection was **not executed**, not passed. Five offline skips
  were counted, but the quiet log does not enumerate every skip reason.
- No live service, real credential, model inference, semantic-model quality,
  installed-package/release proof, or external activation was validated.
- Local fixture HTTP was blocked too; its transport/error and state-transition
  assertions therefore remain unproven under a compatible isolated environment.
- Custody, malformed input, interrupt/reconcile, tombstone, concurrent-owner and
  finalization tests that failed early do not prove their downstream invariants.
- No injected interruption of this actual full runner, no unisolated rerun,
  and no repair were performed. Existing subprocess fork deprecation warnings
  are not a demonstrated deadlock.
- Network isolation plus cleared opts/absent dependency supports the bounded
  no-live-effects posture; no syscall audit or exhaustive home/cache audit was
  performed. Other ignored files were inventoried only after execution, so that
  listing is not proof they were newly created or unchanged.

## Effects / custody / next step

All tracked plus nonignored untracked input hashes were identical before/after
execution: inventory SHA-256
`60170424e4b413a71df94e50eb5bc47843cd20be76a649e4eb64fb7697157ce2`.
The `.ontology` files, existing `generated/ci` files, and both retained manifests
also matched byte-for-byte. HEAD, reviewed diff, lockfile, gate selection, hooks,
and tests were unchanged. Ordinary pytest/prek caches and new-run scratch were
permitted effects; the runner removed only its own newly created scratch and
retained a failure record. Evidence copies and this note were written afterward,
within the dispatched diary scope. No staging or sweeping cleanup occurred.

Stop here. Owner/controller should separately authorize baseline diary metadata
and reviewed-pin diagnosis/repair, and review a network-isolation runner variant
that preserves required UID/permission semantics and permits only repository-local
fixture loopback without granting access to host services. Only then consider a
fresh normal heavy-job admission and unchanged full gate. Do not weaken custody
checks, replace the test set, infer success from partial passes, or retry this
attempt implicitly.


## Bounded successor checks only — 2026-09-09

The separately admitted metadata/synthetic-fixture repairs now have independent
bounded SHIP and passing focused final-source/static/native strict metadata checks;
see `diary/2026-09-07--evidence-finalization.md`. This is **not a full-gate retry or
pass**: `run-1788935170-066132954db9cde8` remains exit1, with the exact counts and
isolation-attribution limits above. The 82 attributed cases were not counterfactually
rerun. The raw sibling directory remains unchanged and untracked, deliberately
excluded from the bounded commit because it contains large redundant snapshots
and the 301035-byte log; the compact receipt retains its inventory/hash reference.
No custody guard, production pin or full-suite selection was weakened. A compatible
no-live variant and separate full-run admission remain required.
