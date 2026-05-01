---
summary: "Hands-on walkthrough for program-gen candidate assemblies, execution episodes, replay checks, Oracle-readable evidence, explicit Oracle reporting, and authority boundaries."
read_when:
  - "You want to understand one-intent program generation end to end."
  - "You need to inspect execution_episode.json, behavior_results.json, oracle_evidence.json, manifest, receipt, replay, and optional temp-dir Oracle reporting without invoking AK."
  - "You are explaining the current shipped program-gen product loop to an operator."
type: "guide"
---

# Program-gen Walkthrough

This walkthrough shows the current shipped `program-gen` path from one structured intent to a runnable, evaluated, replayable program-shaped candidate assembly.

It is deliberately local-first and non-authoritative:

- uses `DSPX_PROVIDER=stub`
- sets `MLFLOW_ENABLE=0`
- writes to a temp directory
- does not call `ak`
- does not invoke Oracle indexing or interpretation during `program-gen` or mutate Oracle DBs unless the optional explicit temp-dir indexing step is run
- can optionally materialize deterministic local dataset split evidence when intent declares `dataset` or `datasets`
- `program-gen` does not run a model jury or promotion adjudicator; explicit local deterministic jury execution is a separate `program-promote jury` sidecar command
- does not rank, select winners, prune, promote, run GEPA/search, export authority, or mutate governance state

The goal is to see the current artifact contract clearly, not to claim a final product loop.

## What this proves today

The current `program-gen` loop proves:

1. A structured intent can materialize a deterministic program-shaped candidate assembly.
2. Signature, module, program, jury, promotion, and eval harness surfaces are generated as separate artifacts.
3. Explicit user/Pi-declared topology can be validated and preserved in artifacts; the narrow supported `pipeline` subset is rendered into multiple signatures/modules and a composed program, while topology is never inferred.
4. `module_surfaces.json` is a standalone `program-module-surfaces-v1` artifact containing one or more `program-module-surface-v1` contracts for the generated module surfaces that `program-gen` composed.
5. `execution_episode.json` is a standalone `program-execution-episode-v1` contract artifact.
6. When examples exist, `eval_examples.py` invokes the generated program locally and writes `behavior_results.json`.
6. When a dataset is declared, `program-gen` writes `dataset_manifest.json`, deterministic `splits/train.jsonl`, `splits/validation.jsonl`, `splits/test.jsonl`, split-specific harnesses, and `behavior_results.train.json` / `.validation.json` / `.test.json` without merging them into inline examples.
6. `oracle_evidence.json` is Oracle-readable evidence derived from inline-example behavior results without invoking Oracle.
7. `oracle index --from-program-evidence` can be run explicitly as local CoordinateIndex ingestion; it is not part of `program-gen`.
8. `oracle program-evidence report` can be run explicitly against that temp CoordinateIndex to summarize example-backed behavior evidence without authority effects; it is not part of `program-gen`.
9. `program-refine propose` can be run explicitly over the manifest, declared behavior evidence, and the Oracle report to write a local proposal artifact only; it is not part of `program-gen`.
10. `program-promote review` can be run explicitly over the manifest, original generated promotion shell artifacts, behavior evidence, Oracle report, and refinement proposal to write a local refined promotion-review packet sidecar; it is not part of `program-gen` and is not promotion approval.
11. `program-promote jury` can be run explicitly over the manifest, planned jury artifacts, and current `eval_examples.py` / `behavior_results.json` evidence to write a local deterministic jury-results sidecar; it is not part of `program-gen` and is not promotion approval.
12. `program-promote decide` can be run explicitly over that refined packet plus operator/adjudicator input to write a local decision-record sidecar; it is not external authority, activation, or automatic promotion.
13. `program-refine generate-candidate` can be run explicitly from a proposed refinement plus a local `request_more_evidence` decision record to materialize one local second candidate at a requested output directory.
14. `program-refine compare-candidates` can be run explicitly over the source and second candidate manifests to write a local comparison sidecar over current example-backed behavior evidence.
15. `program-refine generate-and-compare` can be run explicitly as a convenience workflow for exactly one second-candidate generation followed by the same local comparison sidecar.
16. `program-promote plan` can be run explicitly over an existing candidate manifest, local decision record, and comparison sidecar to write a `program-promotion-plan-v1` local plan sidecar.
17. `adapters authority agent-kernel-export-preflight` can be run explicitly over a manifest, opaque AK ref, and optional decision/comparison sidecars to write a local `program-external-authority-export-preflight-v1` packet that is preflighted/planned/not applied.
18. `program-promote status` can be run explicitly over a manifest plus local sidecars to write one `program-candidate-state-v1` truth-state summary artifact.
19. `program-refine optimize-gepa` can be run explicitly against an existing manifest to write a local `program-refinement-gepa-result-v1` sidecar from explicit train/validation JSONL files, manifest dataset splits, or limited inline examples; it is not part of `program-gen`.
20. `manifest.json` and `manifest.json.meta.json` declare hashes and evidence paths for replay.
19. `dspx run replay --check-only` verifies the declared program evidence artifacts, including `execution_episode.json`.
20. Promotion and authority remain explicitly pending / non-authoritative.

