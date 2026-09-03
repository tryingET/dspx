# 2026-09-03 — foundry jury: fresh `-I -B` child per task-local jury, module split (AK-5354, slice D)

Plan: `~/.claude/jobs/508c6e1b/tmp/plan-phase1-dspx.md`, slice D, on top of slices A-C
(`54568ce2`, `diary/2026-09-03--implementation-foundry-jury-preflight-and-catalog.md`).
Nothing committed; no network; no provider completion calls; no AK mutation.

## What landed

- New `program_foundry_gepa_comparison_jury_child.py` (330 lines). Parent side:
  `default_child_argv()` = `sys.executable -I -B -m dspx.services.program_foundry_gepa_comparison_jury_child`,
  `child_environment(family)` (allowlist `HOME PATH LANG LC_ALL SSL_CERT_FILE SSL_CERT_DIR
  DSPX_CACHE_DIR`, fixed `DSPX_CACHE_ENABLE=0 MLFLOW_ENABLE=0 PYTHONDONTWRITEBYTECODE=1`, plus the
  family's endpoint env when set), `child_timeout_seconds(n)` = `n*60+60`,
  `child_request_payload(...)`, `run_task_local_jury_child(argv, payload, env, timeout)`: Popen
  with stdin request, stdout cap 16 MiB, stderr devnull, `start_new_session`, SIGKILL of the
  session group on timeout, `ProgramFoundryGepaComparisonJuryChildError(RuntimeError)` on nonzero
  exit / timeout / non-JSON / drifted shape. Child side: `main` refuses a non-isolated or
  bytecode-writing interpreter or any pre-loaded `dspy_lm_auth*` module, reads one request (1 MiB
  cap), `revalidate_execution_request`, takes `task_local_process_slot` and
  `_model_jury_process_slot`, `make_task_local_runtime_binding` + `build_comparison_model_jury_result`,
  prints `{"schema_version": "dspx-foundry-jury-child-result-v1", "result": ...}`; prints nothing
  on failure. `--self-check` prints `{isolated, dont_write_bytecode, owner_modules_at_start}`.
- `program_foundry_gepa_comparison_jury.py` (666 -> 414 lines): `_CHILD_ARGV` module seam
  (`None` = in-process, test only); `_run_jury` dispatches task-local families to the child and
  generic providers to the in-process path. Marker, result and receipt writes, post-run lineage
  re-validation and `preflight` passthrough unchanged. Parent still takes the in-process
  model-jury slot before the marker (keeps the pre-marker contention test).
- Split: `program_foundry_gepa_comparison_jury_attempt.py` (263 lines: sha256/canonical JSON,
  snapshot loaders, exclusive sidecar write, `jury_paths`, `jury_input_sha256`, `attempt_payload`,
  `validate_attempt`, `blocked_indeterminate_payload`) and
  `program_foundry_gepa_comparison_jury_receipt_validation.py` (108 lines: `_validate_jury_result`,
  `_validate_existing_receipt`). `validate_successful_program_foundry_gepa_comparison_jury_receipt`
  stays in the orchestrator (see deviation 2). Every name other modules import from the
  orchestrator is still importable there; `adjudicator_dispatch`, `comparison_adjudication`,
  `workflow` and the CLI are untouched.
- Doc: "Fresh subprocess" section appended to `docs/project/2026-09-03-foundry-jury-preflight.md`;
  its "Deferred" bullet for item 8 now points there.

## Deviations, and why

1. **`_CHILD_ARGV` semantics**: the plan asked to expose it "for monkeypatching so existing tests
   keep patching `build_comparison_model_jury_result`". Fakes patched in the parent cannot reach a
   real child, so `None` means "run in this process". Five test files (`_jury`, `_preflight`,
   `_xai`, `_copilot`, `_local_vllm`) got one autouse fixture each setting it to `None`; no test
   body changed for that. The new `tests/test_program_foundry_gepa_comparison_jury_child.py` does
   not use the fixture and exercises the real default argv.
2. **Where the public receipt validator lives**: moving
   `validate_successful_program_foundry_gepa_comparison_jury_receipt` into the new module broke
   the existing test that patches `comparison_jury.validate_successful_program_foundry_gepa_consumption_receipt`
   and then revalidates the receipt (13 such patch sites across the jury tests). It stays in the
   orchestrator so those patches keep binding; the drift checks it shares with the reuse path moved
   out and are called through the module object (`receipt_validation._validate_jury_result`) so
   one patch point covers the fresh, reuse and revalidation paths.
3. **`_validate_jury_result` patch target**: the five tests that patched it on `comparison_jury`
   now patch it on `receipt_validation` (one-line retarget each, same lambda). No other test
   change.
4. **Child posture fact**: a `dspy_loaded_at_start` fact was dropped; `dspx/__init__` imports
   `dspy`, so it is always true for a `-m dspx...` child and says nothing about freshness. The
   three facts that matter (isolated, no bytecode, no owner modules) are what the child enforces.
5. **Timeout floor**: `child_timeout_seconds` uses `max(1, n)` so a zero count (only reachable
   when preflight is patched away) still gets 120 s rather than 60 s.

## Validation

- `uv run --no-sync pytest -q` over the eight plan files + `tests/test_program_foundry_gepa_comparison_jury_child.py`:
  299 passed (283 baseline + 16 new); with `test_program_foundry_gepa_adjudicator_dispatch.py`,
  `test_program_foundry_gepa_comparison_adjudication.py` and `test_program_foundry_gepa_workflow.py`
  added as downstream importers: 333 passed.
- New tests: real `--self-check` child (isolated, no bytecode, no owner modules, `PYTHONPATH`
  ignored); real child exits 1 with empty stdout on a garbage request; `main` refuses a
  non-isolated interpreter; `run_child_request` takes the slot and binds the task-local runtime;
  env allowlist with family endpoint; faked child success path (parent never gains a
  `dspy_lm_auth*` module, env scrubbed, own session, request bound to the marker's
  `execution_request`, `attempt_sha256` and input snapshots; reuse afterwards); child failure
  leaves the marker and blocks replay; CLI exit 3; five unparsable-output shapes; timeout kills
  the child; generic provider still in-process.
- `ruff format --check` / `ruff check` on the ten touched Python files: clean. `ty check` on the
  four touched src modules: clean. `git diff --check`: clean.
- `just task-scope-check task_id=5354`: skip/pass (repo-default scope). `just workflow-contract-check`,
  `direction-contract-check`, `governance-check`: ok. `uvx prek run --all-files`: passed.
  Unqualified `just task-scope-check` still needs task disambiguation (three claims on the repo),
  as in slices A-C.
- Archived receipts, each with its lineage's own `DSPX_CACHE_DIR`, through
  `validate_successful_program_foundry_gepa_comparison_jury_receipt`: AK-5346 Copilot and AK-5352
  local vLLM validate; sha256 of `comparison-jury-{attempt,results,receipt}.json` identical before
  and after; no `dspy_lm_auth*` module in the validating process. AK-5322 Codex still fails
  `task-local provider metadata drifted` (pre-existing owner repin drift, unchanged).

## Open items

- A live task-local run through the child has not been exercised (no network in this pass); the
  first real jury should be watched for the child's exit status and the parent's `--json` output.
- `_jury.py` is 414 lines; the CLI's generic `except Exception -> exit 3` is what maps the child
  error, so a dedicated message for "child failed" vs. "provider call failed" is possible but not
  needed.
