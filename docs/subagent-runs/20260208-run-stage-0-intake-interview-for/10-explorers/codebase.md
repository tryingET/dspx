---
summary: "Archived subagent-run artifact: Codebase explorer report."
read_when:
  - "You are auditing the archived subagent-run workflow output."
  - "You need the recorded artifact for Codebase explorer report."
type: "reference"
---

# Codebase explorer report

## Findings summary
- System4D intake automation lives in `.pi/extensions/4d-intake-router.ts`.
  - key functions found: `parseInterviewIntakeArgs`, `discoverDbCandidates`, `buildKickoffArgs`, `system4dIntakeRouter`.
- Prompt-driven orchestration already exists:
  - intake command: `.pi/prompts/interview-4d-intake.md`
  - kickoff command: `.pi/prompts/subagent-4d-kickoff.md`
- Forge intake path exists and is explicit (`apps/forge/src/dspx_forge/cli.py::intake`).
- Core/app boundaries are healthy in structure:
  - core runtime/services in `packages/dspx-core/src/dspx/*`
  - app layer in `apps/forge/src/dspx_forge/*`
- Practical caveat: broad `cm` indexing at repo root currently pulls `.venv` heavily and emits cache metadata mismatch warning; scoped `cm` runs are reliable.

## Evidence index
- `cm stats packages --format ai` -> `files:80`, `syms:646`
- `cm stats apps --format ai` -> `files:15`, `syms:81`
- `cm stats .pi --format ai` -> `files:16`, `syms:63`
- `cm query system4dIntakeRouter .pi/extensions --format ai --context full`
- `cm query buildKickoffArgs .pi/extensions --format ai --context full`
- `cm query intake apps/forge/src --format ai --context full`
- files:
  - `.pi/extensions/4d-intake-router.ts`
  - `apps/forge/src/dspx_forge/cli.py`
  - `packages/dspx-core/src/dspx/services/*`

## 4 Dimensions
### Container
- Boundary:
  - intake/kickoff automation code and workflow scaffolding logic.
- Constraint:
  - canonical Stage-0 -> kickoff field contract enforced by router + prompts.
- Edge:
  - extension ↔ prompt assets ↔ run artifacts (`docs/subagent-runs/*`).
- Dependency:
  - interview responses must include required fields for kickoff synthesis.
- Anti-Goal:
  - no implicit architecture/implementation decisions inside intake code.

### Compass
- Driver:
  - reliable recovery and deterministic kickoff packet generation.
- Outcome:
  - auto-proposed commands with explicit gate checks.
- Trade-off:
  - convenience automation vs strict required-field completeness.

### Engine
- Trigger:
  - first non-command message, interview tool results, recovery statuses.
- State:
  - idle -> intent_captured -> interview_command_proposed -> interview_running -> recovery|kickoff_proposed.
- Invariant:
  - incomplete interview => recovery command, not kickoff command.
- Lifecycle:
  - parse -> prefill intake -> process interview result -> prefill recovery/kickoff.

### Fog
- Assumption:
  - user intent text contains parseable structured fields.
- Risk:
  - root-level indexing noise can hide relevant symbols.
- Exception:
  - interview timeout/cancel/incomplete-required-fields statuses.
- Debt:
  - no native “prefill from prior answers” pipeline yet in router/prompt handoff.

## Capabilities (existing/missing)
- Existing:
  - robust intake arg parsing and recovery command generation.
  - kickoff arg synthesis from interview response IDs.
  - explicit gate-aware behavior in extension flow.
- Missing:
  - direct prefill of previously submitted answers into follow-up interview JSON.
  - explicit symbol indexing exclusions for `.venv` in default cm workflow scripts.

## Open questions
- Should router persist last successful interview responses and pre-seed next recovery form via `recommended` fields?
- Should kickoff arg DB path prefer interview `db_path_confirmation` over initial `DB_PATH_OR_NONE` input automatically?
