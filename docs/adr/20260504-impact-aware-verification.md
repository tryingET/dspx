---
summary: "Adopt deterministic impact-aware verification planning as a local development validation tier while preserving verify-full as the broad confidence gate."
read_when:
  - "You are changing DSPx validation, CI, Justfile verification targets, or developer workflow."
  - "You need to know when impact-aware verification may replace manual targeted checks but not verify-full."
  - "You are implementing or reviewing scripts/ci/verify_changed.py or verification-impact.yml."
system4d:
  container:
    boundary: "DSPx local validation workflow and CI command surface."
    edges:
      - "docs/rfc/RFC-DSPX-VERIFY-20260504-impact-aware-verification.md"
      - "docs/project/developer_workflow.md"
      - "Justfile"
      - "scripts/ci/verify-full.sh"
  compass:
    driver: "Reduce local validation latency without creating false confidence or replacing the full gate."
    outcome: "A deterministic plan-first impact-aware verification tier with conservative fail-wide behavior."
  engine:
    invariants:
      - "verify-full remains the broad final confidence gate."
      - "impact-aware verification is table-driven and deterministic, not AI-selected."
      - "unknown, CI/dependency, broad shared, or cross-domain changes fail wide."
      - "planning never mutates AK, governance, Oracle, generated artifacts, or external authority."
  fog:
    risks:
      - "Partial checks may be mistaken for full regression confidence."
      - "The impact map can become stale as service seams evolve."
      - "The planner can become too broad to help or too narrow to be safe."
---

# ADR 20260504 — Impact-Aware Verification

## Status

- accepted
- date: 2026-05-04
- owner: DSPx maintainers
- reviewers: DSPx core reviewers, CI/runtime maintainers
- AK decision: `#26 Adopt deterministic impact-aware verification planning for DSPx`
- related_docs:
  - `docs/rfc/RFC-DSPX-VERIFY-20260504-impact-aware-verification.md`
  - `docs/project/developer_workflow.md`
  - `Justfile`
  - `scripts/ci/verify-full.sh`

## Executive summary

DSPx will add a deterministic, impact-aware local verification tier that selects checks from changed files through a checked-in impact map, prints the plan before execution, and fails wide on uncertainty. This improves local iteration speed without replacing `just verify-full`, which remains the broad final confidence gate for risky changes, release/merge confidence, and unmapped surfaces.

## Context

DSPx has a strong validation posture, but the current command surface is coarse:

- `just verify-fast` protects workflow, governance, task-scope, and pre-commit contracts.
- `just verify-runtime` protects replay/runtime/boundary/docs invariants.
- `just verify-tests` runs typecheck plus the full pytest suite.
- `just verify-full` runs the full confidence path and can exceed interactive local/tool time budgets.

Recent program-generation and refinement slices needed repeatable targeted validation over narrow surfaces, while full verification took long enough to be impractical for every iteration. Humans and agents can choose targeted tests manually, but that is not auditable, stable, or safe enough to become the normal workflow.

## Problem statement

DSPx needs a first-class middle validation tier between manual targeted checks and `just verify-full`.

The tier must answer:

> Given this concrete set of changed files, what is the smallest truthful verification plan that should run now, and when must the change escalate to broad/full verification?

Without such a tier, local development alternates between slow full validation and ad-hoc hand-picked checks that can miss important adjacent consumers.

## Decision drivers

- Preserve `verify-full` as the broad integration confidence gate.
- Make local validation faster for narrow, high-frequency change surfaces.
- Replace ad-hoc targeted-test selection with an auditable deterministic plan.
- Fail closed for unknown, cross-cutting, dependency, CI, or safety-critical changes.
- Keep the planner small enough to maintain; avoid turning it into a second CI system.
- Avoid any runtime authority mutation or hidden automation in validation planning.

## Decision

Adopt a deterministic impact-aware verification planner for DSPx with two user-facing targets:

```bash
just verify-impact-plan
just verify-impact
```

The planner will inspect changed files, classify them through a checked-in impact map, print a stable verification plan, and either execute the selected commands or require broad/full verification when the change is not safely mapped.

`just verify-full` remains unchanged and remains the final broad confidence gate.

### Scope

In scope:

- `scripts/ci/verify_changed.py` or equivalent deterministic planner.
- `scripts/ci/verification-impact.yml` or equivalent checked-in impact map.
- `just verify-impact-plan` and `just verify-impact` targets.
- Planner tests that validate mapping, escalation, command ordering, and plan-only behavior.
- Developer workflow documentation describing when this tier is appropriate.

Out of scope:

- Replacing `just verify-full`.
- AI-selected or embedding-selected tests.
- Runtime coverage inference beyond explicit checked-in mapping.
- Mutating AK, governance projections, Oracle indexes, generated artifacts, or external authority.
- Automatically editing task scopes or work-item projections.

### Ownership / seam / policy notes

- Owner: DSPx maintainers.
- Seam: local development and CI preflight command selection.
- Allowed pattern: deterministic mapping from paths to existing commands/tests.
- Prohibited pattern: silent skipping, semantic guessing, or claiming full confidence from a partial plan.

## Alternatives considered

### Option A — Keep only manual targeted checks plus verify-full

Description: continue current practice: humans or agents pick targeted tests manually, then run `verify-full` when time permits.

