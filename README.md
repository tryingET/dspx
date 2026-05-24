---
summary: "Primary DSPx README with product overview, quickstart, and command examples."
read_when:
  - "You are onboarding to DSPx."
  - "You need the main user-facing overview or current CLI examples."
type: "guide"
---

DSPx — local DSPy toolkit (native signatures first)
===================================================

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)
[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/downloads/)

DSPx is a **local CLI toolkit** for DSPy workflows.

Primary focus:
- native signature generation (`signature gen`)
- signature refinement (`signature refine`)
- module generation (`module-gen`)
- optimization with GEPA (`optimize gepa`)
- replay + explainability via local artifacts/cache (MLflow optional)

If you only need one mental model, use this loop:

1) generate signature → 2) refine signature → 3) generate module/program →
4) optimize with GEPA → 5) replay from artifacts and explain with traces.

---

## What this repo is (and is not)

- Is: local-first developer toolchain around DSPy.
- Is: provider-agnostic runtime with sane defaults.
- Is not: hosted SaaS.
- Is not: CI-only automation project.

Day-to-day value is the local CLI workflow.

---

## Quick start (local)

Requirements:
- Python 3.13+
- `uv`
- `just`
- optional provider CLIs (e.g. `pi`)

Install/sync:

```bash
just install
```

Run CLI from source:

```bash
just dspx --help
just forge --help   # optional separate app CLI
```

Offline/deterministic posture (recommended while iterating):

```bash
export DSPX_PROVIDER=stub
export MLFLOW_ENABLE=0
```

First local base-layer loop (offline, temp-dir by default, no AK calls):

```bash
just smoke-base
```

This runs signature generation, module generation, `program-gen`, generated eval harnesses, and the non-mutating authority export-plan adapter using `examples/program_gen/ticket_intent.yaml`. See `docs/project/first-local-loop.md`; for a step-by-step inspection of `execution_episode.json`, behavior evidence, Oracle-readable evidence, replay, and authority boundaries, see `docs/project/program-gen-walkthrough.md`.

Program-refinement loop smoke (also offline/temp-dir by default, no AK calls):

```bash
just smoke-program-refinement
```

This runs the explicit local evidence/refinement path through temp-dir Oracle indexing/reporting, proposal, refined review packet, request-more-evidence decision record, one second-candidate generation, and local comparison sidecar. A separate `program-promote plan` command can then consume an existing candidate manifest, local decision record, and comparison sidecar to write a `program-promotion-plan-v1` local plan. A separate authority adapter can now consume a manifest, an explicit Agent Kernel ref, and optional decision/comparison sidecars to write a local `program-external-authority-export-preflight-v1` packet. The GEPA program-refinement seam is separate: `program-refine optimize-gepa` must be invoked explicitly against an existing manifest. These paths remain non-authoritative and do not call AK, rank, select a winner, promote, export/apply authority, mutate governance, or introduce `eval_behavior.py`.

---

## Native signature workflow (core)

### 1) Generate signature

Deterministic template path (no LM):

```bash
just dspx signature gen "Extract names from text" \
  --template-version simple-v1 \
  --class-name Sig_Names \
  --input text \
  --output names \
  --outfile generated/sig_names.py
```

Native LM-backed path (spec-first):

```bash
just dspx signature gen "Extract names from text" \
  --template-version v1 \
  --provider pi-rpc \
  --class-name Sig_Names \
  --input text \
  --output names \
  --max-attempts 3 \
  --summary \
  --summary-json-out generated/sig_names.summary.json \
  --outfile generated/sig_names.py
```

### 2) Refine signature

```bash
just dspx signature refine "Extract names from text" \
  --attempts 3 \
  --provider pi-rpc \
  --summary \
  --summary-json-out generated/sig_names.refine.summary.json \
  --outfile generated/sig_names_refined.py
```

### 3) Inspect quality telemetry

```bash
just dspx signature quality-summary --json
```

Strict gate run (fails with exit code 2 on gate failure):

```bash
just dspx signature quality-summary \
  --json \
  --fail-on-gate \
  --max-fallback-rate 0.25 \
  --max-attempts-p95 3.0 \
  --min-validation-pass-rate 0.90 \
  --min-smoke-pass-rate 0.90
```

CI/provider-corpus parity gate (same profile used in core CI):

```bash
uv run -q python scripts/build_signature_provider_quality_log.py \
  --out generated/ci/signature_provider_quality.jsonl

just dspx signature quality-summary \
  --log-path generated/ci/signature_provider_quality.jsonl \
  --run-kind signature-gen \
  --json \
  --fail-on-gate \
  --max-fallback-rate 0.10 \
  --max-attempts-p95 1.0 \
  --min-validation-pass-rate 1.0 \
  --min-smoke-pass-rate 1.0
```

Native signature pipeline details:
- `docs/SIGNATURE_NATIVE_PIPELINE.md`

---

## Module generation

```bash
just dspx module-gen \
  --name Summarizer \
  --description "Summarize a passage" \
  --input text \
  --output summary \
  --template-version simple-v1 \
  --outfile generated/module_summarizer.py
```

---

## Program generation

Generate a deterministic program-shaped candidate assembly from one structured intent.

If you want Pi to turn a natural-language DSPy program request into this YAML first, use the repo-owned project skill at `.pi/skills/dspx-program-intent-authoring/SKILL.md` (see `docs/project/pi-dspx-intent-assistant.md`). The skill is a Pi-side authoring surface only; DSPx core still consumes structured intent and does not own natural-language interpretation.

