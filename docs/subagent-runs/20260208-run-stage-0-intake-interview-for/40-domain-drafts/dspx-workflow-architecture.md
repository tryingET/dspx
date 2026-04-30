---
summary: "Archived subagent-run artifact: DSPx workflow architecture draft (Stage 4)."
read_when:
  - "You are auditing the archived subagent-run workflow output."
  - "You need the recorded artifact for DSPx workflow architecture draft (Stage 4)."
type: "reference"
---

# DSPx workflow architecture draft (Stage 4)

## Context + constraints

### Container
- **Boundary:** Improve System4D workflow reliability/usability from intake recovery through prompt-factory handoff; no feature implementation in product code.
- **Constraint:** No destructive git/file ops; no DB mutation; canonical schema and gate rules stay authoritative.
- **Edge:** `.pi/extensions/4d-intake-router.ts` ↔ `.pi/prompts/*` ↔ `docs/subagent-runs/<RUN_ID>/*`.
- **Dependency:** Canonical DB input semantics (`db_path_or_none` = Stage-1 DB explorer input), canonical run-id semantics, existing RFC packet.
- **Anti-Goal:** Silent fallback from `mlflow.db` to `generated/sixe.db`.

### Compass
- **Driver:** Reduce recovery friction and ambiguity after intake timeout/restart.
- **Outcome:** Deterministic Stage transitions with less operator confusion and fewer manual corrections.
- **Trade-off:** Strong governance checks over convenience auto-healing.

### Engine
- **Trigger:** Interview completion, timeout recovery, kickoff gate evaluation.
- **State:** `interview_complete -> gate_eval -> stage_artifacts -> stage_status update`.
- **Invariant:** Explicit command `RUN_ID` remains authoritative.
- **Lifecycle:** Recovery loop may repeat until required fields + path checks pass.

### Fog
- **Assumption:** Existing router and prompts remain the control plane for workflow UX.
- **Risk:** Prefill and canonicalization logic drift between extension and docs.
- **Exception:** Canonical DB path missing locally must block DB-dependent stages.
- **Debt:** qmd index scope drift for subagent workflow docs.

---

## Option matrix

### Option A — Minimal strict gate (status quo+)

#### Container
- Keep existing stage gates and manifest updates.
- Add only wording clarifications in prompts/docs.

#### Compass
- Fastest path, lowest engineering change.

#### Engine
- No new state or persistence behavior.
- Manual user correction remains primary recovery mode.

#### Fog
- Ongoing risk: repeated confusion around DB-path meaning and interview answer precedence.

---

### Option B — Recovery-aware canonicalization + prefill + index health (recommended)

#### Container
- Add deterministic canonicalization module at intake/kickoff boundary:
  1) command `RUN_ID` authoritative,
  2) explicit command `DB_PATH_OR_NONE` authoritative for Stage-1,
  3) interview DB answer may annotate mismatch but never override explicit command path.
- Add interview response prefill from latest successful/partial response artifact.
- Add docs-retrieval drift check (`qmd` coverage check for `docs/subagent-runs/**`, `.pi/prompts/**`, optional `docs/rfc/**`).

#### Compass
- Best balance: better UX + preserved governance.

#### Engine
- New recovery sequence:
  1) parse command attrs,
  2) prefill from prior responses,
  3) run interview,
  4) reconcile canonical fields,
  5) enforce DB-path existence gate,
  6) emit kickoff or recovery command.

#### Fog
- Moderate implementation/test effort.
- Must pin precedence behavior in tests to avoid regressions.

---

### Option C — Full workflow state store + proactive consensus scaffolding

#### Container
- Introduce durable state graph across stages with assistant-generated consensus skeletons.

#### Compass
- Highest long-term automation potential.

#### Engine
- Requires new persisted state contracts and broader orchestration logic.

#### Fog
- Highest complexity and risk of overreach for current run scope.

---

## Recommended path

### Container
- Select **Option B**.
- Keep changes bounded to workflow UX/control-plane logic and docs/indexing behavior.

### Compass
- Why now: directly addresses observed failure modes in this run:
  - timeout recovery friction,
  - DB-path ambiguity,
  - docs index drift.

### Engine
- **Phased rollout**
  - **Phase 1 (rules hardening):** codify DB/run-id precedence in router prompts + tests.
  - **Phase 2 (recovery UX):** response prefill for interview recovery.
  - **Phase 3 (docs retrieval reliability):** qmd scope health check + fallback guidance.

### Fog
- If phase rollout stalls, ship Phase 1 first; keep Phase 2/3 as explicit follow-ups.

---

## Implementation sequencing (high-level only)

### Container
- Touchpoints:
  - `.pi/extensions/4d-intake-router.ts`
  - `.pi/prompts/interview-4d-intake.md`
  - `.pi/prompts/subagent-4d-kickoff.md`
  - workflow docs (`docs/SUBAGENT_WORKFLOW.md`, `docs/subagent-runs/schema/README.md`)

### Compass
- Sequence aims for deterministic behavior before UX niceties.

### Engine
1. Add/verify canonical precedence helpers + tests.
2. Add recovery prefill read path from latest `00-intake/interview-4d.responses.md`.
3. Add qmd coverage checker task + documented fallback path.
4. Update stage templates/checklists for explicit blocker handling.

### Fog
- Open dependency: maintainers must confirm desired qmd default scope before finalizing step 3.

---

## Risks / mitigations

### Container
- **Risk:** Conflicting precedence rules across prompts/extension.
- **Mitigation:** Single precedence table in schema README + mirrored tests.

### Compass
- **Risk:** Recovery UX improvements accidentally bypass strict gate behavior.
- **Mitigation:** Gate remains source of truth; prefill affects inputs only, never gate decisions.

### Engine
- **Risk:** DB blocker bypass via non-canonical fallback.
- **Mitigation:** explicit path-missing branch: block + recovery command; never auto-substitute `sixe.db`.

### Fog
- **Risk:** qmd drift persists.
- **Mitigation:** scheduled index health check and direct-file fallback policy.

---

## Non-destructive validation plan + acceptance checks

### Container
- Validate using read-only/documentation checks and existing stage artifacts.

### Compass
- Goal: prove deterministic governance behavior without mutating DB or destructive ops.

### Engine
- Acceptance checks:
  1. Interview timeout recovery prefills prior answers and preserves explicit `RUN_ID`.
  2. Explicit `DB_PATH_OR_NONE=mlflow.db` + missing file results in blocker (no silent substitution).
  3. Kickoff command not proposed while DB-path blocker unresolved.
  4. Manifest stage transitions remain monotonic and explicit.
  5. qmd miss on subagent docs triggers documented direct-file fallback note.

### Fog
- Residual unknown: exact top-3 issue/PR pinning still human-owned.

---

## Open questions for human owner

### Container
- Should qmd default collection include `docs/subagent-runs/**` and `.pi/prompts/**` permanently?

### Compass
- Is stricter blocking acceptable if it increases recovery loop frequency?

### Engine
- Preferred source for prefill precedence when both partial and complete responses exist?

### Fog
- Confirm whether Stage-5 should lock issue/PR priority across DSPx + MLflow + DSPy in one consensus artifact or three linked artifacts.

---

## Evidence
- `00-intake/brief.md`
- `00-intake/interview-4d.responses.md`
- `10-explorers/codebase.md`
- `10-explorers/docs.md`
- `10-explorers/database.md`
- `20-synthesis/technical-writer.md`
- `30-prompt-factory/system-prompts/dspx-architect-system.md`
- `30-prompt-factory/task-prompts/dspx-architect-task.md`