It does **not** prove:

- rich topology inference,
- broad graph execution beyond the supported explicit `pipeline` subset,
- broad dataset/eval orchestration beyond the current deterministic split-specific local harnesses,
- model-backed jury execution,
- model-jury adjudication, external approval, or activation,
- automatic Oracle indexing/interpretation/refinement/promotion-review/decision recording/second-candidate generation/candidate comparison during `program-gen`,
- automatic GEPA/search, ranking, winner selection, or authority export/apply,
- ranking, winner selection, promotion approval, authority apply, or external mutation behavior from candidate comparison, local promotion/adjudication planning, or external-authority export preflight,
- richer phenotype, territory, frontier, or multi-source behavior interpretation,
- GEPA/search materializing a new `program-candidate-assembly-v1` in the current slice,
- broad accepted-proposal policy beyond the explicit request-more-evidence constraints-patch path,
- AK export or task mutation.

## 1. Prepare a temp workspace

From the repo root:

```bash
TD="$(mktemp -d)"
export TD

cat > "$TD/intent.yaml" <<'YAML'
name: TicketProgram
objective: Classify support ticket urgency.
inputs:
  - ticket_text
outputs:
  - urgency
metric: exact_match
constraints:
  - use only the supplied ticket text
# Optional explicit topology is rendered for the narrow supported pipeline subset
# and otherwise preserved as a declared-only planning contract:
# topology:
#   kind: pipeline
#   execution_status: declared_not_materialized
#   modules:
#     - id: classify_ticket
#       primitive: Predict
#       signature:
#         name: ClassifyTicket
#         inputs: [ticket_text]
#         outputs: [urgency]
#   edges:
#     - from: input
#       to: classify_ticket
#     - from: classify_ticket
#       to: output
examples:
  - inputs:
      ticket_text: "Server is down for all users"
    outputs:
      urgency: high
promotion:
  adjudicator:
    kind: human_operator
    id: local_operator
  external_authority:
    refs:
      - system: agent_kernel
        ref: AK-EXAMPLE
        role: optional_authority_export_target
YAML

export DSPX_PROVIDER=stub
export MLFLOW_ENABLE=0
export DSPX_CACHE_DIR="$TD/cache"
export DSPX_CACHE_ENABLE=1
```

These environment settings keep the walkthrough offline and temp-dir scoped.

## 2. Generate the program candidate assembly

```bash
uv run -q python -m dspx.cli.dspx program-gen \
  --intent "$TD/intent.yaml" \
  --outdir "$TD/program"
```

List the top-level generated artifacts:

```bash
find "$TD/program" -maxdepth 1 -type f -printf '%f\n' | sort
```

Expected high-signal artifacts include:

- `plan.json`
- `jury.json`
- `jury_selection.json`
- `jury_rubric.json`
- `promotion_review.json`
- `promotion_adjudication_request.json`
- `promotion_decision_template.json`
- `module_surfaces.json`
- `signature.py`
- `module.py`
- `program.py`
- `eval_smoke.py`
- `eval_jury.py`
- `eval_promotion.py`
- `examples.json`
- `eval_examples.py`
- `behavior_results.json`
- `oracle_evidence.json`
- optional dataset split artifacts when `dataset` / `datasets` are declared: `dataset_manifest.json`, `splits/*.jsonl`, `eval_train.py`, `eval_validation.py`, `eval_test.py`, and `behavior_results.{train,validation,test}.json`
- `execution_episode.json`
- `manifest.json`
- `manifest.json.meta.json`

## 3. Verify generated Python harnesses compile

```bash
python -m py_compile \
  "$TD/program/program.py" \
  "$TD/program/eval_smoke.py" \
  "$TD/program/eval_jury.py" \
  "$TD/program/eval_promotion.py" \
  "$TD/program/eval_examples.py"
```

`program-gen` already ran the generated harnesses during materialization; this command is just a visible operator check.

## 4. Inspect module-surface contracts

```bash
python - <<'PY'
import json, os
root = os.environ["TD"] + "/program"
payload = json.load(open(f"{root}/module_surfaces.json"))
print(json.dumps({
    "schema_version": payload["schema_version"],
    "status": payload["status"],
    "module_surface_count": payload["module_surface_count"],
    "module_ids": [s["module_id"] for s in payload["module_surfaces"]],
    "source_kinds": [s["source_kind"] for s in payload["module_surfaces"]],
    "authority": payload["authority"],
    "non_authority": payload["non_authority"],
}, indent=2, sort_keys=True))
PY
```

How to read it:

- a no-topology intent emits one `generated_single_module_scaffold` surface with `module_id: generated_module`;
- a supported explicit `pipeline` emits one `generated_topology_module` surface per rendered module;
- each surface declares primitive, signature IO, generated signature/module class names, artifact paths, false effect flags, and non-authority flags;
- this is the bridge toward future local custom module refs, but the current slice does not import or execute arbitrary custom Python modules.