```yaml
# intent.yaml
name: AnswerQuestion
objective: Answer a question from the supplied context.
inputs:
  - context
  - question
outputs:
  - answer
  - confidence
metric: exact_match
constraints:
  - cite only supplied context
# Optional richer field specs:
# input_fields:
#   - name: context
#     type: str
#     desc: Supplied evidence
# output_fields:
#   - name: confidence
#     type: Literal['low', 'high']
#     desc: Confidence label
# Optional: explicit future jury contract (planned only; no juror model calls here)
# jury:
#   selection_model: perspective_balanced_explicit_pool
#   minimum_jurors: 3
#   perspectives: [correctness, robustness, clarity]
#   jurors:
#     - id: correctness_local
#       model: local-small
#       perspective: correctness
# Optional: explicit promotion adjudicator (decision authority, still pending)
# promotion:
#   adjudicator:
#     kind: human_operator  # or ai_agent, ai_council, hybrid, policy_gate
#     id: local_operator
#   # Optional opaque refs for a future adapter/export tool; DSPx core does not call them.
#   external_authority:
#     refs:
#       - system: agent_kernel
#         ref: AK-1234
#         role: optional_authority_export_target
# Optional: explicit topology contract (rendered for the narrow pipeline subset;
# preserved as declared input and never inferred)
# topology:
#   kind: pipeline
#   execution_status: declared_not_materialized
#   modules:
#     - id: classify_ticket
#       primitive: Predict
#       signature:
#         name: ClassifyTicket
#         inputs: [ticket_text]
#         outputs: [route]
#     - id: draft_response
#       primitive: ChainOfThought
#       signature:
#         name: DraftResponse
#         inputs: [ticket_text, route]
#         outputs: [response]
#   edges:
#     - from: input
#       to: classify_ticket
#     - from: classify_ticket
#       to: draft_response
#       when:
#         field: route
#         equals: billing
#     - from: draft_response
#       to: output
# Optional: inline examples or examples_path: examples.yaml
# Optional: local dataset split evidence (coexists with inline examples):
# dataset:
#   path: data/support_tickets.jsonl
#   input_fields: [ticket_text]
#   output_fields: [urgency]
#   split:
#     strategy: ratio
#     train: 0.7
#     validation: 0.15
#     test: 0.15
#     seed: 42
# Optional explicit split files are also accepted:
# datasets:
#   train: data/train.jsonl
#   validation: data/validation.jsonl
#   test: data/test.jsonl
```

```bash
just dspx program-gen \
  --intent intent.yaml \
  --outdir generated/programs/answer_question
```

The generated candidate assembly contains a structured plan, separate surfaces, and replayable metadata:

- `plan.json` — deterministic `program-plan-v1` contract derived from the intent; records normalized field specs, task type, default single-module topology or explicit declared topology, `declared_topology` vs `materialized_topology`, truthful topology execution/materialization status, materialized surfaces including `module_surfaces.json`, metric/runtime/constraints, examples metadata, non-authority defaults, and an explicit planned `program-jury-v1` multi-model evaluation shape when provided
- `jury.json` — standalone planned jury contract copied out of the plan so future jury execution can bind to an exact per-program juror/perspective pool artifact; when no explicit pool is supplied, DSPx infers one from intent features such as task type, metric, examples, fields, and constraints
- `jury_selection.json` — deterministic non-authoritative juror selection artifact; prefers diverse perspectives from the per-program pool, records selected jurors, and still calls no models
- `jury_rubric.json` — deterministic non-authoritative per-juror rubric artifact; binds selected perspectives to criteria and adversarial questions for a later jury execution episode
- `promotion_review.json` — deterministic non-authoritative local promotion-review shell; records the explicit pending adjudicator (`human_operator`, `ai_agent`, `ai_council`, `hybrid`, or `policy_gate`), optional opaque `external_authority` refs for a separately invoked adapter/export tool, pending behavioral evaluation, model-jury execution, and adjudicator-decision requirements while keeping the candidate unpromoted
- `promotion_adjudication_request.json` — deterministic non-authoritative decision packet for the configured adjudicator, including evidence refs, missing evidence, allowed outcomes, optional opaque external authority refs, and a pending decision-record template
- `promotion_decision_template.json` — standalone pending `program-promotion-decision-v1` template that an explicit adjudicator may later fill; it is not a decision
- `module_surfaces.json` — standalone `program-module-surfaces-v1` artifact containing one or more `program-module-surface-v1` contracts; each generated module surface declares `module_id`, `source_kind`, primitive, capability ref, signature IO, generated class/path metadata, false effect flags, and explicit non-authority flags. This is the bridge toward future local custom module references, but this slice does not import or execute arbitrary custom Python modules.
- `program_capability_registry.json` — standalone `program-capability-registry-v1` descriptor-only contract that records the generated-program capability boundary. It marks generated `Predict`/`ChainOfThought` as materializable, explicit pipeline `Retriever` modules as conditionally materializable only when they use the bounded `inline_corpus` adapter, and `ReAct`/`ProgramOfThought`/`Custom` as declared-only until explicit safe adapters exist; it does not bind external tools/retrievers, load imports, call providers, rank, promote, or mutate authority.
- `generated_module_policy.json` — standalone `program-generated-module-policy-v1` artifact that statically verifies generated `module.py` imports/calls/effect claims before materialization proceeds; it fails closed on dynamic imports, filesystem/network/subprocess calls, `dspy.Retrieve`, `dspy.settings`, tools, ReAct, and ProgramOfThought.
- `signature.py` — signature surface generated through the signature service
- `module.py` — module surface generated through the module service
- `program.py` — program assembly wrapper exporting `build_program()` / `build_student()`
- `eval_smoke.py` — deterministic smoke harness
- `eval_jury.py` — deterministic jury artifact binding harness that validates `jury.json`, `jury_selection.json`, and `jury_rubric.json` without calling models
- `eval_promotion.py` — deterministic promotion artifact binding harness that validates `promotion_review.json`, `promotion_adjudication_request.json`, and `promotion_decision_template.json` without invoking an adjudicator
- `examples.json` / `eval_examples.py` — emitted when the intent includes inline `examples` or `examples_path`; validates example binding, invokes the generated program locally, and writes replayable behavior evidence without calling juror models
- `behavior_results.json` — emitted when examples are present; records `program-behavior-results-v1` evidence with intent/IO identifiers, per-example inputs, expected outputs, observed outputs when available, status/error/degraded notes, summary counts, and non-authoritative evidence-only authority
- `dataset_manifest.json` / `splits/{train,validation,test}.jsonl` / `eval_{train,validation,test}.py` / `behavior_results.{train,validation,test}.json` — emitted when the intent declares `dataset` or `datasets`; materializes deterministic local dataset split evidence from JSONL or JSON/YAML list-of-object records shaped like inline examples (`inputs`/`outputs`), runs split-specific local harnesses, permits empty splits with `summary.total: 0` and `status: no_examples`, and carries explicit non-authority flags
- `oracle_evidence.json` — emitted when inline-example behavior results exist; records `program-oracle-evidence-v1` readability-only evidence with candidate/assembly/episode/receipt IDs, intent/task/metric/IO facets, behavior result hash/summary/status counts, failure/degraded/error signals, compact deterministic `oracle_text`, source artifact hashes, and explicit non-authority flags. Dataset split behavior evidence is manifest/receipt/replay evidence in this slice; Oracle indexing remains explicit and is not run automatically.
- `execution_episode.json` — standalone `program-execution-episode-v1` contract that separates materialization, compile/smoke checks, examples binding, jury binding, promotion binding, behavioral evaluation, Oracle readability, and non-authority flags; it does not invoke Oracle and cannot rank, prune, promote, export, or mutate external authority
- `intent.json` — normalized structured intent
- `manifest.json` — candidate assembly / execution episode / receipt-bundle metadata, including plan/jury/selection/rubric/promotion-review/adjudication-request/decision-template/execution-episode hash provenance plus behavior result and Oracle-readability hashes/summaries when examples are present
- `manifest.json.meta.json` — standard `program-gen` run receipt, including the same plan/jury/selection/rubric/promotion-review/adjudication-request/decision-template/execution-episode evidence plus behavior result and Oracle-readability hashes/summaries when examples are present

