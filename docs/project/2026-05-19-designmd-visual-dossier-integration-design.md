---
summary: "Review-only UI/API contract for DesignMD visual-source dossier DSPx packet export and evidence import."
read_when:
  - "Implementing DesignMD UI/API affordances for DSPx visual-dossier requirements or evidence."
  - "Reviewing authority boundaries for DSPx visual-dossier evidence in DesignMD."
type: "design-contract"
system4d:
  container: "DesignMD-facing UI/API contract for DSPx visual-dossier packet export and imported evidence viewing."
  compass: "Make DSPx evidence usable in DesignMD without turning it into accepted design authority or hidden execution."
  engine: "Export requirements packet -> operator-run DSPx -> import/view evidence -> human review context only."
  fog: "Risk of UI copy, state names, or buttons implying DSPx evidence accepts dossier guidance or mutates DESIGN.md."
---

# DesignMD DSPx visual-dossier review-only UI/API contract

Task: `AK-3171`
Direction: `SF-DESIGNMD-VDOS` / `IW-DV-03-DESIGN`
Date: 2026-05-19

## Decision

DesignMD should implement a review-only UI/API contract in two product slices:

1. **Packet export UX**: expose the existing `designmd.dspx-visual-dossier-requirements.v1` packet in the visual-source dossier UI with copy/download/runbook affordances.
2. **Imported evidence viewer**: accept and display operator-supplied DSPx JSON artifacts as review evidence only.

DesignMD must not launch DSPx prepare/program-gen in the first implementation wave. Full orchestration remains explicitly deferred to `IW-DV-07-IMPLEMENT-ORCHESTRATION`.

## Non-authority invariant

Every UI surface, API response, stored record, and materialized dossier reference must preserve this invariant:

```text
DSPx visual-dossier artifacts are proposal_context or review_evidence only. They do not mutate DESIGN.md, approve docs/design, accept dossier guidance, create AK/society authority, or activate generated programs for production use.
```

## First implementation slice: packet export UX

### UI placement

Add a DSPx handoff section to each dossier card / dossier preview action area in the existing Visual Sources workflow.

Allowed labels:

- `Export DSPx requirements`
- `Copy DSPx CLI commands`
- `Download requirements JSON`
- `DSPx review evidence only`

Disallowed labels in this slice:

- `Run DSPx`
- `Generate analyzer`
- `Accept DSPx guidance`
- `Approve dossier`
- `Apply to DESIGN.md`

### API use

Use the existing endpoint:

```http
GET /api/visual-sources/:sourceId/dspx-requirements/:dossierId
```

Expected response shape:

```json
{
  "dspxRequirements": {
    "schemaVersion": "designmd.dspx-visual-dossier-requirements.v1"
  }
}
```

The UI should render a compact summary:

- packet schema version;
- project id;
- source id;
- analysis run id;
- dossier draft id;
- source index hash / `DESIGN.md` hash freshness status;
- role coverage count and names;
- accepted output posture;
- forbidden claims;
- fail-closed blockers.

### Copy/download behavior

The UI should provide:

1. copy full packet JSON;
2. download full packet JSON with a deterministic filename such as:

```text
designmd-dspx-visual-dossier-requirements-<sourceId>-<dossierId>.json
```

3. copy command snippets for operator-run DSPx:

```bash
dspx program-gen prepare \
  --profile designmd-visual-dossier \
  --requirements <requirements.json> \
  --outdir <gate-dir> \
  --intent-out <intent.yaml> \
  --json

# Optional follow-on after generation_allowed=true:
dspx program-gen \
  --intent <intent.yaml> \
  --outdir <program-dir> \
  --generation-gate-preflight <gate-dir>/generation_gate_preflight.json \
  --print-manifest
```

The UI must state these commands are copied for operator execution outside DesignMD. The browser/server does not execute them in this slice.

## Second implementation slice: imported evidence viewer

### Accepted artifact families

The first imported-evidence viewer should accept these DSPx JSON artifacts:

- `generation_gate_preflight.json` with schema `gen-generation-gate-preflight-v1`;
- `generation_traceability.json` with schema `gen-traceability-v1`;
- `generation_fitness_results.json` with schema `gen-fitness-results-v1`.

Optional later artifacts:

- `generation_target_contract.json`;
- `generation_fitness_suite.json`;
- `manifest.json` from the generated candidate assembly.

