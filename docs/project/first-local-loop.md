---
summary: "First clean-repo local smoke loop for trying DSPx base-layer generation without live providers or authority mutation."
read_when:
  - "You want to try DSPx locally from a clean checkout."
  - "You need the shortest safe walkthrough for signature, module, program-gen, eval harnesses, and authority export planning."
type: "guide"
---

# First Local Loop

This is the smallest safe loop for trying the current DSPx base layer from a clean repo state.

It demonstrates the current shipped path:

```text
signature surface -> module surface -> module-surface contracts -> program-shaped candidate assembly -> optional example/dataset evidence -> execution episode -> receipt bundle -> authority export plan sidecar -> optional external-authority export preflight packet -> optional candidate truth-state summary
```

The default starter intent still exercises the single-module path. `program-gen` also supports explicit user-declared `pipeline` topology for the narrow `Predict` / `ChainOfThought` subset with `signature.name` / `signature.inputs` / `signature.outputs` and simple `when.field` / `when.equals` routing. In both paths it emits `module_surfaces.json` (`program-module-surfaces-v1`) so generated module surfaces are replayable, hashable, and IO-declared. Structured intent may also declare local dataset split evidence via `dataset` (JSONL/JSON/YAML source plus ratio seed) or `datasets` (explicit train/validation/test files), which adds `dataset_manifest.json`, split JSONL files, split eval harnesses, and split behavior results. Dataset support does not change topology rendering: DSPx does not infer topology, run arbitrary expressions, or import/execute custom Python modules.

The loop is intentionally offline and non-authoritative:

- uses `DSPX_PROVIDER=stub`
- sets `MLFLOW_ENABLE=0`
- writes to a temp directory by default
- does not call `ak`
- does not mutate Agent Kernel or any other external authority
- `program-gen` does not promote, rank, select winners, prune, run GEPA/search, run jury execution, or grant Oracle/governance authority; explicit local deterministic jury execution is a separate `program-promote jury` sidecar command over an existing manifest

## One command

From the repo root:

```bash
just install          # once, if the uv environment is not already synced
just smoke-base
```

The target prints the generated directory and key artifacts at the end. By default the directory is a fresh temp path such as `/tmp/dspx-smoke-base.xxxxxx`, so the repo working tree stays clean.

To write to a chosen local directory instead:

```bash
just smoke-base generated/playground/smoke-base
```

Use a generated directory only when you explicitly want the artifacts under the repo; those artifacts are playground output, not source truth.

## What the command does

`just smoke-base` runs `scripts/smoke_base_loop.sh`, which:

1. Generates a deterministic signature:

   ```bash
   uv run --package dspx-core -q python -m dspx.cli.dspx signature gen \
     "Classify support tickets" \
     --template-version simple-v1 \
     --class-name TicketSig \
     --outfile "$OUT_DIR/ticket_sig.py"
   ```

2. Generates a deterministic module with an embedded signature:

   ```bash
   uv run --package dspx-core -q python -m dspx.cli.dspx module-gen \
     --name TicketClassifier \
     --description "Classify support ticket urgency" \
     --input ticket_text \
     --output urgency \
     --template-version simple-v1 \
     --use-signature \
     --outfile "$OUT_DIR/ticket_module.py"
   ```

3. Copies `examples/program_gen/ticket_intent.yaml` into the output directory. The example intent contains one inline example and an opaque optional external-authority ref.

4. Materializes a program-shaped candidate assembly:

   ```bash
   uv run --package dspx-core -q python -m dspx.cli.dspx program-gen \
     --intent "$OUT_DIR/intent.yaml" \
     --outdir "$OUT_DIR/program"
   ```

5. Runs the generated deterministic harnesses from the generated program directory:

   ```bash
   cd "$OUT_DIR/program"
   uv run --project "$REPO_ROOT" --package dspx-core -q python eval_smoke.py
   uv run --project "$REPO_ROOT" --package dspx-core -q python eval_jury.py
   uv run --project "$REPO_ROOT" --package dspx-core -q python eval_promotion.py
   uv run --project "$REPO_ROOT" --package dspx-core -q python eval_examples.py
   ```

6. Produces a sidecar Agent Kernel export plan from the generated evidence:

   ```bash
   uv run --package dspx-core -q python -m dspx.cli.dspx adapters authority agent-kernel-plan \
     --manifest "$OUT_DIR/program/manifest.json" \
     --external-ref AK-EXAMPLE \
     --out "$OUT_DIR/program/ak-export-plan.json"
   ```

The adapter step emits `ak-export-plan.json` plus `ak-export-plan.json.meta.json`. The plan status is `planned_not_exported`; it is a local sidecar plan and receipt, not an AK write and not a promotion decision.

## Key artifacts to inspect

After a successful run, start with:

- `intent.yaml` — copied starter intent from `examples/program_gen/ticket_intent.yaml`
- `ticket_sig.py` — generated signature surface
- `ticket_module.py` — generated module surface
- `program/plan.json` — deterministic program plan
- `program/jury.json`, `program/jury_selection.json`, `program/jury_rubric.json` — planned non-authoritative jury artifacts
- `program/promotion_review.json` — local pending promotion-review shell
- `program/promotion_adjudication_request.json` — pending decision packet
- `program/promotion_decision_template.json` — unfilled decision template
- `program/module_surfaces.json` — standalone `program-module-surfaces-v1` contract containing one `program-module-surface-v1` per generated module surface; this prepares for future local custom module refs without executing them now
- `program/execution_episode.json` — standalone `program-execution-episode-v1` contract separating materialization, binding checks, source-indexed evaluation evidence, aggregate behavior evidence summary, Oracle readability, and non-authority flags
- `program/behavior_results.json` — example-backed behavior evidence when examples exist; the execution episode records whether it came from inline examples or `examples_path`, plus result path/hash, count, provider, and metric facts already known
- optional `program/dataset_manifest.json`, `program/splits/*.jsonl`, `program/eval_{train,validation,test}.py`, and `program/behavior_results.{train,validation,test}.json` — split-specific local behavior evidence when the intent declares a dataset, with each split listed as its own execution-episode evaluation source
- `program/oracle_evidence.json` — source-aware Oracle-readable evidence when local behavior results exist from inline examples, `examples_path`, and/or dataset splits; Oracle is not invoked
- `program/manifest.json` — candidate assembly / execution episode / receipt-bundle metadata
- `program/manifest.json.meta.json` — `program-gen` receipt
- `program/ak-export-plan.json` — sidecar authority export plan, `planned_not_exported`
- `program/ak-export-plan.json.meta.json` — receipt for the sidecar plan

## Guided walkthrough

For a command-by-command inspection of the generated assembly, including `execution_episode.json`, `behavior_results.json`, `oracle_evidence.json`, clean replay, replay drift detection, and the optional sidecar authority export plan, see `docs/project/program-gen-walkthrough.md`.

## Adjacent refinement-loop smoke

After the base smoke, the next explicit local refinement smoke is:

```bash
just smoke-program-refinement
```

That target runs `scripts/smoke_program_refinement_loop.sh` in a temp directory by default. It exercises the local evidence/refinement path through explicit temp-dir Oracle indexing/reporting, `program-refine propose`, `program-promote review`, `program-promote decide --outcome request_more_evidence`, and `program-refine generate-and-compare`.

From those explicit sidecars, an operator can separately build a local external-authority preflight packet:

```bash
uv run -q python -m dspx.cli.dspx adapters authority agent-kernel-export-preflight \
  --manifest "$OUT_DIR/program/manifest.json" \
  --external-ref AK-EXAMPLE \
  --decision-record "$OUT_DIR/promotion/promotion_decision_record.json" \
  --comparison "$OUT_DIR/refinement/candidate_comparison.json" \
  --out "$OUT_DIR/export/ak-export-preflight.json" \
  --json
```

The packet has `schema_version: program-external-authority-export-preflight-v1`; it records hashes, manifest identity, deterministic idempotency/export ID, an `ak_task_evidence_attachment` planned payload, local preflight blockers in `blocking_reasons`, and future apply limitations in `external_apply_blocking_reasons`.

To put the candidate's local truth into one inspectable artifact, use `program-promote status` with the manifest and whichever sidecars exist:

```bash
uv run -q python -m dspx.cli.dspx program-promote status \
  --manifest "$OUT_DIR/program-v2/manifest.json" \
  --source-manifest "$OUT_DIR/program/manifest.json" \
  --oracle-report "$OUT_DIR/oracle/program-evidence-report.json" \
  --refinement-proposal "$OUT_DIR/refinement/refinement_proposal.json" \
  --review "$OUT_DIR/promotion/promotion_review_refined.json" \
  --decision-record "$OUT_DIR/promotion/promotion_decision_record.json" \
  --jury-results "$OUT_DIR/promotion/jury_results.json" \
  --comparison "$OUT_DIR/refinement/candidate_comparison.json" \
  --export-preflight "$OUT_DIR/export/ak-export-preflight.json" \
  --out "$OUT_DIR/state/program_candidate_state.json" \
  --json
```

The state artifact has `schema_version: program-candidate-state-v1`; it summarizes materialization, behavior evidence, Oracle readability/reporting, review/decision/jury-results/comparison/plan/preflight posture, artifact hashes, no-mutation effects, and future apply requirements. It is still offline and non-authoritative: it does not call AK, does not mutate repo Oracle indexes, does not rank or select winners, does not promote, does not run GEPA/search, does not apply/export authority, does not mutate governance, and does not introduce `eval_behavior.py`. The execution episode's richer source summaries and source-aware Oracle evidence remain evidence only; they do not make Oracle, AK, governance, or external authority authoritative. Missing optional sidecars are reported as missing rather than invented; explicit identity/authority mismatches fail closed. The GEPA seam is a separate explicit command, `program-refine optimize-gepa`, over an existing manifest; it writes a local `program-refinement-gepa-result-v1` sidecar and can degrade truthfully without materializing a candidate assembly.

## Boundary reminder

This loop proves local materialization and evidence plumbing only.

DSPx core emits portable local evidence and opaque external authority refs. The authority adapter consumes those evidence artifacts to produce a planned sidecar export plan or a stronger local export-preflight packet, and `program-promote status` can summarize all local truth into one state artifact. These surfaces must not call Agent Kernel, mutate task state, invoke an adjudicator, apply/export authority, or turn evidence into authority. Actual external apply remains future work requiring exact AK target-contract binding, external duplicate checks, an apply receipt, and rollback/failure semantics.

Oracle may later interpret receipt evidence, but Oracle does not rank, prune, promote, block, or own governance authority in this loop. If you explicitly run `program-promote jury` after this loop, it writes only a local `jury_results.json` sidecar from planned jury artifacts plus current `eval_examples.py` / `behavior_results.json`; it does not mutate the candidate, call external models, create Oracle indexes, rank, select winners, promote, approve, export authority, mutate AK/governance, or introduce `eval_behavior.py`.
