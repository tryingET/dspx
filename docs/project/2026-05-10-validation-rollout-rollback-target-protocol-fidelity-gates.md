---
summary: "Post-ADR validation, rollout, and rollback plan for DSPx target-protocol fidelity gates."
read_when:
  - "You are implementing ADR 20260510 target-protocol fidelity gates."
  - "You need the post-ADR execution gates before coding gen-target-contract sidecars."
type: "plan"
adr: "docs/adr/20260510-target-protocol-fidelity-gates.md"
decision_id: 34
---

# Validation, Rollout, and Rollback — Target-Protocol Fidelity Gates

## Purpose

This is the post-ADR execution pack for `docs/adr/20260510-target-protocol-fidelity-gates.md`.

It translates the accepted decision into implementation gates without widening scope beyond the ADR:

```text
accepted now: shared target-fidelity invariant + program-gen first implementation path
not accepted now: automatic hard enforcement across every existing *-gen surface
future gates: per-surface acceptance before signature-gen/module-gen/future *-gen enforcement
```

## Implementation waves

### Wave 1 — pure schemas and validators

Implement local, deterministic contract helpers for:

```text
gen-target-contract-v1
gen-fitness-suite-v1
gen-generation-gate-preflight-v1
gen-traceability-v1
gen-fitness-results-v1
```

Scope limits:

- no provider calls;
- no candidate generation behavior changes;
- no shared Oracle/Postgres writes;
- no adapter materialization changes;
- no AK/governance mutation from DSPx code;
- no activation, promotion, or domain acceptance claims.

Validation:

- missing owner ref blocks target-bound contract validation;
- objective-only target-bound contract blocks;
- generated-from-docs contract without confirmation blocks;
- missing forbidden shortcuts block;
- missing source/provenance/language policy blocks;
- missing identity/hash binding blocks;
- adversarial suite without executable/checkable cases blocks;
- tutorial/local profile is allowed only when no owner refs, adapter materialization, authority refs, publication, or promotion/export/activation refs are present.

### Wave 2 — `program-gen` preflight commands

Add explicit or equivalent CLI/runtime paths:

```bash
dspx program-gen target-contract ...
dspx program-gen fitness-suite ...
dspx program-gen verify-generation-gate ...
```

Validation:

- target-bound generation blocks before candidate creation when gate fails;
- successful preflight writes non-authoritative `generation_gate_preflight.json`;
- tutorial/local path emits `tutorial_contract_profile_used=true` and `target_protocol_fidelity_claimed=false`;
- existing simple examples remain usable only through tutorial/local constraints.

### Wave 3 — traceability and fitness results after generation

Add post-generation sidecars:

```text
generation_traceability.json
generation_fitness_results.json
```

Validation:

- runnable/schema-valid candidate can still produce `fitness_failed`;
- missing traceability makes candidate `target_fidelity_unknown`, not promotion-ready;
- `fitness_passed` renders only as `eligible_for_downstream_evidence_review`;
- `fitness_passed` never renders as approved/promoted/activated/ready-for-domain-decision.

### Wave 4 — adapter and meta-adjudication integration

Integrate target-fidelity sidecars into:

- Obsidian/PDF review adapter path;
- `program-run` target-fitness readback;
- meta-adjudication target profile / jury requirements / evidence adjudication;
- adjudication behavior traces.

Validation:

- target-bound adapter materialization refuses missing or failed fitness unless writing failure-only/withheld packet;
- normal review queue is not populated from target-failed artifacts;
- generated-program adjudicator decisions distinguish runnable success from target-protocol success;
- invalid dogfood labels default to pending/quarantined or explicitly curated negative.

### Wave 5 — Obsidian/PDF failure fixture and regeneration

Use the current bad Obsidian/PDF output as a regression fixture.

Required failure checks:

- section/procedural heading inflated into Wiki create/draft;
- source language drift;
- skipped chapter/passage/synthesis gate;
- missing merge-before-create conservatism;
- canonical mutation or authority ambiguity.

Validation:

- historical bad outputs fail target-fidelity checks;
- regenerated candidate preserves transition/review boundaries;
- real-PDF runtime episodes are labeled as evidence, not activation;
- no canonical `Wiki/` / `Atlas/` mutation occurs.

### Wave 6 — per-surface widening

Only after `program-gen` gates are proven, evaluate other surfaces.

Each surface needs a per-surface acceptance note defining:

- target-bound triggers;
- minimal target contract;
- tutorial/local profile;
- failure fixtures;
- migration/readback behavior;
- validation commands.

## Rollout gates

A wave may move forward only when:

1. focused tests pass;
2. `just verify-fast` passes;
3. docs strict passes;
4. task-scope validation passes;
5. no shared Oracle/Postgres mutation occurs unless the wave explicitly authorizes a publication command;
6. no owner surface mutation occurs unless the owner/governance activation path explicitly authorizes it.

## Rollback strategy

### Wave 1 rollback

- Remove or disable schema helpers and tests.
- Existing `program-gen` behavior remains unchanged because no generation behavior has changed.

### Wave 2 rollback

- Disable target-bound generation gate integration behind a feature flag or command guard.
- Preserve preflight sidecars as local evidence.
- Do not reinterpret preflight success as promotion authority.

### Wave 3 rollback

- Treat existing generated candidates without sidecars as `target_fidelity_unknown`.
- Do not delete candidate artifacts.
- Do not promote missing sidecars to pass/fail by inference.

### Wave 4 rollback

- Disable adapter normal-queue materialization from target-bound candidates if fitness readback is unreliable.
- Keep failure-only packets as evidence.
- Do not mutate canonical owner surfaces.

### Wave 5 rollback

- Preserve bad historical outputs as failure fixtures.
- Revert regenerated candidate only if it was produced from an invalid target contract.
- Do not train GEPA from unlabeled or invalid dogfood.

## Readback expectations

Every implementation wave should expose a local readback summary that can distinguish:

```text
target_fidelity_unknown
generation_blocked
fitness_failed
fitness_passed_eligible_for_evidence_review
withheld_for_target_protocol_failure
```

Forbidden readback language:

```text
approved
promoted
activated
ready_for_domain_decision
canonical_acceptance
```

## Validation command baseline

Docs/planning slices:

```bash
node ~/ai-society/core/agent-scripts/scripts/docs-list.mjs --docs . --strict --full-list
git diff --check
just task-scope-check task_id=<AK-ID> mode=working-tree
```

Implementation slices:

```bash
uv run pytest tests/test_program_generation_contract.py tests/test_program_gen_pdf_transition.py tests/test_program_meta_adjudication.py -q
uv run ruff check packages/dspx-core/src/dspx/services tests/test_program_generation_contract.py
uv run ty check packages/dspx-core/src/dspx/services
just verify-fast
```

Full confidence / before merge or broad rollout:

```bash
just verify-full
```

## Done condition for first implementation phase

Wave 1 is done when DSPx has pure, tested local validators for the sidecar contracts and all negative tests listed in Wave 1 pass without changing candidate generation behavior.
