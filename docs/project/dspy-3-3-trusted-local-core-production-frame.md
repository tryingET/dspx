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

AK-4692 authors only this frame and its task-scope snapshot. It does not change dependencies, lockfiles, source, tests, runtime behavior, provider state, release state, or publication authority.

## Decision in one sentence

Do not create another strategic frame and do not treat DSPy 3.3 as a routine lock refresh. Execute a compatibility-gated work wave under Core production readiness: close the 3.3 migration hazards first, prove a bounded trusted-artifact local Core target second, migrate typed LM contracts incrementally third, and pilot Flex only through a separate experimental safety gate.

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
| Custom LMs | DSPx providers subclass DSPy LM bases while using DSPx-owned `LMRequest`/`LMResponse` DTOs and capability/error contracts. | DSPy's similarly named typed LM API is not a drop-in replacement. Stabilize the supported legacy bridge before typed migration. |
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
2. **One compatibility variable at a time.** Preserve a 3.1.3 baseline, probe 3.3 in an isolated environment, then mutate the canonical dependency surface only from reviewed evidence.
3. **Legacy bridge before typed rewrite.** Stabilize existing provider behavior on DSPy's supported compatibility bridge before migrating providers to the typed LM contract.
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

## Gate B — canonical DSPy 3.3 compatibility migration

### Entry

- Gate A has an accepted compatibility decision bound to exact DSPy/DSPy-AI/GEPA artifacts and one immutable isolated-environment identity;
- successor tasks have disjoint exact scopes and explicit dependencies on that decision;
- the previous exact 3.1.3 wheel, lock, resolved environment, installed proof, and rollback commands are retained;
- no canonical dependency or availability predicate changes until the ProgramOfThought, custom-LM bridge, and GEPA compatibility proofs all pass against the same target environment.

### Required work

1. Migrate generated `ProgramOfThought` construction and static policy to the 3.3 interpreter-factory lifecycle while preserving the empty filesystem/network/environment/tool sandbox contract.
2. Make each DSPx custom LM's 3.3 bridge posture explicit and test prompt/messages, sync/async behavior where supported, streaming, timeout/cancellation, callbacks, history, copy/state, failure normalization, and secret exclusion.
3. Map proven DSPx capabilities to upstream LM capability properties without overstating child or multi-provider support.
4. Refresh DSPy/DSPy-AI/GEPA and all transitive lock identities only after focused compatibility passes.
5. Regression-test GEPA compile, save, whole-program load, candidate materialization, refreshed behavior, receipt/replay identity, and comparison using exact real optimizer output in a credential-free path. Pickle-backed whole-program loading is compatibility evidence only and remains outside the first production target.
6. Characterize native ReActV2 in the isolated 3.3 environment with explicit opt-in and no user tools; account for upstream internal submission behavior and record structured history/termination/failure shapes. Keep the canonical materialization path disabled after the dependency update: public symbol availability is necessary evidence but never sufficient authorization.
7. Update stale beta wording to experimental wording only when exact upstream status supports it.
8. Keep canonical ReActV2 materialization, Flex, external ReActV2 tools, and typed-LM conversion disabled.

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

## Gate E — incremental typed LM adoption

This gate is a later provider-contract refactoring wave, not part of the base 3.3 lock refresh and not an external-tool gate.

### Entry

- Gate D's bounded technical evidence packet is complete at an immutable commit;
- one low-risk provider and its exact legacy baseline are selected by a separately scoped AK task;
- upstream typed-LM types/version and the DSPx DTO translation boundary are frozen for the attempt.

### Required work

- migrate one provider from the explicit legacy bridge to upstream typed LM request/response contracts;
- define translation between DSPx receipts/DTOs and upstream typed messages, tools, reasoning, usage, citations, cache controls, metadata, and stream events;
- preserve secret redaction, failure identity, cancellation, callback lineage, state/history/copy behavior, and replay semantics;
- compare typed and legacy behavior before each provider transition;
- do not bind external tools or mechanically migrate DSPx DTOs merely because upstream uses the same class names.

### Exit evidence

Provider-specific parity results bind exact request/response/stream/error/capability/receipt shapes. A mixed legacy/typed bridge is acceptable only when explicit and tested; hidden fallback is not.

### Falsifiers

