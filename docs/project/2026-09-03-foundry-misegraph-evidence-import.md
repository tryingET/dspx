---
summary: "Contract for `dspx foundry import-misegraph-evidence`: verified misegraph-evidence-package-v1 in, deterministic program-intent-v2 + inputs + dspx-misegraph-evidence-binding-v1 out (AK-5355, Phase 2 slices D1-D3)."
read_when:
  - "You are importing a Misegraph evidence package into the DSPx foundry flow or authoring the answers file for it."
  - "You are changing program_foundry_misegraph_evidence*.py, program_foundry_misegraph.py, or the checked-in misegraph-evidence-package-v1 fixture."
  - "You need to know what the offline (stub / fixture-replay) foundry lineage proves and what it does not."
type: "reference"
---

# Foundry: Misegraph evidence package import

Companion to `2026-09-01-foundry-dspy-lm-auth-jury-integration.md` (not edited here). This
document covers the consumer half of the Misegraph <-> DSPx evidence seam: how a
`misegraph-evidence-package-v1` directory produced by `misegraph evidence export` becomes the
`intent.json` / `inputs.json` pair that `dspx program-gen`, `dspx program-run`, and `dspx foundry`
consume, and the `dspx-misegraph-evidence-binding-v1` record that `misegraph evidence
verify-receipt` later reads back. Nothing here changes the jury receipt, adjudication, attempt,
or Oracle fixture schemas.

## Authority boundaries

- The package is evidence only. Its manifest carries `non_authority.acceptance_authority=false`,
  `release_authority=false`, `evidence_only=true`; the importer rejects any other values.
- The importer opens the package **read-only** (directory fd + `O_NOFOLLOW`), refuses symlinks
  inside or at the package dir, and never creates, renames, or touches anything under it.
- The importer refuses to write into the package dir, into a directory that contains the package
  dir, or under any directory tree whose ancestor is a Misegraph repository root
  (`Cargo.toml` with `name = "misegraph"`).
- The importer never authors an expected answer. `examples[*].outputs.answer` is copied verbatim
  from the operator-supplied `--answers` file; a selected case without an answer is a hard error.
- No AK call, no network, no Misegraph mutation. Jury consensus, adjudication disposition, and
  the eventual `misegraph-jury-recommendation-v1` record are never mapped onto an AK task state.
- The importer emits candidate material for the foundry flow; it does not grant quality
  acceptance. See "Downstream: what still has to happen" below.

## Modules

| Path | Role | Lines |
| --- | --- | --- |
| `packages/dspx-core/src/dspx/services/program_foundry_misegraph_evidence_package.py` | fail-closed package loader (`load_misegraph_evidence_package`) | 487 |
| `packages/dspx-core/src/dspx/services/program_foundry_misegraph_evidence.py` | answers loader, `build_misegraph_intent`, `build_misegraph_inputs`, `build_misegraph_binding`, `write_import_bundle`, `build_misegraph_source_projection` | 487 |
| `packages/dspx-core/src/dspx/cli/commands/program_foundry_misegraph.py` | Typer registration of `import-misegraph-evidence` | 81 |
| `packages/dspx-core/src/dspx/cli/dspx.py` | `foundry` is now a Typer group whose `invoke_without_command` callback is the unchanged foundry run; the subcommand hangs off it | registration only |
| `tests/fixtures/misegraph-evidence-package-v1/espresso-brownies/` | real `misegraph evidence export examples/espresso-brownies.mise` output (10 files, 43 KB) | fixture |
| `tests/fixtures/misegraph-evidence-package-v1/espresso-brownies-answers.json` | operator-authored answers for the fixture | fixture |

## Input contract: `misegraph-evidence-package-v1`

Field names and the canonical JSON rule are taken from the Misegraph producer
(`src/evidence.rs`, `src/evidence/store.rs`), not from memory.