## 5. Optional: declare dataset split evidence

A dataset declaration uses the same record shape as inline examples:

```yaml
dataset:
  path: data/tickets.jsonl
  input_fields: [ticket_text]
  output_fields: [urgency]
  split:
    strategy: ratio
    train: 0.7
    validation: 0.15
    test: 0.15
    seed: 42
```

`program-gen` accepts JSONL (one object per row) plus JSON/YAML list-of-object files. Ratio split materialization loads source records in order, validates exact `inputs`/`outputs` fields, shuffles indices with `random.Random(seed)`, assigns `floor(n * train)` and `floor(n * validation)` records, and places the remainder in test. Explicit split files can instead be declared with `datasets.train`, `datasets.validation`, and `datasets.test`; those are normalized into canonical `splits/*.jsonl` artifacts without ratio recomputation. Empty splits are allowed and produce split behavior evidence with `summary.total: 0` and `status: no_examples`.

Dataset split evidence is local and non-authoritative. It coexists with inline examples; it does not run Oracle automatically and does not introduce `eval_behavior.py`.

## 6. Inspect the execution episode contract

```bash
python - <<'PY'
import json, os
root = os.environ["TD"] + "/program"
payload = json.load(open(f"{root}/execution_episode.json"))
print(json.dumps({
    "schema_version": payload["schema_version"],
    "status": payload["status"],
    "phase": payload["phase"],
    "materialization": payload["materialization"],
    "checks": payload["checks"],
    "behavioral_evaluation": payload["behavioral_evaluation"],
    "oracle_readability": payload["oracle_readability"],
    "non_authority": payload["non_authority"],
}, indent=2, sort_keys=True))
PY
```

How to read it:

- `materialization` means files were generated and the bundle exists.
- `checks.compile` means generated Python source compiled before write/materialization completed.
- `checks.smoke` means `eval_smoke.py` imported/built the program and checked IO shape.
- `checks.examples_binding` means `examples.json` matched declared input/output fields.
- `checks.jury_binding` means `jury.json`, `jury_selection.json`, and `jury_rubric.json` are internally consistent; no juror model was called.
- `checks.promotion_binding` means promotion review/request/template artifacts are internally consistent; no adjudicator was invoked.
- `behavioral_evaluation` points to `behavior_results.json` only when examples existed and `eval_examples.py` wrote that evidence.
- `oracle_readability` points to `oracle_evidence.json` only when behavior evidence existed; `oracle_invoked` remains `false`.
- `non_authority` keeps evidence separate from ranking, pruning, promotion, governance, Oracle, and external mutation authority.

## 7. Inspect actual behavior over examples

```bash
python - <<'PY'
import json, os
root = os.environ["TD"] + "/program"
payload = json.load(open(f"{root}/behavior_results.json"))
print(json.dumps({
    "schema_version": payload["schema_version"],
    "authority": payload["authority"],
    "summary": payload["summary"],
    "examples": payload["examples"],
}, indent=2, sort_keys=True))
PY
```

This is the behavioral evidence surface. It records what happened when the generated program was invoked over declared examples.

With the stub provider, the example may fail exact-match comparison. That is still useful evidence: it means the generated program executed and produced observable behavior that did not match the expected output.

Do not reinterpret this as promotion or ranking. It is evidence only.

## 8. Inspect Oracle-readable evidence without invoking Oracle

```bash
python - <<'PY'
import json, os
root = os.environ["TD"] + "/program"
payload = json.load(open(f"{root}/oracle_evidence.json"))
print(json.dumps({
    "schema_version": payload["schema_version"],
    "evidence_kind": payload["evidence_kind"],
    "authority": payload["authority"],
    "identity": payload["identity"],
    "behavior": payload["behavior"],
    "oracle_facets": payload["oracle_facets"],
    "non_authority": payload["non_authority"],
    "oracle_text_preview": payload["oracle_text"][:500],
}, indent=2, sort_keys=True))
PY
```

This artifact is shaped for later Oracle consumption, but `program-gen` itself has not run `dspx oracle ...`, has not indexed anything, and has not mutated an Oracle DB.

## 9. Optional explicit Oracle evidence indexing into a temp CoordinateIndex

If you want to exercise the consumer-side seam, run Oracle indexing explicitly and keep the index in the temp workspace:

```bash
export DSPX_ORACLE_EMBEDDING_BACKEND=mock

uv run -q python -m dspx.cli.dspx oracle index \
  --from-program-evidence \
  --path "$TD/program" \
  --index-path "$TD/oracle/coordinates.db" \
  --json
```

Expected JSON facts:

- `scanned: 1`
- `indexed: 1`
- `errors: 0`
- `non_authority_confirmed: true`
- `index_stats.by_run_kind.program-oracle-evidence: 1`

You can then search only that temp index:

```bash
uv run -q python -m dspx.cli.dspx oracle search \
  "ticket urgency server down" \
  --index-path "$TD/oracle/coordinates.db" \
  --kind program-oracle-evidence \
  --json
```

