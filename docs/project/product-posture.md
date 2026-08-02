---
summary: "Current DSPx product maturity, active Core-readiness frontier, owner gates, and proof required to advance it."
read_when:
  - "When choosing the next DSPx product slice."
  - "Before implementation, to identify the current shipped-vs-target gap."
  - "Before loop completion, to refresh the product frontier against observed evidence."
type: "reference"
---

# Product Posture

## Purpose and use

This file is the status-bearing bridge between the durable [vision](vision.md) and current execution.

Use it as an **active work artifact**:

1. read it before selecting a slice;
2. test its apparent frontier against AK, code, tests, and current artifacts during discovery;
3. update it before completion when the shipped baseline, gaps, proof, or lawful next move changed.

This file is a dated projection, not live authority, a task list, or a changelog. Active direction, tasks, decisions, and evidence live in Agent Kernel (AK). Shipped behavior lives in code and its current executable proof. Historical posture snapshots remain available in Git history; do not append implementation diaries here.

## Current snapshot — 2026-08-02

### Posture in one sentence

DSPx has a substantial local-first, behavior-first Core plus verified non-authoritative signing/custody, owner authentication, one qualified recovered single-case proof, one independently accepted installed-wheel live attempt over three declared strata, one qualified recovered MiniLM embedding gate, and one independently accepted 15-query mDenseOn comparison; mDenseOn is the version-2 dense default, while the sole AK-4506 semantic-analysis-LM evaluation terminated on malformed provider JSON and independently preserved a false semantic gate, so any new semantic attempt requires separate authority and shared-store durability remains a distinct later gate.

### Active frontier: Core production readiness

Current AK direction prioritizes making Core DSPx installable, operationally safe, and empirically proven before expanding autonomous foundry behavior.

The latest bounded implementation and proof establish:

- a Core-only wheel installation outside the source checkout with `PYTHONPATH` unset;
- a stub-provider journey through candidate materialization, passing local behavior, receipt checking, candidate-local Oracle indexing/reporting, and candidate-state generation;
- exact installed-wheel payload verification against wheel `RECORD` plus rejection of undeclared importable package files;
- a hash-bound release-evidence v3 envelope over the wheel, sdist, installed proof, exact-wheel CycloneDX SBOM, and point-in-time resolved-environment CycloneDX SBOM;
- exact-wheel metadata reconciliation for resolved-environment evidence: generation requires the installed Core root name, version, and complete canonical requirement inventory to match the wheel, rejects duplicate Core requirement identities instead of normalizing them away, and accepts ambient marker identity only when the caller omits that input entirely; retained validation re-derives active direct root edges and version constraints under the recorded marker environment;
- fail-closed rejection of ambiguous wheel identity headers, duplicate canonical environment components, rewired root edges, and direct-URL dependencies whose artifact provenance is not represented by the environment SBOM;
- an optional mode-0600, no-replace local release bundle retaining those subjects, SBOMs, proof, envelope, manifest, and an unauthenticated local provenance statement;
- machine-readable replay claims that distinguish receipt integrity, deterministic regeneration, runtime reproduction, semantic reproduction, and quality-evaluation reproduction;
- explicit Oracle embedding-backend identity, with mock vectors labeled plumbing-only and unavailable production backends failing closed;
- bounded, paged local Oracle reads that tolerate malformed legacy rows without turning them into trusted evidence.
- successful 14-day and 90-day signed evidence/custody canaries with current paired-availability verification;
- immutable single-owner FIDO policy v003 currentness plus one mechanically displayed, explicitly confirmed YubiKey Bio signature with OpenSSH and strict UP+UV verification;
- one durable authority-false shadow receipt, replay rejection, and independent post-run acceptance with `release_authority=false`, `package_publication=false`, and `sdist_supported=false`.
- one exact Core wheel (`b4d10c1…51e8`) installed outside the checkout with `PYTHONPATH` unset alongside the hash-bound released `dspy-lm-auth==0.1.3` wheel, then used for one benchmark invocation requesting `codex/gpt-5.6-sol` through the named provider route; its bounded authority case scored `1.0`, matched all four required concept groups, and hit no forbidden concepts;
- current receipt-integrity replay plus one candidate-local mock-Oracle record/report, exact installed payload verification, and a final proof (`08ed5ef…dd04e`) accepted by independent review as **qualified recovered verification**: the original runner status remains failed at `independent_evidence_verification`, while corrected deterministic postprocessing passed without a second benchmark/provider invocation.
- a role-bound Oracle semantic LM path: the default no longer depends on the unavailable `gpt-5.6-luna` declaration, and `dspy-lm-auth` construction consumes the same frozen `codex/gpt-5.6-sol` role snapshot used for preferred/configured evidence; the later three-strata attempt used that configured route while executed-model identity remained unproved;
- a versioned no-live evaluation contract that hash-binds all three current program-semantic cases in declared order, freezes one corpus-process attempt with no DSPx retry or selective rerun, separates semantic-analysis LM, embedding-model, and coordinate-store gates, and retains every production/release/publication/activation claim as false.
- one fresh installed-wheel attempt at commit `322902bf` using exact Core wheel `cd70538e…ed6a8` and the configured `dspy-lm-auth/codex/gpt-5.6-sol` route: all three frozen declared strata ran in order, scored `1.0` individually and in aggregate, produced no forbidden hits, passed current receipt-integrity replay, and yielded three uniquely bound candidate-local mock-Oracle records; the final proof (`63c86e0f…02ac`) and terminal runner pass were independently accepted without rerun.
- one exact `sentence-transformers/all-MiniLM-L6-v2` CPU evaluation at commit `c9745ed1…99bf`, with ten commit-bound loader artifacts, exact tokenizer/runtime/normalization/dimension/distance identity, a frozen isolated `uv.lock` runtime, and three candidate-local SQLite rows: all three held-out labels ranked uniquely first, so Recall@1, MRR, and nDCG@3 were each `1.0`; result `92a9d058…0466c` and database `7f70994d…182f` remain unchanged.
- qualified recovered independent embedding verification `f0a23691…49a7`: the first offline external reproduction failed on installation-projection hashes and is preserved as failure `9a75a0b4…634a`; root-cause analysis isolated generated console scripts and `RECORD` paths, two separate model-free isolated runtimes produced the same stable imported-payload digest `3b9b4e0c…0086`, and one corrected complete six-text reproduction matched every original vector hash without model reacquisition or selective query rerun.
- an evidence-ranked comparison of MiniLM, `lightonai/mDenseOn`, and `lightonai/mLateOn`: mDenseOn is the preferred single-vector challenger because it preserves dense cosine storage while adding explicit query/document roles, multilingual training, 8,192-token context, and stronger author-reported retrieval results; mLateOn remains a separate multi-vector/MaxSim architecture rather than a drop-in default.
- one terminal AK-4510 sequence at source commit `7f096db3`: exact mDenseOn commit `a5fdb000…6df3` and all eight artifacts were retained, the baseline ran into local SQLite, and the first mDenseOn document forward call failed before emitting a vector because `token_type_ids` was passed to a `ModernBertModel.forward()` signature that does not accept it. The task-fixed ledger remains consumed and the failure remains immutable history.
- one separately ledgered AK-4517 offline recovery at source commit `647b484b`: the exact retained mDenseOn snapshot was reused with zero acquisition, only `token_type_ids` was removed, and every frozen document/query ran as a complete role-bound batch. mDenseOn scored `1.0` Recall@1/MRR/nDCG@5 over all 15 labels versus MiniLM Recall@1 `0.8`; cross-lingual and long-context Recall@1 improved by `0.333333…` and `1.0`. All identity, absolute-quality, comparative, and CPU-resource gates passed, and independent verification accepted result `b20249ef…03e20` / verification `3bd5db06…06548`.
- version-2 Oracle coordinates now use mDenseOn by default with document-role indexing and query-role text search. Explicit `sentence-transformers` remains the legacy MiniLM path; cross-version in-place upserts fail closed so existing version-1 rows are not silently rewritten.
- one committed-source AK-4506 semantic-analysis membrane at commit `204017bf`: four candidate-local cases share one provider-visible controlled codebook while hidden exact code assignments and evidence-reference labels stay outside the prompt. The sole authorized live process stopped after the first `authority-boundary` response because the observed `openai/gpt-5.6-sol` response was not valid JSON. The terminal result (`12a8577a…13e9`) is `failed`, independent verification (`328496e3…779`) is `rejected`, DSPx recorded zero retries/health probes/selective reruns, and the four-case semantic gate remains false.