Pros:

- No new tooling.
- Maintains the current full gate unchanged.

Cons:

- Targeted validation remains inconsistent and hard to review.
- New contributors and agents cannot know the expected adjacent checks reliably.
- Repeated long-running full validation remains a local iteration tax.

Why not chosen: this preserves the current pain and leaves too much validation selection in memory.

### Option B — Deterministic impact-aware planner

Description: add a table-driven planner that maps changed files to checks, prints a plan, executes it on request, and escalates to wide verification on uncertainty.

Pros:

- Makes targeted validation reproducible and inspectable.
- Keeps full verification intact.
- Captures repeated maintainer knowledge as a reviewable artifact.
- Can start small and expand safely.

Cons:

- Requires maintaining an impact map.
- Partial checks can be misunderstood unless the output and docs are explicit.
- Too-conservative defaults can reduce usefulness.

Why chosen: this balances local speed with safety and makes the tradeoff explicit.

### Option C — Dynamic dependency/coverage-based test selection

Description: infer test impact from import graphs, coverage data, or runtime traces.

Pros:

- Potentially more precise in the long term.
- Could reduce manual map maintenance.

Cons:

- More complex and less predictable.
- Coverage data can be stale or incomplete.
- Import graphs do not capture generated artifacts, docs contracts, governance projections, or boundary invariants well.

Why not chosen: this is too much mechanism for the current need and can create false confidence.

### Option D — Make full verification faster instead

Description: invest only in parallelism, caching, or test-suite performance improvements.

Pros:

- Improves the broad gate for everyone.
- Reduces need for selective validation.

Cons:

- Does not solve the workflow question of what to run for a narrow local change.
- May require larger test/runtime refactors.
- Even a faster full suite may still be too slow for tight iteration.

Why not chosen as the only path: performance work is valuable but complementary. DSPx still needs an explicit middle tier.

## Consequences

### Positive

- Local validation becomes faster and more predictable.
- Reviewers can inspect why a given set of checks was selected.
- Agents can follow repo policy without inventing test selection each session.
- High-risk changes continue to escalate to broad validation.

### Costs

- Maintainers must keep the impact map current.
- The planner and its tests become part of the workflow contract.
- Some changes will still be escalated broadly, especially early in rollout.

### Risks

- Developers may over-trust `verify-impact` as equivalent to `verify-full`.
- The impact map may become stale as files or tests move.
- The planner may grow into an opaque mini-CI system.

### Mitigations

- Label the output clearly: bounded/expanded/wide, full verification required or not.
- Fail wide for unknown files and high-risk categories.
- Keep the map small at first and require tests for map expansion.
- Keep `verify-full` unchanged and documented as the final confidence gate.

## Migration / rollout

### Phase 1 — Plan-only mapper

- Add a planner with `--plan-only`.
- Add a small impact map for docs, governance, and common program-gen/refinement seams.
- Add planner unit tests.
- Add `just verify-impact-plan`.

Implementation task: `AK-2147` begins this rollout by adding the deterministic planner, checked-in impact map, Justfile targets, planner tests, and workflow documentation without changing `verify-full`.

### Phase 2 — Execution mode

- Add `--run`.
- Add `just verify-impact`.
- Execute selected existing commands in deterministic order.
- Require explicit wide/full allowance for wide-risk plans.

### Phase 3 — Workflow adoption

- Update `docs/project/developer_workflow.md`.
- Recommend `verify-impact-plan` before local validation and `verify-impact` during iteration.
- Keep `verify-full` for risky changes, release/merge confidence, and unmapped surfaces.

### Rollback / escape hatch

- Remove or stop using `verify-impact*` targets.
- Continue using existing `verify-fast`, `verify-runtime`, `verify-tests`, and `verify-full` commands.
- Because the planner only selects existing checks and does not mutate runtime authority, rollback is low-risk.

## Architecture fitness functions / validation

Required invariants:

- `verify-full` behavior remains unchanged by the first planner slice.
- `verify-impact-plan` never executes verification commands.
- Unknown files produce a wide-risk plan.
- CI/dependency changes require broad/full verification.
- Mapped service files select the expected adjacent tests.
- Governance/task-scope changes select governance/task-scope checks.
- Plan output is deterministic and schema-versioned.

Implementation checks:

```bash
uv run --no-sync -m pytest -q tests/test_verify_changed.py
uvx ruff check scripts/ci/verify_changed.py tests/test_verify_changed.py
uvx ty check packages/dspx-core/src
node ~/ai-society/core/agent-scripts/scripts/docs-list.mjs --docs . --strict
just task-scope-check task_id=<AK-ID> mode=working-tree
```

If the implementation changes `Justfile`, `scripts/ci/**`, or workflow-contract checks, also run:

```bash
just verify-fast
```

Attempt `just verify-full` when tool time allows or when the impact plan reports wide risk.

## Follow-up decisions / open questions

- Should `verify-impact` default to working-tree changes or staged changes when both exist?
- Should wide plans fail by default or run the broad commands when an environment flag is set?
- Should command results be printed only or also written as a JSON receipt under `generated/ci/`?
- Should CI use `verify-impact` as a fast advisory preflight while keeping full CI required?
- What exact file-count and impact-group thresholds should trigger wide risk?

## Supersession

- supersedes: none
- superseded_by: none
