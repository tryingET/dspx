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

## Pre-live installed corpus and Oracle evaluation contract

Before another installed-wheel provider call, validate the checked-in no-live membrane:

```bash
just installed-live-oracle-evaluation-contract-check
```

The machine-readable contract is `benchmarks/semantic/installed-live-oracle-evaluation-v1.json`. It hash-binds the complete three-case v2 corpus in declared order and freezes:

- one single-module authority-boundary stratum;
- one bounded `Predict` → `ChainOfThought` evidence-calibration stratum;
- one mixed-output review-only runtime-contract stratum;
- score-`1.0` per-case and aggregate thresholds with zero failed/error cases;
- one corpus-process attempt, no separate health probe, no DSPx-managed retry, and no selective quality rerun;
- route identity requirements, privacy/retention posture, failure classes, and explicit falsifiers;
- separate evaluation protocols for the semantic-analysis LM, embedding model, and coordinate store.

This is **declared-strata coverage**, not a statistical or product-representative corpus. It contains only three cases with one example each. Its lexical concept criteria are provider-visible and therefore measure bounded instruction/contract adherence rather than independent general semantic correctness. One benchmark process may execute multiple topology/module/provider operations; the contract never reinterprets that process count as provider transport-call cardinality, and provider-internal retry behavior remains `not_proven`.

The first embedding candidate was explicit `sentence-transformers/all-MiniLM-L6-v2`, evaluated in candidate-local SQLite against three held-out labeled queries using Recall@1, MRR, and nDCG@3. Because each query has one relevant record and all thresholds require the correct record uniquely at rank 1, these metrics describe one three-query top-1 routing gate rather than independent broad semantic-quality measures.

AK-4480 freezes the exact model commit `c9745ed1d9f207416be6d2e6f8de32d1f16199bf`, ten loader-relevant Git/LFS artifact identities, tokenizer runtime, a frozen isolated CPython 3.13 CPU dependency environment, 384-dimensional normalized float32 encoding, cosine ranking, and one-minus-cosine distance in `benchmarks/semantic/oracle-embedding-evaluation-v1.json`. The runner uses one canonical consumed marker keyed by contract hash, accepts no caller-selected ledger namespace, downloads the exact allowlisted snapshot once, writes exactly three local SQLite records, embeds all three records and queries as complete ordered batches, and forbids selective query reruns. Generated external scripts and `.dist-info` installation metadata are projections rather than imported runtime code; selected wheel archive hashes remain frozen while stable runtime hashing covers package and native-library payload inside site-packages.

The retained managed-local attempt `dspx-oracle-embedding-ak4480-20260801T225149Z-2181147` passed every label uniquely at rank 1, producing Recall@1, MRR, and nDCG@3 of `1.0`. Result `92a9d058…0466c` and SQLite `7f70994d…182f` remain unchanged. The first external offline reproduction failed because legacy content hashing included generated console-script and `RECORD` paths; that failure is preserved as `9a75a0b4…634a`. Two separate model-free isolated runtime diagnostics produced identical stable payload map digest `3b9b4e0c…0086`, and one corrected full six-text reproduction matched every original vector hash in recovered verification `f0a23691…49a7`, which independent review accepted with qualifications.

AK-4510 reassessed that model against the July 2026 LightOn collection. `lightonai/mDenseOn` is the preferred dense challenger: it preserves one-vector cosine retrieval while adding asymmetric query/document roles, 768-dimensional CLS pooling, multilingual training, and an 8,192-token window. `lightonai/mLateOn` is excluded from this substitution because its per-token vectors and MaxSim scoring require a separate late-interaction storage and retrieval architecture. Author-reported MTEB/BEIR/MIRACL/MLDR scores justify evaluation, not an Oracle quality claim; see [oracle-embedding-model-assessment.md](oracle-embedding-model-assessment.md).

`benchmarks/semantic/oracle-embedding-selection-v2.json` freezes 15 model-blind queries over 10 Oracle concepts, including six cross-lingual queries and one post-256-token tail label, plus exact model artifacts, tokenizer roles, runtime bytes, CPU resource bounds, candidate-local SQLite, task-fixed one-shot enforcement, and explicit nonclaims. The sole AK-4510 sequence retained exact mDenseOn commit `a5fdb000…6df3` but terminated before the first challenger vector: the tokenizer emitted `token_type_ids`, which the frozen `ModernBertModel.forward()` signature rejects. The failure root `dspx-oracle-embedding-selection-ak4510-20260802T061504Z-737025` and consumed ledger remain unchanged. It is preserved as an adapter failure, not a semantic score.

