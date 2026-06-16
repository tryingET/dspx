---
summary: "Hands-on walkthrough for program-gen and program-loop candidate assemblies, execution episodes, replay checks, Oracle-readable evidence, explicit Oracle reporting, state summaries, and authority boundaries."
read_when:
  - "You want to understand one-intent program generation end to end."
  - "You need to inspect execution_episode.json, behavior_results.json, oracle_evidence.json, manifest, receipt, replay, and optional temp-dir Oracle reporting without invoking AK."
  - "You are explaining the current shipped program-gen / program-loop product loop to an operator."
type: "guide"
---

# Program-gen Walkthrough

This walkthrough shows the current shipped `program-gen` path from one structured intent to a runnable, evaluated, replayable program-shaped candidate assembly.

It is deliberately local-first and non-authoritative:

- uses `DSPX_PROVIDER=stub`
- sets `MLFLOW_ENABLE=0`
- writes to a temp directory
- does not call `ak`
- does not invoke Oracle indexing or interpretation during `program-gen` or mutate Oracle DBs unless the optional explicit temp-dir indexing step is run; `program-loop` uses a candidate-local Oracle index by default and reports that mutation explicitly
- can optionally materialize deterministic local dataset split evidence when intent declares `dataset` or `datasets`
- `program-gen` does not run a model jury or promotion adjudicator; explicit local deterministic jury execution is a separate `program-promote jury` sidecar command
- target-sensitive meta-adjudication sidecars are available via `dspx program-promote meta-adjudication-plan`, `target-profile`, `jury-requirements`, `jury-panel`, `verify-jury-panel`, `adjudicator-formation`, `verify-program-adjudicator`, `evidence-adjudication`, `adjudication-behavior-trace`, and `adjudication-gepa-example`; `program-promote status` can now summarize the generation gate, target-fitness result, target-protocol adjudication, and review-adapter admission readiness, but the whole chain is still not automatic `program-gen` or `program-loop` behavior
- does not rank, select winners, prune, promote, run GEPA/search, export authority, or mutate governance state

The goal is to see the current artifact contract clearly, not to claim a final product loop.

## What this proves today

The current `program-gen` loop proves:

Boundary map for MLflow, Oracle, runtime traces, receipts/replay, and activation authority: [[generated-program-evidence-surface-boundaries]].

