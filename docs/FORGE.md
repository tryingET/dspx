---
summary: "DSPx Forge: intent→clarify→canonicalize→GitLab issues→artifact packs (spec + rollout plan)."
read_when:
  - "You want DSPx to turn a freeform prompt into GitLab issues and later into signatures/modules/optimizations."
  - "You are implementing the Forge pipeline, its schemas, or GitLab API integration."
  - "You are changing the capability/policy model or adding packs/plugins."
---

# DSPx Forge — Spec (Intent → Issues → Artifacts)

Forge turns one freeform prompt into:
- a durable WorkOrder (typed, reproducible),
- a deterministic multi-project plan,
- idempotent GitLab issues (safe, resumable),
- later: artifact packs + evidence packs (signatures/modules/programs/GEPA + tests/evals).

---

# Glossary (v0)

- **WorkOrder**: the “narrow waist” IR that captures intent, constraints, routing, requirements, and acceptance tests in a reproducible way.
- **IssueSpec**: the compiled backlog unit (per project) with stable IDs, a managed description block, and a fingerprint for idempotency.
- **ForgeManifest**: the resumability/audit record mapping IssueSpecs to GitLab `iid`s and recording decisions/actions.
- **Routing**: the decision of which ai-society project(s) own the WorkOrder (auto with override in v0).
- **Overlap review**: a read-only step that finds likely duplicates and forces an explicit resolution before apply.
- **Program**: a cross-project grouping convention (currently assumed to be a label); semantics intentionally deferred.
- **Capability**: a policy-gated “power” (implemented/configured/permitted) required for a step (e.g., `cap_network.mutate`).
- **Pack** (later): a recipe that turns a WorkOrder into an ArtifactPack (signatures/modules/programs/config/tests).
- **EvidencePack** (later): tests/evals/goldens/perf reports that make “done” measurable.

# v0 Contract (normative)

Key words MUST / SHOULD / MAY are used in the RFC-2119 sense.

- Forge MUST sanitize/redact input before it is written to GitLab, logs, MLflow, or any artifact file.
- Forge MUST compute a stable `workorder_fingerprint` from `(sanitized_input + answers + routing overrides + constraints + resource refs)`.
- Forge MUST be offline/deterministic by default; it MUST NOT mutate network unless explicitly allowed by policy and CLI flags.
- Forge MUST be resumable: it MUST write `manifest.json` before any GitLab POST/PUT and it MUST re-run idempotently.
- Forge MUST preserve human edits in GitLab issues by updating only a bounded managed block.
- Forge MUST support multi-project routing via a project map and MUST constrain blast radius via an explicit allowlist.
- Forge SHOULD run overlap review before apply and MUST record the chosen resolution in the manifest.
- Forge MAY support closing duplicates, but only via a separate explicitly-gated command.
- v0 “done” = correct backlog + manifests; artifact generation is not required for v0 success.

Locked v0 decisions:
- Routing authority: auto-route by default (overrideable).
- Cross-project linking: GitLab issue links API when available, else markdown cross-references.
- Overlap detection: heuristic-only (no embeddings yet).
- UX: core engine is front-end agnostic (CLI now; TUI later via the same event protocol).

v0 explicitly out of scope (to prevent creep):
- Generating code/artifacts in other repos (packs come later; v0 is backlog + manifests).
- Embeddings/semantic search for routing or overlaps.
- Auto-closing/auto-transitioning issues as part of apply (close-duplicates is separate and gated).
- GitLab epics/portfolio features as primary objects (issues only in v0).
- Full ontology DB integration (rocs integration is a later upgrade; v0 persists ontology-lite JSON/YAML).

---

# v0 Design (implementation-ready)

## Pipeline (narrow waist)

1) sanitize → `sanitized_input` + `redaction_report`
2) clarify (multi-choice, branching) → `answers`
3) canonicalize (template-driven) → normalized requirements + acceptance tests + issue breakdown
4) route (auto + override) → target projects + reasons
5) plan → steps + capabilities `{implemented, configured, permitted}` + gaps
6) overlaps (read-only) → candidate matches + user resolutions
7) apply (mutating) → create/update/link issues per project, idempotently
8) (optional) close-duplicates (mutating) → only for marked duplicates

Network rules:
- only steps 6+ do `cap_network.read`
- only steps 7+ do `cap_network.mutate`

Filesystem rules:
- writes are constrained to `generated/forge/<workorder_id>/...` by default

