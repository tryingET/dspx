---
summary: "Write-free preflight and read-only catalog check for task-local foundry comparison juries (AK-5354, Phase 1 items 5-6)."
read_when:
  - "You are about to run a task-local foundry comparison jury and want to know what --preflight-only proves and does not prove."
  - "You are changing program_foundry_gepa_comparison_jury_preflight*.py or the FoundryJuryProviderFamily.catalog_path field."
type: "reference"
---

# Foundry comparison jury: pre-marker preflight and catalog check

Companion to `2026-09-01-foundry-dspy-lm-auth-jury-integration.md` (not edited here). This
document covers only the AK-5354 Phase 1 hardening that runs **before** the comparison-jury
attempt marker exists. Nothing here changes the attempt, receipt, `execution_request`,
`_request_identity`, journal reservations, provider metadata, or prompt text.

## What runs, and when

`execute_program_foundry_gepa_comparison_jury` calls
`run_task_local_preflight(request, experiment_root=..., expected_juror_count=..., repo_root=...)`
(module `program_foundry_gepa_comparison_jury_preflight.py`) for the four task-local families
after the existing receipt/attempt/result checks and before the model-jury process slot and
`_write_json_exclusive(paths["attempt"], ...)`. Generic providers are untouched. Any rejection
raises `ProgramFoundryGepaComparisonJuryError` (CLI exit 2) and leaves no attempt marker, no
`provider-outcomes/` directory, and no results file; zero provider completion calls occur.

Gates, in order:

1. `family_for_request` binds the exact endpoint retained in the request; `model_re` and the
   receipt route charset remain the first model gate.
2. `expected_juror_count` from `jury_selection.json` next to the candidate manifest, truncated by
   `max_jurors`; zero selected jurors is rejected here (previously only after the marker).
3. `sys.dont_write_bytecode is True` and `PYTHONDONTWRITEBYTECODE=1`.
4. `dspy_lm_auth` is not already imported into the parent process.
5. `DSPX_CACHE_DIR` set, absolute, an owned non-symlink directory with no group/world write
   bits, outside the owner source root. Exact `0700` is deliberately **not** required: staged
   lineages keep the candidate run receipt under `<lineage>/cache` (created `0755` by the foundry
   tooling) and consumption re-validation (`check_run_receipt`) binds that exact root, so the
   jury must run with `DSPX_CACHE_DIR=<lineage>/cache`.
6. `experiment_root` passes `_private_directory` (`0700`) and `experiment_root/provider-outcomes`
   does not exist.
7. `verify_foundry_jury_owner_source` (exact commit/tree, clean `status --porcelain`, pinned
   module hashes, no bytecode). `verify_owner_source` already runs the git checks, so no second
   `git rev-parse` was added.
8. Installed dependency identity (`dspy`, `litellm`, `httpx`, `httpcore` RECORD/payload digests)
   equals `expected_foundry_jury_dependency_identity()` without importing the owner.
9. `canonical_ak_task_revalidator(minimum_lease_seconds=expected_juror_count * 60 + 30, family)`
   through the pinned read-only AK reader (one `ak task show`).
10. Credential and catalog probe in an isolated child (below). Skipped credential read for
    `auth_provider == "none"` (local vLLM); no catalog for Codex.

## The probe child

`program_foundry_gepa_comparison_jury_preflight_probe.py` is executed as
`sys.executable -I -B <probe> '<json config>'` with stdin `/dev/null`, env scrubbed to
`HOME PATH SSL_CERT_FILE SSL_CERT_DIR LANG LC_ALL PYTHONDONTWRITEBYTECODE=1`, a 5 s bound
(15 s when a catalog GET is configured), 256 KiB output cap, `start_new_session=True`. It imports
only the standard library and `httpx`, never `dspx` or the `dspy_lm_auth` package. It loads the
owner's hash-pinned `src/dspy_lm_auth/auth.py` via `spec_from_file_location` under a non-package
alias, calls `read_existing_oauth_credential_without_refresh(DEFAULT_PI_AUTH_PATH, auth_provider)`
and `validate_oauth_credential_expiry`, and for Copilot checks
`github_copilot_base_url(token) == GITHUB_COPILOT_API_BASE`. The bearer token never enters the
parent process; the child prints only

```json
{"credential_present": bool, "expiry_ok": bool, "expires_ms": int, "endpoint_fixed": bool,
 "catalog": {"status_class": str, "status_code": int, "catalog_count": int,
             "catalog_ids_sha256": str, "model_listed": bool} | null}
```

## Catalog check (item 6)

`FoundryJuryProviderFamily.catalog_path` (`None` for Codex; `/models` for Copilot and local vLLM;
`/v1/models` for xAI whose `endpoint_origin` is `https://api.x.ai`) yields `catalog_url`:

| family | catalog_url | auth |
| --- | --- | --- |
| Codex | none (regex only) | no read |
| GitHub Copilot | `https://api.individual.githubcopilot.com/models` | bearer + fixed non-secret Copilot headers |
| xAI | `https://api.x.ai/v1/models` | bearer |
| local vLLM | `<bound loopback base>/models` | none |

One `httpx` GET inside the probe child: timeout 10 s, no retries, no redirects, `trust_env=False`,
`Accept-Encoding: identity`, 1 MiB body cap. It fails closed on non-2xx (including 429), timeout,
non-JSON, oversized body, or when the requested model id is not in `data[].id`. It is never a
completion call. Codex has no listing API in the fork and adding one would force a repin, so it
stays regex-only.