1. A prose request or structured intent can first be normalized through `program-gen normalize-intent`, which writes `program-intent-normalization-v1` with assumptions, missing evidence, topology/primitive hints, a `program-generation-assumptions-preview-v1` topology/capability preview, and generation risks without generating programs or mutating authority; direct `program-gen` materialization also writes `intent_normalization.json` before candidate surfaces so the same assumption/risk membrane is retained in generated assemblies.
1. A structured intent can then be inspected through `program-architect plan`, which carries the same generation-assumptions preview, writes non-authoritative architecture candidates, adds preview-only advisory rows for tool/retriever/ReAct/ReActV2/ProgramOfThought/custom-module needs that require explicit safe contracts, includes required explicit contract skeletons for bounded no-tool ReAct/ReActV2, empty-sandbox ProgramOfThought, bounded `retrieve_then_answer` when a bounded retriever declaration exists, and safe named DAG drafts such as `generate_critique_revise`, can write those skeletons as review-required explicit contract draft intents with `--contract-outdir`, can verify a reviewed draft with `program-architect verify-contract`, and can require that verification at materialization time with `program-gen --contract-verification`; the verification sidecar is copied into the candidate directory, hash-bound in the generated manifest, and replay-checked. Contract verification accepts bounded `retrieve_then_answer` drafts with inline/local-snapshot retriever configs while still recording `allows_external_retrievers=false`. Named `generate_critique_revise` and `extract_transform_validate` DAGs are validated for their stage roles, required intermediate data flow, and final-output producer semantics instead of only generic acyclic shape. `--portfolio-outdir` still writes only already-materializable intent drafts. None of these planning paths generate programs or mutate authority.
1. A structured intent can materialize a deterministic program-shaped candidate assembly.
1. Signature, module, program, jury, promotion, and eval harness surfaces are generated as separate artifacts.
1. Explicit user/Pi-declared topology can be validated and preserved in artifacts; the supported generated `pipeline` and bounded inline `retrieve_then_answer` subsets are rendered into multiple signatures/modules and a composed program with bounded deterministic DAG scheduling for out-of-order declarations, fan-out, and fan-in. Materializable DAGs fail closed when cyclic, disconnected, missing direct data-dependency edges, missing output edges, stalled at runtime, or unable to produce declared outputs.
1. When no topology is declared, clear routing/generation, extraction/validation, or reasoning/review cues can deterministically infer bounded generated `Predict`/`ChainOfThought` module topologies instead of the default single `Predict` scaffold.
1. `module_surfaces.json` is a standalone `program-module-surfaces-v1` artifact containing one or more `program-module-surface-v1` contracts for the generated module surfaces that `program-gen` composed.
1. `module_surfaces.json` is replay-checked for safe generated module-surface semantics: module ids/primitives/signatures must retain the declared shape, unsafe effect flags must remain false, optional stage metadata must retain the topology-role source, ReAct/ReActV2 surfaces must keep tool binding disabled, and Retriever surfaces must remain bounded inline/local-snapshot declarations. `generated_module_policy.json` replay now also requires an empty violation list, false effect claims, and the static denied-call set to continue denying `dspy.Tool`.
1. `program_runtime_outcomes.json` is a standalone `program-runtime-outcomes-v1` artifact that declares each generated module's normalized final-output and primitive-specific outcome/trajectory shape, including ReActV2-style history/tool-call/final-submit slots and descriptor-only `tool_refs` as evidence contracts without enabling tools. Replay validates that runtime-policy flags do not drift toward actual runtime execution, tool binding, network/filesystem access, live retrievers, or mismatched final-output contracts.
1. `program_runtime_traces.json` is a standalone `program-runtime-traces-v1` artifact that captures local generated-harness runtime trajectory evidence when examples or dataset splits execute: module call records, stage role metadata, input/output field linkage, intermediate field lineage, final-output source linkage, scheduler completion/stall events, per-record trace hashes, per-source record-level module/final-output coverage, trace coverage over expected modules/final outputs, and ReAct/ReActV2/ProgramOfThought step slots with tool-call results empty. ReAct/ReActV2 trace slots preserve descriptor-only `tool_refs`, may record `program-runtime-tool-call-intent-v1` intent-shape records for declared tool refs, and always record `tool_calls_executed=false`. Replay validates scheduler-event and tool-intent shape as part of the strict no-tool/non-authority posture, and cross-checks trace tool intents and ReActV2 readiness against `module_surfaces.json` and `program_tool_contracts.json` so trace refs must match the owning module surface, readiness refs must match ReActV2 surface refs/contracts, and intent records must resolve to pure contracts with hash-bound dry-run-capable generated adapters. It remains evidence-only and non-authoritative.
1. `program_tool_contracts.json` is a standalone `program-tool-contracts-v1` descriptor-only artifact for declared future tools. It records tool id/name, args/return schemas, effect class, allowlists, timeout policy, redaction policy, dry-run/mutation posture, non-authority flags, generated-adapter hashes/provenance for candidate-local non-bound adapter source, deterministic non-executable `program-tool-adapter-blueprint-v1` source hashes and candidate-local `tool_adapters/*_adapter_blueprint.py` / `tool_adapters/*_adapter.py` artifacts for pure tool declarations, `program-tool-adapter-policy-v1` / `program-tool-generated-adapter-policy-v1` requirements for future executable hash-bound adapters, and `program-react-v2-tool-readiness-v1` blockers for ReActV2 tool binding while keeping `dspy.Tool`, ReAct/ReActV2 tools, execution, network, filesystem, subprocess, and mutation disabled. ReAct/ReActV2 topology modules may now declare `tool_refs` as descriptor-only references to tool contracts while executable `tools` remains `[]`; ReActV2 contract draft intents populate `tool_refs` from pure declared tool contracts and exclude non-pure tools, contract verification fails closed when `tool_refs` do not resolve to pure tool declarations, and ReActV2 pure-tool preflight records whether all referenced tool contracts are pure, schema-bounded, blueprint hash-bound, and replay-policy declared; when those checks pass it reports `ready_for_tool_adapter_materialization=true` for the next generated-adapter implementation slice while still keeping `ready_for_react_v2_tool_binding=false` and execution disabled. Generated module code/module surfaces expose those declared refs while still constructing `dspy.ReActV2(..., tools=[])`. Replay verifies blueprint and adapter-source artifact hashes, verifies adapter policy schema/kind/required-before-enablement/hash-bound flags and generated-adapter provenance posture, verifies adapter validation records (`source_compiles`, constants match, source hash matches artifact), statically checks generated adapter source for the expected non-executing shape with an allowlisted call surface, checks adapter constants, source-preview hashes, canonical adapter/blueprint artifact paths, and adapter/blueprint policy counts against the declared tool id/effect class/args schema/return schema, and the generated adapter source now enforces required fields, rejects unexpected fields when `additionalProperties=false`, checks primitive/nested bounded JSON-schema field types plus enum/const and array min/max item constraints at the adapter boundary, and exposes an `adapter_dry_run()` validation-only path that records `validated_not_executed` plus false effect flags for args and optional expected-return shape without calling tools. Replay executes that dry-run path in a restricted namespace over schema-derived samples, compares the result with the adapter validation record's expected dry-run result, and still confirms the real `adapter()` raises instead of executing. Replay confirms adapters are not executable/imported/bound, and fails closed if ReActV2 readiness/preflight fields drift toward tool binding without the required pure/schema/blueprint/replay preconditions.
1. `program_capability_registry.json` is a standalone `program-capability-registry-v1` descriptor-only artifact that makes the generated-program capability boundary replayable: generated `Predict`/`ChainOfThought`, bounded no-tool `ReAct`, and sandboxed `ProgramOfThought` are materializable; explicit pipeline or `retrieve_then_answer` `Retriever` modules are conditionally materializable only with `retriever.mode: inline_corpus` or materialization-time `local_corpus_snapshot`; experimental `ReActV2` remains descriptor-only by default and is materializable only as an explicit opt-in no-tool module when public `dspy.ReActV2` is installed. ReActV2 tool requests are now surfaced in the generation assumptions preview, but tool binding remains blocked until DSPx has explicit tool authority/effect/redaction/timeout/sandbox/replay/receipt contracts and generated adapter provenance. `Custom` and declared tool/import/external-retriever capabilities remain declared-only until explicit safe adapters exist; `program-custom-module-readiness-v1` and `program-external-retriever-readiness-v1` record blockers and replay keeps imports/live retrievers/execution disabled.
1. `generated_module_policy.json` is a standalone `program-generated-module-policy-v1` artifact that statically verifies generated `module.py` imports/calls/effect claims before materialization proceeds; it is hash-bound in the manifest and replay receipt.
1. `execution_episode.json` is a standalone `program-execution-episode-v1` contract artifact with source-indexed behavior evidence summaries.
1. When examples exist, `eval_examples.py` invokes the generated program locally and writes `behavior_results.json`; `execution_episode.json` records whether that source came from inline examples or `examples_path`, plus result path/hash, count, provider, and metric facts already known.
1. When a dataset is declared, `program-gen` writes `dataset_manifest.json`, deterministic `splits/train.jsonl`, `splits/validation.jsonl`, `splits/test.jsonl`, split-specific harnesses, and `behavior_results.train.json` / `.validation.json` / `.test.json` without merging them into inline examples; `execution_episode.json` records each split as a separate evidence source.
1. `oracle_evidence.json` is source-aware Oracle-readable evidence derived from local behavior results without invoking Oracle: inline examples, `examples_path`, and dataset splits can all contribute evidence sources. It includes only a hash-bound `program_runtime_traces.json` summary so Oracle can report trace presence/coverage without becoming the replay validator.
1. `oracle index --from-program-evidence` can be run explicitly as local CoordinateIndex ingestion; it is not part of `program-gen`.
1. `oracle program-evidence report` can be run explicitly against that temp CoordinateIndex to summarize source-aware behavior evidence without authority effects; it is not part of `program-gen`.
1. `program-architect tournament` can materialize each materializable architecture-plan candidate in isolated local directories, replay-check their receipts, summarize aggregate behavior/topology/artifact signals in `program-architecture-tournament-evidence-matrix-v1`, optionally write candidate-local Oracle indexes/reports with `--with-oracle-reports`, and write `program-architecture-tournament-v1`; it fail-closes before writing on candidate identity, source-intent/topology congruence, authority-flag, intent-integrity, or output-collision problems and does not select a winner or mutate authority.
1. `program-architect recommend` can consume a tournament sidecar and write `program-architecture-recommendation-v1` with candidate advisories and next moves; it fail-closes on missing or widened tournament/evidence/row authority flags and does not rank, select a winner, promote, materialize more programs, or mutate authority.
1. `program-architect loop` can compose normalization, architecture planning, tournament materialization/replay, and recommendation into `program-architect-loop-v1` in an empty/new output directory while preserving the same no-winner/no-promotion/no-authority-mutation boundaries.
1. `program-loop` can compose the core shipped loop in one command: `program-gen`, receipt replay check, candidate-local Oracle indexing/reporting, and `program-promote status`-equivalent candidate-state summary. It still does not rank, promote, call AK, deploy, or mutate governance.
1. `program-refine propose` can be run explicitly over the manifest, declared behavior evidence, and the Oracle report to write a local proposal artifact only; it is not part of `program-gen`.
1. `program-promote review` can be run explicitly over the manifest, original generated promotion shell artifacts, behavior evidence, Oracle report, and refinement proposal to write a local refined promotion-review packet sidecar; it is not part of `program-gen` and is not promotion approval.
1. `program-promote jury` can be run explicitly over the manifest, planned jury artifacts, and already-generated behavior evidence (`behavior_results.json` when present, otherwise bounded `behavior_episode.json`) to write a local deterministic jury-results sidecar; it is not part of `program-gen` and is not promotion approval.
1. `program-promote decide` can be run explicitly over that refined packet plus operator/adjudicator input to write a local decision-record sidecar. For the two-adjudicator path, `program-promote adjudicator-delegation` first lets the DSPx/meta adjudicator approve the generated-program adjudicator, then `program-promote generated-adjudicator-decision` records the generated-program adjudicator's local decision from `program-evidence-adjudication-v1`. Neither path is external authority, activation, or automatic promotion.
1. `program-promote status` can consume `--generation-gate-preflight`, `--generation-fitness-results`, and `--program-evidence-adjudication` to expose a `target_fidelity_state` readout. For Obsidian/PDF review, `obsidian_review_adapter_materialization_allowed=true` means only that a review packet may be materialized; `production_or_domain_activation_allowed` and `canonical_mutation_allowed` remain false.
1. `program-refine generate-candidate` can be run explicitly from a proposed refinement plus a local `request_more_evidence` decision record to materialize one local second candidate at a requested output directory.
1. `program-refine compare-candidates` can be run explicitly over the source and second candidate manifests to write a local comparison sidecar over already-generated `behavior_episode.json` evidence plus example-backed `behavior_results.json` when present.
1. `program-refine generate-and-compare` can be run explicitly as a convenience workflow for exactly one second-candidate generation followed by the same local comparison sidecar.
1. `program-refine episode` can be run explicitly over an existing manifest and Oracle report to compose proposal, refined review, explicit local decision record, optional `request_more_evidence` second-candidate generation or ready-GEPA-sidecar candidate materialization, comparison, optional local promotion/adjudication plan, candidate-state refresh, and a `program-refinement-episode-v1` summary sidecar. It is local-only and non-authoritative; it does not invoke Oracle indexing/reporting, run GEPA/search, run model juries, call AK/governance, mutate external authority, activate, rank, select a winner, or apply promotion.
1. `program-promote plan` can still be run explicitly over an existing candidate manifest, local decision record, and comparison sidecar to write a `program-promotion-plan-v1` local plan sidecar when the guided episode did not opt into planning.
1. `adapters authority agent-kernel-export-preflight` can be run explicitly over a manifest, opaque AK ref, and optional decision/comparison sidecars to write a local `program-external-authority-export-preflight-v1` packet that is preflighted/planned/not applied; `program-promote activation-packet --export-preflight` can carry that packet as activation evidence without applying it after rechecking current manifest/decision/evidence hashes.
1. `program-promote status` can be run explicitly over a manifest plus local sidecars to write one `program-candidate-state-v1` truth-state summary artifact.
1. `program-refine optimize-gepa` can be run explicitly against an existing manifest to write a local `program-refinement-gepa-result-v1` sidecar from explicit train/validation JSONL files, manifest dataset splits, or limited inline examples; it is not part of `program-gen`.
1. `program-refine materialize-gepa-candidate` can be run explicitly over a ready GEPA sidecar to create one local non-authoritative candidate assembly that loads copied optimizer output; it does not rank, select a winner, promote, or mutate authority.
1. `manifest.json` and `manifest.json.meta.json` declare hashes and evidence paths for replay.
1. `dspx run replay --check-only` verifies the declared program evidence artifacts, including `program_runtime_outcomes.json`, `program_runtime_traces.json`, `program_tool_contracts.json`, and `execution_episode.json`; runtime-trace replay also checks internal trace hashes, source record-level coverage consistency, trace coverage consistency, status/count consistency, false tool-execution posture, strict non-authority flags, and count/linkage shape.
1. Promotion and authority remain explicitly pending / non-authoritative.