These observations are implemented and exercised by the package and focused test lanes. They are not release approval.

### Validation gate status

The repo-declared local confidence gates are green:

- `just typecheck` passes across Core and Forge after semantic-corpus keys and validated GEPA improvement requests gained explicit string narrowing.
- `just typecheck-tests` passes after release-evidence fixtures gained callable/deeply mutable boundaries and dynamic module imports gained explicit tuple cardinality.
- `just verify-full` passes after the AK-4517 default-adoption slice. The credential-free offline suite passed 2860 tests with 4 expected skips; the residual live/network/model/GPU/Postgres lane reported 5 expected skips. `just verify-pre-push` also passes.
- `just installed-live-oracle-evaluation-contract-check` validates the exact hash-bound three-case corpus/contract, route/attempt budget, held-out Oracle labels/metrics, layer separation, and declared zero-operation/nonclaim posture. The validator is standard-library-only, parses source declarations without importing DSPx, rejects any contract-byte or foreign-corpus drift, and is tested with an empty fresh HOME/cache; this remains a contract check rather than general syscall isolation proof.
- The Oracle route-binding slice passed 93 focused and adjacent model-role, semantic-backend, runtime, foundry, config, and provider tests plus package and test typechecking.
- The final pre-live runner/verifier gate passed 62 focused semantic-benchmark, installed-contract, adversarial claim-binding, and fail-fast tests; independent adversarial review returned PASS before the sole corpus attempt.
- The embedding contract, identity, SQLite metric, tie/falsifier, tamper, one-shot ledger, frozen-runtime, dtype/device, reproduction, and recovery lanes passed 136 focused and adjacent tests plus Core/test typechecking before the full gate. Independent pre-acquisition review returned ACCEPT; final retained evidence-package review returned ACCEPT with qualifications after the preserved external verification failure was reconciled.
- The mDenseOn reassessment's frozen contract, exact tokenizer/runtime identity, source/import-origin checks, task-fixed ledger, SQLite re-ranking, tamper, metric, resource, and claim-boundary lanes passed 32 focused tests and 160 focused/adjacent tests with 3 expected skips before acquisition; independent pre-acquisition review returned ACCEPT. AK-4510 then preserved the first adapter failure. AK-4517's separate full-batch offline recovery passed every original gate, and independent retained-package verification returned `accepted` without reacquisition or selective rerun.
- The version-2 adoption's backend selection, role routing, source binding, cache identity, SQLite preservation/rollback, semantic-space isolation, report/status compatibility, and fail-closed Postgres dimension/transaction wiring passed 181 focused tests plus Core/test typechecking. Independent final code review returned ACCEPT, and adversarial deterministic wiring review returned PASS. No real Postgres connection was made, so shared-store runtime readiness remains unproved.
- AK-4506's controlled-code contract, hidden-label isolation, exact-code/evidence scoring, committed-source provenance, private artifacts, one-shot ledger, adapter-method integrity, tamper rejection, and stop-on-first-failure lanes passed focused tests plus Core/test typechecking before the sole live process. Pre-live independent review accepted the membrane. Post-run deterministic verification rejected the failed result as required, and independent artifact review accepted the failure packet as internally consistent—not as a semantic-quality pass.