## Subsystems
- `forge.intake`: sanitize + clarifier + canonicalization → WorkOrder
- `forge.clarifier`: decision graph engine (patch-based, reversible)
- `forge.routing`: route proposal + override + multi-project split strategy
- `forge.plan`: capabilities inventory + steps + gaps → plan.json
- `forge.overlaps`: heuristic overlap detection + interactive resolution → overlaps.json
- `forge.issues`: GitLab client + apply engine + manifest updates
- `forge.ux`: event protocol (UI adapters: CLI/TUI/JSON)
- later: `forge.packs`, `forge.evidence`

## Identity, determinism, idempotency

Two IDs:
- `workorder_fingerprint` (stable): `sha256:<hex>`
- `run_id` (ephemeral): `run_<ts>_<rand>`

Naming:
- `workorder_id`: `wo_<slug>_<fingerprint_prefix>` (stable; no timestamps)
- IssueSpecs are keyed by fully-qualified ID: `<project_key>/<issue_local_id>`

Idempotency hinges on:
- stable IssueSpec fingerprint
- manifest fast path (update-by-iid)
- bounded managed block updates (do not clobber humans)

## On-disk layout (generated artifacts)

Forge writes only under `generated/forge/<workorder_id>/` by default:
- `workorder.yaml`
- `system_definition_card.md` (4D discipline)
- `plan.json`
- `issues/<project_key>/<issue_local_id>.yaml`
- `overlaps.json` (candidates + decisions)
- `manifest.json` (GitLab iid map + actions)
- `events.jsonl` (optional; UX protocol replay/debug)

## Schemas (v0)

### WorkOrder (YAML)
```yaml
work_order:
  schema_version: 0
  fingerprint: "sha256:..."
  id: "wo_build_cli_ab12cd34"
  run_id: "run_20260111_203500_k3j2"
  title: "Build <thing>"

  raw_input: "<local-only>"
  sanitized_input: "<used everywhere downstream>"
  redaction_report:
    detected: false
    notes: []

  intent:
    deliverable: "python_cli|library|server|workflow|optimizer|integration|eval_harness"
    evidence_level: "smoke|unit|golden|eval|perf"
    risk_profile: "safe_default|power_user"
    offline_default: true

  routing:
    mode: "auto|suggest|manual"
    strategy: "single_primary|primary_with_satellites|multi_primary"
    primary_project: "core|holdingco|financeco|healthco|houseco|teachingco|softwareco"
    secondary_projects: ["core"]
    reasoning: ["..."]
    program:
      id: "prog_optional"
      title: "Optional cross-project program"
      label: "program:<name>"

  constraints:
    - id: "c_offline"
      text: "Offline/deterministic by default"
    - id: "c_no_secrets"
      text: "No secrets in logs/issues/artifacts"
    - id: "c_policy"
      text: "No network mutations without explicit allow"

  requirements:
    - id: "r1"
      text: "..."
      rationale: "..."
      priority: "must|should|could"

  acceptance_tests:
    - id: "a1"
      given: "..."
      when: "..."
      then: "..."

  resources:
    - id: "res_repo"
      kind: "repo"
      ref: "."

  outputs:
    out_dir: "generated/forge/<workorder_id>"
```

### Plan (JSON)
```json
{
  "schema_version": 0,
  "workorder_id": "wo_...",
  "workorder_fingerprint": "sha256:...",
  "capabilities": {
    "needed": ["cap_network.read", "cap_forge.issues.write"],
    "status": {
      "cap_network.read": {"implemented": true, "configured": true, "permitted": true},
      "cap_forge.issues.write": {"implemented": true, "configured": true, "permitted": false}
    },
    "gaps": ["cap_forge.issues.write"]
  },
  "steps": [
    {"id":"s1","kind":"emit_issue_specs","requires":[]},
    {"id":"s2","kind":"overlap_review","requires":["cap_network.read"]},
    {"id":"s3","kind":"gitlab_apply","requires":["cap_network.mutate"]}
  ]
}
```

### IssueSpec (YAML)
Notes:
- `project_key` selects the GitLab project from the routing map.
- `depends_on` entries are fully-qualified as `<project_key>/<issue_local_id>`.
- The managed block stores the 4D card as a stable `workorder://<workorder_id>/system_definition_card.md` reference so issue identity does not drift with the local output root or current working directory.

```yaml
issue_spec:
  schema_version: 0
  local_id: "iss_gitlab_client"
  project_key: "core"
  title: "Forge: add GitLab issue client (idempotent)"
  description_md: |
    <!-- DSPX_MANAGED_START -->
    Context...
    - WorkOrder: wo_build_cli_ab12cd34
    - Fingerprint: sha256:...
    - 4D: workorder://wo_build_cli_ab12cd34/system_definition_card.md
    <!-- DSPX_FINGERPRINT: sha256:... -->
    <!-- DSPX_MANAGED_END -->

    Notes for humans (Forge will not overwrite this section):
    - ...
  labels:
    - "dspx-forge"
    - "dspx-wo:ab12cd34"
    - "dspx-iss:iss_gitlab_client"
    - "program:optional"
    - "capability:network.mutate"
  depends_on:
    - "core/iss_workorder_schema"
  fingerprint: "sha256:..."
```

