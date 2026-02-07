---
summary: "Run GEPA optimization starting from `dspx module-gen` output (with offline smoke + live-gated variants)."
read_when:
  - "You want a copy/pasteable GEPA loop starting from a generated module file."
  - "You want an offline (stub) GEPA smoke run and a live (codex) variant."
---

# GEPA from `module-gen`

Goal: generate a tiny student module via `dspx module-gen`, then run `dspx optimize gepa` using the hooks that the template emits:
`build_student()`, `io_spec()`, `output_weights()`, `normalize_output(...)`.

## Offline smoke (stub provider)

Uses a tiny training CSV at `examples/gepa_modulegen_train.csv`.

Run:

- `just gepa-modulegen-smoke`

What it does:
- Writes a generated `Student` program to a temp dir
- Runs GEPA with `DSPX_PROVIDER=stub`, `MLFLOW_ENABLE=0`, `--max-metric-calls 2`, `--metric contains`
- Asserts `manifest.json` exists in the optimized output dir

## Live smoke (Codex Exec; opt-in)

Run:

- `DSPX_RUN_LIVE_TESTS=1 just gepa-modulegen-live`

Notes:
- Requires `codex` installed + authenticated (`codex login status`).
- Uses the same CSV and a small `--max-metric-calls` budget.