This path is intentionally deterministic and scaffold-first for ordinary no-topology intents, while also rendering the current narrow explicit `pipeline` topology subset. `program-intent-v2` may carry an explicit user/Pi-declared topology (`single_module`, `pipeline`, `router`, `retrieve_then_answer`, `extract_transform_validate`, `generate_critique_revise`, or `custom`) with module IDs, `primitive` names, `signature.name` / `signature.inputs` / `signature.outputs`, and edges. For `pipeline`, DSPx now materializes supported modules (`Predict`, `ChainOfThought`, and explicit bounded `Retriever` modules with `retriever.mode: inline_corpus`) into multiple signature/module classes and a composed `program.py`; the generated runner uses a bounded deterministic scheduler for declared DAGs, so out-of-order module declarations, fan-out, and fan-in can execute when declared inputs become available. Materializable pipeline DAGs must be acyclic, every module must have an inbound edge, non-input data dependencies must come from direct inbound module outputs, and declared outputs must have an edge from a producing module to `output`; runtime stalls or missing declared outputs raise instead of returning blank values. `when` supports only simple field equality (`field` + `equals`) and no executable expressions. When no topology is declared, `program-gen` can now deterministically infer bounded generated `Predict`/`ChainOfThought` module topologies from clear prompt cues such as routing+generation, extraction+validation, or reasoning/review, choosing those generated modules over the default single `Predict` scaffold when they are more valuable; retrievers are never prompt-inferred. `program-gen` also emits `module_surfaces.json` so generated single-module scaffolds, explicit topology modules, and prompt-inferred generated modules are represented as replayable, hashable, IO-declared module surfaces, `program_capability_registry.json` so the richer future primitives/tools/import boundary is explicit and replay-checked instead of implicit, and `generated_module_policy.json` so generated module imports/calls/effect claims are statically checked before candidate assembly. `module-gen` should be understood as one producer of module surfaces; `program-gen` composes module surfaces. Unsupported topology kinds and unsupported primitives remain accepted/preserved as declared-only planning contracts when valid. This slice does not infer provider-backed arbitrary topology, execute arbitrary custom imports, bind or call external tools/retrievers, run ReAct, run ProgramOfThought, or load local custom modules; the only retriever execution is the generated deterministic inline-corpus lexical adapter embedded from the intent, and Retriever modules fail closed if they include external-looking module keys such as provider, endpoint, tool, or import. Example-backed runs capture a minimal local behavior episode via `eval_examples.py` / `behavior_results.json` and a compact Oracle-readable evidence view for explicit later ingestion. Dataset-backed runs additionally materialize deterministic local split files plus split-specific harnesses and `program-behavior-results-v1` evidence; ratio splits use a seeded `random.Random(seed)` shuffle, `floor(n * train)` / `floor(n * validation)` counts, and remaining records for test, while explicit split files are copied into canonical split artifacts without ratio recomputation. Inline examples and dataset splits are never silently merged. `eval_behavior.py` is emitted only when inline/example-file or dataset behavior evidence exists, and no Oracle indexing runs during materialization. The `jury` entry remains a planned evaluation contract during materialization: no juror models are called by `program-gen`. Explicit local deterministic jury execution is available only through `program-promote jury` over an existing manifest and writes a non-authoritative `program-jury-results-v1` sidecar. External authority refs are opaque metadata only: DSPx core does not validate, call, or mutate Agent Kernel or any other external system during materialization. It materializes evidence; it does not automatically index, report, refine, review, decide, generate follow-up candidates, compare candidates, promote, rank, select winners, run GEPA/search, run jury execution, prune, export authority, or grant Oracle/governance authority. Any GEPA-backed program refinement is a separate `program-refine optimize-gepa` command over an existing manifest.

Before materialization, normalize prose or an existing intent into an explicit `program-intent-normalization-v1` packet that surfaces assumptions, missing evidence, topology/primitive hints, and generation risks without calling providers or generating code:

```bash
just dspx program-gen normalize-intent \
  --prompt "Route support tickets, then draft a helpful response with rationale." \
  --out /tmp/dspx-intent-normalization.json \
  --normalized-intent-out /tmp/dspx-normalized-intent.json \
  --json
```

The normalizer writes a valid `program-intent-v2` draft when requested. It does not invent examples/datasets, materialize programs, call Oracle, rank/select winners, promote, call AK, or mutate governance/external authority.

Before materialization, the non-authoritative architecture planner can show the candidate program possibility space and optionally write materializable candidate intent drafts:

```bash
just dspx program-architect plan \
  --intent examples/program_gen/ticket_intent.yaml \
  --out /tmp/dspx-architecture-plan.json \
  --portfolio-outdir /tmp/dspx-architecture-portfolio \
  --json
```

The planner writes `program-architecture-candidates-v1` and, when requested, `program-architecture-intent-portfolio-v1` intent drafts only. Declared materializable pipeline drafts preserve the same bounded execution contract as `program-gen`, including explicit `Retriever` modules only when they carry `retriever.mode: inline_corpus`. It does not materialize candidate programs, call providers, index Oracle, rank/select winners, promote, call AK, or mutate governance/external authority. Materialize a chosen draft explicitly with `dspx program-gen --intent /tmp/dspx-architecture-portfolio/candidate_intents/<candidate>.json --outdir <candidate-dir>` and then replay-check the resulting receipt.