It does **not** prove:

- rich provider-backed or arbitrary topology inference,
- broad graph execution beyond the supported declared/prompt-inferred `pipeline` DAG subset,
- executable live external retriever/tool/custom-import adapters, ReAct/ReActV2 tool binding, `dspy.Tool` execution, and ProgramOfThought with non-empty filesystem/network/env/tool sandbox access beyond descriptor-only capability/tool declarations, explicit pre-materialization boundary previews, explicit opt-in no-tool ReActV2, the bounded inline-corpus Retriever adapter, and the bounded materialization-time local-corpus snapshot adapter,
- broad dataset/eval orchestration beyond the current deterministic split-specific local harnesses,
- model-backed jury execution,
- model-jury adjudication, external approval, or activation,
- automatic Oracle indexing/interpretation/refinement/promotion-review/decision recording/second-candidate generation/candidate comparison during `program-gen`,
- automatic materialization by `program-architect plan`, or ranking/winner selection by any `program-architect` surface,
- automatic GEPA/search, ranking, winner selection, or authority export/apply,
- ranking, winner selection, promotion approval, authority apply, or external mutation behavior from candidate comparison, local promotion/adjudication planning, or external-authority export preflight,
- richer phenotype, territory, frontier, or multi-source behavior interpretation,
- automatic GEPA/search execution during `program-gen`, `program-loop`, or `program-refine episode`; the guided episode can only consume an explicit already-ready GEPA sidecar,
- broad accepted-proposal policy beyond the explicit request-more-evidence constraints-patch path,
- AK export or task mutation,
- one-command refinement/search/review/decision/activation automation from raw intent; `program-loop` currently stops at local evidence/state summary, and `program-refine episode` starts from an existing manifest plus Oracle report and remains local/non-authoritative.

## PDF transition scenario

A concrete Obsidian/PDF-transition `program-gen` fixture now exists for the flow:

```text
PDF -> source package -> section units -> evidence cards -> merge/create -> review -> canonical notes
```

Read `docs/project/pdf-transition-program-gen.md` for the scenario intent, fixture paths, authority boundaries, and test command. The scenario generates reviewable transition/proposal artifacts only; it does not mutate canonical Wiki/Atlas notes. Its generated-program jury/adjudicator contract is distinct from the DSPx/meta-adjudication layer: the generated program declares `source_grounding`, `authority_boundaries`, and `transition_artifact_quality` perspectives plus `dspx_program_adjudicator_v1` as the generated-program promotion adjudicator, while DSPx/meta sidecars separately verify broader target/profile/jury/adjudicator/evidence behavior.

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

## Fast path: run the coherent local loop

`program-loop` is the first integrated operator path for the core one-intent evidence loop:

```bash
uv run -q python -m dspx.cli.dspx program-loop \
  --intent "$TD/intent.yaml" \
  --outdir "$TD/program-loop" \
  --json > "$TD/program-loop-result.json"
```

It writes these high-signal sidecars in the candidate directory:

- `program_loop.json` — local workflow summary;
- `oracle/coordinates.db` — candidate-local Oracle CoordinateIndex, not the shared/default Oracle DB;
- `program_oracle_report.json` — non-authoritative Oracle program-evidence report;
- `program_candidate_state.json` — local truth-state summary over the manifest and Oracle report.

Inspect the loop summary:

```bash
python - <<'PY'
import json, os
payload = json.load(open(os.environ["TD"] + "/program-loop/program_loop.json"))
print(json.dumps({
    "schema_version": payload["schema_version"],
    "status": payload["status"],
    "steps": {key: value["status"] for key, value in payload["steps"].items()},
    "effect": payload["effect"],
    "non_authority": payload["non_authority"],
}, indent=2, sort_keys=True))
PY
```

Use `--skip-oracle-index` when you want generation/replay/state only and no CoordinateIndex mutation. Even without that flag, the default mutation is candidate-local under `--outdir`, not a production/shared Oracle authority action. `program-loop` preflights all active output paths before candidate generation, rejects generated-artifact basenames and duplicate resolved sidecar/index paths, and therefore avoids overwriting candidate files or producing stale path claims.

## Optional: preflight shared Oracle publication without shared writes

Shared Oracle publication starts with a local preflight packet. It validates the future shared-publication boundary but does not contact or mutate shared Oracle, AK, governance, MLflow, or generated program files:

```bash
uv run -q python -m dspx.cli.dspx oracle program-evidence publish-preflight \
  --manifest "$TD/program-loop/manifest.json" \
  --target shared-postgres \
  --publication-label retained \
  --publisher-id local-operator \
  --publisher-role operator \
  --publisher-assertion "share this synthetic behavior evidence for future Oracle retrieval" \
  --redaction-status not_required \
  --retention-class retained_behavior_memory \
  --out "$TD/program-loop/program_oracle_publication_preflight.json" \
  --json
```

The preflight output is a `program-oracle-shared-publication-preflight-v1` packet. It computes a stable publication id, validates non-authority flags and custody fields, redacts backend secret posture, verifies the `program_runtime_traces.json` summary/hash/semantic posture from `oracle_evidence.json`, records `ready_for_shared_publication: true`, and still records `shared_oracle_mutated: false`.

DSPx also owns the adapter preflight for `pi-autoresearch` campaign evidence packets. If Pi emits an `autoresearch.oracle_evidence.v1` JSON packet, validate it here before any future shared Oracle publication:

```bash
uv run -q python -m dspx.cli.dspx oracle autoresearch-evidence publish-preflight \
  --packet "$TD/autoresearch_oracle_evidence.json" \
  --target shared-postgres \
  --publication-label retained \
  --publisher-id local-operator \
  --publisher-role operator \
  --publisher-assertion "share bounded campaign behavior evidence for future Oracle retrieval" \
  --redaction-status checked \
  --retention-class retained_behavior_memory \
  --out "$TD/autoresearch_oracle_publication_preflight.json" \
  --json
```

That adapter preflight writes `autoresearch-oracle-shared-publication-preflight-v1` locally, validates the `pi-autoresearch` packet/record non-authority flags, and records that no shared Oracle, local `coordinates.db`, AK, governance, MLflow, or program files were mutated.

When a shared Oracle Postgres/pgvector backend is explicitly configured and you intend to publish the curated empirical record, run the standalone publish command. This is never automatic `program-loop` behavior:

```bash
uv run -q python -m dspx.cli.dspx oracle program-evidence publish \
  --preflight "$TD/program-loop/program_oracle_publication_preflight.json" \
  --receipt-out "$TD/program-loop/program_oracle_publication_receipt.json" \
  --json
```

The publish command writes one idempotent shared Oracle coordinate record and a local `program-oracle-shared-publication-receipt-v1` receipt. The receipt is evidence only: it records `shared_oracle_mutated: true` while still recording `ak_called: false`, `governance_mutated: false`, and `promotion_state_changed: false`.

You can cite that receipt in candidate-state and activation evidence packets without granting it promotion authority:

```bash
uv run -q python -m dspx.cli.dspx program-promote status \
  --manifest "$TD/program-loop/manifest.json" \
  --oracle-publication-receipt "$TD/program-loop/program_oracle_publication_receipt.json" \
  --out "$TD/program-loop/program_candidate_state.json" \
  --json
```

For activation packets, `--oracle-publication-preflight` and `--oracle-publication-receipt` add readiness/evidence refs only. Activation-packet generation validates shared publication receipt target/backend posture, secret redaction, idempotency/record/source/non-authority posture and, when both preflight and receipt are supplied, binds receipt source hashes back to that exact preflight. If `--candidate-state` also cites those shared Oracle artifacts, it cross-checks that the refs agree and exposes the result under `evidence_alignment.oracle_publication` instead of treating either source as authority. They cannot satisfy the owning-domain decision, canonical binding, rollout owner, or rollback plan gates; see [[generated-program-activation-boundary]].

`program-loop` can also run shared publication as an explicit opt-in after generation; the default remains candidate-local and service-free. The opt-in requires all custody fields and an explicitly configured shared Oracle backend:

```bash
uv run -q python -m dspx.cli.dspx program-loop \
  --intent "$TD/intent.yaml" \
  --outdir "$TD/program-loop" \
  --publish-to-shared retained \
  --publisher-id local-operator \
  --publisher-role operator \
  --publisher-assertion "share this synthetic behavior evidence for future Oracle retrieval" \
  --redaction-status not_required \
  --retention-class retained_behavior_memory \
  --json
```

With the flag, `program_loop.json` records an `oracle_publication` step and points to `program_oracle_publication_receipt.json`. Without the flag, no shared backend is contacted and the publication step remains `skipped`.

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
- `eval_behavior.py`
- `behavior_episode.json`
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
- this is the bridge toward future local custom module refs, but the current slice does not import or execute arbitrary custom Python modules;
- `program_capability_registry.json` records descriptor-only capability contracts and false effect flags (`provider_called`, `tool_called`, `custom_import_loaded`, network/filesystem/subprocess/external-authority effects all false), permits only explicit inline-corpus or materialization-time local-corpus snapshot Retriever adapters as generated local lexical retrieval, rejects external-looking Retriever module keys such as provider/endpoint/tool/import, and its hash is bound into the manifest and run receipt.
- `program_runtime_outcomes.json` records the normalized module outcome/trajectory contract; it makes DSPy ReActV2-style history/tool-call/final-submit evidence shapes explicit without enabling tool execution.
- `program_runtime_traces.json` records hash-bound local generated-harness runtime trace evidence when behavior examples or dataset splits execute; it captures module-call IO linkage, final-output linkage, per-source record-level module/final-output coverage, and coverage over expected modules/final outputs without enabling tools, retrievers, external adapters, or authority mutation. Replay validates each internal trace hash plus source record coverage / module-output coverage / status-count consistency / no-tool / strict non-authority posture.
- `generated_module_policy.json` records the strict generated-module static policy gate; dynamic imports, filesystem/network/subprocess calls, `dspy.Retrieve`, `dspy.settings`, tools, unsafe ReAct shapes, and ProgramOfThought without the generated empty sandbox fail before a manifest is written.

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

Dataset split evidence is local and non-authoritative. It coexists with inline examples; `eval_behavior.py` orchestrates only the generated example/split harnesses and does not run Oracle automatically.

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
    "runtime_conditions": payload["runtime_conditions"],
    "evaluation_sources": payload["evaluation_sources"],
    "behavior_evidence_summary": payload["behavior_evidence_summary"],
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
- `runtime_conditions` records only already-known metric/runtime/provider facts; provider entries come from the local behavior harness payloads.
- `evaluation_sources` lists every local behavior evidence source that actually ran: inline examples, `examples_path`, and/or each dataset split. Each source records kind, source path or split path, result path/hash, count, status, summary, metric, provider, and harness return status.
- `behavior_evidence_summary` aggregates totals/status counts across those sources without claiming quality, selecting a winner, or applying authority.
- `behavioral_evaluation` remains the legacy inline-example summary pointer to `behavior_results.json` when examples existed and `eval_examples.py` wrote that evidence.
- `oracle_readability` points to `oracle_evidence.json` when local behavior evidence existed; `oracle_invoked` remains `false`. The Oracle-readable payload includes a runtime-trace summary/hash but not full module-call/final-output trace records.
- `non_authority` keeps evidence separate from ranking, pruning, promotion, governance, AK mutation, Oracle authority, winner selection, and external authority mutation.

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

## 8. Inspect source-aware Oracle-readable evidence without invoking Oracle

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
    "source_artifacts": payload["source_artifacts"],
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

