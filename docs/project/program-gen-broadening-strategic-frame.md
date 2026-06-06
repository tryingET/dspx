---
summary: "Blocker #1 implementation frame and Definition of Done for broadening program-gen beyond deterministic scaffolding."
read_when:
  - "You are planning or implementing program-gen broadening work."
  - "You need the blocker #1 DoD for richer intent normalization, topology rendering, graph execution, tools/retrievers/ReAct/ProgramOfThought, custom-module references, or generation preview UX."
  - "You need to distinguish descriptor-only support, local dry-run/evaluation support, executable local support, and production activation boundaries for generated programs."
type: "implementation-frame"
---

# Program-gen blocker #1 implementation frame

## Status

Status: blocker-specific implementation frame. It is subordinate to [[vision]] and [[product-posture]] and must not become a second general product posture file.

DRY ownership:

- [[vision]] owns the durable promise: one intent should produce a runnable, evaluated, replayable DSPy candidate assembly whose behavior can be inspected, compared, improved, and governed.
- [[product-posture]] owns shipped-vs-target status for `program-gen` and the current maturity gap.
- [[program-synthesis-boundary]] owns the target runtime-object vocabulary.
- [[program-gen-walkthrough]] owns the current hands-on artifact contract.
- [[generated-program-evidence-surface-boundaries]] and [[generated-program-activation-boundary]] own evidence/authority boundaries.

This document only turns blocker #1, “broaden program-gen beyond deterministic scaffolding,” into an implementation-ready DoD and wave plan. If it starts restating broad product posture, move that text back to [[product-posture]].

## Problem slice

The current product posture says `program-gen` is still scaffold-first: it can emit rich local evidence sidecars and render bounded topology subsets, but it does not yet safely cover richer structured-intent normalization, broad topology inference/rendering, broader graph execution, tool/retriever/ReAct/ProgramOfThought patterns, or custom module references.

Blocker #1 is closed only when those capabilities are represented and, where safe, locally materialized without enabling arbitrary imports, live effects, authority mutation, or production activation.

## Current baseline

Use [[product-posture]] as the current baseline. Implementation work should not duplicate that status here.

For blocker #1, the baseline gap is:

- intent normalization exists but needs stronger support-level classification and assumption preview;
- topology preservation/rendering exists for bounded subsets but needs a broader typed graph contract and renderer;
- local execution/traces exist for generated harnesses but need richer graph semantics and fail-closed coverage;
- tools/retrievers/ReAct/ProgramOfThought/custom refs are partly descriptor/readiness surfaces and must not become live effects accidentally.

## Strategic objective for this blocker

Make `program-gen` a richer local candidate-assembly orchestrator for the one-intent product loop described in [[vision]]:

1. normalize richer user intent into explicit candidate surfaces;
2. infer and preview candidate topology/capabilities before materialization;
3. render only the safe local subset;
4. preserve unsafe or incomplete capabilities as descriptor-only contracts with blockers;
5. bind all new claims into manifest/receipt/replay evidence;
6. leave activation and authority outside this blocker.

## Non-goals and safety boundaries

This blocker must not introduce:

- arbitrary Python imports, dynamic import strings, or unreviewed custom module execution;
- network, filesystem, subprocess, environment, credential, shell, browser, or service effects;
- live external retrievers or external tool calls;
- `dspy.Tool` binding, ReAct/ReActV2 live tool execution, or ProgramOfThought non-empty sandbox access without a later explicit safety contract;
- AK, governance-kernel, shared Oracle, shared-backend, source-owner, production, or external-authority mutation;
- automatic ranking, winner selection, pruning, promotion, deployment, rollout, or activation;
- UI/CLI wording that treats generated-program evidence as authority.

Fail-closed default: if a capability cannot be proven safe, preserve it as descriptor-only with explicit blockers and safe next actions.

## Support taxonomy