This is local evidence ingestion only. It writes to a local CoordinateIndex and does not rank, prune, promote, block, approve, export authority, or mutate governance state.

You can then ask for an explicit interpretation/report over the indexed evidence:

```bash
uv run -q python -m dspx.cli.dspx oracle program-evidence report \
  --index-path "$TD/oracle/coordinates.db" \
  --json > "$TD/oracle/program-evidence-report.json"

python -m json.tool "$TD/oracle/program-evidence-report.json"
```

Expected JSON facts:

- `schema_version: program-oracle-evidence-report-v1`
- `status: ok`
- `total_records: 1`
- behavior status, task type, metric, input/output field, failure signal, and source artifact counts are summarized from indexed evidence
- `interpretation.summary` describes example-backed behavior evidence and its limits
- `non_authority` confirms interpretation-only posture and no ranking, pruning, promotion, governance, or external mutation authority

This report reads the supplied CoordinateIndex. It does not modify `program-gen` artifacts, manifests, receipts, AK, governance, or external authority. The current behavior evidence is still example-backed through `eval_examples.py` / `behavior_results.json`; there is no `eval_behavior.py` orchestration layer yet.

## 10. Optional explicit bounded refinement proposal

If you want to exercise the next consumer-side seam, propose a bounded refinement from the generated manifest and the saved Oracle report:

```bash
uv run -q python -m dspx.cli.dspx program-refine propose \
  --manifest "$TD/program/manifest.json" \
  --oracle-report "$TD/oracle/program-evidence-report.json" \
  --out "$TD/refinement/refinement_proposal.json" \
  --json
```

Expected JSON facts:

- `schema_version: program-refinement-proposal-v1`
- `identity` binds to the same request/candidate/assembly/episode/receipt-bundle IDs as `manifest.json`
- `created_from` references the manifest, Oracle report, and `behavior_results.json` when present
- `evidence_summary` reflects example-backed behavior status/counts plus Oracle report status and record match
- failed example-backed behavior may produce a proposed next candidate intent patch such as tightening output mapping for the observed mismatch
- no-examples assemblies degrade to `insufficient_behavior_evidence` rather than inventing behavior
- `non_authority` confirms proposal-only posture and no apply, candidate generation, ranking, pruning, promotion, governance, or external mutation authority

This command writes only the proposal artifact at `--out`. It does not mutate generated program files, does not create a second candidate assembly, does not index/report Oracle evidence automatically, and does not rank, prune, promote, block, export authority, or mutate governance.

## 11. Optional explicit promotion-review refinement packet

If you want to bring the generated promotion shell, behavior evidence, Oracle report, and refinement proposal into one local adjudication packet, run the promotion-review consumer explicitly:

```bash
uv run -q python -m dspx.cli.dspx program-promote review \
  --manifest "$TD/program/manifest.json" \
  --oracle-report "$TD/oracle/program-evidence-report.json" \
  --refinement-proposal "$TD/refinement/refinement_proposal.json" \
  --out "$TD/promotion/promotion_review_refined.json" \
  --json
```

Expected JSON facts:

- `schema_version: program-promotion-review-refined-v1`
- `promotion_state: not_promoted`
- `candidate_status: exploratory`
- `created_from` references `manifest.json`, original `promotion_review.json`, original `promotion_adjudication_request.json`, original `promotion_decision_template.json`, `behavior_results.json` when present, the Oracle report, and the refinement proposal
- behavior, Oracle report, and refinement proposal summaries are explicit
- model-jury execution and explicit adjudicator decision remain missing unless policy and evidence truly say otherwise
- `adjudication_packet.status` remains `not_ready_missing_required_evidence` when required local evidence is absent
- `non_authority` confirms local review-packet-only posture and no automatic promotion, Oracle ranking/pruning/promotion, program mutation, new candidate generation, governance authority, or external mutation

This command writes only the requested sidecar artifact. It does not overwrite generated `promotion_review.json`, `promotion_adjudication_request.json`, or `promotion_decision_template.json`; it does not mutate `manifest.json`, behavior evidence, Oracle evidence, generated Python files, AK, governance, or external authority; it does not generate a new candidate assembly; it does not invoke an adjudicator or approve promotion. Top-level `status: review_packet_ready` means the packet was assembled from available evidence; it does not mean promotion is allowed. Promotion gating uses `review_readiness.ready_for_adjudicator_review`.

## 12. Optional explicit local jury execution sidecar

If you want local deterministic jury evidence over the current example-backed behavior, run the jury consumer explicitly:

```bash
uv run -q python -m dspx.cli.dspx program-promote jury \
  --manifest "$TD/program/manifest.json" \
  --out "$TD/promotion/jury_results.json" \
  --json
```

Expected JSON facts:

- `schema_version: program-jury-results-v1`
- `status: executed` when `behavior_results.json` is present, or `insufficient_behavior_evidence` when examples/behavior evidence are absent
- `created_from` references `manifest.json`, `jury.json`, `jury_selection.json`, `jury_rubric.json`, and current `behavior_results.json` when present
- `jury` records planned jury, selection, and rubric schemas plus selected juror count/perspectives
- `behavior_evidence` summarizes current `eval_examples.py` / `behavior_results.json` only
- `juror_results` records deterministic local per-juror judgments and criteria results while preserving provider/model fields from the planned jury artifacts
- `aggregate` records judgment counts plus agreement/disagreement
- `effect` and `non_authority` confirm local-only/no-mutation behavior

This command writes only the requested `jury_results.json` sidecar. It does not mutate the candidate, does not mutate `promotion_review.json` or `promotion_review_refined.json`, does not generate a new candidate, does not create an Oracle index, does not call external models, does not require provider auth, does not introduce `eval_behavior.py`, and does not rank, select winners, promote, approve, export authority, mutate AK, or mutate governance.

## 13. Optional explicit local adjudicator decision record

If you want to record an explicit local operator/adjudicator decision against the refined packet, write a separate decision sidecar:

```bash
uv run -q python -m dspx.cli.dspx program-promote decide \
  --review "$TD/promotion/promotion_review_refined.json" \
  --outcome request_more_evidence \
  --decided-by local_operator \
  --rationale "Need model-jury execution before any promotion decision." \
  --out "$TD/promotion/promotion_decision_record.json" \
  --json
```

Expected JSON facts:

- `schema_version: program-promotion-decision-record-v1`
- `status: recorded`
- `outcome` is one of `withhold`, `reject`, `request_more_evidence`, or `promote`
- non-promote outcomes keep `promotion_state_after_decision: not_promoted`
- `identity` matches the refined review packet identity
- `review_snapshot.ready_for_adjudicator_review` and missing required evidence are copied from the refined packet
- `effect` and `non_authority` confirm local-only/no mutation behavior

The command writes only the requested decision sidecar. It does not mutate generated program artifacts, `promotion_review_refined.json`, Oracle indexes, AK, governance, external authority, or candidate code. `promote` fails closed unless `review_readiness.ready_for_adjudicator_review` is explicitly true; there is no override flag in this wave, and top-level `status: review_packet_ready` is not sufficient.

## 14. Optional explicit second candidate from request-more-evidence

If the local decision outcome is `request_more_evidence`, you can materialize one bounded local second candidate from the proposal patch:

```bash
uv run -q python -m dspx.cli.dspx program-refine generate-candidate \
  --manifest "$TD/program/manifest.json" \
  --refinement-proposal "$TD/refinement/refinement_proposal.json" \
  --decision-record "$TD/promotion/promotion_decision_record.json" \
  --outdir "$TD/program-v2" \
  --json
```

Expected JSON facts:

- `schema_version: program-refinement-candidate-result-v1`
- `status: materialized`
- `source_identity` matches the proposal and decision record identity
- `decision.outcome: request_more_evidence`
- `applied_patch.allowed_patch_fields: ["constraints"]`
- the new candidate manifest exists under `$TD/program-v2/manifest.json`
- the new candidate intent records `options.refinement_lineage`
- the source candidate, proposal, and decision record are not mutated
- the new candidate remains local and `not_promoted`

This command is explicit follow-up candidate generation, not automatic program-gen behavior. It requires a `program-refinement-proposal-v1` with `status: proposed` and a local decision record with `outcome: request_more_evidence`. This first slice applies only bounded `constraints` intent patches. It does not mutate the source candidate, proposal, decision record, Oracle indexes, AK, governance, or external authority, and it does not promote either candidate.

## 14a. Optional explicit comparison of source and second candidate

After the second candidate exists, compare the source and candidate behavior evidence without generating or promoting anything:

```bash
uv run -q python -m dspx.cli.dspx program-refine compare-candidates \
  --source-manifest "$TD/program/manifest.json" \
  --candidate-manifest "$TD/program-v2/manifest.json" \
  --refinement-proposal "$TD/refinement/refinement_proposal.json" \
  --decision-record "$TD/promotion/promotion_decision_record.json" \
  --out "$TD/refinement/candidate_comparison.json" \
  --json
```

Expected JSON facts:

- `schema_version: program-refinement-candidate-comparison-v1`
- `status: compared` when both manifests declare valid `behavior_results.json`, or `insufficient_behavior_evidence` when one side lacks example-backed behavior evidence
- `source_identity` and `candidate_identity` come from the two manifests
- `lineage` reports whether the candidate declares refinement lineage and whether that lineage points back to the source identity
- `behavior_comparison.source` and `.candidate` summarize current `eval_examples.py` / `behavior_results.json` evidence only
- `behavior_comparison.delta` reports failed/error/degraded count deltas, status change, and failure signals added, removed, and persisted
- `interpretation` may say whether improvement was observed on the narrow example-backed evidence, but it is not approval
- `effect` and `non_authority` confirm local-only/no-mutation posture