For an empirical local portfolio run, use the tournament surface:

```bash
just dspx program-architect tournament \
  --architecture-plan /tmp/dspx-architecture-plan.json \
  --outdir /tmp/dspx-architecture-tournament \
  --out /tmp/dspx-architecture-tournament.json \
  --json
```

`program-architect tournament` materializes each materializable candidate in an isolated local directory, replay-checks each generated receipt, summarizes aggregate behavior/topology/artifact signals in a `program-architecture-tournament-evidence-matrix-v1`, and writes `program-architecture-tournament-v1`. It validates the supplied architecture plan before creating tournament directories and fail-closes on duplicate/unknown candidate identities, plan-level or candidate-level authority-widening flags, and materializable candidate intent integrity issues. Add `--with-oracle-reports` to explicitly write candidate-local `oracle/coordinates.db` indexes and `program_oracle_report.json` files for each materialized candidate. It is still evidence-only: no raw examples/outputs in the matrix, no shared Oracle mutation, no Oracle ranking, no winner selection, no promotion, no AK/governance/external-authority mutation.

For the guided local product loop, compose normalization, architecture planning, tournament materialization/replay, and recommendation in one command:

```bash
just dspx program-architect loop \
  --prompt "Route support tickets, then draft a helpful response with rationale." \
  --outdir /tmp/dspx-architect-loop \
  --json
```

`program-architect loop` writes `normalization.json`, `normalized_intent.json`, `architecture_plan.json`, `tournament.json`, `architecture_recommendation.json`, and `program_architect_loop.json`. Add `--with-oracle-reports` only when you want explicit candidate-local Oracle indexes/reports. The loop still does not rank/select winners, promote, call AK, mutate governance, or mutate shared Oracle/external authority.

To turn an existing tournament sidecar into next moves without selecting a winner, write a recommendation packet:

```bash
just dspx program-architect recommend \
  --tournament /tmp/dspx-architecture-tournament.json \
  --out /tmp/dspx-architecture-recommendation.json \
  --json
```

`program-architect recommend` writes `program-architecture-recommendation-v1`: candidate advisories, limitations, and next moves such as adding examples, rerunning with candidate-local Oracle reports, fixing replay, or sending candidates to explicit human/adjudicator review. It fail-closes if the tournament, evidence matrix, or candidate rows contain missing or widened authority flags. It does not materialize programs, rank candidates, select winners, promote, call Oracle indexes, call AK, or mutate governance/external authority.

Oracle ingestion is a separate local command that writes only to a chosen CoordinateIndex:

```bash
DSPX_ORACLE_EMBEDDING_BACKEND=mock just dspx oracle index \
  --from-program-evidence \
  --path generated/programs/answer_question \
  --index-path /tmp/dspx-program-oracle/coordinates.db \
  --json
```

That command indexes `program-oracle-evidence-v1` records for later Oracle interpretation/search. It does not rank, prune, promote, block, approve, export authority, or mutate governance state.

The current Oracle storage backend is intentionally local SQLite only. The DS1621 Postgres service discussed in the MLflow setup backs MLflow metadata, not Oracle coordinates; DSPx does not currently provision or consume a shared Oracle Postgres/pgvector backend. To make that boundary executable, inspect it with:

```bash
just dspx oracle backend-status --json
```

`backend-status` is read-only: it does not create the CoordinateIndex, does not connect to Postgres, and does not report secret values from database-related environment variables.

Oracle interpretation/reporting is also explicit and separate. It reads indexed `program-oracle-evidence` records from the supplied local CoordinateIndex and summarizes example-backed behavior evidence from `eval_examples.py` / `behavior_results.json` without mutating program artifacts, governance, or external authority:

```bash
DSPX_ORACLE_EMBEDDING_BACKEND=mock just dspx oracle program-evidence report \
  --index-path /tmp/dspx-program-oracle/coordinates.db \
  --json > /tmp/dspx-program-oracle/program-evidence-report.json
```

The report is evidence-grounded and non-authoritative: it summarizes behavior statuses, task/metric/IO facets, source artifacts, and failure signals such as output mismatches. It does not rank, prune, promote, block, approve, export authority, or activate policy.

Bounded refinement proposal is another explicit, separate command. It consumes the `program-gen` manifest, declared example-backed behavior evidence, and the non-authoritative Oracle report, then writes one local proposal artifact:

```bash
just dspx program-refine propose \
  --manifest generated/programs/answer_question/manifest.json \
  --oracle-report /tmp/dspx-program-oracle/program-evidence-report.json \
  --out /tmp/dspx-program-refine/refinement_proposal.json \
  --json
```

The proposal is local and advisory only. It does not mutate generated program files, does not create a new candidate assembly, and does not rank, prune, promote, block, export authority, or mutate governance.

Promotion-review refinement is also explicit and separate. It consumes the `program-gen` manifest, original generated promotion shell artifacts, declared behavior evidence when present, the non-authoritative Oracle report, and the non-authoritative refinement proposal, then writes one local sidecar packet:

```bash
just dspx program-promote review \
  --manifest generated/programs/answer_question/manifest.json \
  --oracle-report /tmp/dspx-program-oracle/program-evidence-report.json \
  --refinement-proposal /tmp/dspx-program-refine/refinement_proposal.json \
  --out /tmp/dspx-program-promote/promotion_review_refined.json \
  --json
```

The refined packet is local review evidence only. It keeps `promotion_state: not_promoted`, preserves the need for explicit adjudicator decision and any required model-jury evidence, does not overwrite `promotion_review.json`, `promotion_adjudication_request.json`, or `promotion_decision_template.json`, does not generate a new candidate assembly, and does not rank, prune, promote, block via Oracle, export authority, or mutate governance.

Explicit local jury execution is a separate sidecar command over an already-materialized candidate:

```bash
just dspx program-promote jury \
  --manifest generated/programs/answer_question/manifest.json \
  --out /tmp/dspx-program-promote/jury_results.json \
  --json
```