This establishes the cited repo-local full-gate baseline. Separate bounded evidence establishes signer verification, public CI evidence custody, authority-false owner authentication, the qualified recovered one-case result, one end-to-end installed runner pass over three declared strata, one qualified recovered three-query MiniLM gate, and one accepted 15-query mDenseOn comparison. Neither three one-example lexical contracts nor the bounded embedding labels establish statistical representativeness, broad live-provider/semantic quality, executed provider-model identity, package publication, release approval, or activation.

For the lossless-normalization fixup, `just loop-impact-run` passed the repo-selected expanded plan: 14 focused environment-SBOM tests, 91 impact-planner tests, 69 release-bundle tests, workflow and Ruff checks, and a fresh Core/Forge package and retained-bundle journey. The proof covers duplicate Core requirements, bounded iterable consumption, and explicit empty, incomplete, widened, or invalid marker environments. This is current working-tree proof, not commit-bound or release-authoritative evidence.

### Accepted signing/custody decisions and observed authority-false activation

Decision 88 and `docs/adr/20260731-core-release-signing-custody.md` accept the owner policy for exact keyless Core wheel-evidence signing, a separate fail-closed 2-of-3 owner threshold, and bounded public non-secret GitHub Actions evidence custody. Decision 91 permits the non-authoritative evidence plane to activate without fabricating three owner principals; it does not weaken or satisfy the release threshold. These decisions are architecture truth, not implementation evidence or package release authority.

1. **Signer implementation** — Decision 92 and Decision 93 now select immutable trust policy v2 after live Fulcio extension `.1.24` exposed a numeric-ID-bound token-subject change. V1 remains immutable history. The exact wheel-only statements, generic Fulcio OID `.1.8`–`.1.24` matching, pinned-root offline Cosign verification, live-AK selector resolution, deny policy, anti-rollback checkpointing, and separate 2-of-3 approval evaluation remain active. Live 14/90-day canaries verified workload signatures, but the unbound roster keeps release authority false and package publication unavailable.
2. **CI evidence custody activation** — runs `30659977281` (14-day) and `30660312181` (90-day) completed successfully with signed evidence, signed custody receipts, and fresh exact paired-availability checks. Downloaded artifacts passed the public non-secret preflight and retained false package-release/publication claims. The environment reviewer is the same solo operator and is only a deliberate-action gate, not independent review. `DSPX_CORE_RELEASE_SIGNING_ENABLED=true` remains enabled after both canaries; see `docs/project/2026-07-31-core-evidence-live-dogfood.md` for receipts, failed-path evidence, and current expiry.
3. **Owner-authentication shadow** — Decision 96 accepts the explicit concentrated single-owner FIDO architecture; Decision 99 activates immutable owner policy v003 only for authority-false shadow proof. AK-4420 completed one exact mechanical display, explicit hash confirmation, YubiKey Bio UP+UV signature, durable `shadow_verified_not_authorized` receipt, replay rejection, negative matrix, and independent closeout review. No package or registry effect occurred.
4. **Exact-sdist install proof** — AK-4137 remains contingent on a later owner declaring sdist support/signer-subject inclusion or on an observed sdist defect. Decision 88 keeps the sdist in the explicit non-subject auxiliary role `unsigned_unsupported_distribution_evidence`, so it does not trigger AK-4137.

Inspect the completed implementation records with `ak task show 4125`, `ak task show 4126`, and `ak task show 4420`; inspect the continuing event gate with `ak task show 4137` and `ak task deferred`. AK-4383 was reconciled as already satisfied after anonymous public `origin/main` ancestry proved all Decision 88 offline commits reachable; no duplicate Git effect was performed. Live signature, bounded custody, and hardware owner authentication are observed. They remain evidence only and do not prove release authorization, package publication, permanent custody, or sdist support.

### Explicit nonclaims

Current evidence does **not** prove:

- broad live-provider correctness, statistically representative program quality, or broad production-semantic Oracle quality; provider evidence covers exactly three one-example, provider-visible lexical contract strata, while the current embedding comparison covers exactly 15 frozen labels over 10 declared Oracle concepts;
- embedding comparison quality beyond that frozen 15-query corpus; independent semantic-analysis-LM quality and shared-coordinate-store readiness also remain unproved;
- OS-level network isolation or exclusion of absolute-path/external API effects;
- hash-locked dependency resolution, retained dependency artifacts, reproducible builds, or future resolver stability;
- artifact-source provenance for direct-URL dependencies, which the resolved-environment SBOM now rejects rather than representing incompletely;
- vulnerability, license, VEX, or supply-chain policy acceptance;
- release-authoritative provenance, an independently controlled owner quorum, registry authority, or publication approval;
- exact-sdist PEP 517 build/install behavior or source-to-wheel equivalence;
- registry publication, technical release completeness, release readiness, promotion, activation, or external authority.

## Current product baseline

| Runtime area | Shipped baseline | Main bounded gap |
|---|---|---|
| One-intent candidate assembly | `program-gen` normalizes structured intent and materializes separate signatures, modules, topology, harnesses, manifests, execution evidence, and receipts. Bounded pipeline/router/retriever/review topologies are supported; unsupported valid capabilities remain declared-only. | No arbitrary graph/effect engine, custom-import execution, live external tool/retriever binding, or provider-backed arbitrary topology inference. |
| Execution and replay | Generated examples/datasets can run through bounded behavior harnesses and explicit runtime episodes. Replay claims are machine-readable and receipt-bound. | No general semantic-reproduction claim, broad provider/runtime coverage, or receipt-bound multi-episode product contract. |
| Oracle behavioral evidence | Candidate-local evidence can be indexed and reported with explicit backend identity; Oracle exposes search, drift, territory, frontier, attractor, and program-evidence concepts. Exact MiniLM identity and three rank-1 labels remain historical evidence. The preserved AK-4510 adapter failure was forward-recovered under AK-4517: mDenseOn passed all 15 frozen labels and is the version-2 dense default with explicit document/query roles, while version-1 rows remain unmodified. AK-4506 separately preserved one malformed-response semantic-LM failure. | The semantic-analysis-LM gate is false; no retry is authorized by the failed attempt. Shared Postgres/pgvector durability remains a separate gate. Broad semantic quality and mLateOn readiness remain unproved. Oracle remains interpretation, not authority. |
| Refinement and review | Local proposals, GEPA attempts, second candidates, comparisons, jury/model-jury evidence, adjudication records, plans, status, and activation-preflight packets exist as inspectable sidecars and guided workflows. | Further autonomous orchestration is paused. External apply, activation, and owner acceptance remain unavailable without their own authority contracts. |
| Packaging and release evidence | Core-only installed-wheel behavior, exact-wheel identity, two SBOM scopes, signed public CI evidence/custody, immutable owner-policy currentness, one hardware-authenticated authority-false shadow consume, one qualified recovered live-provider proof, and one fresh end-to-end installed-wheel pass over three frozen declared strata are observed. | The three-strata corpus is declared lexical-contract coverage rather than statistically representative or production-semantic evidence. Package publication, release authority, independently controlled quorum, and sdist support remain unavailable or unproved. |
| Operator experience | `program-loop` provides a coherent local intent-to-candidate/evidence/state path; `just smoke-base` dogfoods an offline no-AK loop; the installed live journey composes exact wheel origin, three ordered real-provider cases, replay, and local reporting, while embedding and semantic experiments enforce task-fixed ledgers, frozen source/runtime identity, preserved terminal failures, and explicit layer boundaries. | The AK-4506 semantic attempt is consumed and false. Diagnose or propose a separately authorized successor; do not rerun, reuse embedding evidence, or convert Oracle interpretation into authority. |

### Root cause and sequencing consequence