This command writes only the requested sidecar. It does not mutate the source candidate, second candidate, proposal, decision record, Oracle index, AK, governance, or external authority. It does not generate a third candidate, rank candidates, select a winner, promote, block via Oracle, or introduce `eval_behavior.py`.

If you want the explicit one-shot local workflow, use:

```bash
uv run -q python -m dspx.cli.dspx program-refine generate-and-compare \
  --manifest "$TD/program/manifest.json" \
  --refinement-proposal "$TD/refinement/refinement_proposal.json" \
  --decision-record "$TD/promotion/promotion_decision_record.json" \
  --outdir "$TD/program-v2" \
  --comparison-out "$TD/refinement/candidate_comparison.json" \
  --json
```

This workflow returns `schema_version: program-refinement-generate-and-compare-result-v1`, materializes exactly one second candidate, writes the same comparison sidecar, and still does not rank, select a winner, promote, mutate governance, export authority, or automate `program-gen`.

## 14b. Optional explicit local promotion/adjudication plan

After a second candidate and comparison sidecar exist, you can capture a local-only plan over the available evidence:

```bash
uv run -q python -m dspx.cli.dspx program-promote plan \
  --manifest "$TD/program-v2/manifest.json" \
  --decision-record "$TD/promotion/promotion_decision_record.json" \
  --comparison "$TD/refinement/candidate_comparison.json" \
  --target local_preferred_candidate \
  --authority-owner local_operator \
  --out "$TD/promotion/promotion_plan.json" \
  --json
```

Expected JSON facts:

- `schema_version: program-promotion-plan-v1`
- `status: planned_not_applied`
- `promotion_state: not_promoted`
- target kind and `authority_owner` are copied from explicit CLI input
- `candidate_identity` matches the candidate manifest
- `created_from` records candidate manifest, decision record, comparison sidecar, optional review/source paths, and schemas
- `evidence_hashes` records candidate manifest, behavior results, execution episode, Oracle-readable evidence, decision record, and comparison sidecar hashes when present
- `eligibility.status` can be `eligible_for_local_plan_only`, but `eligibility.allowed_for_apply` remains `false`
- `missing_required_evidence` includes future authority/apply requirements such as `no_external_authority_contract` and `apply_not_supported`
- `audit_trail` records evidence hashes plus `created_by`
- `reversibility` says no rollback is required because no promotion was applied
- `effect` and `non_authority` confirm local-only/no-mutation behavior

This command writes only the requested `promotion_plan.json` sidecar. It does not mutate either candidate, the decision record, the comparison sidecar, Oracle indexes, AK, governance, or external authority. It does not rank, select a winner, approve, promote, deploy, export authority, make Oracle authoritative, or introduce `eval_behavior.py`. Unsupported targets such as `ak`, `deployment`, `production_route`, `current_symlink`, or `promoted_directory` fail closed.

## 15. Optional: run a local GEPA refinement attempt

GEPA refinement is explicit and local. It consumes the existing manifest plus the current local evidence surfaces. If you do not pass explicit files, the command prefers manifest dataset splits when present, then falls back to inline examples with limitation notes.

```bash
uv run -q python -m dspx.cli.dspx program-refine optimize-gepa \
  --manifest "$TD/program/manifest.json" \
  --outdir "$TD/program-gepa" \
  --result-out "$TD/refinement/gepa_refinement_result.json" \
  --max-metric-calls 2 \
  --json
```

The sidecar has `schema_version: program-refinement-gepa-result-v1`. It records source identity, selected evidence source/counts, held-out-validation status, GEPA attempt status, any local optimizer output path, and non-authority flags. In this slice the GEPA optimizer output is not yet a normal `program-candidate-assembly-v1`, so `candidate` remains `null` and the top-level status can degrade truthfully even if GEPA was attempted. The command writes only to the requested `--outdir` and `--result-out`, does not mutate the source candidate or source dataset split artifacts/results, does not create a repo Oracle index, does not rank, select a winner, promote, mutate AK/governance/external authority, or introduce `eval_behavior.py`.

## 16. Inspect manifest and receipt declarations

```bash
python - <<'PY'
import json, os
root = os.environ["TD"] + "/program"
manifest = json.load(open(f"{root}/manifest.json"))
receipt = json.load(open(f"{root}/manifest.json.meta.json"))
print("## manifest execution episode artifact")
print(json.dumps(manifest["execution_episode_artifact"], indent=2, sort_keys=True))
print("## receipt run summary")
print(json.dumps({
    "run_kind": receipt["run_kind"],
    "hash": receipt["hash"],
    "module_surfaces_path": receipt["run_summary"].get("module_surfaces_path"),
    "module_surfaces_hash": receipt["run_summary"].get("module_surfaces_hash"),
    "execution_episode_path": receipt["run_summary"].get("execution_episode_path"),
    "execution_episode_hash": receipt["run_summary"].get("execution_episode_hash"),
    "behavior_results_hash": receipt["run_summary"].get("behavior_results_hash"),
    "oracle_evidence_hash": receipt["run_summary"].get("oracle_evidence_hash"),
}, indent=2, sort_keys=True))
print("## receipt bundle evidence keys")
print(sorted(manifest["receipt_bundle"]["evidence"].keys()))
PY
```