This is local evidence ingestion only. It writes to a local CoordinateIndex and does not rank, prune, promote, block, approve, export authority, or mutate governance state. For the DRY map of local SQLite vs shared Oracle Postgres/pgvector vs MLflow Postgres, see [[oracle-backend-current-status]].

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
- behavior status, task type, metric, input/output field, failure signal, behavior source kind, and source artifact counts are summarized from indexed evidence
- `interpretation.summary` describes the indexed behavior source kinds and their limits
- `behavior_source_kind_counts`, `evidence_source_count`, and `total_evaluation_count` summarize source-aware coverage across examples and/or dataset splits
- `non_authority` confirms interpretation-only posture and no ranking, pruning, promotion, governance, or external mutation authority

This report reads the supplied CoordinateIndex. It does not modify `program-gen` artifacts, manifests, receipts, AK, governance, or external authority. The current behavior evidence is still local and bounded through `eval_behavior.py` orchestrating `eval_examples.py` / `behavior_results.json` and/or split-specific `eval_{train,validation,test}.py` / `behavior_results.<split>.json`; there is no broad behavior execution layer beyond those generated harnesses.

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
- `created_from` references the manifest, Oracle report, and `behavior_results.json` when inline/example-file behavior exists; dataset-only proposals keep that path `null` and use source-indexed execution/oracle evidence instead
- `evidence_summary` reflects local behavior status/counts, behavior source kinds, evidence source counts, total evaluation count, Oracle report status, and record match
- failed local behavior may produce a proposed next candidate intent patch such as tightening output mapping for the observed mismatch
- no-examples assemblies degrade to `insufficient_behavior_evidence` rather than inventing behavior
- `non_authority` confirms proposal-only posture and no apply, candidate generation, ranking, pruning, promotion, governance, or external mutation authority

This command writes only the proposal artifact at `--out`. It does not mutate generated program files or behavior result artifacts, does not create a second candidate assembly, does not index/report Oracle evidence automatically, and does not rank, prune, promote, block, export authority, or mutate governance.

## 11. Optional explicit promotion-review refinement packet

If you want to bring the generated promotion shell, behavior evidence, Oracle report, refinement proposal, and optional provider-backed model-jury results into one local adjudication packet, run the promotion-review consumer explicitly:

```bash
uv run -q python -m dspx.cli.dspx program-promote review \
  --manifest "$TD/program/manifest.json" \
  --oracle-report "$TD/oracle/program-evidence-report.json" \
  --refinement-proposal "$TD/refinement/refinement_proposal.json" \
  --out "$TD/promotion/promotion_review_refined.json" \
  --json
```

Add `--model-jury-results "$TD/promotion/model_jury_results.json"` when a valid provider-backed model-jury sidecar already exists.

Expected JSON facts:

- `schema_version: program-promotion-review-refined-v1`
- `promotion_state: not_promoted`
- `candidate_status: exploratory`
- `created_from` references `manifest.json`, original `promotion_review.json`, original `promotion_adjudication_request.json`, original `promotion_decision_template.json`, `behavior_results.json` when present, `behavior_episode.json` when present, the Oracle report, the refinement proposal, and optional `program-model-jury-results-v1` evidence
- behavior, Oracle report, refinement proposal, and optional model-jury summaries are explicit; behavior evidence records whether it came from example-backed `behavior_results.json` or bounded `behavior_episode.json`
- model-jury execution is satisfied only by a valid identity-matched provider-backed model-jury sidecar or an already satisfied generated shell requirement; explicit adjudicator decision remains missing unless policy and evidence truly say otherwise
- `adjudication_packet.status` remains `not_ready_missing_required_evidence` when required local evidence is absent
- `non_authority` confirms local review-packet-only posture and no automatic promotion, Oracle ranking/pruning/promotion, program mutation, new candidate generation, governance authority, or external mutation

This command writes only the requested sidecar artifact. It validates any supplied model-jury sidecar for schema, manifest identity, provider-backed execution, adjudicator non-authority, non-readiness for promotion decision, evidence-only effect flags, and non-authority flags before it can satisfy the model-jury evidence requirement. It does not overwrite generated `promotion_review.json`, `promotion_adjudication_request.json`, or `promotion_decision_template.json`; it does not mutate `manifest.json`, behavior evidence, Oracle evidence, generated Python files, AK, governance, or external authority; it does not generate a new candidate assembly; it does not invoke an adjudicator or approve promotion. Top-level `status: review_packet_ready` means the packet was assembled from available evidence; it does not mean promotion is allowed. Promotion gating uses `review_readiness.ready_for_adjudicator_review`.

## 12. Optional explicit local jury execution sidecar

If you want local deterministic jury evidence over already-generated behavior evidence, run the jury consumer explicitly:

```bash
uv run -q python -m dspx.cli.dspx program-promote jury \
  --manifest "$TD/program/manifest.json" \
  --out "$TD/promotion/jury_results.json" \
  --json
```

Expected JSON facts:

- `schema_version: program-jury-results-v1`
- `status: executed` when `behavior_results.json` or `behavior_episode.json` is present, or `insufficient_behavior_evidence` when behavior evidence is absent
- `created_from` references `manifest.json`, `jury.json`, `jury_selection.json`, `jury_rubric.json`, current `behavior_results.json` when present, and current `behavior_episode.json` when present
- `jury` records planned jury, selection, and rubric schemas plus selected juror count/perspectives
- `behavior_evidence` summarizes current example-backed `behavior_results.json` when present, otherwise bounded `behavior_episode.json` from generated example/split harness orchestration
- `juror_results` records deterministic local per-juror judgments and criteria results while preserving provider/model fields from the planned jury artifacts
- `aggregate` records judgment counts plus agreement/disagreement
- `effect` and `non_authority` confirm local-only/no-mutation behavior

This command writes only the requested `jury_results.json` sidecar. It reads already-generated evidence only: it does not mutate the candidate, does not mutate `promotion_review.json` or `promotion_review_refined.json`, does not generate a new candidate, does not run example/dataset/model-jury/topology/custom-module execution, does not create an Oracle index, does not call external models, does not require provider auth, does not introduce or broaden `eval_behavior.py`, and does not rank, select winners, promote, approve, export authority, mutate AK, or mutate governance.

## 12a. Optional explicit provider-backed model jury

If the program has generated review/extraction artifacts that should be judged by the selected jury perspectives, run a provider-backed model jury explicitly:

```bash
DSPX_PROVIDER=dspy-lm-auth \
uv run -q python -m dspx.cli.dspx program-promote model-jury \
  --manifest "$TD/program/manifest.json" \
  --evidence "$TD/runtime-episode/role_findings_json" \
  --evidence "$TD/runtime-episode/component_inventory_json" \
  --adjudicator-kind target_repo_product_manager_agent \
  --adjudicator-id target_repo_product_manager_agent \
  --adjudicator-repo calisthenics-ai-coach \
  --out "$TD/promotion/model_jury_results.json" \
  --json
```

Expected JSON facts:

- `schema_version: program-model-jury-results-v1`
- `jury.execution_mode: provider_backed_model`
- `jury.provider_backed_model_calls: true`
- `adjudicator` records the downstream target/domain reviewer that should receive the critique, for example a target-repo product-manager agent
- `juror_results` contains one model-backed judgment per selected juror, with outcome, rationale, concerns, and `improvement_requests`
- `aggregate` summarizes blocking concerns and unique improvement requests
- `effect` and `non_authority` confirm no candidate mutation, promotion, AK mutation, governance mutation, Oracle mutation, or external-authority apply