| Level | Meaning | Allowed for blocker #1 |
|---|---|---|
| Descriptor-only | Intent/topology/capability is represented, hash-bound, and replay-checked, but not executed. | Yes; default for unsafe or incomplete capabilities. |
| Local dry-run/evaluation | Candidate-local validation checks schemas, hashes, args, previews, or expected output shapes without calling live tools/retrievers or mutating outside candidate-local evidence paths. | Yes, if effect flags remain false and replay proves the boundary. |
| Executable local | Generated candidate code executes under explicit local runtime/evaluation conditions with no external effects beyond declared candidate/evaluation artifacts. | Yes, only for capability-registry-materializable safe primitives and bounded local retriever/sandbox modes. |
| Production activation | Candidate affects live routing, canonical state, source-owner systems, or external authority. | No; governed separately by [[generated-program-activation-boundary]]. |

## Target capability areas

### Structured intent normalization

DoD contribution:

- classify every declared or inferred capability by support level;
- record assumptions, missing evidence, unsafe requests, confidence, and safe next actions;
- preserve user-declared topology/capability hints instead of silently downgrading them;
- keep normalization sidecars non-authoritative and replayable.

### Topology inference/rendering

DoD contribution:

- represent module ids, primitives, signatures, edges, routing predicates, fan-out/fan-in, stage roles, capability refs, and final-output producers;
- infer candidates from clear routing, retrieval, extraction, validation, reasoning, critique/revise, tool, and retriever cues;
- render only safe materializable subsets;
- preserve unsupported nodes/edges as declared-only with blockers;
- fail closed on cycles, disconnected graphs, unresolved inputs, missing output producers, and unsupported effect claims.

### Graph execution semantics

DoD contribution:

- execute materialized DAG nodes through deterministic local scheduling;
- record scheduler completion/stall/failure events, module-call lineage, intermediate field lineage, and final-output source linkage;
- bind graph traces into `program_runtime_traces.json`, execution episodes, manifest, and replay;
- avoid hidden agentic loops or open-ended planners.

### Tools, retrievers, ReAct, and ProgramOfThought

DoD contribution:

- keep tool declarations descriptor-only until generated-adapter policy proves schema-bounded, hash-bound, dry-run-capable, non-executing posture;
- keep ReAct/ReActV2 `tool_refs` visible while executable tool bindings remain disabled;
- allow bounded local Retriever execution only for inline corpus or materialization-time local snapshots;
- keep external/live retrievers descriptor-only;
- allow ProgramOfThought only in empty or explicitly safe local sandbox profiles;
- record readiness/blockers in capability, module-surface, runtime-outcome, runtime-trace, and replay sidecars.

### Safe custom module references/import policy

DoD contribution:

- define custom refs as descriptors: module id, expected symbol, IO schema, primitive/effect claims, provenance, hash/package identity when available, and support level;
- reject arbitrary imports, path traversal, dynamic import expressions, mutable global initialization, network/filesystem/subprocess calls, and side-effectful module loading;
- preserve custom refs as descriptor-only until a later explicit safe adapter policy exists;
- require any future executable path to be allowlisted, hash-bound, sandboxed, effect-scanned, replay-checked, and explicitly opted in.

### Generation assumptions / preview UX

DoD contribution:

- preview normalized intent, inferred topology candidates, rendered-vs-declared-only nodes, support levels, blockers, missing evidence, safe next actions, and expected artifacts before materialization;
- require explicit reviewed contract/opt-in for ambiguous capability materialization;
- avoid activation language unless [[generated-program-activation-boundary]] gates are actually satisfied by owner-authorized evidence.

## Definition of Done for blocker #1

Blocker #1 is done when:

1. `program-gen normalize-intent` and materialization both emit richer preview/normalization with support levels, assumptions, blockers, missing evidence, and safe next actions.
2. Topology contracts represent multi-module DAGs with stage roles, edges, routing, fan-out/fan-in, final-output producers, and declared-only unsupported nodes.
3. Validation/replay fail closed on malformed topology, unsupported effects, mismatched support-level claims, unbound external calls, unsafe imports, or authority drift.
4. Generated assemblies render a broader safe local subset than the old scaffold while preserving unsupported patterns as hash-bound declarations.
5. Local graph execution records scheduler events, module-call lineage, intermediate/final-output coverage, and failure/stall states in runtime traces and execution episodes.
6. Tool/retriever/ReAct/ProgramOfThought/custom-ref policies distinguish descriptor-only, dry-run/evaluation, executable local, and activation-out-of-scope states.
7. Custom module refs have descriptor/readiness contracts and fail-closed import policy; arbitrary imports remain impossible.
8. Preview UX makes it obvious what will run, what will only be declared, what remains blocked, and what evidence artifacts will prove the boundary.
9. Manifest/receipt/replay bind all new normalization, topology, capability, trace, and readiness artifacts.
10. No blocker #1 implementation path mutates AK/governance/shared Oracle/external authority, performs undeclared effects, binds live tools/retrievers, or claims promotion/activation.

## Suggested implementation waves

1. **Preview vocabulary:** add support-level classification, blockers, and safe next actions to normalization/preview schemas.
2. **Topology contract:** expand typed nodes/edges/stage roles/final-output producer validation and declared-only preservation.
3. **Bounded renderer:** generate deterministic local DAG scheduling for the safe subset.
4. **Pattern descriptors:** expand descriptor-only surfaces for tools, retrievers, ReAct/ReActV2, ProgramOfThought, and custom refs.
5. **Dry-run validation:** add hash-bound non-executing adapter/schema validation where useful.
6. **Executable safe subset:** enable only reviewed local-safe primitives/retriever/sandbox modes.
7. **Preview UX:** make CLI preview/materialization summaries stable and testable.
8. **Replay hardening:** add negative fixtures for imports, effects, live retrievers, tool binding drift, topology mismatch, stale readiness, and activation wording drift.

## Verification plan

Minimum future implementation validation:

- normalization/preview golden fixtures;
- topology validation tests for valid DAGs, cycles, disconnected graphs, missing producers, unsupported primitives, routing mismatch, and declared-only preservation;
- generated-code compile/smoke tests for each executable local subset;
- replay tests for new sidecars and semantic safety fields;
- adversarial static-policy tests for import, network, filesystem, subprocess, `dspy.Tool`, live retriever, and custom-module attempts;
- behavior/runtime-trace tests for scheduler events, lineage, coverage, failure, and stall recording;
- CLI tests for preview UX;
- docs strict validation and `git diff --check` for docs-only slices.

## Expected evidence artifacts when done

Expected generated-candidate evidence should include updates or additions to:

- `intent_normalization.json` / generation preview content;
- `plan.json` topology and rendered-vs-declared-only status;
- `program_capability_registry.json` support-level policies;
- `module_surfaces.json` primitive/topology/capability readiness;
- `program_runtime_outcomes.json` and `program_runtime_traces.json`;
- `program_tool_contracts.json` or successor pattern-readiness sidecars;
- custom-module readiness sidecars;
- `execution_episode.json`, behavior results, manifest, receipt metadata, and replay output.

All artifacts remain generated-program evidence, not authority.

## Relationship to later blockers

- **Execution episodes as evaluation evidence:** this blocker improves graph traces; richer evaluation quality and model-jury execution remain later work.
- **Oracle non-authoritative integration:** broader traces can improve Oracle-readable evidence, but Oracle remains interpretation-only.
- **Refinement/search loops:** clearer contracts give search/refinement safer mutation targets; automatic refinement and winner selection remain later work.
- **Promotion/governance/activation:** better evidence may feed review packets, but activation remains governed by [[generated-program-activation-boundary]].
- **Guided operator UX:** preview taxonomy supports later guided UX; one-command refinement/review/activation automation remains out of scope.
- **Product hardening:** replay/static-policy/negative-fixture work feeds hardening, but broad production readiness is not claimed here.