### Evidence validation contract

Fail closed when:

- schema version is absent or unsupported;
- JSON is malformed;
- `non_authority` fields are missing or claim activation/promotion/governance/external-mutation authority;
- `effect` claims `canonical_target_mutated`, `ak_mutated`, `governance_mutated`, or shared Oracle mutation;
- evidence cannot be associated with the selected source/dossier by available hashes or operator declaration.

Display as warning, not acceptance, when:

- `generation_allowed` is false;
- `fitness_results.status` is not `fitness_passed`;
- traceability has uncovered requirements;
- identity hashes cannot be fully matched but the operator explicitly imports for review context.

### Evidence summary display

Render a compact status panel:

| Field | Display |
|---|---|
| Generation gate | `generation_allowed` or blocked with fail-closed reasons |
| Traceability | covered / uncovered requirement counts |
| Fitness | `fitness_passed`, `fitness_failed`, or `target_fidelity_unknown` |
| Rendered state | e.g. `eligible_for_downstream_evidence_review` |
| Authority | always `review_evidence_only` |

Raw JSON should be expandable and copyable, but summarized status should be the default UI.

### Storage and redaction

Imported evidence should be stored as runtime/private visual-source evidence, not committed design truth.

Recommended private runtime layout in DesignMD:

```text
data/projects/<project>/visual-sources/<sourceId>/dspx-evidence/<evidenceId>/
  manifest.json
  generation_gate_preflight.json
  generation_traceability.json
  generation_fitness_results.json
```

Public dossier docs may cite a redacted evidence summary only. They must not include absolute local paths or generated candidate source paths unless redacted.

### Review record contract

Imported evidence should create or support a visual review record with target kind `dossier` and a review-only decision/status. If DesignMD's current review enum cannot represent this without implying acceptance, add a new decision such as:

```text
dspx_evidence_attached
```

or:

```text
proposal_context_available
```

The review record must include:

- source id;
- dossier id;
- imported evidence id(s);
- summary status;
- explicit non-authority statement;
- actor and timestamp;
- blockers/warnings if generation or fitness failed.

This review record must not transition `DossierDraft.state` to `reviewed_accepted` and must not set authority posture to `reviewed_dossier_guidance`.

## Orchestration deferral

DesignMD must not add a `Run DSPx` button, server-side subprocess, or automatic generated-candidate materialization until a later explicit orchestration design is accepted.

Minimum unblockers for orchestration:

- executable discovery/version pinning;
- path confinement and realpath containment;
- output directory custody and cleanup policy;
- timeout/cancel UX;
- stderr/stdout redaction;
- proof that no provider secrets are read and no provider calls occur unless explicitly requested;
- rollback posture for generated files;
- UI copy that distinguishes `generation_allowed`, `fitness_passed`, and human acceptance.

## Implementation wave mapping

### `IW-DV-05-IMPLEMENT-PACKET-UX`

Owner repo: DesignMD Foundry.

Scope:

- UI button/action for `Export DSPx requirements`.
- Fetch existing requirements endpoint.
- Render summary + copy/download JSON.
- Render copied DSPx CLI command snippets.
- Browser/API tests verifying endpoint use and non-execution copy.

Not in scope:

- importing evidence;
- running DSPx;
- changing dossier acceptance behavior.

### `IW-DV-06-IMPLEMENT-PREPARE-EVIDENCE`

Owner repo: DesignMD Foundry, with DSPx schema references.

Scope:

- Import/view gate, traceability, and fitness JSON.
- Validate schema/non-authority/effect fields.
- Store private runtime evidence sidecars.
- Add review-only evidence record/status.
- Show evidence summary in dossier UI.

Not in scope:

- launching DSPx;
- accepting dossier guidance;
- `DESIGN.md` mutation.

### `IW-DV-07-IMPLEMENT-ORCHESTRATION`

Owner repos: DesignMD Foundry + DSPx, only after explicit later decision.

Scope:

- bounded local orchestration if selected;
- path and subprocess membrane;
- cancellation, retention, and redaction;
- full validation fixtures.

## Design conclusion

The next implementation should be `IW-DV-05-IMPLEMENT-PACKET-UX` in DesignMD Foundry. It should expose the already implemented requirements packet and runbook commands without executing DSPx. This gives the operator a usable bridge immediately while preserving the architecture needed for later imported evidence viewing and optional orchestration.