This is the first executable model-jury layer. It still does not improve files in place or approve promotion. To include it in the local adjudication packet, rerun `program-promote review` with `--model-jury-results "$TD/promotion/model_jury_results.json"`; the refined packet will mark model-jury evidence present while still requiring any explicit adjudicator decision. Use the resulting `improvement_requests` as explicit evidence for a later refinement/rerun pass, then route the result to the declared target-repo adjudicator.

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

When the generated program declares a generated-program adjudicator and you want both adjudicator layers explicit, first let the DSPx/meta adjudicator delegate local decision scope:

```bash
uv run -q python -m dspx.cli.dspx program-promote adjudicator-delegation \
  --manifest "$TD/program-loop/manifest.json" \
  --adjudicator-verification "$TD/program-loop/program_adjudicator_verification.json" \
  --out "$TD/program-loop/program_adjudicator_delegation.json" \
  --json
```

Then let the generated-program adjudicator decide:

```bash
uv run -q python -m dspx.cli.dspx program-promote generated-adjudicator-decision \
  --evidence-adjudication "$TD/program-loop/program_evidence_adjudication.json" \
  --adjudicator-delegation "$TD/program-loop/program_adjudicator_delegation.json" \
  --out "$TD/program-loop/promotion_decision_record.json" \
  --json
```

This writes the same `program-promotion-decision-record-v1` shape, but its `created_from` points at both `program-evidence-adjudication-v1` and `program-adjudicator-delegation-v1`. `adjudicator_delegation.decided_by` records the DSPx/meta adjudicator, while `decided_by` records the generated-program adjudicator. It is still local and non-authoritative: it cannot record `promote`, cannot activate production, and cannot mutate AK/governance/Oracle authority.

### 13a. Guided local refinement episode

For the common local request-more-evidence path, `program-refine episode` composes the separate proposal, refined review, explicit decision record, one proposal-derived second candidate, comparison, optional already-produced local jury/model-jury evidence, optional local promotion plan, and candidate-state refresh into one guided episode over an existing manifest and Oracle report. If a ready GEPA sidecar already exists, the same episode can instead consume `--gepa-result` to materialize and compare one GEPA-backed candidate without running GEPA/search:

```bash
uv run -q python -m dspx.cli.dspx program-refine episode \
  --manifest "$TD/program/manifest.json" \
  --oracle-report "$TD/oracle/program-evidence-report.json" \
  --outdir "$TD/refinement-episode" \
  --decision-outcome request_more_evidence \
  --decided-by local_operator \
  --rationale "Need one bounded second candidate before any promotion decision." \
  --promotion-plan \
  --promotion-plan-target local_preferred_candidate \
  --promotion-plan-authority-owner local_operator \
  --json
```

Expected JSON facts:

- `schema_version: program-refinement-episode-v1`
- `steps.refinement_proposal.path`, `steps.promotion_review_refined.path`, `steps.decision_record.path`, either `steps.second_candidate.manifest_path` or `steps.gepa_candidate.manifest_path`, `steps.promotion_plan.path`, and `steps.candidate_state.path` point to local artifacts
- `decision_record.outcome: request_more_evidence`
- local candidate materialization is allowed only for `request_more_evidence`; other decision outcomes require `--no-generate-second-candidate` and no `--gepa-result`
- optional `steps.promotion_plan.status: planned_not_applied` and `steps.promotion_plan.allowed_for_apply: false`
- if `--jury-results "$TD/promotion/jury_results.json"` is supplied, `steps.jury_results.status: included` and the candidate-state sidecar records that deterministic local jury evidence as evidence only
- if `--model-jury-results "$TD/promotion/model_jury_results.json"` is supplied, `steps.model_jury_results.status: included` and the refined review/state sidecars record that provider-backed model-jury evidence as local evidence only
- `effect.ak_called`, `effect.external_authority_mutated`, `effect.governance_mutated`, `effect.promotion_applied`, and `effect.winner_selected` remain false
- source generated-program files are not mutated; sidecar paths are preflighted away from generated-program roots

This guided episode is an ergonomic composition, not new authority. It does not invoke Oracle indexing/reporting, run GEPA/search, run local juries or model juries, call external preflight, AK, governance, activation, ranking, winner selection, or promotion apply. When `--jury-results` is supplied, candidate-state validation rechecks schema, exact candidate identity, local-jury evidence-only effects, and non-authority flags before the evidence can appear in state summaries. When `--model-jury-results` is supplied, the existing model-jury validator rechecks schema, exact candidate identity, provider-backed execution, adjudicator non-authority, evidence-only effects, and non-authority flags before the evidence can appear in review/state summaries. When `--gepa-result` is supplied, GEPA optimizer output is consumed only after the existing GEPA materializer revalidates source identity, readiness, hashes, payload inventory, side-effect flags, and path isolation; the GEPA candidate-result output path and GEPA candidate output root must also stay disjoint from the protected GEPA input sidecar. The optional promotion plan is the same local-only plan sidecar shape as `program-promote plan` and remains `allowed_for_apply=false`. Delete the local sidecar directory and optional second-candidate/GEPA-candidate directory to roll it back.

When writing the adjudication behavior trace, pass the delegation and decision sidecars so future Oracle/GEPA analysis sees the full two-adjudicator behavior, not only the evidence-adjudication step:

```bash
uv run -q python -m dspx.cli.dspx program-promote adjudication-behavior-trace \
  --evidence-adjudication "$TD/program-loop/program_evidence_adjudication.json" \
  --adjudicator-delegation "$TD/program-loop/program_adjudicator_delegation.json" \
  --decision-record "$TD/program-loop/promotion_decision_record.json" \
  --out "$TD/program-loop/adjudication_behavior_trace.json" \
  --json
```

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

This command writes only the requested sidecar. It reads already-generated `behavior_episode.json` evidence plus example-backed `behavior_results.json` when present, but it does not run new behavior harnesses. It does not mutate the source candidate, second candidate, proposal, decision record, Oracle index, AK, governance, or external authority. It does not generate a third candidate, rank candidates, select a winner, promote, block via Oracle, or broaden `eval_behavior.py` beyond its generated harness orchestration role.

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

After a second candidate and comparison sidecar exist, you can capture a local-only plan over the available evidence. If `program-refine episode --promotion-plan ...` was used, this plan already exists in the episode sidecar directory; otherwise run:

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
- `evidence_hashes` records candidate manifest, behavior results when present, behavior episode, execution episode, Oracle-readable evidence, decision record, and comparison sidecar hashes when present
- `eligibility` reports whether behavior evidence came from example-backed `behavior_results.json` or the broader bounded `behavior_episode.json`; dataset-only evidence can qualify the local plan without implying apply readiness
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

The sidecar has `schema_version: program-refinement-gepa-result-v1`. It records source identity, selected evidence source/counts, held-out-validation status, GEPA attempt status, prepared input CSV hashes, any local optimizer output path, optimizer-output manifest hash/readiness when present and valid, and non-authority flags. Missing, invalid, or non-object optimizer-output manifests are recorded as `status: gepa_output_unverified` with `ready_for_future_candidate_materializer=false`. A valid optimizer output is classified as `optimizer_output_hash_bound_not_candidate`: hash-bound input for the explicit materializer below, not by itself a generated program candidate, ranking, winner selection, promotion, AK/governance mutation, or external authority apply. The command preflights `--outdir` and `--result-out` before writes: optimizer output must be outside and not contain the source candidate root, the result sidecar must be outside the source candidate root, and the sidecar must not overlap the optimizer output directory. It writes only to those isolated requested paths, does not mutate the source candidate or source dataset split artifacts/results, does not create a repo Oracle index, does not rank, select a winner, promote, mutate AK/governance/external authority, or introduce `eval_behavior.py`.

