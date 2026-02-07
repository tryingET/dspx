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

## GEPA optimization

Optimize a program exporting `build_student()` against train/val data:

```bash
just dspx optimize gepa \
  --program examples/gepa_demo_program.py \
  --train examples/gepa_demo_train.csv \
  --out generated/gepa_demo_optimized \
  --student-provider pi-rpc \
  --metric exact \
  --max-metric-calls 2
```

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
- sidecar metadata (`*.meta.json`)
- on-disk cache (`generated/cache/...`)

Inspect cache:

```bash
just dspx cache info
just dspx cache list
```

Explainability sink (optional):
- MLflow traces/metrics/artifacts when enabled.
- execution must still work with `MLFLOW_ENABLE=0`.

Enable MLflow only when you want tracing:

```bash
export MLFLOW_ENABLE=1
export MLFLOW_TRACKING_URI=http://127.0.0.1:5000
```

MLflow behavior and constraints:
- `docs/MLFLOW_OBSERVABILITY_PLAN.md`

---

## Providers

Default posture:
- default provider fallback: `pi-rpc`
- offline testing provider: `stub`

Smoke providers:

```bash
just dspx providers smoke --json
```

List providers:

```bash
just dspx providers list
```

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

Validation loop used on this branch:

```bash
pre-commit run --all-files
just monorepo-check
just test
```

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
- roadmap: `NEXT_STEPS.md`
- monorepo boundaries: `docs/MONOREPO_TRANSITION.md`
- GEPA quick path: `docs/GEPA_FROM_MODULE_GEN.md`
- observability/MLflow: `docs/MLFLOW_OBSERVABILITY_PLAN.md`
- forge app: `docs/FORGE.md`

---

## License

AGPL-3.0 — see `LICENSE`.