The former product-proof gap was compositional rather than absence of components. Dogfood exposed the missing seams instead of hiding them: the wrapper argument order did not match its documented positional order; aggregate-schema lookup depended on scratch cwd; generated provider-facing signatures retained intent quality criteria only as evaluator metadata; replay freshness compared equivalent relative and absolute path spellings; and auth-wheel verification reused a Core-only package-root inventory assumption. AK-4450 preserved the first semantic failure. AK-4458 projected declared objective/constraints/output quality into provider-visible signatures, fixed the path and package assumptions, then produced one score-`1.0` live behavior result and a recovered deterministic proof without weakening the corpus, scorer, or authority boundary.

First-principles review exposed a second compositional ambiguity: “Oracle backend” had been collapsing three independent layers. The semantic-analysis LM, embedding model, and coordinate store have different identities, failure modes, and evidence claims; successful Postgres/pgvector durability cannot prove semantic quality, and a live LM analysis cannot prove embedding retrieval quality. It also exposed a route-binding defect: the Oracle semantic layer reported a preferred role model while constructing generic `dspy-lm-auth` from unrelated LM-auth defaults. AK-4466 resolved the role once, passes that frozen model/reasoning snapshot into provider construction, and preserves preferred, configured, and observed identities separately. The unavailable Luna default no longer drives execution.

The no-live contract converts the next experiment from an ambiguous “representative” run into declared-strata coverage: three cases, one example each, provider-visible lexical criteria, and no statistical sampling frame. It precommits thresholds, falsifiers, case order, privacy, one corpus-process attempt, and no selective rerun without pretending that one process bounds provider transport calls.

AK-4471 adapted the installed runner/verifier, closed pre-live fail-fast and claim-binding defects found by adversarial review, then performed exactly the one precommitted corpus-process attempt. The terminal proof binds all three passing episodes, replays, and mock-Oracle rows and was independently accepted. At that point, production-semantic work moved to strengthening embedding identity beyond model name/dimension and evaluating `sentence-transformers/all-MiniLM-L6-v2` against held-out labels in local SQLite; semantic-analysis LM quality and shared-store durability remained later separate gates. Deterministic release evidence, credentials, shared Oracle publication, and activation stayed outside that slice.

AK-4480 then separated model artifact identity from installation projections, froze the CPU dependency/wheel/runtime surface, and consumed one canonical acquisition/evaluation ledger. Its three held-out queries all routed uniquely to the expected local SQLite record. The initial external reproduction failure was not erased: the corrected verifier excludes generated console scripts and `RECORD` from imported-payload hashes while retaining exact wheel archive hashes and observed package payloads, and the recovered full-batch proof is explicitly qualified. This advances only the embedding layer; semantic-analysis-LM quality and shared-store durability remain later separate gates. Deterministic release evidence, credentials, shared Oracle publication, and activation stayed outside the slice.

AK-4510 challenged that old-model choice rather than treating the successful membrane as a permanent default. External architecture and benchmark evidence favored mDenseOn over MiniLM for the existing single-vector store; mLateOn was rejected as a different late-interaction architecture. The attempt then exposed a local adapter defect before semantic output: the generic fast tokenizer emitted `token_type_ids`, while the frozen ModernBERT forward signature rejects that field. The failure, exact retained model, baseline SQLite, and consumed ledger remain evidence.

AK-4517 forward-recovered that defect without rewriting it. A separately consumed recovery ledger reused the exact retained snapshot offline, removed only `token_type_ids`, and reran the complete frozen batch. mDenseOn uniquely ranked all 15 expected records first, passed every precommitted identity/comparative/resource gate, and was independently accepted. The runtime now defaults new coordinates to embedding version 2 with document/query role separation; old version-1 rows are protected from cross-version replacement. This advances only dense retrieval. Semantic-analysis-LM quality and shared-store durability remain the next separate gates.

AK-4506 then replaced heuristic prose matching with a shared controlled-code classification contract, exact hidden code/evidence labels, committed-source and production-adapter provenance, and a canonical one-shot ledger. The only authorized live process received a response with observed model identity `openai/gpt-5.6-sol` but could not parse it as JSON, stopped before later cases, and produced a rejected verification packet. This is terminal failure evidence, not permission to retry and not semantic-quality acceptance; shared-store durability still cannot satisfy the false semantic-LM gate.