## 16. Optional: materialize one local GEPA-backed candidate

When `optimize-gepa` produced a valid hash-bound optimizer output, the explicit materializer can turn it into a new local `program-candidate-assembly-v1` that loads the copied optimizer output:

```bash
uv run -q python -m dspx.cli.dspx program-refine materialize-gepa-candidate \
  --manifest "$TD/program/manifest.json" \
  --gepa-result "$TD/refinement/gepa_refinement_result.json" \
  --outdir "$TD/program-gepa-candidate" \
  --result-out "$TD/refinement/gepa_candidate_result.json" \
  --json
```

The result sidecar has `schema_version: program-refinement-gepa-candidate-result-v1`. The command validates source identity, GEPA readiness, non-authority/effect flags, optimizer-manifest hash, optimizer payload inventory/tree hash, source-program hash, path separation, and symlink-free optimizer output before writing the candidate. The new candidate manifest records `gepa_refinement`, includes `gepa_optimizer_output/manifest.json` and `gepa_candidate_lineage.json` as hash-bound surfaces, records the optimizer payload tree hash, refreshes `behavior_episode.json` after replacing `program.py` with the GEPA loader, and removes stale pre-rewrite `oracle_evidence.json` rather than carrying scaffold-era Oracle readability evidence forward. The result sidecar reports `behavior_refresh`; failed GEPA-loader execution is local behavior evidence, not promotion authority. It writes only the requested candidate directory plus optional result sidecar; it does not mutate the source candidate, GEPA output, Oracle, AK, governance, or external authority, and it does not rank, select a winner, approve, promote, deploy, or activate the candidate.

When the next local action is comparison, use the explicit composed workflow instead of hand-threading the generated candidate manifest path:

```bash
uv run -q python -m dspx.cli.dspx program-refine materialize-and-compare-gepa-candidate \
  --manifest "$TD/program/manifest.json" \
  --gepa-result "$TD/refinement/gepa_refinement_result.json" \
  --outdir "$TD/program-gepa-candidate" \
  --comparison-out "$TD/refinement/gepa_candidate_comparison.json" \
  --gepa-candidate-result-out "$TD/refinement/gepa_candidate_result.json" \
  --workflow-out "$TD/refinement/gepa_generate_compare_result.json" \
  --json
```

The composed workflow writes `program-refinement-gepa-generate-and-compare-result-v1` as a local receipt over exactly one GEPA candidate materialization plus one source-vs-GEPA-candidate comparison sidecar. It is still evidence only: no winner selection, ranking, promotion, Oracle authority mutation, AK/governance mutation, or external authority export is performed.

If the operator is already in the guided refinement episode, consume the same ready GEPA result there instead of hand-threading the standalone workflow:

```bash
uv run -q python -m dspx.cli.dspx program-refine episode \
  --manifest "$TD/program/manifest.json" \
  --oracle-report "$TD/oracle/program-evidence-report.json" \
  --outdir "$TD/refinement-episode-gepa" \
  --decision-outcome request_more_evidence \
  --decided-by local_operator \
  --rationale "Compare one ready GEPA candidate before any promotion decision." \
  --gepa-result "$TD/refinement/gepa_refinement_result.json" \
  --promotion-plan \
  --promotion-plan-target local_preferred_candidate \
  --promotion-plan-authority-owner local_operator \
  --json
```

Expected additional JSON facts:

- `steps.gepa_candidate.gepa_result_path` points at the explicit ready GEPA result sidecar.
- `steps.gepa_candidate.manifest_path`, `steps.gepa_candidate.comparison_path`, and `steps.gepa_candidate.candidate_result_path` point to local episode artifacts.
- `effect.local_second_candidate_generated: false`, `effect.local_gepa_candidate_generated: true`, `effect.gepa_optimizer_output_mutated: false`, and `effect.winner_selected: false`.
- `non_authority.gepa_candidate_evidence_only: true`, `non_authority.gepa_approval: false`, and `non_authority.winner_selection: false`.

This guided GEPA branch still does not run GEPA/search, select a winner, promote, apply authority, mutate the source candidate, mutate optimizer output, or mutate AK/governance/external authority. It consumes a ready GEPA sidecar and writes local evidence only.

If an operator wants to carry a standalone comparison into local non-applying planning, record an explicit comparison decision first. Comparison-only decisions may withhold, reject, or request more evidence; they cannot promote:

```bash
uv run -q python -m dspx.cli.dspx program-promote decide-comparison \
  --comparison "$TD/refinement/gepa_candidate_comparison.json" \
  --outcome withhold \
  --decided-by local-operator \
  --rationale "GEPA comparison is local evidence only; keep candidate withheld pending external authority." \
  --out "$TD/refinement/gepa_comparison_decision.json" \
  --json

uv run -q python -m dspx.cli.dspx program-promote plan \
  --manifest "$TD/program-gepa-candidate/manifest.json" \
  --decision-record "$TD/refinement/gepa_comparison_decision.json" \
  --comparison "$TD/refinement/gepa_candidate_comparison.json" \
  --source-manifest "$TD/program/manifest.json" \
  --target local_preferred_candidate \
  --authority-owner local-operator \
  --out "$TD/refinement/gepa_promotion_plan.json" \
  --json
```

The decision record and plan are local evidence/planning artifacts only. They do not approve, promote, rank, select a winner, mutate Oracle/AK/governance, or export external authority.

## 17. Inspect manifest and receipt declarations

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
  --model-jury-results "$TD/promotion/model_jury_results.json" \
  --comparison "$TD/refinement/candidate_comparison.json" \
  --gepa-refinement "$TD/refinement/gepa_refinement_result.json" \
  --export-preflight "$TD/export/ak-export-preflight.json" \
  --out "$TD/state/program_candidate_state.json" \
  --json