## CLI

- `--preflight-only`: runs every gate above, prints `{"status": "preflight_ok", "preflight": {...}}`
  and exits 0; exits 2 on rejection. Writes nothing.
- A live run's `--json` output carries the same facts under `"preflight"`. They are **not** bound
  into the attempt marker or the receipt; retained artifacts are byte-identical to before.

## What the preflight proves, and what it cannot

It proves, at T0: exact owner and dependency identity, bytecode and destination posture, an active
AK claim whose lease covers every selected juror, provider reachability, credential presence and
validity, and catalog membership of the requested model.

It cannot prove capacity or entitlement at completion time. A provider-side 429 on the first juror
call after the attempt marker still burns the one-shot slot by design; the marker is the honest
record that a provider effect was possible. The preflight shrinks the window of avoidable burns
(expired token, unserved model, stale lease, wrong cache root) and nothing more.

## Dry run (AK-5353 staged xAI lineage, 2026-09-03)

`--preflight-only` against `misegraph-foundry-xai-5353.jrIysb` with
`DSPX_CACHE_DIR=<lineage>/cache`, owner root `dspy-lm-auth-owner-I1M2`, task 5353, claimant
`claude-code:508c6e1b`: exit 0, `expected_juror_count=3`, `ak_minimum_lease_seconds=210.0`,
credential present and valid, `catalog_count=12`, `model_listed=true` for `grok-4.6`,
`provider_completion_calls=0`. A before/after file listing of the lineage and owner trees showed
no lineage change; the only delta was the owner checkout's `.git` directory mtime from the
pre-existing `git status --porcelain` owner verification. With a temporary cache root instead of
the lineage's own, consumption re-validation rejects before the preflight ("candidate receipt is
not reusable"): the run receipt must live under `DSPX_CACHE_DIR`.

## Retained artifact revalidation

`validate_successful_program_foundry_gepa_comparison_jury_receipt` with each lineage's own cache
root: AK-5346 (Copilot) and AK-5352 (local vLLM) validate byte-for-byte. AK-5322 (Codex,
`misegraph-foundry-dogfood.aNniZ0`) fails with `task-local provider metadata drifted` both before
and after this change: its metadata binds owner commit `755a3787...`, and the owner was repinned
to `777388ad...` afterwards. That is pre-existing pin drift, not a preflight effect.

## Deferred

- Item 8 (fresh subprocess per jury) landed in slice D; see "Fresh subprocess" below.
- No unbound preflight sidecar file is written; facts surface through CLI output only.

## Fresh subprocess (item 8, slice D)

Every task-local jury now runs in its own interpreter. After the parent has taken the foundry
lock, passed the preflight, taken the in-process model-jury slot and written
`comparison-jury-attempt.json`, it runs

```
sys.executable -I -B -m dspx.services.program_foundry_gepa_comparison_jury_child
```

with one closed request object on stdin (`dspx-foundry-jury-child-request-v1`: the normalized
`execution_request`, `experiment_root`, `attempt_sha256`, the candidate manifest and comparison
paths, and the pre-marker input hashes). The child re-normalizes the request with
`revalidate_execution_request`, takes its own task-local and model-jury process slots, builds the
task-local runtime binding (owner verification, AK revalidation, provider journals under
`<experiment_root>/provider-outcomes`) and runs `build_comparison_model_jury_result` exactly as the
in-process path did. It prints one JSON object (`dspx-foundry-jury-child-result-v1`) on stdout and
nothing else.

Parent-side bounds: stdin is the request, stdout is capped at 16 MiB, stderr goes to `/dev/null`,
the environment is scrubbed to `HOME PATH LANG LC_ALL SSL_CERT_FILE SSL_CERT_DIR DSPX_CACHE_DIR`
plus fixed `DSPX_CACHE_ENABLE=0 MLFLOW_ENABLE=0 PYTHONDONTWRITEBYTECODE=1` and the family's endpoint
variable (`DSPX_LOCAL_VLLM_BASE_URL`) when it is set, `start_new_session=True`, and the timeout is
`selected_jurors * 60 s + 60 s`. On timeout the whole child session is killed with SIGKILL.

Failure semantics are unchanged in spirit and stricter in mechanism: a nonzero exit, a timeout,
unparsable stdout or a drifted result shape raises `ProgramFoundryGepaComparisonJuryChildError`
(a `RuntimeError`, CLI exit 3). The attempt marker stays in place, so the next run answers
`blocked_indeterminate`; no result or receipt is written. The parent validates the child's result
and writes `comparison-jury-results.json` and `comparison-jury-receipt.json` exactly as before;
retained artifact formats do not change and the AK-5346 / AK-5352 receipts revalidate
byte-for-byte.

What the child guarantees at start-up, and `--self-check` prints without reading any input:
`sys.flags.isolated`, `sys.dont_write_bytecode is True`, and no `dspy_lm_auth*` module loaded. The
child refuses to run a request when any of those is false. The parent process never imports the
owner package during a task-local run; the old `preflight_task_local_request` `sys.modules` check
is therefore enforced where it matters, in the process that will call the provider.

Generic (registry) providers keep running in-process. `_CHILD_ARGV = None` on the orchestrator
module is a test-only seam that restores the in-process path so fixtures can patch
`build_comparison_model_jury_result`; it is never set in production.
