---
summary: "Implementation frame for DSPy 3.3 compatibility and a bounded trusted-artifact local Core production target."
read_when:
  - "Planning or reviewing the DSPy 3.3 dependency migration."
  - "Deciding what DSPx means by a first production-capable local Core release."
  - "Sequencing ReActV2, typed LM, external-tool, or Flex work."
type: "implementation-frame"
---

# DSPy 3.3 and trusted-local Core production implementation frame

## Status

Status: active implementation frame for AK-native work wave `IW-CPR-06-DSPY33-TRUSTED-LOCAL-CORE`, subordinate to the active `SF-CORE-PRODUCTION-READINESS` strategic frame.

This is a planning artifact, not live direction, release authority, or a second product-posture store. AK owns direction/task/decision/evidence truth. [Vision](vision.md) owns the durable product promise, [Product posture](product-posture.md) owns the current shipped-vs-target projection, [Developer workflow](developer_workflow.md) owns validation commands, and [Architecture](../ARCHITECTURE.md) owns package/runtime boundaries.

AK-4692 authored only this frame and its task-scope snapshot. AK-4693 subsequently accepted Gate A's `cap_current_range_pending_repairs` disposition. AK-4702 adopts only the narrow S0 scheduling variance defined below; it does not itself change dependencies, lockfiles, source, tests, runtime behavior, provider state, release state, or publication authority.

## Decision in one sentence

Do not create another strategic frame and do not treat DSPy 3.3 as a routine lock refresh. Decision 118 replaces the legacy-bridge sequence with a hard typed-LM cutover: preserve DSPx provider/effect authority behind one DSPy 3.3 typed adapter, intentionally contract the supported provider matrix during migration, prove the bounded trusted-artifact local Core target, and pilot ReActV2 or Flex only through their separate gates.

## Why this wave exists

DSPx has a substantial local behavior-first Core, but its declared dependency range and verified runtime have diverged:

- the Core package declares `dspy-ai>=3.1.3`;
- the checked-in lock and current repository environment resolve `dspy-ai==3.1.3`, `dspy==3.1.3`, and `gepa==0.0.26`;
- the latest stable public DSPy release verified on 2026-08-08 is `3.3.0`;
- a downstream installation of a DSPx wheel is not protected by the repository lock and may resolve a newer DSPy allowed by the open lower bound;
- DSPy 3.3 changes APIs and runtime contracts that DSPx currently generates or extends.

Therefore the present constraint is not merely stale. It permits an unreviewed consumer resolution that is wider than the compatibility evidence.

Upstream snapshot sources:

