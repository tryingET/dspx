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

## Current snapshot — 2026-08-01

### Posture in one sentence

DSPx has a substantial local-first, behavior-first Core plus verified non-authoritative signing/custody, owner authentication, and one qualified recovered installed-wheel real-provider case; the active product gap is representative live-behavior breadth and production-semantic Oracle quality, not more release-authority machinery or autonomous-foundry expansion.

### Active frontier: Core production readiness

Current AK direction prioritizes making Core DSPx installable, operationally safe, and empirically proven before expanding autonomous foundry behavior.

The latest bounded proof establishes:

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

These observations are implemented and exercised by the package and focused test lanes. They are not release approval.

### Validation gate status

The repo-declared local confidence gates are green:

- `just typecheck` passes across Core and Forge after semantic-corpus keys and validated GEPA improvement requests gained explicit string narrowing.
- `just typecheck-tests` passes after release-evidence fixtures gained callable/deeply mutable boundaries and dynamic module imports gained explicit tuple cardinality.
- `just verify-full` passes at the AK-4458 recovered-verification baseline. The credential-free offline suite passed 2742 tests with 4 expected skips; the residual live/network/model/GPU/Postgres lane reported 5 expected skips.

This establishes the cited repo-local full-gate baseline. Separate bounded evidence establishes signer verification, public CI evidence custody, authority-false owner authentication, and one installed-wheel live-provider case. That single case does not establish broad live-provider or production-semantic quality, an end-to-end runner status pass, package publication, release approval, or activation.

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

- broad live-provider correctness, representative program quality, or production-semantic quality; current live evidence covers only one bounded authority case;
- production-semantic Oracle embeddings or comparison quality;
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
| Oracle behavioral evidence | Candidate-local evidence can be indexed and reported with explicit backend identity; Oracle exposes search, drift, territory, frontier, attractor, and program-evidence concepts. | Production-semantic embedding quality and shared-backend readiness remain separate empirical/operational gates. Oracle remains interpretation, not authority. |
| Refinement and review | Local proposals, GEPA attempts, second candidates, comparisons, jury/model-jury evidence, adjudication records, plans, status, and activation-preflight packets exist as inspectable sidecars and guided workflows. | Further autonomous orchestration is paused. External apply, activation, and owner acceptance remain unavailable without their own authority contracts. |
| Packaging and release evidence | Core-only installed-wheel behavior, exact-wheel identity, two SBOM scopes, signed public CI evidence/custody, immutable owner-policy currentness, one hardware-authenticated authority-false shadow consume, and one qualified installed-wheel live-provider proof are observed. | Representative multi-case/provider behavioral coverage, package publication, release authority, independently controlled quorum, and sdist support remain unavailable or unproved. |
| Operator experience | `program-loop` provides a coherent local intent-to-candidate/evidence/state path; `just smoke-base` dogfoods an offline no-AK loop; one live invocation plus recovered verification composes exact wheel origin, one real-provider case, replay, and candidate-local Oracle reporting. | No representative installed-wheel live corpus or production-semantic Oracle lane is proven, and the corrected verifier has not yet completed inside a fresh runner invocation end to end. |

### Root cause and sequencing consequence

The former product-proof gap was compositional rather than absence of components. Dogfood exposed the missing seams instead of hiding them: the wrapper argument order did not match its documented positional order; aggregate-schema lookup depended on scratch cwd; generated provider-facing signatures retained intent quality criteria only as evaluator metadata; replay freshness compared equivalent relative and absolute path spellings; and auth-wheel verification reused a Core-only package-root inventory assumption. AK-4450 preserved the first semantic failure. AK-4458 projected declared objective/constraints/output quality into provider-visible signatures, fixed the path and package assumptions, then produced one score-`1.0` live behavior result and a recovered deterministic proof without weakening the corpus, scorer, or authority boundary.

The sequencing consequence now changes. Exact installed composition is observed for one bounded case, so repeating release ceremony or one-case canaries has lower product value. The next lawful product slice should broaden representative installed-wheel live behavior and then evaluate a production-semantic Oracle backend against those observed episodes, while keeping deterministic release evidence, credentials, shared Oracle, publication, and activation separate.

## Durable boundaries

- `packages/dspx-core` is the product kernel; apps such as Forge consume Core and must not become Core dependencies.
- DSPx owns local generation, execution, evaluation, replay, receipts, and Oracle-backed empirical interpretation.
- Oracle interprets observed behavior; it does not rank, promote, activate, or become governance authority by implication.
- Receipts, bundles, reports, sidecars, and candidate-state packets are evidence or projections. They do not approve release or mutate external authority.
- Prompt/procedure truth remains in Prompt Vault, semantic ontology remains with ROCS/owner repos, and task/direction/decision/evidence authority remains in AK.
- Domain-specific generated review programs consume owner-supplied contracts and evidence; DSPx does not redefine domain truth, remediation policy, or acceptance authority.

## Observed exit signals and next gap

One live invocation plus recovered deterministic verification established the following one-case conditions without widening claims:

- an exact Core wheel path and SHA-256 are installed outside the checkout with `PYTHONPATH` unset;
- a pinned released auth-provider dependency and an explicit requested provider/model route execute one bounded existing semantic intent;
- behavior status and declared quality are derived from observed outputs, including truthful nonzero failure on provider or semantic failure;
- manifest, receipt, behavior, Oracle evidence/report, candidate identity, and exact wheel/provider dependency identities are hash-bound in one sanitized evidence packet;
- receipt replay integrity passes while runtime execution reproduction, semantic reproduction, and quality-evaluation reproduction remain explicitly not run or not evaluated;
- candidate-local Oracle indexing/reporting succeeds with mock embeddings labeled plumbing-only and no shared publication;
- credential paths, tokens, headers, auth-store contents, and secret-shaped errors are neither inspected nor retained; possible provider-owned auth refresh is disclosed rather than denied;
- focused package/provider/semantic/replay/Oracle tests, scoped static checks, impact validation, direction checks, and pre-push validation pass;
- product posture and AK state are reconciled before any completion or readiness statement.

These signals are now observed for one bounded case through AK evidence 5927–5932 and the qualified recovered proof. They do not establish representative behavioral breadth, production-semantic Oracle quality, network isolation, reproducible live inference, an end-to-end runner status pass, release approval, registry publication, rollout, or production activation.

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
