---
summary: "Contract for `dspx foundry import-misegraph-evidence`: verified misegraph-evidence-package-v1 in, deterministic program-intent-v2 (package-derived concept groups, optional operator answers) + inputs + dspx-misegraph-evidence-binding-v1 out (AK-5355, Phase 2 slices D1-D3; AK-5362 honest loop: live typed Oracle backend, concept_coverage GEPA metric, provider_evidence_kind labelling)."
read_when:
  - "You are importing a Misegraph evidence package into the DSPx foundry flow or authoring the optional answers file for it."
  - "You are changing program_foundry_misegraph_evidence*.py, program_foundry_misegraph.py, or the checked-in misegraph-evidence-package-v1 fixture."
  - "You need to know what an offline (stub / fixture-replay) or a live (typed openai-compatible) foundry lineage proves, and how provider_evidence_kind labels it."
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
- The importer never authors a judgment. With `--answers`, `examples[*].outputs.answer` is copied
  verbatim from the operator file (a selected case without an answer is a hard error). Without
  `--answers`, the answer is the deterministic package-derived projection string described below
  and provenance says so (`answers.origin = "package_derived"`,
  `non_authority.answers_authored_by_importer = true`).
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

## Package-derived expected projection (AK-5362)

`derive_misegraph_expected(package, case_id)` (`program_foundry_misegraph_evidence.py`) turns
package facts into the quality criterion and, when no answers file is supplied, the example
answer. Nothing comes from a template or an operator's memory:

- `required_concept_groups` (one group = one fact, any listed spelling satisfies it):
  recipe id tokens from `canonical.json.id` (`espresso`, `brownies`); one group per ingredient
  `[id, id with spaces, name]`; one group per equipment `[id, name]`; for every step carrying a
  `temperature` / `duration`, one group of spellings per amount (`170 C`, `170 °C`, `170°C`,
  `170 degrees C`; `30 min`, `40 min`, `30-40 min`, ...); one group for the `check.json` error
  count (`0 errors`, `zero errors`, `no errors`, `error_count 0`, `no diagnostics`, ... or
  `N errors`). Bounds are the evaluator's (≤ 20 groups, ≤ 10 terms per group, ≤ 256 chars);
  exceeding them fails the import closed rather than truncating facts.
- `projection`: a case-specific canonical restatement (`Misegraph evidence projection for case
  check-json (exit code 0). Recipe espresso_brownies ... Step bake_brownies (bake): temperature
  170 C, duration 30-40 min. Check: 0 errors, 0 diagnostics; ... not a judgment.`). The importer
  asserts that the projection satisfies its own derived criterion.
- The intent's `misegraph_recipe_fidelity` criterion carries the derived groups instead of the
  template's literal `[["espresso","brownies"],["ingredient","process"],["bake","temperature"]]`;
  every other non-example intent field is still the pinned AK-5346 reference (the test pins the
  intent with the template groups substituted back).
- `misegraph-import-provenance.json` gains `answers.origin` (`operator` | `package_derived`) and
  an `expected_projection` block (`dspx-misegraph-expected-projection-v1`: criterion id, derived
  groups, `derived_from`, `projection_sha256_by_case`, `used_as_example_answer`). The binding
  file is unchanged and stays byte-compatible with Misegraph's `receipt.rs`.

## Answers file (optional): `dspx-misegraph-example-answers-v1`

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
  [--answers <answers.json>] # optional dspx-misegraph-example-answers-v1 (origin=operator)
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
   version, `package_sha256`, `manifest_sha256`,
   `answers{origin,schema_version,path,sha256}` (nulls when package-derived),
   `expected_projection{...}`, `binding{path,sha256}`, `example_cases`,
   `canonical_ir_validator`, and a non-authority block whose `answers_authored_by_importer` is
   `false` for operator answers and `true` for the package-derived projection. It exists because
   the binding is closed by the Misegraph verifier and cannot carry these facts.

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

## Honest loop additions (AK-5362, 2026-09-04)

### Live Oracle semantic backend on the typed port

`program_oracle_semantic_backend.TypedProviderOracleSemanticBackend` restores a live backend
inside the Decision 118 boundary: `provider_registry.create` restricted to `openai-compatible`
(`DSPX_ORACLE_SEMANTIC_BACKEND=live`, `DSPX_ORACLE_SEMANTIC_PROVIDER=openai-compatible`,
`DSPX_OPENAI_COMPAT_API_BASE|MODEL|TIMEOUT`, optional `DSPX_ORACLE_SEMANTIC_MODEL` which must be
a `local/` id; any credential env rejects). One `DSPyTypedLMAdapter` invocation carries the
existing `_analysis_prompt`; `_parse_analysis_text` is strict (one JSON object, no unknown
fields, `uniqueItems`, and every `items.enum` of `_analysis_response_format` — codebook codes and
the request-derived `evidence_refs` — is closed, so a model cannot cite a ref the request did not
offer). Results: `execution_status ∈ {succeeded, failed_before_live_success,
failed_after_live_response}`, `configured_*` from env, `executed_*` from the provider's observed
attempt, `live_call_succeeded` from the effect disposition. An `effect_indeterminate` disposition
raises and latches the backend (terminal; the runtime sidecar records `indeterminate`, foundry
reports `blocked_indeterminate`). Preflight validates configuration only and never dispatches.
`model_roles.ModelRole` accepts `local/` ids and labels them `provider=openai-compatible,
auth_route=loopback_credential_free` instead of `dspy-lm-auth`.