The jury sidecar has `schema_version: program-jury-results-v1`. It consumes `manifest.json`, planned `jury.json` / `jury_selection.json` / `jury_rubric.json`, and current `eval_examples.py` / `behavior_results.json` evidence when present. This first slice is offline and deterministic: it preserves planned juror provider/model fields but does not call external models, does not require provider auth, and degrades to `insufficient_behavior_evidence` instead of inventing behavior when `behavior_results.json` is absent. It writes only the requested `jury_results.json` sidecar, does not mutate the candidate or promotion review, does not generate a new candidate, does not create or mutate Oracle indexes, does not introduce `eval_behavior.py`, and does not rank, select winners, promote, approve, export authority, mutate AK, or mutate governance.

Explicit local adjudicator decision recording is a separate sidecar command:

```bash
just dspx program-promote decide \
  --review /tmp/dspx-program-promote/promotion_review_refined.json \
  --outcome request_more_evidence \
  --decided-by local_operator \
  --rationale "Need model-jury execution before any promotion decision." \
  --out /tmp/dspx-program-promote/promotion_decision_record.json \
  --json
```

The decision record has `schema_version: program-promotion-decision-record-v1`. It consumes the refined packet, records explicit `withhold`, `reject`, `request_more_evidence`, or gated `promote` input, and writes only the requested sidecar. Non-promote outcomes keep `promotion_state_after_decision: not_promoted`. `promote` fails closed unless `review_readiness.ready_for_adjudicator_review` is explicitly true; top-level `status: review_packet_ready` is not enough. The command does not mutate generated program artifacts, the refined review packet, Oracle indexes, AK, governance, external authority, or candidate code.

A request-more-evidence decision can explicitly materialize one local second candidate from the bounded proposal patch:

```bash
just dspx program-refine generate-candidate \
  --manifest generated/programs/answer_question/manifest.json \
  --refinement-proposal /tmp/dspx-program-refine/refinement_proposal.json \
  --decision-record /tmp/dspx-program-promote/promotion_decision_record.json \
  --outdir /tmp/dspx-program-refine/answer_question_v2 \
  --json
```

This command requires a `program-refinement-proposal-v1` with `status: proposed` and a local decision record with `outcome: request_more_evidence`. It applies only the bounded `constraints` intent patch for this first slice, records local refinement lineage inside the new candidate intent, and materializes a normal local program candidate assembly at `--outdir`. It does not mutate the source candidate, proposal, decision record, Oracle indexes, AK, governance, or external authority, and it does not promote either candidate.

After a second candidate already exists, candidate comparison is an explicit local sidecar command:

```bash
just dspx program-refine compare-candidates \
  --source-manifest generated/programs/answer_question/manifest.json \
  --candidate-manifest /tmp/dspx-program-refine/answer_question_v2/manifest.json \
  --out /tmp/dspx-program-refine/candidate_comparison.json \
  --json
```

The comparison sidecar has `schema_version: program-refinement-candidate-comparison-v1`. It consumes the two existing `program-candidate-assembly-v1` manifests, reads their current example-backed `behavior_results.json` evidence from `eval_examples.py`, records identity/lineage facts when available, and reports behavior-status/count deltas plus failure signals added, removed, and persisted. It is local comparison only: it does not mutate either candidate, generate another candidate, rank, select a winner, promote, export authority, make Oracle authoritative, mutate AK/governance, or introduce `eval_behavior.py`.

For operator ergonomics, the same local generation-plus-comparison path can be invoked explicitly in one command:

```bash
just dspx program-refine generate-and-compare \
  --manifest generated/programs/answer_question/manifest.json \
  --refinement-proposal /tmp/dspx-program-refine/refinement_proposal.json \
  --decision-record /tmp/dspx-program-promote/promotion_decision_record.json \
  --outdir /tmp/dspx-program-refine/answer_question_v2 \
  --comparison-out /tmp/dspx-program-refine/candidate_comparison.json \
  --json
```

This explicit workflow returns `schema_version: program-refinement-generate-and-compare-result-v1`, materializes exactly one local second candidate, then writes the same comparison sidecar. It is not `program-gen` automation, does not generate a third candidate, and still does not rank, select a winner, promote, export authority, mutate Oracle authority, AK, or governance.

Local promotion/adjudication planning is another explicit sidecar command:

```bash
just dspx program-promote plan \
  --manifest /tmp/dspx-program-refine/answer_question_v2/manifest.json \
  --decision-record /tmp/dspx-program-promote/promotion_decision_record.json \
  --comparison /tmp/dspx-program-refine/candidate_comparison.json \
  --target local_preferred_candidate \
  --authority-owner local_operator \
  --out /tmp/dspx-program-promote/promotion_plan.json \
  --json
```

The plan has `schema_version: program-promotion-plan-v1`, `status: planned_not_applied`, and `promotion_state: not_promoted`. It records the local target, declared authority owner, candidate identity, source artifact schemas, evidence hashes, eligibility for local planning only, audit trail, and reversibility posture. It writes only the requested `promotion_plan.json` sidecar. It does not mutate candidate artifacts, decision records, comparison sidecars, Oracle indexes, AK, governance, or external authority, and it does not rank, select a winner, approve, promote, deploy, export authority, or make Oracle authoritative. `allowed_for_apply` is always false; a future apply surface would need a separate authority contract.

For governance-kernel's generated cognition-program activation transition, DSPx can export a non-authoritative activation evidence packet:

```bash
just dspx program-promote activation-packet \
  --manifest generated/programs/answer_question/manifest.json \
  --owning-domain softwareco/program-governance \
  --activation-target softwareco-production-route:answer_question \
  --authority-owner softwareco-program-governance \
  --oracle-report /tmp/dspx-program-oracle/program-evidence-report.json \
  --jury-results /tmp/dspx-program-promote/jury_results.json \
  --review /tmp/dspx-program-promote/promotion_review_refined.json \
  --decision-record /tmp/dspx-program-promote/promotion_decision_record.json \
  --rollout-owner softwareco-runtime-operator \
  --rollback-plan "disable generated route and restore previous production program" \
  --out /tmp/dspx-program-promote/activation_packet.json \
  --json
```

The packet has `schema_version: generated-cognition-program-production-activation-packet-v1` and maps local DSPx/Oracle/MLflow/jury evidence to `generated-cognition-program.production_activation`. It never activates production, never calls AK, and never mutates governance; it remains blocked until the owning domain decision, canonical binding, rollout, and rollback requirements are satisfied. The society-wide governance boundary lives in `~/ai-society/holdingco/governance-kernel/docs/core/definitions/generated-dspy-program-promotion-governance.md`.

