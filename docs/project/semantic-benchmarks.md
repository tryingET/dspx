---
summary: "Reproducible offline semantic corpus and explicit opt-in live-provider benchmark contract."
read_when:
  - "You are running or changing DSPx semantic benchmarks."
  - "You need the semantic benchmark result or authority boundary."
---

# Semantic benchmarks

DSPx ships a small, versioned semantic regression corpus at `benchmarks/semantic/corpus-v1.json`. It covers paraphrase preservation, bounded entailment, evidence calibration, instruction following, concept distinction, and the evidence/authority boundary.

## Deterministic default

```bash
just semantic-benchmark
# explicit output override
just semantic-benchmark out=/tmp/semantic-result.json
```

The default uses checked-in responses only. It makes no provider or network call, uses no randomness or wall-clock fields, and produces byte-stable semantic scores and hashes. The command exits `0` only when declared corpus thresholds pass, `1` when valid results miss thresholds, and `2` for invalid configuration/runtime failure.

## Optional live provider

Live execution is deliberately separate and requires both the live switch and a named registry provider:

```bash
just semantic-benchmark-live provider=dspy-lm-auth out=/tmp/semantic-live.json
# equivalent:
uv run --no-sync python scripts/run_semantic_benchmarks.py \
  --live --provider dspy-lm-auth --out /tmp/semantic-live.json
```

Supplying a provider without `--live`, or `--live` without a provider, fails before corpus execution. Provider/model availability, authentication, latency, and output variability make live results non-deterministic. Live runs are never part of the offline default gate.

## Result contract and thresholds

Both modes write `dspx-semantic-benchmark-result-v1` JSON. Its JSON Schema is checked in at `benchmarks/semantic/result-schema-v1.json`. It includes:

- exact corpus schema/name/version and canonical SHA-256;
- execution mode, explicit provider, network posture, and determinism posture;
- copied corpus thresholds and aggregate pass/fail summary;
- per-case category, semantic score, missing concept-group indexes, forbidden hits, response SHA-256, status, and sanitized error;
- explicit evidence-only/non-authority flags.

Raw provider responses are not persisted in the result. Corpus v1 requires overall score `>= 0.90`, every case score `>= 0.75`, and zero failed/error cases. Scoring is deterministic lexical concept-group coverage with fail-closed forbidden claims; it is intentionally inspectable rather than an embedding/model judge.

## Generated-program semantic corpus

The direct-provider corpus above checks provider/scorer semantics. A separate lane proves the product path through actual generated candidate assemblies:

```bash
# The work root must not already exist; use a fresh root for every run.
just program-semantic-benchmark \
  root=/tmp/dspx-program-semantic \
  out=/tmp/dspx-program-semantic-result.json

# Live execution is separate and explicit.
just program-semantic-benchmark-live dspy-lm-auth \
  root=/tmp/dspx-program-semantic-live \
  out=/tmp/dspx-program-semantic-live-result.json
```

The default `benchmarks/semantic/program-corpus-v2.json` includes one single-module assembly, one bounded `Predict` → `ChainOfThought` pipeline, and one mixed-output PDF-transition review case. Each checked-in case declares intent-native `concept_coverage` quality criteria matching its outer aggregate scoring contract in output field, evaluator, required concept groups, forbidden terms, and threshold. Each case is materialized through `program-loop`; the consumer re-derives quality from the current manifest intent and observed outputs, requires canonical hash-bound behavior quality evidence, and then computes the aggregate semantic score. It does not call a provider directly from the benchmark scorer.

In deterministic offline mode, the review case additionally executes the candidate through `program-run --contract-mode pdf_transition_review`, captures a private mode-0600 replay fixture, executes receipt-bound replay, and requires `executed_valid_review_only`, declared quality `passed`, and `execution_reproduced` without approval authority. Its aggregate row hash-binds the runtime episode, runtime receipt, replay fixture, and replay evidence. Live mode remains provider-backed and does not capture the stub-only replay fixture; its runtime-replay field is null with explicit `not_run_live_unsupported` status rather than claiming unsupported reproduction. Ordinary cases use `not_required`; successful offline review replay uses `passed`; failures use `failed`.

The aggregate `dspx-program-semantic-benchmark-result-v2` packet records corpus identity, candidate/receipt identities, current manifest/workflow/behavior hashes, and optional runtime-replay evidence. Raw generated responses and replay-fixture contents are represented only by SHA-256 in the aggregate. Candidate and runtime directories remain available for local inspection. Benchmark runtime inputs are created exclusively with mode `0600`; replay rechecks that the candidate tree remains unchanged and binds the runtime episode, runtime receipt, and replay evidence to the candidate manifest hash. Corpus/result v1 remain accepted for external compatibility; legacy v1 cases without intent quality criteria retain outer aggregate scoring without gaining a candidate-quality claim.

The lane fails closed on stale or substituted evidence, failed/degraded generated behavior, review-boundary or declared-quality failure, runtime/replay semantic drift, path overlap, symlink corpus input, pre-existing work/runtime roots, invalid mode/provider combinations, and widened authority/effect flags. A valid semantic miss or case runtime failure produces benchmark evidence with exit `1`; invalid invocation or contract/runtime setup failure exits `2`. Candidate directories may remain after failure and are evidence for inspection, not a success claim. Delete the fresh work root and aggregate result to roll back local artifacts.

Offline mode uses the stub provider through the generated DSPy program runtime. Live mode uses only the explicitly selected provider, remains non-deterministic, and is never a default CI gate.

## Authority and artifact boundary

A passing result is local benchmark evidence only. Neither harness approves or activates a program, selects or promotes a candidate, indexes shared Oracle, calls AK, mutates governance, or mutates external authority. The direct-provider harness writes only its atomically replaced result file. The generated-program harness writes a fresh work root containing intents, caches, candidate assemblies, receipts, behavior evidence, and workflow sidecars, plus its atomically replaced aggregate result; remove both the work root and aggregate result to roll back those local artifacts. Any later evidence registration, adjudication, or activation must occur through its owning authorized surface.