AK-4517 then performed one separately authorized offline full-batch recovery under `benchmarks/semantic/oracle-embedding-selection-recovery-v1.json`. It reused the exact retained snapshot with zero artifact acquisitions, removed only `token_type_ids`, preserved all other model inputs, and encoded every frozen document and query under its explicit role. mDenseOn achieved Recall@1, MRR, and nDCG@5 of `1.0`; MiniLM achieved `0.8`, `0.842857…`, and `0.833333…`. Cross-lingual Recall@1 improved by `0.333333…`, and the long-context case improved by `1.0`. Model load took `2.1398` seconds, total encoding `4.3162` seconds, and observed peak RSS was `1,907,945,472` bytes. Independent verification accepted the retained vectors, both SQLite rankings, metrics, resource observations, zero-acquisition recovery, and preserved AK-4510 lineage. Result SHA-256 is `b20249ef…03e20`; verification SHA-256 is `3bd5db06…06548`.

mDenseOn is therefore the version-2 dense default for new coordinates. Indexed records use its document role; text searches use its query role. Explicit `sentence-transformers` remains available for the legacy MiniLM path, and version-1 rows are not silently rewritten: cross-version in-place upserts fail closed and require a new/rebuilt version-2 index. Search binds embedding version and backend-space identity where an engine identity is available.

This establishes only the frozen production-semantic **embedding routing gate**. It does not establish broad or statistically representative semantic correctness. The semantic-analysis LM remains a separate layer: fixture replay is its deterministic offline path, and any live evaluation requires the role-bound `dspy-lm-auth` route plus distinct preferred, configured, and observed model evidence. Shared Postgres/pgvector is a third durability/publication layer and cannot satisfy either semantic-quality gate.

AK-4506 froze that separate semantic-analysis evaluation in `benchmarks/semantic/oracle-semantic-analysis-evaluation-v1.json`. Four candidate-local cases receive the same provider-visible field codebook; hidden expected/forbidden code partitions and exact evidence-reference labels remain outside the prompt. Scoring accepts only the exact hidden code set for every field, exact expected evidence references, no forbidden references, and bounded confidence. Unknown prose, synonyms, missing/extra/duplicate codes, contrary allowed codes, source drift, test doubles, rebound adapter methods, widened authority, and artifact tampering fail closed. The runner requires one committed source snapshot, private artifacts, the exact production adapter, one canonical ledger, no health probe/DSPx retry/selective rerun, and stop after the first failed or indeterminate case.

The sole authorized AK-4506 process ran from commit `204017bf…7ac1`. Its first `authority-boundary` call observed model identity `openai/gpt-5.6-sol` but returned text that failed JSON parsing. Execution stopped immediately with one DSPx analyze invocation; later cases were not attempted. Result `12a8577a…13e9` is `failed`, verification `328496e3…779` is `rejected`, and independent review accepted only the internal consistency and preservation of that terminal failure. Executed provider identity, provider transport cardinality, and provider-internal retry absence remain unproved. The four-case semantic-analysis gate is false, and the consumed ledger authorizes no retry.

AK-4568 separately authorized the successor contract in `benchmarks/semantic/oracle-semantic-analysis-evaluation-v2.json`. Its dependency was absent from the local environment, so the first case stopped before provider transport with zero live calls. Result `214f3353…f1efb8` is failed and independent verification rejected it while confirming that the distinct ledger and prior AK-4506 history remained preserved.

AK-4569 bound a v3 contract and added an exact `tryinget-dspy-lm-auth==0.1.5` import/version preflight before root or ledger creation. The preflight passed and the first live response was valid typed JSON from `openai/gpt-5.6-sol`, but the model selected related and precautionary codes in addition to directly evidenced codes. Exactness was `0.2`, so result `6edbd569…79fbc2` failed and the process stopped after one call.

AK-4570 addresses that observed failure without exposing any case label: the shared semantic prompt now requires the minimum field-specific code set directly and unambiguously entailed by receipt-bound evidence, empty arrays when none are entailed, and exclusion of merely possible, generic, precautionary, alternative, opposite, or downstream codes. The v4 contract retains the same hidden labels, thresholds, order, and no-retry boundary under a new ledger.

A passing installed-live contract check still proves only that the exact hash-bound no-live protocol is internally consistent with the checked-in corpus and source-declared backend identities. The standard-library validator performs no provider/model/store operation. The separate explicit embedding runner has a model/network effect and is never a default CI gate; its local evidence grants no representative-quality, semantic-LM, shared-store, release, publication, governance-authority, or activation claim.

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

The runner makes exactly one corpus-process invocation, runs no separate health probe or mechanical retry, disables DSPx's historical Codex stream-compatibility retry, and disallows selective quality reruns. Retry behavior internal to the released provider dependency and provider transport-call cardinality remain `not_proven` rather than being inferred from one process. Before any live effect, the runner validates and snapshots the exact checked-in three-case corpus plus precommitted evaluation contract. It stops conservatively after the first caught case error so an effect-indeterminate provider/setup failure cannot be followed by a later case call; a valid semantic miss remains terminal evidence rather than a retry trigger.