### ForgeManifest (JSON)
Written before any GitLab POST/PUT. Updated after applies.
```json
{
  "schema_version": 0,
  "workorder_id": "wo_...",
  "workorder_fingerprint": "sha256:...",
  "created_at": "2026-01-11T20:35:00Z",
  "run_id": "run_20260111_203500_k3j2",
  "gitlab": {
    "base_url": "https://gitlab.example.com",
    "projects": {
      "core": {"project_id": 101},
      "teachingco": {"project_id": 106}
    }
  },
  "issue_map": {
    "core/iss_gitlab_client": {"iid": 42, "web_url": "...", "fingerprint": "sha256:..."}
  },
  "decisions": {
    "overlaps": [],
    "routing_overrides": []
  }
}
```

## Sanitization/redaction (mandatory)
- `raw_input` is stored locally only.
- `sanitized_input` is used for all downstream processing and anything that may leave the machine (GitLab).
- If a likely secret is detected (API keys, bearer tokens, `op://...`, long high-entropy strings), Forge asks:
  1) redact and continue (default)
  2) abort
  3) mark as “not a secret” and continue (explicit confirmation)

## Clarifier (multiple-choice, branching)
`Question` is a decision graph: `{id, prompt, choices[{id,label,explanation,effects,next}]}`.

Constraints:
- question budget: default N=7; after that, emit “assumptions taken”
- top-3 first; `more` reveals additional options
- reversible patches; `back` removes last patch
- emits events (UI-agnostic)

Required early questions (v0):
- Q-1 Routing: auto vs manual vs split into multiple WorkOrders
- Q0 Deliverable: CLI/library/server/workflow/optimizer/integration/eval-harness
- Q1 Evidence: smoke/unit/golden/eval/perf
- Q2 Risk profile: safe-default vs power-user

## Canonicalization (template-driven)
Canonicalization is deterministic by default (works with `DSPX_PROVIDER=stub`).

It always emits:
- normalized requirements
- acceptance tests (Given/When/Then)
- issue breakdown (IssueSpecs)
- routing decision + reasons
- `system_definition_card.md` (4D discipline)

LLM-assisted rewriting is a separate opt-in capability (later): `cap_forge.llm_assist`.

## Routing (ai-society multi-project)

Inputs:
- sanitized input text
- intent selections
- resource hints (paths, URLs, domain keywords)

Outputs:
- primary project
- secondary projects (optional)
- strategy
- reasoning list

Heuristic algorithm (v0):
1) if manual: take it
2) if prompt references known repo paths/names: route to that
3) otherwise score by keyword/resource hints
4) pick top-1; show top-3 as override candidates

Future (v1+): ontology-assisted routing using ai-society core (rocs).

## Overlaps (don’t create duplicates)

Heuristics (v0):
- same `dspx-iss:<local_id>` label (strong)
- same fingerprint marker (strong)
- title similarity (token overlap)
- keyword overlap with requirement text
- same program label (weak)

Resolutions:
1) keep new issue
2) link to existing
3) merge into existing (update existing managed block; cancel new)
4) cancel

## Capability model (implemented/configured/permitted)

Capabilities are policy-gated “powers”.

Core:
- `cap_filesystem.read`, `cap_filesystem.write`
- `cap_network.read`, `cap_network.mutate`
- `cap_code.exec` (dangerous; off by default)

Forge:
- `cap_forge.intake`, `cap_forge.plan`, `cap_forge.route`, `cap_forge.overlaps`
- `cap_forge.issues.read`, `cap_forge.issues.write` (requires `cap_network.mutate`)

Service caps (later):
- `cap_artifact.signature`, `cap_artifact.module`, `cap_artifact.program`
- `cap_optimize.gepa`, `cap_eval.run`

Plan output must include per-capability `{implemented, configured, permitted}` to explain blockers precisely.

## GitLab integration (self-hosted, multi-project)

Configuration:
- `DSPX_GITLAB_BASE_URL`
- `DSPX_GITLAB_TOKEN` (env only)
- routing map:
  - `DSPX_GITLAB_PROJECT_MAP_JSON` or `DSPX_GITLAB_PROJECT_MAP_FILE`
- blast radius:
  - `DSPX_GITLAB_ALLOWED_PROJECT_KEYS`
  - `DSPX_GITLAB_ALLOWED_HOSTS` (defaults to host in base url)