- `manifest.json` is canonical JSON: 2-space pretty print, keys sorted, trailing newline. The
  importer re-serializes and requires byte equality (Python `json.dumps(indent=2,
  sort_keys=True, ensure_ascii=False) + "\n"` reproduces serde_json's output for this schema).
- Closed keys at every level (`deny_unknown_fields` on the Rust side):
  - top: `schema_version`, `producer{name,version,ir_schema_version}`, `recipe{id,title}`,
    `artifacts{<file>: {kind, format?, profile?, sha256, bytes}}`,
    `conformance{status,error_count,warning_count,deny_warnings}`, `package_sha256`,
    `non_authority{acceptance_authority,release_authority,evidence_only}`.
  - `format`/`profile` appear only on `kind == "render"` artifacts.
- `package_sha256` = sha256 of the canonical manifest serialized without that field; recomputed.
- Required artifacts and kinds: `source.mise` (`mise_source`), `canonical.json` (`canonical_ir`),
  `check.json` (`diagnostics`), `schema.json` (`ir_json_schema`), `behavior.json`
  (`behavior_cases`), `malformed.json` (`malformed_probes`), `episode.json` (`episode`). The
  intent additionally needs `render.text.txt`.
- Every artifact: plain file name (no separators, no leading dot, not `.`/`..`), regular file
  (not a symlink), byte length and sha256 equal to the manifest entry, size bounds (manifest
  1 MiB, artifact 32 MiB).
- No stray entries: `listdir(package) ⊆ artifacts ∪ {manifest.json}` (hidden files count).
- `canonical.json` validates against the packaged `schema.json` with `jsonschema`
  (draft-07 fixture); a strict structural check is the fallback if `jsonschema` were missing.
  The validator used is recorded in the provenance sidecar.
- `behavior.json` (`misegraph-behavior-cases-v1`) is closed per case; `input_sha256` must equal
  the `source.mise` hash and `output_sha256` must equal the manifest hash of `output_artifact`.

Any failure raises `MisegraphEvidencePackageError`; the CLI maps it to exit 2 as
`Error: package rejected: <reason>` and writes nothing.

## Answers file: `dspx-misegraph-example-answers-v1`

```json
{
  "schema_version": "dspx-misegraph-example-answers-v1",
  "answers": {
    "render-text": "<expected answer for the render-text example>",
    "check-json": "<expected answer for the check-json example>"
  }
}
```

Exactly two top-level keys; every value a non-blank string; keys are behavior case ids. Extra
entries for unselected cases are allowed; a missing entry for a selected case is an error. The
file's sha256 is recorded in `misegraph-import-provenance.json` and is transitively bound by the
binding's `emitted.intent_sha256` (the answers are inside the intent).

## CLI

```bash
uv run --no-sync dspx foundry import-misegraph-evidence \
  --package <dir>            # misegraph-evidence-package-v1, read-only
  --answers <answers.json>   # dspx-misegraph-example-answers-v1
  --outdir <dir>             # receives the four files below; no-clobber
  [--case render-text --case check-json]   # ordered; default: render-text, check-json
  [--json]
```

Exit codes: 0 ok; 2 for any package, answers, case, or placement rejection (nothing written, or
nothing beyond files already present). The unchanged foundry run is still
`dspx foundry --intent ... --quality-proposal ... --inputs ... --outdir ...`; calling `dspx foundry`
with no subcommand and no options exits 2 with an explicit message.

## Emitted files

Writes are atomic and no-clobber: temp file in `--outdir`, fsync, `link()` into place (fails if
the name exists), temp unlinked. The pre-write preflight also refuses if any of the four names
already exists.

1. `intent.json` — `program-intent-v2`, pretty sorted JSON. All fields except `examples` are
   identical to the AK-5346/5352/5353 reference intent (name
   `AssessAMisegraphRecipeFromSupplied`, `inputs=["evidence"]`, `outputs=["answer"]`,
   `metric="concept_coverage"`, the same `options.normalization` / `options.quality_proposal`
   provenance block, the same `misegraph_recipe_fidelity` quality criterion). The test suite pins
   sha256 `58429c80…c5e6` of the intent-minus-examples. One example per selected case:
   - `inputs.evidence` = compact canonical JSON (sorted keys, `,`/`:` separators) of
     `{recipe, package_sha256, source:{sha256,text}, canonical:{sha256,json}, render:{sha256,text},
     check:{sha256,diagnostics}, case:{id,argv,exit_code}}`;
   - `outputs.answer` = the operator's answer for that case.
   No `"\nValidation copy."` suffix hack: the second example differs by its `case` block.
2. `inputs.json` — `{"inputs": examples[0].inputs}`.
3. `misegraph-evidence-binding.json` — `dspx-misegraph-evidence-binding-v1`, exactly the shape
   `src/evidence/receipt.rs` deserializes with `deny_unknown_fields` (no extra keys anywhere):

```json
{
  "schema_version": "dspx-misegraph-evidence-binding-v1",
  "package": {"dir": "<abs>", "manifest_sha256": "…", "package_sha256": "…",
              "producer": {"name": "misegraph", "version": "0.1.0", "ir_schema_version": 1}},
  "validation": {"artifact_hashes_ok": true, "canonical_ir_schema_valid": true,
                 "unknown_manifest_keys": [],
                 "freshness": {"mode": "hash_bound", "check": "manifest_sha256_matches_at_import"}},
  "emitted": {"intent_path": "<abs>", "intent_sha256": "…", "inputs_path": "<abs>", "inputs_sha256": "…"},
  "example_cases": ["render-text", "check-json"],
  "non_authority": {"misegraph_mutated": false, "acceptance_authority": false}
}
```

   Paths are absolute because the Misegraph verifier opens `emitted.*_path` with
   `Path::new(path)` and re-hashes them. The only Misegraph-side path that appears is
   `package.dir`; the intent and inputs carry no absolute paths at all.
4. `misegraph-import-provenance.json` — `dspx-misegraph-import-provenance-v1`: importer schema
   version, `package_sha256`, `manifest_sha256`, `answers{schema_version,path,sha256}`,
   `binding{path,sha256}`, `example_cases`, `canonical_ir_validator`, and a non-authority block
   including `answers_authored_by_importer: false`. It exists because the binding is closed by
   the Misegraph verifier and cannot carry the answers hash.

Determinism: the four files are a pure function of (package bytes, answers bytes, case
selection, resolved outdir path). `intent.json` and `inputs.json` are identical across outdirs;
the binding and provenance differ across outdirs only in the recorded paths.

## `misegraph_source` projection for evidence docs

`build_misegraph_source_projection(binding)` reloads and re-verifies the package at
`binding.package.dir`, checks `manifest_sha256` / `package_sha256` against the binding, and
returns `{source:{path,sha256}, canonical:{path,sha256}, render:{path,sha256}, package:{…}}` for
the `misegraph_source` block of `docs/project/*-evidence.json`. It is a generator for authoring,
not a runtime step.

## Downstream: what still has to happen

- `dspx program-gen --intent <outdir>/intent.json --outdir <root>/candidate --print-manifest` and
  `dspx program-run --manifest <root>/candidate/manifest.json --inputs <outdir>/inputs.json
  --outdir <root>/runtime --skip-oracle-index --json` accept the emitted files unchanged
  (offline: `DSPX_PROVIDER=stub`, `DSPX_REPLAY_FIXTURE_JSON` derived from the intent's objective
  and `examples[0].outputs.answer`). This is exercised by
  `tests/test_program_foundry_misegraph_evidence.py::test_offline_stub_program_gen_and_run_accept_emitted_bundle`.
- `dspx foundry` requires a `program-quality-criteria-proposal-v1` envelope whose
  `candidate_intent` equals the emitted intent (`program_foundry._accepted_intent_binding`). The
  reference envelope from AK-5346 is bound to the hand-assembled intent and will not match; a
  new acceptance must be produced for the emitted intent before foundry runs. The importer does
  not and must not fabricate that envelope.
- **Offline runs keep fixture-replay.** The Oracle semantic backend `fixture-replay` is keyed
  by a per-run request hash that is only known after the runtime episode exists. Every offline
  lineage so far (AK-5327, 5346, 5352, 5353) added a hand-authored entry for that hash, copied
  from an earlier entry. That entry is **authored fixture replay**, not Oracle analysis: label it
  `authored_fixture_replay` in the lineage's `commands-run.txt` and in any evidence document,
  and do not present the resulting `program_oracle_semantic.json` as an analytical finding. This
  import does not change that; it only makes the intent/inputs side reproducible and hash-bound.

## Validation performed (2026-09-03)

- `uv run --no-sync -m pytest -q tests/test_program_foundry_misegraph_evidence.py` — 34 passed.
- `tests/test_program_foundry.py`, `tests/test_program_foundry_gepa_workflow.py` — pass
  unchanged with the `foundry` group conversion.
- `ruff check` / `ruff format --check` on touched files; `ty check` on touched `src` modules.
- Offline smoke under `$TMPDIR` with the emitted bundle: `program-gen` rc=0 (3 s), `program-run`
  rc=0 (1 s), `effect.ak_called=false`. `dspx foundry` was not run (needs the matching quality
  envelope and the per-run fixture entry).