## Durable boundaries

- `packages/dspx-core` is the product kernel; apps such as Forge consume Core and must not become Core dependencies.
- DSPx owns local generation, execution, evaluation, replay, receipts, and Oracle-backed empirical interpretation.
- Oracle interprets observed behavior; it does not rank, promote, activate, or become governance authority by implication.
- Receipts, bundles, reports, sidecars, and candidate-state packets are evidence or projections. They do not approve release or mutate external authority.
- Prompt/procedure truth remains in Prompt Vault, semantic ontology remains with ROCS/owner repos, and task/direction/decision/evidence authority remains in AK.
- Domain-specific generated review programs consume owner-supplied contracts and evidence; DSPx does not redefine domain truth, remediation policy, or acceptance authority.

## Observed exit signals and next gap

The offline contract slice now establishes these preparation facts without live effects:

- the complete checked-in v2 corpus is hash-bound as three declared strata in fixed order with score-`1.0` per-case/aggregate thresholds and zero allowed failures;
- one corpus-process attempt, zero health probes, zero DSPx-managed retries, no selective quality rerun, and effect-indeterminate stop behavior are precommitted;
- provider transport-call cardinality and provider-internal retries remain explicitly unproved;
- the semantic-analysis LM, embedding model, and coordinate store have separate acceptance/falsifier surfaces;
- three held-out embedding queries and Recall@1/MRR/nDCG@3 thresholds are frozen as one three-query top-1 routing smoke, not independent broad semantic-quality measures; AK-4480 later satisfied that exact narrow gate without widening its coverage;
- contract validation returns a declared zero-operation contract from a standard-library-only, canonical-file reader with no DSPx/provider/model/store imports and a fresh-HOME/cache no-write test; this is not general syscall or OS-isolation proof.

The fresh AK-4471 attempt establishes these additional conditions without widening claims:

- exact Core wheel `cd70538e…ed6a8`, built from commit `322902bf`, was installed outside the checkout with `PYTHONPATH` unset alongside the exact released auth-provider wheel;
- one corpus-process invocation used the configured `dspy-lm-auth/codex/gpt-5.6-sol` route, no separate health probe, no DSPx-managed/mechanical retry, and no selective quality rerun; provider transport-call cardinality and provider-internal retry behavior remain unproved;
- all three frozen cases executed in order, scored `1.0`, matched every required concept group, and hit no forbidden concepts;
- three unique candidate/receipt identities plus manifest, behavior, episode, Oracle, workflow, and replay hashes are bound in final proof `63c86e0f…02ac`;
- receipt-integrity replay passes for each case while runtime execution reproduction, semantic reproduction, and quality-evaluation reproduction remain explicitly not run or not evaluated;
- candidate-local Oracle indexing/reporting contains exactly three mock-embedding rows labeled plumbing-only with no shared publication;
- credential paths, tokens, headers, auth-store contents, and secret-shaped errors were neither inspected nor retained; possible provider-owned auth refresh is disclosed rather than denied;
- the runner completed terminally, and independent deterministic verification/review accepted the retained packet without another provider invocation.

The AK-4480 embedding attempt establishes these separate conditions:

- one canonical local attempt ledger was consumed for exact `sentence-transformers/all-MiniLM-L6-v2` commit `c9745ed1…99bf`; a prior wrapper-version setup failure occurred before the ledger, model acquisition, or evidence-root creation and is not counted as a model sequence;
- ten loader-relevant model artifacts match their precommitted commit-tree Git OIDs or LFS SHA-256, including `model.safetensors` SHA-256 `53aa5117…d9db`;
- the isolated frozen CPython 3.13 CPU runtime binds `uv.lock`, seven selected wheel hashes and versions, stable imported-payload hashes, tokenizer identity, 384-dimensional normalized float32 vectors, and cosine similarity / one-minus-cosine distance;
- all three frozen queries ranked the expected record uniquely first, with Recall@1, MRR, and nDCG@3 equal to `1.0`; result `92a9d058…0466c` and SQLite `7f70994d…182f` remain the unchanged terminal evidence;
- the first external offline full-batch reproduction failed on legacy installation-projection hashes and remains preserved; two model-free isolated runtime diagnostics established stable imported-payload hashes, and recovered verification `f0a23691…49a7` matched all six original vector hashes and received independent ACCEPT with qualifications;
- no semantic-analysis-LM call, shared-store connection, shared Oracle publication, AK mutation from evaluated code, release/activation mutation, or selective query rerun occurred.

