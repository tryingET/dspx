---
summary: "AK-5355 Phase 2 slices D1-D3: read-only misegraph-evidence-package-v1 loader, deterministic intent/inputs/binding importer, `dspx foundry import-misegraph-evidence`, docs; offline stub smoke green, foundry itself not run."
read_when:
  - "Resuming the Misegraph <-> DSPx evidence seam (M3 verify-receipt after a real run, quality acceptance for the emitted intent)."
  - "Checking why `foundry` became a Typer group or where the answers-file hash lives."
type: "diary"
---

# Implementation: foundry Misegraph evidence import (D1-D3)

## What changed

- New `services/program_foundry_misegraph_evidence_package.py` (487 lines):
  `load_misegraph_evidence_package(dir)` — directory-fd + `O_NOFOLLOW` reads, closed manifest keys
  at every level (derived from `misegraph/src/evidence.rs`), canonical-form byte equality,
  `package_sha256` recomputation, per-artifact byte length + sha256, required artifact kinds,
  stray/hidden file rejection, plain-name guard, `canonical.json` validated against the packaged
  `schema.json` with `jsonschema` (structural fallback), `behavior.json` cross-checked against the
  manifest. Never writes.
- New `services/program_foundry_misegraph_evidence.py` (487 lines): answers loader
  (`dspx-misegraph-example-answers-v1`), `build_misegraph_intent` (reference template + one
  example per selected case, evidence = compact canonical JSON of
  `{recipe, package_sha256, source, canonical, render, check, case}`), `build_misegraph_inputs`,
  `build_misegraph_binding` (exact `receipt.rs` shape), `write_import_bundle` (preflight guards,
  atomic `link()` no-clobber writes of intent/inputs/binding/provenance),
  `build_misegraph_source_projection`.
- New `cli/commands/program_foundry_misegraph.py` (81 lines) and `cli/dspx.py` registration:
  `foundry` is now a Typer group (`foundry_app`) with an `invoke_without_command=True` callback
  holding the unchanged run; its four required options became `Optional` with an explicit
  "required when foundry has no subcommand" guard (exit 2). `dspx foundry --intent ...` behaves
  as before; `dspx foundry import-misegraph-evidence ...` is the new subcommand.
- Fixture: `tests/fixtures/misegraph-evidence-package-v1/espresso-brownies/` (real export,
  `package_sha256 0be06d8d…4905`, `manifest_sha256 5c1fd0f5…c5e4`) plus
  `espresso-brownies-answers.json`.
- Tests: `tests/test_program_foundry_misegraph_evidence.py` (34 tests, 737 lines).
- Docs: `docs/project/2026-09-03-foundry-misegraph-evidence-import.md`,
  `docs/learnings/2026-09-03-misegraph-evidence-import-closed-consumer-schemas.md`.

## Decisions worth remembering

- Answers hash is **not** in the binding: every binding struct in `receipt.rs` is
  `deny_unknown_fields`, so adding a key would make Misegraph reject the binding. It lives in
  `misegraph-import-provenance.json`; the intent hash binds it transitively. Deviation from the
  task wording, deliberate.
- `preflight_foundry_paths` was not reused: it requires a quality-proposal path the importer
  does not have. The importer has its own guards (symlink outdir, outdir inside package, package
  inside outdir, Misegraph repo root via `Cargo.toml name = "misegraph"`, answers inside outdir).
- Non-example intent fields are copied verbatim from the AK-5346 reference intent, including the
  `options.quality_proposal` / `options.normalization` provenance hashes (`f70a8862…`). This is
  what "accept unchanged" requires; the test pins the intent-minus-examples hash
  `58429c80…c5e6`. A fresh quality acceptance is still needed before `dspx foundry`.
- `render.text.txt` is required for the intent (text render is part of the evidence) but the
  loader treats render artifacts as optional, matching the producer's `ExportOptions.formats`.

## Validation

- `uv run --no-sync -m pytest -q tests/test_program_foundry_misegraph_evidence.py` → 34 passed.
- `... tests/test_program_foundry.py tests/test_program_foundry_gepa_workflow.py` → pass.
- `tests/test_cli_dspx.py`: 2 pre-existing failures (`optimize gepa --help` lacks
  `--proposal-sampling` / `--num-threads` on an unmodified `optimize.py`); unrelated.
- ruff check/format, ty check on touched src: clean; `just lint` and `just typecheck-core` on the whole
  tree: clean. `git diff --check`: clean.
- `just check`: workflow/direction/governance checks pass; `task-scope-check` without an id aborts
  because 5353/5354/5355 are all claimed on this repo — `just task-scope-check task_id=5355` passes
  (repo-default scope), `uvx prek run --all-files` passes.
- Offline smoke in `$TMPDIR/misegraph-import-smoke-5355.*`: `program-gen --print-manifest` rc=0
  (3 s), `program-run --skip-oracle-index --json` rc=0 (1 s), `effect.ak_called=false`.
  Environment: `DSPX_PROVIDER=stub DSPX_ORACLE_SEMANTIC_BACKEND=fixture-replay MLFLOW_ENABLE=0
  DSPX_REPLAY_FIXTURE_JSON={"reasoning": <objective>, "answer": <examples[0].answer>}`.
- `dspx foundry` not run: it needs a quality envelope whose `candidate_intent` equals the emitted
  intent (the AK-5346 envelope does not) and then a per-run authored fixture entry
  (`authored_fixture_replay`). The Oracle request hash is therefore unknown for this bundle.

## Open items / handoff

- M3 (Misegraph `evidence verify-receipt`) needs a real DSPx run: quality acceptance for the
  emitted intent, foundry, GEPA execute/consume, jury, adjudication; then point verify-receipt at
  `misegraph-evidence-binding.json` from this importer.
- Integration doc section "Misegraph evidence package import" is owned by another agent; this
  slice added a standalone project doc instead.
- Nothing committed; no AK mutation; no network.