- optional:
  - `DSPX_GITLAB_DEFAULT_LABELS`
  - `DSPX_GITLAB_PROGRAM_LABEL_TEMPLATE` (default `program:{name}`)

Example project map JSON (ai-society keys):
```json
{"core":{"id":101},"holdingco":{"id":102},"financeco":{"id":103},"healthco":{"id":104},"houseco":{"id":105},"teachingco":{"id":106},"softwareco":{"id":107}}
```

Policy/safety:
- default apply is dry-run; `--apply` + `--allow-network-mutate` required
- all requests must stay within allowed hosts
- never log token; redact headers (use `dspx.redaction`)

Idempotency:
- fingerprint excludes labels/milestones/assignees by default (metadata shouldn’t churn fingerprints)
- embed markers:
  - `DSPX_MANAGED_START/END`
  - `DSPX_FINGERPRINT`
- apply order:
  1) manifest fast path: update by iid
  2) recovery: list/search by labels + marker
  3) create if missing
  4) if multiple matches: stop or require interactive resolution (record warning)

Managed-block update rules:
- replace only between managed markers
- if missing markers: prepend new managed block and record warning

Retries/timeouts:
- 401/403: fail fast; no retry
- 404 project: fail fast; treat as routing-map misconfig
- 429: honor `Retry-After`; bounded backoff; surface progress
- do not blindly retry POST/PUT without recording attempt boundaries in manifest

Endpoints (GitLab v4):
- `GET /api/v4/projects/:id/issues`
- `POST /api/v4/projects/:id/issues`
- `PUT /api/v4/projects/:id/issues/:issue_iid`
- links (preferred): `POST /api/v4/projects/:id/issues/:issue_iid/links`

Closing duplicates:
- separate command only: `forge issues close-duplicates`
- requires `--allow-network-mutate` and `--allow-issue-close`
- default interactive confirm per issue

## UX protocol (front-end agnostic)

Forge core emits structured events; UIs render them.

Examples:
- `QuestionAsked`, `ChoicesPresented`, `ChoiceSelected`, `WorkOrderPatched`
- `RouteProposed`, `OverlapCandidates`
- `ApplyPreview`, `ApplyResult`

Frontends:
- CLI interactive (now): numbered menus
- TUI (later): consumes same events
- JSON mode (later): automation + playback

## CLI surface (v0)
- `just forge intake "<prompt>"` (or `dspx-forge intake ...`; interactive clarifier unless `--non-interactive`)
- `just forge plan workorder.yaml`
- `just forge route workorder.yaml` (show top-3 + override)
- `just forge overlaps workorder.yaml`
- `just forge issues apply workorder.yaml [--dry-run|--apply] [--project <key>] [--program <id>]`
- `just forge issues close-duplicates workorder.yaml` (explicitly gated)

Note: core CLI (`dspx`) no longer hosts `forge` subcommands on this branch.

## Acceptance tests (MVP)
- intake writes WorkOrder with intent + routing fields + fingerprint
- plan is deterministic: same WorkOrder → same IssueSpecs fingerprints
- dry-run never POST/PUT; still writes manifest
- apply twice is idempotent (no duplicate issues)
- multi-project: creates/updates only within allowed project keys
- managed-block update preserves human edits outside the block
- overlap “merge” cancels new issue and updates existing managed block with provenance
- GitLab 401/429 produce clear errors; token never printed

---

# Roadmap & Appendices (non-normative)

## Programs (cross-project containers) — placeholder
Current understanding (2026-01-11): “programs” is likely a GitLab label convention.

Open questions:
- exact label format (examples): `program:<name>` vs `prog/<name>` vs something else?
- does “program” imply primary project, milestone, or a “header issue” pattern?

## Threat model & safety checklist (v0)
- accidental multi-project spam → project allowlist + route override + dry-run default
- secret leakage → sanitize stage + redaction report + explicit confirmation
- silent network mutation → policy gates + explicit flags
- overwriting humans → managed block only
- duplicates → stable fingerprints + manifest fast path + overlap review

## Failure modes (expected behavior)
- missing GitLab config: plan still works; overlaps/apply fail fast with `configured=false`
- 401/403: fail fast; no retries; never print token
- 404 project: stop before mutation; report misconfigured project map
- 429: honor retry-after; bounded backoff; resumable
- partial apply/crash: rerun uses manifest; no duplicates
- missing markers in an edited issue: append managed block; record warning

## Evolution roadmap (stones not yet turned)
- Ontology-assisted routing + overlap detection via ai-society core (rocs)
- Embeddings-based overlap search (opt-in)
- Packs: artifact generation + evidence packs (unit/golden/eval/perf)
- TUI frontend + JSON automation mode