- [DSPy 3.3.0 on PyPI](https://pypi.org/project/dspy/3.3.0/)
- [DSPy 3.3.0 release](https://github.com/stanfordnlp/dspy/releases/tag/3.3.0)
- [DSPy normalized LM API migration](https://github.com/stanfordnlp/dspy/blob/3.3.0/docs/docs/community/normalized-lm-api-migration.md)
- [DSPy Flex guide](https://github.com/stanfordnlp/dspy/blob/3.3.0/docs/docs/diving-deeper/flex.md)

These upstream facts are dated discovery evidence. A successor dependency-mutation task must re-query exact stable releases, artifacts, requirements, and hashes rather than assuming this snapshot remains current.

## Observed compatibility baseline

| Surface | Current DSPx posture | Migration consequence |
|---|---|---|
| Dependency constraint | `dspy-ai>=3.1.3` in `packages/dspx-core/pyproject.toml` | Consumer resolution is wider than verified compatibility. |
| Repository lock/runtime | `dspy==3.1.3`, `dspy-ai==3.1.3`, `gepa==0.0.26` | Current local evidence is a 3.1.3 baseline, not 3.3 evidence. |
| `ProgramOfThought` | Generated code supplies `interpreter=dspy.PythonInterpreter(...)`; generated policy requires that shape. | DSPy 3.3 uses an interpreter-factory lifecycle; renderer and policy must migrate together. |
| ReAct | Direct agent service uses legacy `dspy.ReAct`; generated programs keep user tools disabled. | Preserve current behavior and distinguish direct-agent tool wiring from generated-program no-tool policy. |
| ReActV2 | DSPx has explicit-opt-in/no-user-tool contracts, readiness metadata, traces, and policy tests, but the locked DSPy exposes no public `ReActV2`. | Existing tests prove DSPx contract rendering, not native DSPy 3.3 execution. Activate only after real 3.3 no-user-tool proof. |
| Custom LMs | DSPx providers subclass DSPy LM bases while using DSPx-owned `LMRequest`/`LMResponse` DTOs and capability/error contracts. | Decision 118 requires a hard break: providers become DSPx-owned ports, one adapter owns DSPy's typed contract, and unmigrated providers become explicitly unavailable. |
| GEPA | DSPx calls GEPA directly and saves/materializes optimizer output; lock is `0.0.26`. | DSPy 3.3 resolves newer GEPA behavior/result shapes; compile, save, load, materialize, replay, and comparison need exact regression proof. |
| Flex | No DSPx capability, policy, source receipt, sandbox, or test integration; absent from the locked DSPy. | Generic GEPA support is not Flex support. Flex remains a later experimental pilot. |
| DSPy cache/persistence | DSPx owns receipts and caches; generated GEPA candidates may load DSPy artifacts with pickle enabled. | Evaluate upstream cache hardening separately; do not conflate cache restrictions with safety of owner-supplied whole-program artifacts. |

## First bounded production target

The first target is **trusted-artifact local Core**, not generic hosted or untrusted-code production.

A supported deployment at this target means:

- an exact Core wheel is installed outside the source checkout together with an exact Python/OS identity and a complete hash-bound resolved environment/constraints artifact; the installed dependency graph must match that retained environment;
- direct DSPy, DSPy-AI, GEPA, and provider dependencies are bounded to the exact tested compatibility window rather than relying on an alias package or an open lower bound;
- programs are owner-built or owner-reviewed, exact-source/hash-bound artifacts admitted by the supported capability matrix;
- execution is local, single-operator, and constrained to the documented safe generated-program subset; runtime-generated Python, optimizer-authored code, arbitrary custom imports, and pickle-backed whole-program artifacts are excluded from this first target;
- required manifests, receipts, traces, and replay-integrity checks persist successfully or the operation fails explicitly;
- provider/model/runtime identity is recorded to the extent directly observed, with unknown fields remaining unknown;
- local SQLite/candidate-local evidence is the default data posture;
- no artifact, Oracle report, jury result, signature, or receipt implies promotion, publication, or activation.

This target deliberately excludes:

- hosted SaaS or a production HTTP multi-tenant service;
- untrusted arbitrary Python, custom imports, pickle artifacts, or optimizer-authored code;
- live external tools/retrievers or ReActV2 tool binding;
- shared Oracle/Postgres production readiness;
- automatic Oracle ranking, pruning, promotion, or activation;
- an independently controlled release-owner quorum, registry publication, sdist support, or external activation unless their separate owner gates pass.

For this first target, generated `ProgramOfThought` is excluded because the surrounding reviewed artifact does not make LM-produced runtime code owner-reviewed or OS-confined. Current pickle-backed GEPA whole-program load/materialization is also excluded. Gate B may characterize both paths for compatibility, but Gate D may include GEPA only through a separately proven non-pickle, hash-bound materialization path; otherwise GEPA remains outside the supported production matrix.

A future hosted, shared-store, untrusted-code, or autonomous-foundry target requires its own threat model, owner contract, rollout, rollback, and acceptance evidence. It cannot inherit production status from this bounded target.

## Execution principles

1. **Compatibility before feature adoption.** A dependency migration may expose ReActV2 and Flex, but exposure is not integration or authorization.
2. **One reviewed cutover transaction.** Preserve the exact 3.1.3 rollback baseline, build the typed provider kernel in the isolated 3.3 environment, then move source, exact dependencies, lock, and the intentionally reduced provider support matrix as one reviewed transaction.
3. **Remove the bridge instead of repairing it.** Transport providers do not inherit DSPy; one anti-corruption adapter owns the DSPy 3.3 typed request/response lifecycle. No compatibility alias or mixed legacy/typed fallback survives on the canonical path.
4. **Characterize before enabling ReActV2.** Gate B may run native no-user-tool ReActV2 only in an isolated compatibility probe. Installing DSPy 3.3 or detecting `dspy.ReActV2` must not make the canonical materialization path available. A separate Gate C adoption decision and proof must precede enablement; external tool binding remains outside this wave.
5. **Trusted artifacts before sandbox claims.** The first production target explicitly limits artifact trust; Python-level guards are not an OS sandbox.
6. **Receipts must fail closed.** A successful product operation cannot silently omit a required artifact or receipt.
7. **Release authority remains separate.** Technical readiness evidence flows to `IW-CPR-05-RELEASE-OPERATIONS`; it does not bind owners, authorize a registry, or publish packages.
8. **The semantic empirical line remains separate.** AK-4643/v10 and the v11 Gate sequence retain their own immutable identities, process budgets, and authority gates.

## Gate A — isolated compatibility probe and adoption decision

### Entry

- exact current 3.1.3 baseline and failing/passing commands are recorded;
- a successor AK task has exact source/test/dependency scope;
- the probe uses an isolated `TMPDIR`-backed environment and does not rewrite the canonical lock.

### Required work

- resolve exact DSPy/DSPy-AI/GEPA artifacts and transitive changes for the chosen 3.3 target;
- inventory public API, constructor, serialization, tool-schema, callback, caching, hashing, exception, and dependency changes used by DSPx;
- run a focused compatibility matrix over generated programs, providers, GEPA, replay, runtime traces, save/load, and package installation;
- classify failures as existing defects, intentional upstream breaks, bridge gaps, or experimental-feature gaps;
- place the support-window choice and compatibility strategy through the repo's AK decision membrane before canonical dependency mutation.

### Exit evidence

Retain the exact compatibility report, current-baseline result, target Python/OS and resolved-environment identity, DSPy/DSPy-AI/GEPA artifact hashes, focused command results, classified failures, and AK decision identity. The reviewed decision selects one bounded outcome:

- migrate to an exact reviewed `3.3.x` compatibility window;
- temporarily cap the current supported range while blockers are resolved;
- or stop because upstream drift invalidates the proposed target.

### Falsifiers

Stop rather than refresh the lock when:

- exact artifacts or requirements cannot be retained/reconstructed;
- current provider semantics cannot be represented truthfully on the supported bridge;
- generated-code safety policy would need to weaken;
- GEPA save/load/materialization lineage becomes ambiguous;
- tests require enabling external tools, live effects, or unreviewed pickle/code execution.

### Rollback

Delete the isolated probe environment and retain the compatibility report. The canonical dependency declaration and lock remain unchanged.

### Owner and handoff

DSPx owns the isolated probe, compatibility matrix, and non-secret report. AK owns the support-window/adoption decision and successor-task authorization. Security, dependency/provenance, and release owners receive exact evidence for their own gates only; Gate A cannot delegate or satisfy their acceptance authority.

## Accepted S0 variance — exact 3.1.3 consumer-safety cap

Gate A's accepted `cap_current_range_pending_repairs` disposition exposed one immediate consumer-safety defect: the open `dspy-ai>=3.1.3` declaration permits wheel consumers to resolve DSPy versions outside the only currently passing baseline. S0 may therefore precede S1-S4 solely to replace that open range with exact direct `dspy==3.1.3` and `dspy-ai==3.1.3` bounds and to retain the matching lock/environment as the rollback baseline for later migration work.

This is a scheduling variance, not DSPy 3.3 adoption. AK-4702 authorizes only the frame amendment and snapshot that define it. A separate accepted implementation task must own any dependency or lock mutation.

### Entry

- AK-4693's reviewed compatibility probe and `cap_current_range_pending_repairs` disposition remain accepted and unchanged;
- the implementation task binds the exact pre-S0 open declaration identity plus the exact current 3.1.3 lock, built-wheel, installed-environment, and focused-baseline identities retained by AK-4693;
- its scope is limited to the Core dependency declaration, matching lock changes, exact consumer/package proof, and the retained S0 rollback receipt;
- peer-owned source, generated policy, providers, tests unrelated to dependency proof, release state, and runtime state remain outside scope.

### Exact S0 work and proof

- declare both DSPy distribution identities directly and exactly at `3.1.3`; do not use a compatible-release, lower-bound-only, wildcard, or alias-only constraint;
- update the canonical lock only as required to represent those exact current versions; GEPA remains at the current `0.0.26` baseline and unrelated transitive versions must not refresh by convenience;
- prove the declaration, lock, built Core wheel metadata, a clean wheel-consumer resolution, and the installed runtime all report `dspy==3.1.3` and `dspy-ai==3.1.3` with no source-checkout leakage;
- rerun the accepted current-baseline compatibility commands and package/import/CLI journey needed to show that the cap preserves current behavior;
- retain the exact declaration, lock, resolved environment, wheel hashes, commands, exits, and downgrade/reinstall commands as the S0 baseline used by S1-S5.

S0 does not authorize DSPy/DSPy-AI `3.3.x`, GEPA `0.1.1`, Python support-window changes, `ProgramOfThought` repair, generated-smoke repair, custom-LM changes, ReActV2, typed LM, Flex, providers, tools, release, publication, or activation. Dependency availability cannot satisfy any later feature or owner gate.

### Falsifiers

Stop and leave the canonical dependency/lock transaction unapplied or reverted when:

- the wheel declaration, lock, resolver output, installed distributions, or retained environment disagree on either exact 3.1.3 identity;
- the lock operation refreshes unrelated dependencies or changes GEPA;
- the baseline, build, installed-wheel, import, or CLI proof regresses;
- the proof requires source leakage, credentials, provider effects, generated-code policy weakening, or any 3.3/feature enablement;
- the pre-S0 state and exact accepted S0 state cannot both be reconstructed for audit and rollback.

### Rollback and successor dependency

Apply S0 as one declaration/lock/proof transaction. If its proof fails, revert only that transaction, retain the failed evidence, prohibit package release under the reopened range, and create no compatibility claim. Once accepted, the exact 3.1.3 declaration, lock, resolved environment, and installed proof become the retained rollback target for S5; they are not permission to discard the earlier audit baseline.

S1 and S2 remain accepted compatibility repairs against the exact isolated 3.3 target. AK-4722 and AK-4725 remain truthful terminal evidence but no longer gate the canonical transaction: Decision 118 supersedes S3 legacy-bridge repair with a typed provider-kernel cutover and keeps pickle-backed S4b materialization outside the trusted-local production matrix. S0 remains the exact rollback baseline and cannot waive typed-kernel, installed-artifact, or safety proof.

### Owner and handoff

DSPx owns the separately scoped S0 declaration/lock implementation and local consumer proof. AK owns its task contract, evidence, and acceptance. Dependency/provenance and release owners retain their own judgments; S0 establishes neither release readiness nor publication authority.

## Gate B — canonical DSPy 3.3 compatibility migration

### Entry

- Gate A has an accepted compatibility decision bound to exact DSPy/DSPy-AI/GEPA artifacts and one immutable isolated-environment identity;
- successor tasks have disjoint exact scopes and explicit dependencies on that decision;
- accepted S0 exact 3.1.3 direct bounds, wheel, lock, resolved environment, installed proof, and rollback commands are retained;
- S1/S2 compatibility repairs remain accepted, Decision 118 is accepted, and the isolated T1 typed provider kernel passes against the retained exact target; AK-4722/AK-4725 remain historical evidence rather than entry gates.

### Required work

1. Migrate generated `ProgramOfThought` construction and static policy to the 3.3 interpreter-factory lifecycle while preserving the empty filesystem/network/environment/tool sandbox contract.
2. Replace dual-interface provider objects with DSPx-owned provider ports plus the sole typed `DSPyTypedLMAdapter`; delete legacy provider subclasses, response facsimiles, mixed history ownership, and `MultiProviderLM` before the canonical dependency move.
3. Start with the deterministic offline stub, reject unsupported typed content before effects, and restore providers only through an explicit support allowlist after provider-specific effect, error, redaction, receipt, and capability proof.
4. Refresh DSPy/DSPy-AI/GEPA and all transitive lock identities only in the reviewed typed source/dependency/lock transaction after isolated typed-kernel proof.
5. Retain S4a/S4b as compatibility evidence. A separately scoped credential-free real GEPA materialization journey may run later, but pickle-backed whole-program loading and materialization remain outside the first production target and do not gate the typed transaction.
6. Characterize native ReActV2 in the isolated 3.3 environment with explicit opt-in and no user tools; account for upstream internal submission behavior and record structured history/termination/failure shapes. Keep the canonical materialization path disabled after the dependency update: public symbol availability is necessary evidence but never sufficient authorization.
7. Update stale beta wording to experimental wording only when exact upstream status supports it.
8. Keep canonical ReActV2 materialization, Flex, and external ReActV2 tools disabled; typed-LM conversion is the selected migration mechanism and authorizes no feature by availability alone.

### Exit evidence

- exact dependency declaration and lock diff;
- focused 3.1.3 baseline versus 3.3 compatibility report;
- generated-policy and runtime negative tests;
- package build and installed-wheel journey;
- clean task scope, static/type gates, focused tests, full gate, and CI at one immutable commit;
- independent compatibility and safety review.

### Owner and handoff

DSPx owns source compatibility, provider bridges, generated policy, package tests, and local evidence. The AK decision membrane owns the support-window/adoption decision. Security and release owners receive evidence only; Gate B cannot authorize the production matrix or publication.

### Falsifiers

- any supported generated topology becomes silently non-materializable;
- provider/model identity, request shape, streaming, retry, or failure semantics drift without explicit contract changes;
- replay treats different DSPy/GEPA versions or hashes as equivalent;
- whole-program loading broadens the trusted-artifact claim;
- the dependency range again allows versions outside tested compatibility;
- installing 3.3 or exposing a public symbol silently enables ReActV2, Flex, tools, runtime-generated code, or another previously unavailable capability;
- the installed dependency graph differs from the retained exact target environment.

### Rollback

Revert the dependency/source migration as one reviewed transaction and restore the retained exact wheel, declaration, lock, and resolved environment. Quarantine 3.3-created caches, GEPA/pickle artifacts, and version-bound receipts from the restored runtime; preserve failed evidence and never claim cross-version replay equivalence.

## Gate C — separate native no-user-tool ReActV2 adoption

### Entry

- Gate B is accepted at one immutable commit with the canonical ReActV2 path still disabled;
- a separate AK task binds that commit, exact DSPy/ReActV2 identity, generated-policy identity, and explicit-opt-in contract;
- an AK decision or task-native adoption contract selects only no-user-tool characterization/adoption; external tools and production activation are excluded.

### Required work

- execute native ReActV2 with no user tools under the exact Gate B environment;
- account explicitly for upstream's internal submission tool, structured history, tool-call/result representation, forced submission, iteration limits, context/parse failures, exceptions, callbacks, save/load, and replay;
- verify that declared tool references remain descriptors, `tools=[]` remains enforced, and runtime evidence cannot claim user-tool execution;
- prove default-disabled behavior and show that public symbol availability, an environment variable, or stale configuration cannot bypass the Gate C adoption state;
- preserve a clean unsupported outcome when native behavior cannot satisfy DSPx policy without weakening it.

### Exit evidence

One reviewed result records either:

- `supported_explicit_opt_in_no_user_tools`, bound to exact code/dependency/policy/tests; or
- `unsupported`, with the canonical path remaining disabled and exact falsifiers retained.

Neither outcome authorizes external tools, typed-LM migration, production activation, or Flex.

### Falsifiers

Stop if ReActV2 executes or represents user tools, availability bypasses adoption state, internal submission is misclassified as a user effect, structured terminal/history evidence cannot be replay-bound, save/load changes policy identity, or failure handling loses effect/receipt truth.

### Rollback

Disable the ReActV2 adoption state and restore Gate B's canonical-disabled policy while retaining the exact attempt evidence. DSPy 3.3 compatibility remains independently valid if its Gate B contract still passes.

### Owner and handoff

DSPx owns generated-program policy, explicit opt-in, traces, receipts, and local adoption evidence. AK owns the adoption decision/task lineage. Provider-tool, external-effect, security/sandbox, release, and activation owners receive no implied authority.

## Gate D — trusted-artifact local Core production proof

### Entry

- Gate B is accepted at one immutable commit with exact wheel, declaration, lock, and hash-bound resolved-environment identities;
- Gate C has either accepted native no-user-tool ReActV2 or recorded it as unsupported; availability alone is not treated as support;
- a successor AK task binds the exact candidate, supported/unsupported matrix, owner handoffs, and rollback target;
- security, dependency/provenance, and release-operations owners have named acceptance inputs without delegating their authority to DSPx evidence.

### Required work

- define the exact supported local capability/provider/runtime matrix and explicit unsupported matrix;
- require successful artifact/receipt persistence for a successful operation;
- build and install the exact Core wheel outside the checkout with no source-path leakage, using the retained complete hash-bound resolved environment/constraints artifact; reject any installed dependency-graph drift;
- exercise representative owner-built/hash-bound generated programs, runtime episodes, receipt-integrity replay, and local Oracle indexing/reporting; exclude ProgramOfThought and pickle-backed whole-program artifacts;
- include a GEPA candidate journey only if a separate non-pickle, hash-bound materialization path has passed its own admission and replay proof; otherwise declare GEPA unsupported for this target;
- run a declared live-provider compatibility matrix separately from credential-free CI, with exact model/provider/runtime identity and retained non-secret evidence;
- declare local evidence retention, deletion, secret redaction, cache, and failure behavior;
- run vulnerability, license, dependency, provenance, and package-metadata acceptance through their owner-approved gates;
- hand technical evidence to `IW-CPR-05-RELEASE-OPERATIONS` without claiming publication authority.

### Exit

The technical evidence packet is complete for release-operations evaluation of the bounded target, or it explicitly identifies the remaining failed technical/owner gates. This frame makes no releasability, release-readiness, publication, or activation claim.

### Falsifiers

- required receipts or artifacts can be lost while the command reports success;
- a supported path requires arbitrary/untrusted Python or inherited secrets;
- live compatibility evidence cannot bind exact provider/model/runtime identity enough for the declared claim;
- the full gate, package gate, installed journey, or security acceptance is not current at the candidate commit;
- release evidence is used as a substitute for owner authorization.

### Rollback

Retain the last supported exact Core wheel, dependency declaration, lock, resolved environment, and installed proof. Exercise a downgrade installation and post-rollback journey before Gate D exits. Quarantine incompatible 3.3-created caches, GEPA/pickle artifacts, and version-bound evidence; preserve all failed receipts. Rollback triggers include dependency-graph drift, receipt/persistence loss, provider-contract regression, unsupported artifact execution, or any failed required gate.

### Owner and handoff

DSPx owns the bounded local capability matrix and technical evidence. Security/dependency/provenance owners own their acceptance gates. `IW-CPR-05-RELEASE-OPERATIONS` owns release subjects, signing/quorum, registry, publication, yank/rollback, and operational release judgment. No owner may be inferred from a passing DSPx artifact.

## Gate E — additive provider restoration after the typed cutover

This gate restores provider breadth after the hard typed-LM cutover. It is not a compatibility-bridge, external-tool, or feature-adoption gate.

### Entry

- the typed provider kernel and canonical exact-3.3 transaction are accepted at an immutable commit;
- the provider is explicitly unavailable in the current support matrix;
- one provider-specific AK task freezes its DSPx port, effect, receipt, redaction, and capability contract.

### Required work

- remove DSPy inheritance from the provider and implement the DSPx-owned provider port;
- route it through the sole typed adapter without fake OpenAI response envelopes or provider-specific DSPy lifecycle code;
- preserve secret redaction, failure identity, effect disposition, provider/model identity, bounded usage, and receipt semantics;
- reject unsupported typed parts, async, cancellation, or streaming before effects;
- add the provider to the explicit support allowlist only after exact contract proof.

### Exit evidence

Provider-specific results bind exact request/result/effect/error/capability/receipt shapes. The provider is either accepted into the support matrix or remains explicitly unavailable; no hidden fallback exists.

### Falsifiers

Stop if the provider remains a DSPy subclass, typed translation loses identity or receipt attribution, a failure becomes answer text, an indeterminate effect can retry, upstream/DSPx DTO names are conflated, or migration implicitly enables tools.

### Rollback

Revert the failed additive provider source commit, remove the provider from the support allowlist, and retain evidence while preserving the accepted typed runtime generation. Do not restore legacy inheritance or rewrite receipts.

### Owner and handoff

DSPx owns provider ports, typed translation, effect disposition, and receipts. Each external provider/auth owner retains transport and credential semantics. External ReActV2 tool binding requires a different owner-gated wave and is not authorized here.

## Gate F — separate experimental Flex pilot

Flex is not a production-readiness shortcut and is not implied by GEPA compatibility.

### Entry

- Gate D's trusted-artifact target is stable and Gate E is complete or explicitly not required for the pilot;
- an accepted AK decision defines Flex's experimental status, exact DSPy version, threat model, interpreter owner, budgets, and non-authority ceiling;
- the pilot has an isolated runtime and separately scoped task; it cannot alter the supported production matrix.

### Required work

- define `dspy.Flex` as an explicit experimental capability with exact version binding;
- retain optimizer-authored source, hashes, lineage, receipts, and comparison evidence;
- establish interpreter/runtime ownership and a real isolation posture appropriate to optimizer-authored code;
- enforce predictor-call, token/cost, time, CPU, memory, process, filesystem, and network budgets;
- permit no external tools or inherited secrets in the first pilot;
- prove failure scoring, invalid-code handling, save/load/replay, and operator review before any candidate transition;
- grant no Oracle promotion, shared publication, release, or activation authority.

### Exit evidence

One local experimental candidate is either reproducibly retained and evaluated under the accepted containment contract, or the pilot records a terminal unsupported disposition. Neither outcome changes the Gate D production matrix.

### Falsifiers

Stop if generated code cannot be confined, attributed, deterministically retained, resource-bounded, or evaluated without weakening the trusted-artifact target; if Deno/interpreter ownership is unresolved; or if tools, secrets, production, or activation enter the pilot.

### Rollback

Delete/disable the experimental capability and isolated runtime, quarantine optimizer-authored artifacts from supported paths, and retain the full attempt evidence. Gate D artifacts and dependency identities remain unchanged.

### Owner and handoff

DSPx owns local experimental evidence. The interpreter/sandbox owner owns containment. AK owns the experimental decision and task lineage. Release, shared Oracle, provider-tool, and activation owners receive no implied authority.

## Success criteria for IW-CPR-06

The work wave is complete only when:

1. the dependency support window matches tested compatibility rather than an unbounded lower-bound assumption;
2. DSPy 3.3 constructor, typed adapter, GEPA supported/unsupported posture, save/load, tracing, replay, and generated-policy changes have exact regression evidence;
3. native no-user-tool ReActV2 is characterized under Gate B and remains canonically disabled until Gate C separately records either explicit support with evidence or explicit unsupported status;
4. Flex remains absent or separately experimental—never silently enabled by dependency resolution;
5. one immutable Core candidate has clean full/CI/package/installed evidence under an exact hash-bound resolved environment for the bounded trusted-artifact local target;
6. supported and unsupported deployment/capability matrices are explicit;
7. evidence durability, artifact trust, provider identity, local data, security, and rollback boundaries are fail-closed;
8. technical release evidence is handed to the release-operations owner without claiming quorum, registry publication, sdist support, or activation;
9. hosted server, shared Oracle, untrusted-code, external-tool, autonomous-foundry, and semantic-evaluation claims remain separate owner-gated propositions.

## Successor-task decomposition

AK-4693 completed the compatibility probe and accepted `cap_current_range_pending_repairs`. Its successor dependencies are explicit:

0. **S0 — exact 3.1.3 rollback cap** — completed consumer proof retained as the rollback baseline.
1. **S1 — interpreter/generated-policy compatibility proof** — completed while preserving explicit production exclusion.
2. **S2 — generated-smoke attribution and repair** — completed without weakening `generated_code_guard.py`.
3. **S3 historical result** — AK-4722 remains `unsupported_legacy_bridge`; Decision 118 supersedes repair with the typed hard cutover rather than relabeling the result.
4. **S4 historical result** — S4a remains compatibility-only and S4b remains `unsupported_real_materialization`; pickle paths remain production-excluded and nonblocking.
5. **T1 — typed provider kernel and offline canary** — prove DSPx provider ports, sole typed adapter, stub, pre-effect rejection, state/copy/history separation, and effect disposition against the exact isolated target.
6. **T2 — canonical DSPy 3.3 typed source/dependency/lock transaction** — atomically install exact direct bounds, typed kernel, explicit supported-provider allowlist, deletion of every importable legacy provider/response/aggregation path, generated-policy regressions, installed-wheel proof, and retained rollback unit.
7. **T3 — additive provider restoration** — migrate providers one at a time without DSPy inheritance; unavailable providers remain explicit.
8. **T4 — aggregation replacement** — `MultiProviderLM` was deleted in T2; add only a new DSPx-port aggregate whose effect and cancellation rules pass separately.
9. **T5 — trusted-local Core evidence candidate** — package, installed environment, supported/unsupported matrix, downgrade, safety inputs, and current full evidence.
10. **S6/ReActV2 and Flex** — separate decisions/tasks after the typed Core candidate; tools remain blocked.

No task may move the canonical lock to DSPy/DSPy-AI 3.3 before isolated T1 proof and an accepted T2 source/dependency/lock contract. S0 remains the exact 3.1.3 rollback baseline with GEPA 0.0.26. The T2 transaction may resolve the retained exact GEPA 0.1.1 dependency identity without claiming pickle-backed production support. Parallel work must use disjoint files/worktrees, the same exact target identity, and separate evidence.

## Relationship to existing work

- `IW-CPR-04-ORACLE-SEMANTIC-TRUTH` owns its separate v10/v11 empirical sequence. This frame neither retries nor authorizes it.
- `IW-CPR-05-RELEASE-OPERATIONS` owns signing, quorum, registry publication, supported distribution subjects, and operational release gates.
- `SF-AUTONOMOUS-PROGRAM-FOUNDRY` remains paused while Core production readiness is established. Oracle-guided GEPA automation, autonomous transition, and Flex expansion do not move into this frame by convenience.
- [Program-gen broadening strategic frame](program-gen-broadening-strategic-frame.md) remains historical guidance for the shipped bounded generated-program baseline; this frame changes dependency/runtime compatibility, not its authority ceiling.

## Validation for this frame

AK-4692's original frame-authoring evidence remains unchanged. AK-4702 closes only after:

- strict docs validation passes for `docs/project`;
- the exact task scope passes with runtime-owned `.ontology` excluded from Git status discovery;
- `git diff --check` passes for the frame and snapshot;
- independent review confirms sequencing, safety, evidence, rollback, and owner boundaries;
- AK task contract, scope, guardrails, direction linkage, and lifecycle state reconcile.