The runner creates a clean Python 3.13 environment outside the checkout and downloads the exact tryingET GitHub release wheel for `dspy-lm-auth==0.1.4` as an independent payload-verification artifact. It verifies that wheel's SHA-256, then installs the exact hash-bound local Core wheel with its `lm-auth` extra. The extra carries the same tryingET release-wheel URL and immutable SHA-256 binding in Core's built metadata, so the resolver installs one non-conflicting auth dependency and does not depend on the DSPx workspace's `tool.uv.sources` configuration or on the abandoned upstream's PyPI publication. Independent verification compares the installed auth payload against the predownloaded release wheel and requires the installed distribution's direct URL to name that exact tryingET release. It unsets `PYTHONPATH`, requires the precommitted `codex/gpt-5.6-sol` route, passes the checkout's v2 aggregate schema by absolute path, and runs all three cases in declared order through the installed Core program-semantic path. Generated provider-facing topology signatures project each intent's declared objective, constraints, and output-specific bounded quality criteria; these are program-intent semantics, not hidden benchmark answers or authority. The runner then performs current receipt-integrity replay for every case, indexes all three evidence records into one candidate-local mock-embedding Oracle database, regenerates and compares the local Oracle report, and independently re-derives semantic concept coverage from each current observed behavior artifact.

The direct release reference makes current GitHub-distributed Core wheels self-contained, but standard package indexes such as PyPI do not accept distributions whose metadata depends on a direct URL. A future PyPI publication therefore requires a separately published maintained dependency identity on that index and a reviewed replacement of this direct reference; the current GitHub release binding must not be presented as PyPI-compatible.

The fixed evidence packet is `<root>/installed-core-live-semantic-proof.json`. It binds exact Core and released auth wheel identities plus installed `RECORD` payload verification, the frozen corpus/evaluation contract, requested provider/model, three unique candidate and receipt identities, independently derived per-case and aggregate scores, current behavior/manifest/receipt/workflow/Oracle/replay hashes, the invocation disposition, and all three candidate-local Oracle records. The provider's final resolved model identity remains `not_proven`; requested/configured model metadata is not silently upgraded into executed-model proof.

The retained AK-4471 attempt at commit `322902bf` used the then-current upstream PyPI `dspy-lm-auth==0.1.3` wheel and passed the three declared strata in order at `1.0` per case and aggregate, with zero forbidden hits, current receipt-integrity replay for all three cases, and three candidate-local mock-Oracle rows. That dependency identity is historical evidence and is not rewritten by the current tryingET `0.1.4` adoption. Its proof SHA-256 is `63c86e0f…02ac`; the exact Core wheel SHA-256 is `cd70538e…ed6a8`. Independent review accepted this as declared-strata installed-wheel live behavior evidence only. The original Core wheel archive remains in a separate managed scratch path rather than inside the retained journey root, so later review reverified the installed `RECORD`, direct-URL binding, and exact commit-source match but could not rehash that archive from the evidence root alone.

Effects and privacy boundaries:

- network reads and provider-owned auth refresh may occur;
- the runner never inspects or copies tokens, headers, auth-store contents, or credential paths;
- unbounded provider responses and raw failure details are not retained, while the one bounded checked-in benchmark behavior output remains inspectable in the local candidate artifacts;
- failure preserves the owner-only journey root plus a step/exit receipt; that receipt distinguishes possible bounded sanitized benchmark detail from unretained raw error detail and reports only a PATH-canary observation for AK;
- mock Oracle embeddings prove indexing/report plumbing only and never production-semantic quality;
- the runner requests no shared Oracle, AK, governance, promotion, activation, registry, or publication mutation; the proof confirms workflow declarations plus no PATH-canary observation but does not claim broad AK-invocation absence.

A pass proves only that the exact installed Core wheel used the configured real-provider route to produce behavior satisfying all three frozen declared-strata lexical contracts in order, that current receipt/artifact integrity replay passed for each, and that candidate-local Oracle could index/report the resulting evidence. It does not prove statistical or product representativeness, broad semantic correctness, runtime execution reproduction, semantic reproduction, quality-evaluation reproduction, network isolation, auth-store nonmutation, exact executed/resolved-model identity, provider transport-call cardinality, provider-internal retry absence, broad AK-invocation absence, production-semantic Oracle quality, release authority, package publication, or sdist support.

This live journey is never a default CI or release-evidence gate. Do not modify `ci-package` or the stub-backed installed proof to consume its nondeterministic credentialed output.

## Authority and artifact boundary

A passing result is local benchmark evidence only. Neither harness approves or activates a program, selects or promotes a candidate, indexes shared Oracle, calls AK, mutates governance, or mutates external authority. The direct-provider harness writes only its atomically replaced result file. The generated-program harness writes a fresh work root containing intents, caches, candidate assemblies, receipts, behavior evidence, and workflow sidecars, plus its atomically replaced aggregate result; remove both the work root and aggregate result to roll back those local artifacts. Any later evidence registration, adjudication, or activation must occur through its owning authorized surface.
