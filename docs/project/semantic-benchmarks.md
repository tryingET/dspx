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

The default `benchmarks/semantic/program-corpus-v2.json` includes one single-module assembly, one bounded `Predict` → `ChainOfThought` pipeline, and one mixed-output PDF-transition review case. Each checked-in case declares intent-native `concept_coverage` quality criteria matching its outer aggregate scoring contract in output field, evaluator, required concept groups, forbidden terms, and threshold. Each case is materialized through `program-loop`; generated behavior episodes validate and preserve record, child-result, source, and episode-aggregate quality evidence with explicit `criteria_declared` and `quality_approved=false`. Empty sources retain whether criteria were declared without fabricating an evaluation; legacy child summaries without the declaration flag are normalized from their bound intent. The benchmark consumer re-derives quality from the current manifest intent and observed outputs, requires those hash-bound levels to agree, and then computes the aggregate semantic score. It does not call a provider directly from the benchmark scorer.

In deterministic offline mode, the review case additionally executes the candidate through `program-run --contract-mode pdf_transition_review`, captures a private mode-0600 replay fixture, executes receipt-bound replay, and requires `executed_valid_review_only`, declared quality `passed`, and `execution_reproduced` without approval authority. Its aggregate row hash-binds the runtime episode, runtime receipt, replay fixture, and replay evidence. Live mode remains provider-backed and does not capture the stub-only replay fixture; its runtime-replay field is null with explicit `not_run_live_unsupported` status rather than claiming unsupported reproduction. Ordinary cases use `not_required`; successful offline review replay uses `passed`; failures use `failed`.

The aggregate `dspx-program-semantic-benchmark-result-v2` packet records corpus identity, candidate/receipt identities, current manifest/workflow/behavior hashes, and optional runtime-replay evidence. Raw generated responses and replay-fixture contents are represented only by SHA-256 in the aggregate. Candidate and runtime directories remain available for local inspection. Benchmark runtime inputs are created exclusively with mode `0600`; replay rechecks that the candidate tree remains unchanged and binds the runtime episode, runtime receipt, and replay evidence to the candidate manifest hash. Corpus/result v1 remain accepted for external compatibility; legacy v1 cases without intent quality criteria retain outer aggregate scoring without gaining a candidate-quality claim.

The lane fails closed on stale or substituted evidence, failed/degraded generated behavior, review-boundary or declared-quality failure, runtime/replay semantic drift, path overlap, symlink corpus input, pre-existing work/runtime roots, invalid mode/provider combinations, and widened authority/effect flags. A valid semantic miss or case runtime failure produces benchmark evidence with exit `1`; invalid invocation or contract/runtime setup failure exits `2`. Candidate directories may remain after failure and are evidence for inspection, not a success claim. Delete the fresh work root and aggregate result to roll back local artifacts.

Offline mode uses the stub provider through the generated DSPy program runtime. Live mode uses only the explicitly selected provider, remains non-deterministic, and is never a default CI gate.

## Exact installed-wheel live semantic journey

The source-checkout live benchmark and the credential-free installed-wheel package proof intentionally remain separate. To test their composition without weakening either contract, use the explicit opt-in journey with a newly built exact Core wheel, its SHA-256, one currently available Codex subscription model, and a fresh managed scratch root outside the checkout:

```bash
just installed-core-live-semantic \
  wheel=/absolute/path/dspx_core-0.1.0-py3-none-any.whl \
  wheel_sha256=<64-lowercase-hex> \
  provider=dspy-lm-auth \
  model=codex/gpt-5.6-sol \
  root="$TMPDIR/dspx-installed-live-$(date -u +%Y%m%dT%H%M%SZ)"
```

The recipe arguments are positional despite their `name=value` spelling; keep the documented order `wheel`, `wheel_sha256`, `provider`, `model`, `root`. The provider is explicit rather than defaulted so a reordered invocation fails at the wrapper boundary instead of silently remapping live-run inputs.

The runner makes exactly one benchmark invocation, runs no separate health probe or mechanical retry, and disables DSPx's historical Codex stream-compatibility retry for this journey. Retry behavior internal to the released provider dependency remains `not_proven` rather than being inferred from one invocation. The runner creates a clean Python 3.13 environment outside the checkout, downloads the exact PyPI wheel recorded by `uv.lock` for `dspy-lm-auth==0.1.3`, verifies its SHA-256, and installs both that artifact and the exact hash-bound Core wheel by local hash-bound URL. It unsets `PYTHONPATH`, snapshots the exact checked-in `single-module-authority-boundary` case, and runs that case through the installed Core program-semantic path. It then performs current receipt-integrity replay, indexes the resulting evidence into a candidate-local mock-embedding Oracle database, regenerates and compares the local Oracle report, and independently re-derives semantic concept coverage from current observed behavior.

The fixed evidence packet is `<root>/installed-core-live-semantic-proof.json`. It binds exact Core and released auth wheel identities plus installed `RECORD` payload verification, requested provider/model, candidate and receipt identities, independently derived semantic score, current behavior/manifest/receipt/workflow/Oracle/replay hashes, the invocation disposition, and the candidate-local Oracle record. The provider's final resolved model identity remains `not_proven`; requested model metadata is not silently upgraded into executed-model proof.

Effects and privacy boundaries:

- network reads and provider-owned auth refresh may occur;
- the runner never inspects or copies tokens, headers, auth-store contents, or credential paths;
- unbounded provider responses and raw failure details are not retained, while the one bounded checked-in benchmark behavior output remains inspectable in the local candidate artifacts;
- failure preserves the owner-only journey root plus a step/exit receipt; that receipt distinguishes possible bounded sanitized benchmark detail from unretained raw error detail and reports only a PATH-canary observation for AK;
- mock Oracle embeddings prove indexing/report plumbing only and never production-semantic quality;
- the runner requests no shared Oracle, AK, governance, promotion, activation, registry, or publication mutation; the proof confirms workflow declarations plus no PATH-canary observation but does not claim broad AK-invocation absence.

A pass proves only that the exact installed Core wheel used the named real-provider route to produce behavior satisfying this bounded semantic case, that current receipt/artifact integrity replay passed, and that candidate-local Oracle could interpret the resulting evidence. It does not prove runtime execution reproduction, semantic reproduction, quality-evaluation reproduction, network isolation, auth-store nonmutation, exact resolved-model identity, provider-internal retry absence, broad AK-invocation absence, production-semantic Oracle quality, release authority, package publication, or sdist support.

This live journey is never a default CI or release-evidence gate. Do not modify `ci-package` or the stub-backed installed proof to consume its nondeterministic credentialed output.

## Authority and artifact boundary

A passing result is local benchmark evidence only. Neither harness approves or activates a program, selects or promotes a candidate, indexes shared Oracle, calls AK, mutates governance, or mutates external authority. The direct-provider harness writes only its atomically replaced result file. The generated-program harness writes a fresh work root containing intents, caches, candidate assemblies, receipts, behavior evidence, and workflow sidecars, plus its atomically replaced aggregate result; remove both the work root and aggregate result to roll back those local artifacts. Any later evidence registration, adjudication, or activation must occur through its owning authorized surface.