The AK-4510/AK-4517 mDenseOn comparison establishes these further bounded conditions:

- AK-4510 remains the immutable first adapter failure with its consumed ledger, exact retained `a5fdb000…6df3` snapshot, and zero challenger vectors;
- AK-4517 consumed one separate recovery ledger, performed zero model acquisitions/network calls, removed only unsupported `token_type_ids`, and encoded all frozen documents and queries as complete role-bound batches;
- mDenseOn Recall@1, MRR, and nDCG@5 were each `1.0` over 15 labels, versus MiniLM `0.8`, `0.842857…`, and `0.833333…`; cross-lingual and long-context Recall@1 improved by `0.333333…` and `1.0`;
- model load, total encode time, and peak RSS were `2.1398` seconds, `4.3162` seconds, and `1,907,945,472` bytes under the exact frozen CPU runtime;
- independent verification accepted both SQLite rankings, retained vectors, metrics, resource bounds, zero-acquisition recovery, selection, and preserved lineage;
- new default coordinates use mDenseOn embedding version 2 with document/query role separation; explicit MiniLM remains available, and an in-place version-1-to-version-2 upsert is rejected rather than rewriting the old row.

Together these signals establish declared-strata installed-wheel behavior breadth and one narrowly qualified production-semantic embedding routing gate. They do not establish statistical representativeness, broad semantic correctness, independent semantic-analysis-LM quality, shared-store readiness, executed provider-model identity, network isolation, reproducible live inference, provider transport-call cardinality, release approval, registry publication, rollout, or production activation.

## Target product experience

A user should be able to state one intent and receive a runnable, evaluated, replayable DSPy candidate assembly whose behavior can be inspected, compared, improved, and governed.

The direct product loop is:

1. normalize intent and expose assumptions;
2. materialize explicit candidate surfaces;
3. execute under declared runtime/provider/data/metric conditions;
4. emit and verify receipts, traces, and evaluation evidence;
5. let Oracle interpret observed behavior without granting it authority;
6. refine or compare candidates through explicit bounded attempts;
7. keep review, signing, release, promotion, and activation as separate owner-governed transitions.

See [vision.md](vision.md) for the durable architecture and [program-gen-walkthrough.md](program-gen-walkthrough.md) for the current local product path.

## Status language rules

- Say **observed**, **implemented**, or **verified by `<command/artifact>`** only when current evidence supports it.
- Say **target**, **planned**, **deferred**, **contingent**, or **owner-gated** when behavior or authorization has not landed.
- Keep a positive proof adjacent to its limitations; do not preserve “closes X” while dropping “does not prove Y.”
- Do not use “production ready,” “approved,” “attested,” “signed,” “published,” “activated,” or “authoritative” for local evidence unless the owning contract and current proof establish that exact claim.
- Do not infer current task state from this file. Query AK.

## Authority and orientation map

- Durable product ambition: [vision.md](vision.md)
- Current product projection: this file
- Architecture and package boundaries: [../ARCHITECTURE.md](../ARCHITECTURE.md)
- Local workflow and validation: [developer_workflow.md](developer_workflow.md)
- Current generated-program walkthrough: [program-gen-walkthrough.md](program-gen-walkthrough.md)
- Runtime/source evidence: code, tests, built artifacts, and current validated receipts owned by this repo
- Active direction, execution, decisions, and canonical evidence: AK runtime
- Raw session history: `diary/`
- Crystallized reusable learning: `docs/learnings/`
