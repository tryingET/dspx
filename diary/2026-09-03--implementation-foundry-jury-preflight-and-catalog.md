# 2026-09-03 — foundry jury: pre-marker preflight, catalog check, evidence-gap tests (AK-5354, slices A-C)

Plan: `~/.claude/jobs/508c6e1b/tmp/plan-phase1-dspx.md`. Slice D (fresh subprocess per jury)
deliberately not started; A-C are green and D changes the execution path, so it gets its own pass.
Nothing committed; no AK mutation (only `ak task show` through the pinned reader).

## What landed

- New `program_foundry_gepa_comparison_jury_preflight.py` (381 lines): `run_task_local_preflight`,
  `selected_juror_count`, `probe_credential_and_catalog`, `run_probe`. Closed facts dict
  (`dspx-foundry-jury-preflight-v1`), never bound into attempt/receipt.
- New `program_foundry_gepa_comparison_jury_preflight_probe.py` (216 lines): the `-I -B` child.
  stdlib + httpx only; loads the owner's hash-pinned `auth.py` by file location under an alias;
  prints five closed keys; does the one catalog GET so the bearer never enters the parent.
- `FoundryJuryProviderFamily.catalog_path` / `catalog_url` (None Codex, `/models` Copilot and
  vLLM, `/v1/models` xAI). Default `None` keeps every pinned-literal test unchanged.
- `_jury.py`: preflight call replaces `preflight_task_local_request` (kept in `_runtime.py` for
  rollback); `preflight_only` keyword returns `{"status": "preflight_ok", "preflight": ...}` before
  the model-jury slot; live-run return dict carries `"preflight"` for task-local families.
  `_jury_input_sha256` now maps `ProgramFoundryGepaProposalError` (missing rubric/selection/
  comparison) to `ProgramFoundryGepaComparisonJuryError` so a partial bundle exits 2, not 3
  with the misleading "provider calls may have occurred" text.
- CLI `--preflight-only` (prints facts, exit 0/2, writes nothing).
- Doc: `docs/project/2026-09-03-foundry-jury-preflight.md` (integration doc untouched).

## Deviations from the plan, and why

1. **Cache dir posture**: plan asked for `_private_directory` (exact 0700) on `DSPX_CACHE_DIR`.
   Staged lineages create `<lineage>/cache` as 0755 and `check_run_receipt` requires the
   candidate run receipt to live under `DSPX_CACHE_DIR`, so consumption re-validation already
   forces `DSPX_CACHE_DIR=<lineage>/cache`. With exact-0700 the dry run could never pass without
   `chmod` on a lineage dir (a stop condition). Implemented: absolute, owned, non-symlink dir,
   no group/world write bits, outside the owner root. Tests cover 0755 accept / 0775 and symlink
   reject.
2. **Test seam rename**: four existing tests patched `comparison_jury.preflight_task_local_request`
   with `lambda request: None`; the new call takes keywords, so those four lines now patch
   `run_task_local_preflight` with `lambda request, **kwargs: None`. No literals changed.
3. **Slice C shared-validator tightening not done**: requiring the six-key judgment set or an
   `error` object for failed jurors in `_validate_juror_results` would break existing fixtures
   (`_model_result` uses two-key judgments; `test_program_promotion_refinement` pins the
   `judged juror` message for a bare failed juror). The six-key rule is tested where it is
   enforced (`parse_model_judgment`, parametrized over each missing key); the failed-juror
   `error` guarantee is tested producer-side on `run_program_model_jurors`.
4. **Zero-juror rejection** applies to task-local families only; the generic-provider fixture
   in the existing jury tests has no `selected_jurors` and mocks the model jury.
5. `git rev-parse`/`status --porcelain` equality was already inside `verify_owner_source`; no
   duplicate added.
6. Optional unbound sidecar file: not written (facts via CLI output only).

## Validation

- `uv run --no-sync pytest -q` over the eight plan test files: 283 passed (baseline before new
  tests: 242; preflight file alone: 28).
- ruff format --check / ruff check on touched files: clean. `ty check` on touched src: clean.
  `git diff --check`: clean. `uvx prek run --all-files`: passed.
- `just check` fails only in `task-scope-check` because three tasks (5353, 5354, 5355) are claimed
  on this repo; `just task-scope-check task_id=5354` passes (repo-default scope). Other
  `verify-fast` steps pass.
- Archived receipts (each lineage's own `DSPX_CACHE_DIR`): AK-5346 Copilot and AK-5352 vLLM
  validate byte-for-byte. AK-5322 Codex fails `task-local provider metadata drifted` at HEAD too
  (bound owner commit 755a3787 predates the 777388ad repin): pre-existing, not from this change.
  Without a cache root all three fail earlier in consumption re-validation
  ("candidate receipt is not reusable"), which is how the cache-posture deviation was found.

## Dry run (write-free)

`PYTHONDONTWRITEBYTECODE=1 DSPX_CACHE_DIR=<lineage>/cache uv run --no-sync dspx program-refine
jury-foundry-gepa-comparison --receipt .../consumption-receipt.json --provider
foundry-dspy-lm-auth-xai --owner-source-root <owner-I1M2> --execution-task-id 5353
--execution-claimant claude-code:508c6e1b --preflight-only` -> exit 0, `preflight_ok`:
3 jurors, lease minimum 210 s (AK 5353 claimed by that claimant, lease to 18:38Z), owner commit
777388ad verified, dependency identity verified, credential present/valid (expires
2026-09-03T20:16Z), xAI catalog 2xx with 12 ids and `grok-4.6` listed, 0 completion calls.
Before/after `find -printf` listing over lineage + owner: no lineage change; only the owner
`.git` directory mtime moved (pre-existing `git status` in owner verification). No `__pycache__`
under lineage or owner. A first attempt with a temporary 0700 cache root exited 2 at consumption
re-validation and also wrote nothing.

## Open items for the next pass

- Slice D (per-jury `-I -B` child, `_CHILD_ARGV` seam, child self-check test).
- `_jury.py` is 666 lines (was 628): over the 500-line budget before this change; a split of the
  receipt-revalidation half into its own module is the obvious cut.
- AK-5322 Codex receipt no longer revalidates against current owner pins; decide whether
  historical receipts should validate against their own bound pins.

Follow-up: slice D and the module split landed in
`diary/2026-09-03--implementation-foundry-jury-fresh-subprocess-and-split.md`.