Stop if typed translation loses identity, usage, reasoning, stream ordering, cancellation, errors, redaction, or receipt attribution; if upstream/DSPx DTO names are conflated; or if the migration implicitly enables tools.

### Rollback

Restore the provider's explicit legacy bridge and retain typed-attempt evidence. Do not change other providers or rewrite receipts.

### Owner and handoff

DSPx owns provider translation and receipts. Each external provider/auth owner retains transport and credential semantics. External ReActV2 tool binding requires a different owner-gated wave and is not authorized here.

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
2. DSPy 3.3 constructor, LM bridge, GEPA, save/load, tracing, replay, and generated-policy changes have exact regression evidence;
3. native no-user-tool ReActV2 is characterized under Gate B and remains canonically disabled until Gate C separately records either explicit support with evidence or explicit unsupported status;
4. Flex remains absent or separately experimental—never silently enabled by dependency resolution;
5. one immutable Core candidate has clean full/CI/package/installed evidence under an exact hash-bound resolved environment for the bounded trusted-artifact local target;
6. supported and unsupported deployment/capability matrices are explicit;
7. evidence durability, artifact trust, provider identity, local data, security, and rollback boundaries are fail-closed;
8. technical release evidence is handed to the release-operations owner without claiming quorum, registry publication, sdist support, or activation;
9. hosted server, shared Oracle, untrusted-code, external-tool, autonomous-foundry, and semantic-evaluation claims remain separate owner-gated propositions.

## Successor-task decomposition

Successor dependencies are explicit:

1. **Compatibility probe and decision packet** — isolated 3.3 environment, complete compatibility matrix, exact support-window decision.
2. After task 1, three proof slices may run in parallel only when their scopes are disjoint and all bind the same exact isolated target environment:
   - **Interpreter/generated-policy compatibility proof** — `ProgramOfThought` factory, static/negative policy tests, and explicit production exclusion;
   - **Custom-LM legacy-bridge proof** — capabilities, errors, state/history/copy/stream tests;
   - **GEPA compatibility proof** — exact compile/save/load/materialization/replay behavior, with pickle paths classified as compatibility-only.
3. **Canonical dependency/source/lock transaction** — depends on accepted results from all three task-2 proofs; installs exact direct bounds and a retained hash-bound resolved environment as one rollback unit.
4. **Native no-user-tool ReActV2 adoption decision/proof** — depends on task 3's immutable candidate; canonical materialization remains disabled until this task accepts it. Tools remain blocked.
5. **Trusted-local Core evidence candidate** — depends on tasks 3 and 4; package, installed environment, supported/unsupported matrix, downgrade, live compatibility, security inputs, and current full evidence.
6. **Typed-LM pilot** — depends on task 5; one provider, parity evidence, no tool enablement.
7. **Flex design and pilot** — separate decision/task only after task 5 and its containment prerequisites; it does not depend on typed-LM completion unless its exact design requires it.

No task may move the canonical lock before all task-2 proofs are accepted. Parallel work must use disjoint files/worktrees, the same exact target identity, and separate evidence. Tasks must not be combined merely to reduce task count when doing so hides failure attribution, ownership, or rollback.

## Relationship to existing work

- `IW-CPR-04-ORACLE-SEMANTIC-TRUTH` owns its separate v10/v11 empirical sequence. This frame neither retries nor authorizes it.
- `IW-CPR-05-RELEASE-OPERATIONS` owns signing, quorum, registry publication, supported distribution subjects, and operational release gates.
- `SF-AUTONOMOUS-PROGRAM-FOUNDRY` remains paused while Core production readiness is established. Oracle-guided GEPA automation, autonomous transition, and Flex expansion do not move into this frame by convenience.
- [Program-gen broadening strategic frame](program-gen-broadening-strategic-frame.md) remains historical guidance for the shipped bounded generated-program baseline; this frame changes dependency/runtime compatibility, not its authority ceiling.

## Validation for this frame

AK-4692 closes only after:

- strict docs validation passes for `docs/project`;
- the exact task scope passes with runtime-owned `.ontology` excluded from Git status discovery;
- `git diff --check` passes for the frame and snapshot;
- independent review confirms sequencing, safety, evidence, rollback, and owner boundaries;
- AK task contract, scope, guardrails, direction linkage, and lifecycle state reconcile.