Replay is declaration-driven: the receipt points at `manifest.json`, and the manifest/receipt bundle declare which evidence artifacts and hashes must match.

## 17. Run clean replay

```bash
uv run -q python -m dspx.cli.dspx run replay \
  --from "$TD/program/manifest.json.meta.json" \
  --check-only \
  --json
```

Expected result:

- exit code `0`
- `status: ok`
- `checks.output_hash_match: true`
- `checks.program_module_surfaces_hash_match: true`
- `checks.program_execution_episode_hash_match: true`
- `checks.program_behavior_results_hash_match: true`
- `checks.program_oracle_evidence_hash_match: true`

Replay is local/offline. It should not require MLflow, a provider, Oracle, or AK.

## 18. Prove replay detects execution-episode drift

```bash
cp "$TD/program/execution_episode.json" "$TD/execution_episode.original.json"
python - "$TD/program/execution_episode.json" <<'PY'
import json, sys
p = sys.argv[1]
payload = json.load(open(p))
payload["status"] = "drifted"
open(p, "w").write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
PY

if uv run -q python -m dspx.cli.dspx run replay \
  --from "$TD/program/manifest.json.meta.json" \
  --check-only \
  --json > "$TD/execution-episode-drift.json"; then
  echo "expected replay drift failure" >&2
  exit 1
fi

python - "$TD/execution-episode-drift.json" <<'PY'
import json, sys
payload = json.load(open(sys.argv[1]))
assert payload["status"] == "failed"
assert payload["checks"]["output_hash_match"] is True
assert payload["checks"]["program_execution_episode_hash_match"] is False
assert "program_evidence_hash_mismatch" in payload["error_codes"]
print("execution episode replay drift check ok")
PY

cp "$TD/execution_episode.original.json" "$TD/program/execution_episode.json"
```

This proves `execution_episode.json` is a replay-checked evidence artifact, not just duplicated metadata.

## 19. Optional sidecar authority export plan

The local base smoke includes an optional authority adapter planning step:

```bash
uv run -q python -m dspx.cli.dspx adapters authority agent-kernel-plan \
  --manifest "$TD/program/manifest.json" \
  --external-ref AK-EXAMPLE \
  --out "$TD/program/ak-export-plan.json"
```

This writes:

- `ak-export-plan.json`
- `ak-export-plan.json.meta.json`

The plan status is `planned_not_exported`. It is not an AK mutation, not a promotion decision, and not an authority export.

## 19a. Optional external-authority export preflight packet

After the explicit refinement path has produced a local decision record and comparison sidecar, you can build a stronger local preflight packet for a future AK evidence attachment without calling AK:

```bash
uv run -q python -m dspx.cli.dspx adapters authority agent-kernel-export-preflight \
  --manifest "$TD/program/manifest.json" \
  --external-ref AK-EXAMPLE \
  --decision-record "$TD/promotion/promotion_decision_record.json" \
  --comparison "$TD/refinement/candidate_comparison.json" \
  --out "$TD/export/ak-export-preflight.json" \
  --json
```

Expected JSON facts:

- `schema_version: program-external-authority-export-preflight-v1`
- `status: ready_not_applied` when the manifest ref, decision record, and comparison sidecar all match; `incomplete_preflight` when optional decision/comparison inputs are absent
- `target.system: agent_kernel`, `target.target_contract: ak_task_evidence_attachment`, `mutation_supported: false`, and `apply_command_available: false`
- `artifact_hashes` contains SHA-256 hashes for the manifest plus any supplied decision/comparison sidecars
- `idempotency.export_id` is deterministic for the target system/ref/contract/schema and artifact hashes
- `preflight.blocking_reasons` contains local preflight blockers only; it is empty when `status: ready_not_applied`
- `preflight.ready_for_future_apply: false` with `external_apply_blocking_reasons` including `external_apply_not_implemented` and `target_contract_not_bound_to_ak_runtime`
- `effect.ak_called`, `effect.external_authority_mutated`, and `effect.governance_mutated` are all `false`
- `non_authority.preflight_only` and `non_authority.planned_not_exported` are `true`

This command writes only the requested preflight packet. It does not call AK, validate the ref against AK, mutate external authority, mutate governance, mutate program/decision/comparison artifacts, rank, select a winner, promote, apply, or introduce `eval_behavior.py`. A future apply command would need exact AK target-contract binding, external duplicate checks, an apply receipt, and rollback/failure semantics.

## 19b. Optional whole-candidate truth-state summary

After local sidecars exist, summarize the current candidate truth state in one artifact:

```bash
uv run -q python -m dspx.cli.dspx program-promote status \
  --manifest "$TD/program-v2/manifest.json" \
  --source-manifest "$TD/program/manifest.json" \
  --oracle-report "$TD/oracle/program-evidence-report.json" \
  --refinement-proposal "$TD/refinement/refinement_proposal.json" \
  --review "$TD/promotion/promotion_review_refined.json" \
  --decision-record "$TD/promotion/promotion_decision_record.json" \
  --jury-results "$TD/promotion/jury_results.json" \
  --comparison "$TD/refinement/candidate_comparison.json" \
  --export-preflight "$TD/export/ak-export-preflight.json" \
  --out "$TD/state/program_candidate_state.json" \
  --json
```

Expected JSON facts:

- `schema_version: program-candidate-state-v1`
- `status` is a truth-preserving local posture such as `not_promoted_external_preflighted_not_applied`
- `candidate_identity` and optional `source_identity` identify the exact artifacts being summarized
- `evidence_state` reports behavior evidence, execution episode, Oracle-readable evidence, optional Oracle report, and optional refinement proposal
- `promotion_state` reports review readiness, decision outcome, optional local jury-results evidence, comparison role, optional promotion plan, optional external-authority local preflight blockers, and separate future external-apply blockers
- `truth_summary` keeps `promotion_applied`, `external_authority_mutated`, `governance_mutated`, `ak_called`, `winner_selected`, `automatic_promotion`, and `ready_for_future_apply` false
- `artifact_hashes` records deterministic hashes for every supplied sidecar

This command writes only the requested state summary. Local jury results are summarized as evidence only and do not create promotion authority or winner selection. The command does not mutate candidate artifacts or sidecar inputs, does not create or mutate Oracle indexes, does not call AK, does not apply authority, does not select a winner, does not promote, and does not introduce `eval_behavior.py`.

## 20. Cleanup

```bash
rm -rf "$TD"
```

## Interpretation checklist

Use this checklist when reviewing a generated program assembly:

- `manifest.json` exists and has `schema_version: program-candidate-assembly-v1`.
- `module_surfaces.json` exists and has `schema_version: program-module-surfaces-v1`.
- each module surface has `schema_version: program-module-surface-v1`, declared IO, false effects, and no authority to rank/prune/promote/govern/mutate externally.
- `execution_episode.json` exists and has `schema_version: program-execution-episode-v1`.
- `execution_episode.json` separates materialization, topology execution status, binding checks, behavioral evaluation, and Oracle readability.
- If examples exist, `behavioral_evaluation.result_artifact` is `behavior_results.json` and its hash matches manifest/receipt declarations.
- If examples do not exist, behavioral evaluation is `not_applicable` rather than falsely passed.
- `oracle_readability.oracle_invoked` is `false`.
- `promotion_review.json` keeps `promotion_state: not_promoted`.
- replay passes before drift and fails after declared evidence drift.
- no automatic topology inference, broad graph execution, custom Python module import/execution, Oracle indexing, interpretation, refinement, promotion-review refinement, decision recording, second-candidate generation, candidate comparison, promotion planning, authority export preflight, candidate-state summarization, AK mutation, ranking, winner selection, pruning, promotion, deployment, or governance mutation happened; if an explicit supported `pipeline` topology is present, `topology_execution.status` is `pipeline_materialized`, while unsupported valid topology kinds remain declared-only; if the optional indexing step was run, it wrote only to `$TD/oracle/coordinates.db`, if the optional report step was run, it only read that temp CoordinateIndex, if the optional refinement step was run, it wrote only the `--out` proposal artifact, if the optional promotion-review refinement step was run, it wrote only the requested sidecar packet without overwriting generated promotion artifacts, if the optional jury execution step was run, it wrote only the requested jury sidecar without mutating the candidate, promotion review, Oracle index, AK, governance, or external authority, if the optional decision-recording step was run, it wrote only the requested decision sidecar without mutating the refined review packet, if the optional second-candidate step was run, it wrote only the requested new candidate directory without mutating the source candidate, if the optional comparison step was run, it wrote only the requested comparison sidecar without mutating either candidate or generating another candidate, if the optional generate-and-compare workflow was run, it explicitly wrote one second candidate plus one comparison sidecar without generating a third candidate or making either artifact authoritative, if the optional promotion/adjudication plan step was run, it wrote only the requested plan sidecar with `allowed_for_apply: false` and no authority mutation, if the optional export-preflight step was run, it wrote only the requested preflight packet with `ak_called: false`, `external_authority_mutated: false`, and `ready_for_future_apply: false`, and if the optional candidate-state step was run, it wrote only the requested `program-candidate-state-v1` summary without mutating any input artifact.

## Where this points next

The best next implementation wave after this walkthrough is either bounded territory/frontier integration for the same indexed run kind, broader accepted-proposal policy beyond request-more-evidence constraints patches, richer execution episodes once a narrow behavior-source target exists, or a future external-authority apply layer that consumes export preflight plus candidate-state packets only after exact AK contract binding, duplicate checks, apply receipts, and rollback/failure semantics exist.

A richer execution-episode wave should wait until there is a narrow target such as dataset splits, traces, selected model-jury execution, or enough distinct behavior sources to justify a future `eval_behavior.py` orchestration layer. Promotion/adjudication should remain separate until an explicit authority contract exists.