Observed 2026-09-04 against the loopback vLLM 0.27 (`local/Qwen3.8-27B-AEON-NVFP4-FP8`): the
typed port's response validator (`openai_compatible_provider._validated_response`, outside the
AK-5362 edit scope) classifies every reply as `completed_failure` because vLLM adds null message
keys (`refusal`, `annotations`, `audio`, `function_call`, `reasoning`) and
`usage.prompt_tokens_details`. The live-marked test records this as an `xfail` with the reason;
the fake-transport tests prove the backend contract. Until the port accepts that shape, a live
lineage over this server terminates at `failed_before_live_success` — recorded, not papered over.

### Metric honesty for GEPA

- `program_foundry_gepa_proposal._SUPPORTED_METRICS` adds `concept_coverage`; the plan binds it
  to the intent's criteria (`concept_coverage_binding{criterion_ids, criteria_sha256,
  optimizer_backend_metric: exact}`) and refuses `exact`/`exact_match` for a `concept_coverage`
  intent (`--gepa-metric concept_coverage` is the honest choice). The executor contract accepts
  the metric.
- `program_refinement_gepa` writes `_gepa_inputs/concept_coverage_program.py`, a wrapper that
  re-exports the candidate program and whose `normalize_output` projects gold/pred onto a
  `concept_coverage[<ids>]:passed|failed (...)` verdict so the optimizer's `exact` backend scores
  1.0 only when every declared criterion passes; feedback names the missing groups. The result
  records `metric_honesty{intent_metric, optimizer_metric, aligned}` and the binding hashes.
- `program_refinement` (and `program_refinement_comparison`) emit `differs:<field>` instead of
  the blocking `mismatch:<field>` when the intent metric is not exact; `differs` never selects the
  `tighten_output_mapping` change or the "failed exact_match" rationale.

### Provider evidence labelling

`program_foundry_provider_evidence.py` derives the closed `provider_evidence_kind`
(`live` | `authored_fixture_replay` | `stub_echo`; absent/null = unknown) from the actual runtime:
`openai-compatible` and the task-local jury families → `live`; `stub` / `stub/echo` →
`stub_echo`; Oracle `fixture-replay` → `authored_fixture_replay`. A lineage label is the weakest
link (stub_echo < authored_fixture_replay < live; an unknown link keeps the lineage unknown
unless a weaker known link decides it). It is written to: the Oracle sidecar
(`program_oracle_semantic.json.provider_evidence_kind`), `foundry.json.provider_evidence`
(`links{program_run, oracle_semantic, gepa}` + `lineage`) and its stage blocks, the GEPA
`execution-receipt.json`, `candidate-comparison.json.interpretation` (plus
`provider_evidence_links` and a `limits` line), and the comparison-jury attempt/receipt
`execution_request.provider_evidence_kind` (weakest of comparison, GEPA receipt, Oracle sidecar,
and the jury's own provider). The jury receipt keeps `schema_version
dspx-program-foundry-gepa-comparison-jury-v1`; the field is additive and optional, retained
AK-5346/5352/5358/5360/5361 receipts (see `docs/project/*-evidence.json`) still revalidate, and
Misegraph's `receipt.rs` reads absent as `unknown`.

### Honest lineage run (2026-09-04, `$ROOT = $TMPDIR/misegraph-foundry-honest-5362.NtdPDD`)

Prescribed env (`DSPX_PROVIDER=openai-compatible`, loopback vLLM, `DSPX_ORACLE_SEMANTIC_BACKEND=live`,
no `DSPX_REPLAY_FIXTURE_JSON`, no fixture path) plus two recorded additions:
`DSPX_POLICY_ALLOW_NETWORK_MUTATE=1` (the typed port preflight-rejects dispatch without it) and
`DSPX_PROGRAM_HARNESS_TIMEOUT=600` (program-gen's `eval_examples.py` hit the 60 s default while the
27B model was still generating). Every command and rc is in `$ROOT/commands-run.txt`.

- export rc=0 (`package_sha256 0be06d8d…4905`), import rc=0 (`answers.origin=package_derived`),
  program-gen rc=0, program-run rc=0 with behavior `error`: the port classified the model's reply
  as `completed_failure` (response-shape rejection above); `foundry.json` was therefore never
  written by a successful foundry run.
- foundry rc=2: the live Oracle stage ended `effect_indeterminate` (typed-port read timeout at
  `DSPX_OPENAI_COMPAT_TIMEOUT=180` while the model was still generating); the sidecar is terminal,
  so no GEPA proposal exists and `execute-foundry-gepa` did not run. A deliberate second attempt
  into a **new** sidecar (`program_oracle_semantic.retry-600s.json`, 600 s timeout) let the model
  finish, and the typed port then classified the reply as `completed_failure`
  (`failed_before_live_success`, `executed_model` observed, zero recommended experiments); the
  canonical sidecar was never replayed.
- The quality-proposal envelope is still the AK-5346 injected test double re-bound to the emitted
  intent (recorded as a remaining hollow link); consume and jury were not run (task scope).

## Validation performed (2026-09-03)

- `uv run --no-sync -m pytest -q tests/test_program_foundry_misegraph_evidence.py` — 34 passed.
- `tests/test_program_foundry.py`, `tests/test_program_foundry_gepa_workflow.py` — pass
  unchanged with the `foundry` group conversion.
- `ruff check` / `ruff format --check` on touched files; `ty check` on touched `src` modules.
- Offline smoke under `$TMPDIR` with the emitted bundle: `program-gen` rc=0 (3 s), `program-run`
  rc=0 (1 s), `effect.ak_called=false`. `dspx foundry` was not run (needs the matching quality
  envelope and the per-run fixture entry).
