---
summary: "DSPx product overview, local-first quick start, primary behavior loop, boundaries, and documentation map."
read_when:
  - "You are onboarding to DSPx."
  - "You need the main user-facing overview or current CLI entry points."
type: "guide"
---

# DSPx — local-first behavioral runtime for DSPy

DSPx helps users turn structured intent into runnable DSPy candidate assemblies, execute and evaluate them locally, retain replayable evidence, and inspect observed behavior through Oracle.

The shortest useful mental model is:

```text
intent
→ candidate assembly
→ execution and evaluation
→ receipts and replay
→ Oracle interpretation
→ bounded refinement or review
```

`packages/dspx-core` is the product kernel. Forge is an optional app that consumes Core; Core never depends on Forge.

## Current product posture

DSPx already ships local signature/module generation, provider-aware execution, one-intent program assembly, receipts/replay, candidate-local Oracle evidence, and bounded refinement/review surfaces.

The active frontier is **Core production readiness**, not further autonomous-foundry expansion. The installed Core wheel has a bounded stub-backed product-journey proof and exact-wheel release evidence, but signer policy, signature verification, CI evidence custody, live-provider quality, publication, and release approval remain separate gates. Production-code `just typecheck` is green; `just typecheck-tests` and therefore `just verify-full` remain red under deferred AK baseline work, so focused/package proof is not a green release gate.

Read [the active product posture](docs/project/product-posture.md) before selecting implementation work. AK direction/task/decision runtime remains authoritative for current execution state.

## Quick start

Requirements:

- Python 3.13+
- [`uv`](https://docs.astral.sh/uv/)
- [`just`](https://just.systems/)

Install the workspace and inspect the command surfaces:

```bash
just install
just help
just dspx --help
just forge --help  # optional app
```

Use the deterministic local posture while learning or iterating:

```bash
export DSPX_PROVIDER=stub
export MLFLOW_ENABLE=0
```

Run the first local product loop:

```bash
just smoke-base
```

`smoke-base` uses a temporary directory by default and exercises signature generation, module generation, `program-gen`, generated evaluation, replay evidence, and a non-mutating authority-plan seam. It does not call AK or mutate external authority. Materialization and behavior are reported separately; failed behavior exits non-zero even if candidate creation succeeded.

See [First local loop](docs/project/first-local-loop.md) for the exact steps and nonclaims.

## One intent to local evidence

A minimal structured intent can be YAML or JSON:

```yaml
# /tmp/answer-question.yaml
name: AnswerQuestion
objective: Answer a question using only the supplied context.
inputs:
  - context
  - question
outputs:
  - answer
metric: exact_match
constraints:
  - Cite only supplied context.
examples:
  - inputs:
      context: Paris is the capital of France.
      question: What is the capital of France?
    outputs:
      answer: Paris
```

Materialize a candidate assembly without Oracle indexing:

```bash
rm -rf /tmp/dspx-answer-question
# Deterministic plumbing fixture for this example; not model-quality evidence.
DSPX_STUB_RESPONSE_JSON='{"answer":"Paris"}' \
  just dspx program-loop \
    --intent /tmp/answer-question.yaml \
    --outdir /tmp/dspx-answer-question \
    --skip-oracle-index \
    --json
```

DSPx refuses a non-empty candidate output directory rather than silently overwriting existing evidence.

For candidate-local Oracle indexing/reporting, explicitly select a semantic backend first. Mock embeddings are suitable only for deterministic plumbing proof:

```bash
export DSPX_ORACLE_EMBEDDING_BACKEND=mock
rm -rf /tmp/dspx-answer-question
DSPX_STUB_RESPONSE_JSON='{"answer":"Paris"}' \
  just dspx program-loop \
    --intent /tmp/answer-question.yaml \
    --outdir /tmp/dspx-answer-question \
    --json
```

The loop composes:

1. structured intent validation and normalization;
2. candidate surface materialization;
3. bounded generated behavior evaluation when examples or datasets exist;
4. receipt integrity checking;
5. optional candidate-local Oracle indexing and reporting;
6. a local candidate-state summary.

It does not rank candidates, promote, activate, publish, call AK, or mutate governance.

For a complete artifact walkthrough, use [Program generation walkthrough](docs/project/program-gen-walkthrough.md). To convert a natural-language program request into a valid intent, use the repo-owned Pi skill documented in [Pi DSPx intent assistant](docs/project/pi-dspx-intent-assistant.md); Core itself consumes structured intent and does not claim ownership of natural-language interpretation.

## Candidate assemblies and evidence

`program-gen` materializes a candidate assembly rather than a loose code snippet. Depending on the intent, it can include:

- normalized intent and assumptions;
- explicit signature, module, and program surfaces;
- declared and materialized topology;
- generated smoke, example, dataset, and behavior harnesses;
- execution episodes and local behavior evidence;
- capability, generated-module-policy, jury, and review contracts;
- manifest identity and a standard run receipt;
- Oracle-readable evidence.

The candidate inventory is versioned in its manifest and receipt. `program-loop` can subsequently add a candidate-local Oracle report, candidate-state summary, and workflow sidecar; those downstream artifacts are recorded by the workflow result rather than retroactively added to the original manifest. Consumers revalidate current bytes and identity instead of trusting producer summaries.

Important boundaries:

- Unsupported valid capabilities remain declared-only; they do not gain execution authority.
- External tools, retrievers, custom imports, network access, and filesystem effects require explicit bounded adapters and policy.
- Jury, review, comparison, planning, activation-packet, and export-preflight sidecars are local evidence. They do not approve or activate a candidate.
- Oracle interprets empirical behavior. It is not promotion, release, or governance authority.

See [Generated-program evidence boundaries](docs/project/generated-program-evidence-surface-boundaries.md) and [Program synthesis boundary](docs/project/program-synthesis-boundary.md).

## Direct generation and inspection

Generate without the integrated loop:

```bash
rm -rf /tmp/dspx-candidate
DSPX_STUB_RESPONSE_JSON='{"urgency":"high"}' \
  just dspx program-gen \
    --intent examples/program_gen/ticket_intent.yaml \
    --outdir /tmp/dspx-candidate \
    --print-manifest
```

Check its receipt without executing a new run:

```bash
just dspx run replay \
  --from /tmp/dspx-candidate/manifest.json.meta.json \
  --check-only \
  --json
```

Inspect Oracle backend selection without creating an index or loading a model:

```bash
just dspx oracle backend-status
```

Summarize an existing candidate’s current local truth state:

```bash
just dspx program-promote status \
  --manifest /tmp/dspx-candidate/manifest.json \
  --out /tmp/dspx-candidate-state.json \
  --json
```

Use `just dspx <command> --help` for the current contract. Do not copy old sidecar inventories or flags from historical logs.

## Signature and module surfaces

Signature and module generation remain useful standalone surfaces and reusable candidate-assembly providers.

Deterministic signature generation:

```bash
just dspx signature gen "Extract names from text" \
  --template-version simple-v1 \
  --class-name ExtractNames \
  --input text \
  --output names \
  --outfile generated/extract_names.py
```

Deterministic module generation:

```bash
just dspx module-gen \
  --name Summarizer \
  --description "Summarize a passage" \
  --input text \
  --output summary \
  --template-version simple-v1 \
  --outfile generated/summarizer.py
```

See [Native signature pipeline](docs/SIGNATURE_NATIVE_PIPELINE.md) and [GEPA from module generation](docs/GEPA_FROM_MODULE_GEN.md) for specialized workflows.

## Providers and credentials

DSPx supports deterministic and provider-backed paths. Provider availability, authentication, model support, and runtime outcomes are distinct facts; failed transport/auth/process results must not become success-shaped outputs.

Start with:

```bash
just dspx providers --help
just dspx providers list
just dspx oracle backend-status
```

Prefer file, stdin, hidden prompt, environment, or secret-manager references over credentials in shell history. Never commit credentials, local auth databases, provider output containing secrets, or machine-local evidence stores.

The CLI defaults to read-only HTTP/tool behavior. Mutating network methods require explicit invocation-scoped allowance and still remain subject to policy. `--bypass-permissions` is unsafe and should not appear in ordinary workflows or evidence claims.

See [Provider runtime V4](docs/project/provider-runtime-v4.md) and [Security policy](SECURITY.md).

## Receipts, replay, and Oracle

Receipts and manifests bind the inputs, outputs, configuration, and artifacts needed for supported checks or replay modes. A passing receipt check proves only its declared claim matrix; it does not imply semantic reproduction, quality approval, release readiness, or authority.

Oracle can search, compare, and map observed behavioral evidence:

```bash
just dspx oracle search "routing failures"
just dspx oracle territory
just dspx oracle frontiers
just dspx oracle attractors --health
just dspx oracle contract verify
```

Mock embeddings are deterministic plumbing evidence only. A production-semantic claim requires an explicit model-backed configuration and separate empirical acceptance evidence.

See [Run, replay, and explain](docs/RUN_REPLAY_EXPLAIN.md) and [Semantic benchmarks](docs/project/semantic-benchmarks.md).

## Local artifacts and cleanup

Generated/server roots are local, non-authoritative storage and are never cleaned implicitly.

Preview aged artifacts first:

```bash
just artifact-cleanup
```

Apply only with the unchanged plan ID and exact root confirmation:

```bash
just artifact-cleanup generated/server 7 \
  --apply \
  --plan-id <reviewed-plan-id> \
  --confirm-root generated/server
```

The cleanup path rejects dangerous roots and changed candidates, and does not follow symlinks.

## Development workflow

Install hooks once per clone:

```bash
just hooks-install
```

Standard local commands:

```bash
just help
just check
just test
just lint
just typecheck
just doctor
just run       # DSPx CLI help when called without arguments
```

Focused change verification:

```bash
just task-scope-check task_id=<AK-ID> mode=working-tree
just verify-impact-plan
just verify-impact
just hooks-run files="path/one.py path/two.py"
just verify-pre-push
```

Full or release-adjacent verification:

```bash
just verify-full
just ci-quality
just ci-test-shards
just ci-package
```

`just ci-package` proves a bounded Core-only installed-wheel journey and validates exact-wheel release evidence before separately smoking Forge. Its local provenance is unauthenticated, signatures are unverified, and publication/readiness/authority remain false.

The canonical command and validation contract is [Developer workflow](docs/project/developer_workflow.md). Successful validation is evidence; it does not close AK tasks or authorize release/activation. Read-only verification commands use `uv run --no-sync` where applicable so validation does not rewrite the lockfile.

## Monorepo boundaries

Allowed dependency direction:

```text
apps/* → packages/dspx-core
```

Forbidden:

```text
packages/dspx-core → apps/*
```

Core must never import `dspx_forge.*`. Check the boundary with:

```bash
just monorepo-check
```

## Repository map

- Core runtime: `packages/dspx-core/src/dspx/`
- Core CLI: `packages/dspx-core/src/dspx/cli/dspx.py`
- Forge app: `apps/forge/src/dspx_forge/`
- Tests: `tests/`
- CI and developer scripts: `scripts/`
- Documentation: `docs/`
- Local session notes: `diary/`

## Canonical documentation

- [Vision](docs/project/vision.md)
- [Current product posture](docs/project/product-posture.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Developer workflow](docs/project/developer_workflow.md)
- [First local loop](docs/project/first-local-loop.md)
- [Program generation walkthrough](docs/project/program-gen-walkthrough.md)
- [Program synthesis boundary](docs/project/program-synthesis-boundary.md)
- [Generated-program evidence boundaries](docs/project/generated-program-evidence-surface-boundaries.md)
- [Native signature pipeline](docs/SIGNATURE_NATIVE_PIPELINE.md)
- [Run, replay, and explain](docs/RUN_REPLAY_EXPLAIN.md)
- [Forge](docs/FORGE.md)
- [Contributing](CONTRIBUTING.md)
- [Security](SECURITY.md)