GEPA-backed program refinement is also explicit and local. It consumes an existing `program-candidate-assembly-v1` manifest, chooses input evidence from explicit `--train` / `--validation` JSONL files, manifest-declared `splits/train.jsonl` and `splits/validation.jsonl`, or limited inline `examples.json` fallback, and writes a `program-refinement-gepa-result-v1` sidecar:

```bash
just dspx program-refine optimize-gepa \
  --manifest generated/programs/answer_question/manifest.json \
  --outdir /tmp/dspx-program-refine/answer_question_gepa \
  --result-out /tmp/dspx-program-refine/gepa_refinement_result.json \
  --max-metric-calls 2 \
  --json
```

The result records source identity, evidence source/counts, held-out-validation limitations, GEPA attempt status, any local optimizer output, and non-authority flags. In the current slice the existing GEPA optimizer may write a local DSPy optimizer output, but it does not yet produce a new `program-candidate-assembly-v1`; the sidecar therefore degrades truthfully with `candidate: null` unless a real candidate-assembly materializer exists. The command does not mutate the source candidate, source dataset split artifacts/results, Oracle indexes, AK, governance, or external authority; it does not rank, select a winner, promote, export authority, or introduce `eval_behavior.py`.

`program-gen` still does not automatically index, report, interpret, refine, review, decide, generate follow-up candidates, compare candidates, or run GEPA.

A separately invoked adapter can plan an Agent Kernel export from the generated evidence without mutating AK:

```bash
just dspx adapters authority agent-kernel-plan \
  --manifest generated/programs/answer_question/manifest.json \
  --external-ref AK-1234 \
  --out generated/programs/answer_question/ak-export-plan.json
```

That legacy adapter output is a sidecar export plan (`planned_not_exported`) plus a local `*.meta.json` receipt for the plan, not a promotion decision and not an AK write.

For the stronger base-layer authority boundary, a separate preflight command can bind local evidence artifacts to an explicit opaque AK ref and report what would still have to be true before any future apply layer could be allowed:

```bash
just dspx adapters authority agent-kernel-export-preflight \
  --manifest generated/programs/answer_question/manifest.json \
  --external-ref AK-1234 \
  --decision-record /tmp/dspx-program-promote/promotion_decision_record.json \
  --comparison /tmp/dspx-program-refine/candidate_comparison.json \
  --out /tmp/dspx-program-export/ak-export-preflight.json \
  --json
```

The preflight packet has `schema_version: program-external-authority-export-preflight-v1`. It records manifest/decision/comparison schemas and hashes, manifest identity, deterministic `export_id` and idempotency fingerprint, an `ak_task_evidence_attachment` planned payload, effect flags proving `ak_called: false` / `external_authority_mutated: false` / `governance_mutated: false`, and blocking reasons including `external_apply_not_implemented` plus `target_contract_not_bound_to_ak_runtime`. Missing optional decision/comparison inputs degrade to `incomplete_preflight`; explicit identity mismatches fail closed. It does not call AK, mutate external authority, mutate governance, promote, select a winner, or provide an apply command.

To explain the whole local truth state for a candidate in one sidecar, use:

```bash
just dspx program-promote status \
  --manifest /tmp/dspx-program-refine/answer_question_v2/manifest.json \
  --source-manifest generated/programs/answer_question/manifest.json \
  --oracle-report /tmp/dspx-program-oracle/program-evidence-report.json \
  --refinement-proposal /tmp/dspx-program-refine/refinement_proposal.json \
  --review /tmp/dspx-program-promote/promotion_review_refined.json \
  --decision-record /tmp/dspx-program-promote/promotion_decision_record.json \
  --jury-results /tmp/dspx-program-promote/jury_results.json \
  --comparison /tmp/dspx-program-refine/candidate_comparison.json \
  --promotion-plan /tmp/dspx-program-promote/promotion_plan.json \
  --export-preflight /tmp/dspx-program-export/ak-export-preflight.json \
  --out /tmp/dspx-program-state/program_candidate_state.json \
  --json
```

The state artifact has `schema_version: program-candidate-state-v1`. It summarizes materialization, behavior evidence, Oracle readability/reporting, refinement proposal, review readiness, decision outcome, optional local jury-results evidence, comparison role, promotion plan/apply posture, external-authority preflight blockers, deterministic artifact hashes, and the remaining future-apply requirements. It is a state summary only: it does not call AK, mutate inputs, mutate Oracle indexes, apply promotion, select a winner, or mutate governance/external authority. DSPy's native `Adapter` abstraction remains the right pattern for LM protocol/format adaptation; AK authority export is kept as a DSPx authority adapter over evidence artifacts rather than as part of deterministic `program-gen` core.

---

## GEPA optimization

Optimize a program exporting `build_student()` against train/val data:

```bash
just dspx optimize gepa \
  --program examples/gepa_demo_program.py \
  --train examples/gepa_demo_train.csv \
  --out generated/gepa_demo_optimized \
  --student-provider vllm-local \
  --reflection-provider dspy-lm-auth \
  --metric exact \
  --max-metric-calls 2
```

Use config-driven mixed-provider defaults (`[optimize]`) without passing provider flags:

```bash
TD="$(mktemp -d)"
DSPX_CONFIG=config.provider-runtime-v4.example.toml MLFLOW_ENABLE=0 uv run -q python -m dspx.cli.dspx module-gen \
  --name Student \
  --description "Answer a short question with a short answer" \
  --input question \
  --output answer \
  --template-version simple-v1 \
  --outfile "$TD/student.py"

DSPX_CONFIG=config.provider-runtime-v4.example.toml MLFLOW_ENABLE=0 just dspx optimize gepa \
  --program "$TD/student.py" \
  --train examples/gepa_modulegen_train.csv \
  --out "$TD/optimized" \
  --metric contains \
  --max-metric-calls 2 \
  --nrows 3
```

For the currently verified mixed-provider setup, caveats, and end-to-end smoke notes, see:
- `docs/project/provider-runtime-v4.md`

Fast smoke from generated module:

```bash
just gepa-modulegen-smoke
```

