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

## Authority and artifact boundary

A passing result is local benchmark evidence only. The harness does not approve or activate a program, select or promote a candidate, index Oracle, call AK, mutate governance, or mutate any external authority. It writes only the explicitly requested result file (atomically); deleting that file rolls back its local artifact effect. Any later evidence registration, adjudication, or activation must occur through its owning authorized surface.