```

Expected JSON facts:

- `schema_version: program-candidate-state-v1`
- `status` is a truth-preserving local posture such as `not_promoted_external_preflighted_not_applied`
- `candidate_identity` and optional `source_identity` identify the exact artifacts being summarized
- `evidence_state` reports example-backed behavior results when present, bounded `behavior_episode.json` evidence when present, execution episode, Oracle-readable evidence, optional Oracle report, optional refinement proposal, and optional role-aware GEPA optimizer evidence/readiness for the candidate or source manifest
- `promotion_state` reports review readiness, decision outcome, optional local deterministic jury-results evidence, optional provider-backed model-jury-results evidence, comparison role, optional promotion plan, optional external-authority local preflight blockers, optional activation-packet status/next-action/blockers, and separate future external-apply blockers
- `truth_summary` keeps `promotion_applied`, `external_authority_mutated`, `governance_mutated`, `ak_called`, `winner_selected`, `automatic_promotion`, and `ready_for_future_apply` false; optional GEPA evidence may set `gepa_output_ready_for_future_candidate_materializer=true` without generating a candidate, and optional activation evidence may set `activation_packet_present=true` without applying activation
- `artifact_hashes` records deterministic hashes for every supplied sidecar plus local behavior result / behavior episode evidence when present

This command writes only the requested state summary. Local jury results, provider-backed model-jury results, GEPA refinement results, export preflights, and activation packets are summarized as evidence only and do not create promotion authority, candidate materialization, activation, or winner selection. The command does not mutate candidate artifacts or sidecar inputs, does not create or mutate Oracle indexes, does not call AK, does not apply authority, does not select a winner, does not promote, and does not introduce `eval_behavior.py`.

## 19c. Optional activation evidence packet with model-jury evidence

When behavior, Oracle, refined review, rollout owner, and rollback evidence are present, a provider-backed model-jury sidecar can satisfy the activation packet's jury-evidence slot without applying activation:

```bash
uv run -q python -m dspx.cli.dspx program-promote activation-packet \
  --manifest "$TD/program/manifest.json" \
  --owning-domain softwareco/dspx-generated-program-governance \
  --activation-target local-dogfood-only \
  --authority-owner softwareco-program-governance \
  --oracle-report "$TD/oracle/program-evidence-report.json" \
  --model-jury-results "$TD/promotion/model_jury_results.json" \
  --review "$TD/promotion/promotion_review_refined.json" \
  --export-preflight "$TD/export/ak-export-preflight.json" \
  --rollout-owner softwareco-runtime-operator \
  --rollback-plan "Disable the generated-program route and restore the previous production program version." \
  --out "$TD/activation/activation_packet.json" \
  --json
```

Expected JSON facts:

- `schema_version: generated-cognition-program-production-activation-packet-v1`
- `status: ready_for_domain_adjudication` when the behavior, Oracle, model-jury, review, rollout-owner, and rollback evidence are present and no decision record has been supplied
- `missing_required_evidence: []`
- `remaining_activation_blockers` still includes `domain_decision_record` and `canonical_binding_ref`
- `evidence.model_jury_results` records the model-jury sidecar path/hash/schema; `evidence.jury_results` may be `null` when deterministic local jury results were not supplied
- `evidence.external_authority_export_preflight` records the export-preflight path/hash/schema, `status`, `export_id`, target system/contract, opaque `external_ref`, `ready_for_future_apply: false`, and future external-apply blockers when supplied
- `effect.production_activation_applied`, `effect.ak_mutated`, and `effect.external_authority_mutated` remain `false`
- `non_authority.activation_packet_only` is `true`

Activation-packet generation validates model-jury schema, executed/executed-with-failures status, manifest identity, provider-backed execution, at least one judged juror, adjudicator non-authority, non-readiness for promotion decision, evidence-only effect flags, and no promotion/ranking/domain/external/canonical authority claims. When `--export-preflight` is supplied, it also validates exact candidate identity, preflight-only/planned-not-exported posture, false `ready_for_future_apply`, false external mutation request, target mutation/apply disabled, false AK/governance/external/program/promotion effects, false non-authority widening flags, complete planned evidence refs, and current manifest/decision/evidence hashes. The packet is local activation evidence only: it does not activate, deploy, promote, select a winner, call AK, mutate governance, mutate Oracle, mutate external authority, apply the preflight, or replace the domain decision/canonical binding gates. If this packet is later supplied to `program-promote status --activation-packet`, candidate state accepts only supported local activation-packet statuses and rechecks the packet's manifest/evidence hashes against required evidence refs for any sidecars supplied to status, while also binding any supplied export-preflight manifest/decision/comparison hashes, before summarizing next action, missing evidence, remaining activation blockers, rollout owner, rollback-plan presence, and canonical binding ref while preserving the same no-activation boundary.

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
- `execution_episode.json` separates materialization, topology execution status, binding checks, bounded `eval_behavior.py` orchestration, source-indexed evaluation evidence, behavioral evaluation, and Oracle readability.
- If examples exist, `behavioral_evaluation.result_artifact` is `behavior_results.json` and its hash matches manifest/receipt declarations; `evaluation_sources` also states whether the source was inline examples or `examples_path`.
- If dataset splits exist, each split appears in `evaluation_sources` with its split artifact hash, `behavior_results.<split>.json` path/hash, count, status, and provider/metric facts already present.
- If examples do not exist, behavioral evaluation is `not_applicable` rather than falsely passed.
- `oracle_readability.oracle_invoked` is `false`.
- `promotion_review.json` keeps `promotion_state: not_promoted`.
- replay passes before drift and fails after declared evidence drift.
- no arbitrary/provider-backed topology inference, broad graph execution, external retriever/tool execution, ReAct tool binding, ProgramOfThought filesystem/network/env/tool sandbox access, custom Python module import/execution, Oracle indexing, interpretation, refinement, promotion-review refinement, decision recording, second-candidate generation, candidate comparison, promotion planning, authority export preflight, candidate-state summarization, AK mutation, ranking, winner selection, pruning, promotion, deployment, or governance mutation happened; bounded deterministic prompt-inferred `Predict`/`ChainOfThought` pipelines may materialize when clear cues are present; if an explicit supported `pipeline` topology is present, `topology_execution.status` is `pipeline_materialized`; if an explicit supported `retrieve_then_answer` topology is present, `topology_execution.status` is `retrieve_then_answer_materialized` and every bounded inline or snapshot Retriever output must feed a downstream answer module that reaches `output`; supported explicit pipeline modules include bounded no-tool `ReAct` and sandboxed `ProgramOfThought`; unsupported valid topology kinds/primitives/capability declarations remain declared-only in `program_capability_registry.json`; if the optional indexing step was run, it wrote only to `$TD/oracle/coordinates.db`, if the optional report step was run, it only read that temp CoordinateIndex, if the optional refinement step was run, it wrote only the `--out` proposal artifact, if the optional promotion-review refinement step was run, it wrote only the requested sidecar packet without overwriting generated promotion artifacts, if the optional jury execution step was run, it wrote only the requested jury sidecar without mutating the candidate, promotion review, Oracle index, AK, governance, or external authority, if the optional decision-recording step was run, it wrote only the requested decision sidecar without mutating the refined review packet, if the optional second-candidate step was run, it wrote only the requested new candidate directory without mutating the source candidate, if the optional comparison step was run, it wrote only the requested comparison sidecar without mutating either candidate or generating another candidate, if the optional generate-and-compare workflow was run, it explicitly wrote one second candidate plus one comparison sidecar without generating a third candidate or making either artifact authoritative, if the optional promotion/adjudication plan step was run, it wrote only the requested plan sidecar with `allowed_for_apply: false` and no authority mutation, if the optional export-preflight step was run, it wrote only the requested preflight packet with `ak_called: false`, `external_authority_mutated: false`, and `ready_for_future_apply: false`, and if the optional candidate-state step was run, it wrote only the requested `program-candidate-state-v1` summary without mutating any input artifact.

## Where this points next

The best next implementation wave after this walkthrough is either bounded territory/frontier integration for the same indexed run kind, broader accepted-proposal policy beyond request-more-evidence constraints patches, richer execution episodes once a narrow behavior-source target exists, or a future external-authority apply layer that consumes export preflight plus candidate-state packets only after exact AK contract binding, duplicate checks, apply receipts, and rollback/failure semantics exist.

A richer execution-episode wave should wait until there is a narrow target such as traces or selected model-jury execution. The current `eval_behavior.py` layer is intentionally bounded to generated example/split harness orchestration. Promotion/adjudication should remain separate until an explicit authority contract exists.