More:
- `docs/GEPA_FROM_MODULE_GEN.md`

---

## Replay + explain (practical model)

Replay/source of truth:
- local generated artifacts (`generated/...`)
- sidecar run receipts (`*.meta.json`, schema `receipt_version: v2`)
- on-disk cache (`generated/cache/...`)

Inspect cache:

```bash
just dspx cache info
just dspx cache list
```

Receipt-first replay check (local/offline):

```bash
just dspx run replay --from generated/sig_names.py.meta.json --check-only
# CI-friendly payload:
just dspx run replay --from generated/sig_names.py.meta.json --check-only --json
```

Replay exit codes:
- `0`: verification passed
- `1`: receipt parsed, but drift detected (hash/cache/provenance)
- `2`: invalid receipt/arguments

Replay JSON diagnostics (stable machine-readable fields):
- `error_codes`: ordered unique replay issue codes
- `error_details`: `{code, message, check?}` entries for each issue

Local-first explain (receipt/manifest facts first):

```bash
just dspx run explain --from generated/sig_names.py.meta.json
just dspx run explain --from generated/sig_names.py.meta.json --json
# optional best-effort MLflow linkage scan:
just dspx run explain --from generated/sig_names.py.meta.json --with-mlflow --json
# optional bounded remote candidate lookup (remote tracking URIs only; default off):
just dspx run explain --from generated/sig_names.py.meta.json --with-mlflow --mlflow-remote-lookup --json
```

`--with-mlflow` requires an explicit tracking URI. Explicit sqlite URIs are treated as local scan candidates; remote URIs stay bounded/no-network unless `--mlflow-remote-lookup` is set.

Explain exit codes:
- `0`: explanation generated (`ok` or `degraded`)
- `2`: invalid receipt/arguments

Explain JSON includes replay-derived fields:
- `replay_status`
- `replay_error_codes`, `replay_error_details`

Replay/explain contract:
- `docs/RUN_REPLAY_EXPLAIN.md`

Explainability sink (optional):
- MLflow artifacts/metrics/tags when enabled.
- execution must still work with `MLFLOW_ENABLE=0`.

MLflow defaults/policy:
- `MLFLOW_ENABLE=1` + no `MLFLOW_TRACKING_URI` -> no MLflow side effects; DSPx does not keep a local sqlite fallback
- runs are started explicitly by DSPx commands/services (no implicit run start during bootstrap)
- DSPy autolog traces are disabled by default to avoid noisy GEPA span warnings

Use the shared DS1621 MLflow server when you want the UI / shared remote tracking surface:

```bash
just mlflow-up
export MLFLOW_ENABLE=1
export MLFLOW_TRACKING_URI=http://ds1621:50000
```

The DS1621 server is the normal DSPx MLflow target. Replay/explain correctness remains local-first from receipts/manifests and does not require MLflow availability. `dspx program-gen` logs a `program-gen` run and uploads only declared materialized assembly artifacts when MLflow is configured; generated `program.py` also exposes explicit runtime hooks for `program-runtime` runs, and generated `eval_behavior.py` logs `program-eval` metrics/artifacts.

MLflow behavior and constraints:
- `docs/MLFLOW_OBSERVABILITY_PLAN.md`

---

## Oracle Time Travel (Phase C slice)

Receipt v2 metadata now supports a first local CLI slice for behavioral history:

```bash
# Ingest program-gen Oracle-readable evidence into a local CoordinateIndex
just dspx oracle index --from-program-evidence --path generated/programs --index-path /tmp/dspx-program-oracle/coordinates.db --json

# Report on indexed program Oracle evidence without authority effects
just dspx oracle program-evidence report --index-path /tmp/dspx-program-oracle/coordinates.db --json > /tmp/dspx-program-oracle/program-evidence-report.json

# Propose a bounded refinement artifact without mutating generated files or authority
just dspx program-refine propose --manifest generated/programs/answer_question/manifest.json --oracle-report /tmp/dspx-program-oracle/program-evidence-report.json --out /tmp/dspx-program-refine/refinement_proposal.json --json

# Build a local refined promotion-review sidecar without promotion authority
just dspx program-promote review --manifest generated/programs/answer_question/manifest.json --oracle-report /tmp/dspx-program-oracle/program-evidence-report.json --refinement-proposal /tmp/dspx-program-refine/refinement_proposal.json --out /tmp/dspx-program-promote/promotion_review_refined.json --json

# Run explicit local deterministic jury execution as sidecar evidence only
just dspx program-promote jury --manifest generated/programs/answer_question/manifest.json --out /tmp/dspx-program-promote/jury_results.json --json

# Record an explicit local adjudicator decision sidecar without external authority
just dspx program-promote decide --review /tmp/dspx-program-promote/promotion_review_refined.json --outcome request_more_evidence --decided-by local_operator --rationale "Need model-jury execution before promotion." --out /tmp/dspx-program-promote/promotion_decision_record.json --json

# Explicitly materialize one local second candidate from request-more-evidence
just dspx program-refine generate-candidate --manifest generated/programs/answer_question/manifest.json --refinement-proposal /tmp/dspx-program-refine/refinement_proposal.json --decision-record /tmp/dspx-program-promote/promotion_decision_record.json --outdir /tmp/dspx-program-refine/answer_question_v2 --json

# Explicitly compare already-materialized source and second-candidate behavior evidence
just dspx program-refine compare-candidates --source-manifest generated/programs/answer_question/manifest.json --candidate-manifest /tmp/dspx-program-refine/answer_question_v2/manifest.json --out /tmp/dspx-program-refine/candidate_comparison.json --json

# Or explicitly generate one second candidate and immediately write the local comparison sidecar
just dspx program-refine generate-and-compare --manifest generated/programs/answer_question/manifest.json --refinement-proposal /tmp/dspx-program-refine/refinement_proposal.json --decision-record /tmp/dspx-program-promote/promotion_decision_record.json --outdir /tmp/dspx-program-refine/answer_question_v2 --comparison-out /tmp/dspx-program-refine/candidate_comparison.json --json

# Write a local planned_not_applied promotion/adjudication plan sidecar from existing evidence
just dspx program-promote plan --manifest /tmp/dspx-program-refine/answer_question_v2/manifest.json --decision-record /tmp/dspx-program-promote/promotion_decision_record.json --comparison /tmp/dspx-program-refine/candidate_comparison.json --target local_preferred_candidate --authority-owner local_operator --out /tmp/dspx-program-promote/promotion_plan.json --json

# List known behavioral branches from local receipts
just dspx oracle branch --path generated --json

# Inspect one branch timeline
just dspx oracle branch feature-x --path generated --json

# Compare two branches via shared lineage IDs and branch-local runs
just dspx oracle diff feature-x feature-y --path generated --json

# Find the first bad outcome boundary inside a branch
just dspx oracle bisect feature-x --path generated --json
```

