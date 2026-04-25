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

---

## Native signature workflow (core)

### 1) Generate signature

Deterministic template path (no LM):

```bash
just dspx signature gen "Extract names from text" \
  --template-version simple-v1 \
  --class-name Sig_Names \
  --outfile generated/sig_names.py
```

Native LM-backed path (spec-first):

```bash
just dspx signature gen "Extract names from text" \
  --template-version v1 \
  --provider pi-rpc \
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

Generate a deterministic program-shaped candidate assembly from one structured intent:

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
# Optional: inline examples or examples_path: examples.yaml
```

```bash
just dspx program-gen \
  --intent intent.yaml \
  --outdir generated/programs/answer_question
```

The generated candidate assembly contains a structured plan, separate surfaces, and replayable metadata:

- `plan.json` — deterministic `program-plan-v1` contract derived from the intent; records normalized field specs, task type, default single-module topology, materialized surfaces, metric/runtime/constraints, examples metadata, non-authority defaults, and an explicit planned `program-jury-v1` multi-model evaluation shape when provided
- `jury.json` — standalone planned jury contract copied out of the plan so future jury execution can bind to an exact per-program juror/perspective pool artifact; when no explicit pool is supplied, DSPx infers one from intent features such as task type, metric, examples, fields, and constraints
- `jury_selection.json` — deterministic non-authoritative juror selection artifact; prefers diverse perspectives from the per-program pool, records selected jurors, and still calls no models
- `jury_rubric.json` — deterministic non-authoritative per-juror rubric artifact; binds selected perspectives to criteria and adversarial questions for a later jury execution episode
- `promotion_review.json` — deterministic non-authoritative local promotion-review shell; records the explicit pending adjudicator (`human_operator`, `ai_agent`, `ai_council`, `hybrid`, or `policy_gate`), optional opaque `external_authority` refs for a separately invoked adapter/export tool, pending behavioral evaluation, model-jury execution, and adjudicator-decision requirements while keeping the candidate unpromoted
- `promotion_adjudication_request.json` — deterministic non-authoritative decision packet for the configured adjudicator, including evidence refs, missing evidence, allowed outcomes, optional opaque external authority refs, and a pending decision-record template
- `promotion_decision_template.json` — standalone pending `program-promotion-decision-v1` template that an explicit adjudicator may later fill; it is not a decision
- `signature.py` — signature surface generated through the signature service
- `module.py` — module surface generated through the module service
- `program.py` — program assembly wrapper exporting `build_program()` / `build_student()`
- `eval_smoke.py` — deterministic smoke harness
- `eval_jury.py` — deterministic jury artifact binding harness that validates `jury.json`, `jury_selection.json`, and `jury_rubric.json` without calling models
- `eval_promotion.py` — deterministic promotion artifact binding harness that validates `promotion_review.json`, `promotion_adjudication_request.json`, and `promotion_decision_template.json` without invoking an adjudicator
- `examples.json` / `eval_examples.py` — emitted when the intent includes inline `examples` or `examples_path`, validating example binding without calling an LM
- `intent.json` — normalized structured intent
- `manifest.json` — candidate assembly / execution episode / receipt-bundle metadata, including plan/jury/selection/rubric/promotion-review/adjudication-request/decision-template hash provenance
- `manifest.json.meta.json` — standard `program-gen` run receipt, including the same plan/jury/selection/rubric/promotion-review/adjudication-request/decision-template evidence

This path is intentionally deterministic and scaffold-first. The `jury` entry is a future evaluation contract shape only: no juror models are called during materialization. External authority refs are opaque metadata only: DSPx core does not validate, call, or mutate Agent Kernel or any other external system during materialization. It materializes evidence; it does not promote, rank, prune, export authority, or grant Oracle/governance authority.

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

`--with-mlflow` local scan resolves sqlite custom artifact roots via MLflow experiment metadata when available.

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
- `MLFLOW_ENABLE=1` + no `MLFLOW_TRACKING_URI` -> local sqlite backend (`sqlite:///mlflow.db`)
- runs are started explicitly by DSPx commands/services (no implicit run start during bootstrap)
- DSPy autolog traces are disabled by default to avoid noisy GEPA span warnings

Enable MLflow for local tracing:

```bash
export MLFLOW_ENABLE=1
# optional: omit this for local sqlite default
export MLFLOW_TRACKING_URI=http://127.0.0.1:5000
```

MLflow behavior and constraints:
- `docs/MLFLOW_OBSERVABILITY_PLAN.md`

---

## Oracle Time Travel (Phase C slice)

Receipt v2 metadata now supports a first local CLI slice for behavioral history:

```bash
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
- `codex/gpt-5.4` is verified through `dspy-lm-auth`
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