The Phase C slice is receipt-backed only: it reads local `*.meta.json` files,
uses `branch`, `parent_run_id`, and `causal_chain` when present, and falls back
cleanly when lineage is partial.

---

## Providers

Default posture:
- default provider fallback: `pi-rpc`
- offline testing provider: `stub`
- local student provider: `vllm-local`
- auth-backed reflection provider: `dspy-lm-auth`

List providers:

```bash
just dspx providers list
```

Resolve provider configuration:

```bash
just dspx providers resolve --provider vllm-local --json
```

Health-check providers:

```bash
just dspx providers health --provider vllm-local --probe --json
just dspx providers health --provider dspy-lm-auth --probe --json
```

How to verify DSPx is using your Pi auth-backed subscription:

```bash
just show-dspy-lm-auth-route
```

Equivalent manual checks:

```bash
just dspx providers resolve --provider dspy-lm-auth --json
just dspx providers health --provider dspy-lm-auth --probe --json
```

What to check:
- `runtime.auth_storage` / `metadata.auth_storage` should point to `~/.pi/agent/auth.json`
- `auth_storage_exists` should be `true`
- the health payload should report `auth available for provider=codex`
- `--probe` should succeed if DSPx can actually use that auth-backed route

Important: DSPx does **not** always use your Pi auth-backed subscription. In the mixed provider profile, `vllm-local` stays local while `dspy-lm-auth` uses the auth-backed route. For optimize runs, that usually means the student path is local and only the reflection path uses your Pi/Codex-backed auth.

Benchmark providers:

```bash
just dspx providers benchmark --provider vllm-local --provider dspy-lm-auth --json
```

Known compatibility note:
- mixed-provider profile (`vllm-local` + `dspy-lm-auth`) live-verified on `2026-03-22`
- program-gen example/dataset behavior harnesses default to `dspy-lm-auth` rather than the deterministic stub; tests may explicitly set `DSPX_PROVIDER=stub`, but real program creation should use an auth-backed provider
- `codex/gpt-5.5` is the default `dspy-lm-auth` model for real generated-program execution
- `codex/gpt-5.4` was previously verified through `dspy-lm-auth`; keep only as an explicit compatibility override if needed
- `codex/gpt-5.4-nano` is rejected on the active ChatGPT/Codex account route
- for local editable `dspy-lm-auth` work, prefer `just link-dspy-lm-auth` so DSPx resolves `dspy_lm_auth` from `~/ai-society/softwareco/contrib/dspy-lm-auth`
- details and benchmark snapshot: `docs/project/provider-runtime-v4.md`

---

## Monorepo boundaries

Non-negotiable boundary:
- allowed: `apps/* -> core`
- forbidden: `core -> apps/*`
- never import `dspx_forge.*` from core.

Guardrail:

```bash
just monorepo-check
```

---

## Day-to-day commands

Standardized outer surface:

```bash
just help
just check
just ci
just doctor
just run              # falls back to DSPx CLI help when called without args
just smoke-base
just smoke-program-refinement
```

Repo-local quality commands:

```bash
just fmt
just lint
just typecheck
just test
```

Core-only slice:

```bash
just lint-core
just typecheck-core
just test-core
```

Forge-only slice:

```bash
just lint-forge
just typecheck-forge
just test-forge
```

Hook setup (once per clone):

```bash
just hooks-install
```

Canonical workflow contract:
- `docs/project/developer_workflow.md`

Validation tiers:

```bash
# pre-commit hook (fast, staged-only):
# - ruff format/check
# - whitespace check

# pre-push hook (fast gate):
# - just verify-pre-push
#   - workflow contract + governance validation
#   - task-scope attestation for the committed slice via explicit task_id, AK claim, or changed task-scope artifact path
#   - pre-commit all-files
# explicit full gate:
# - just verify-full
#   - runs verify-fast first, then executes runtime/invariant and typecheck/test branches in parallel
```

Batch-commit flow (run once before push):

```bash
just task-scope-check task_id=<AK-ID> mode=working-tree
just verify-pre-push
just verify-full
```

Read-only verification and sanity commands keep `uv.lock` clean by using `uv run --no-sync` under the hood.

---

## Repo map

- core runtime: `packages/dspx-core/src/dspx/`
- core CLI entrypoint: `packages/dspx-core/src/dspx/cli/dspx.py`
- forge app: `apps/forge/src/dspx_forge/`
- tests: `tests/`
- scripts: `scripts/`
- docs: `docs/`

---

## Canonical docs map

- architecture: `docs/ARCHITECTURE.md`
- native signatures: `docs/SIGNATURE_NATIVE_PIPELINE.md`
- status: `PROJECT_STATUS.md`
- direction stack: `docs/project/vision.md`, `docs/project/strategic_goals.md`, `docs/project/tactical_goals.md`, `docs/project/operational_goals.md`
- program-gen walkthrough: `docs/project/program-gen-walkthrough.md`
- monorepo boundaries: `docs/MONOREPO_TRANSITION.md`
- GEPA quick path: `docs/GEPA_FROM_MODULE_GEN.md`
- observability/MLflow: `docs/MLFLOW_OBSERVABILITY_PLAN.md`
- replay/explain receipts: `docs/RUN_REPLAY_EXPLAIN.md`
- architecture draft kickoff (DSPx + upstream): `docs/OBSERVABILITY_ARCH_DRAFTS.md`
- observability RFC templates: `docs/RFC_TEMPLATE_DSPX_NEXT.md`, `docs/RFC_TEMPLATE_UPSTREAM_MLFLOW.md`, `docs/RFC_TEMPLATE_UPSTREAM_DSPY.md`
- forge app: `docs/FORGE.md`

---

## License

AGPL-3.0 — see `LICENSE`.
