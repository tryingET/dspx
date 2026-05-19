---
summary: "Implementation plan for imported DSPx visual-dossier evidence viewer in DesignMD Foundry."
read_when:
  - "Implementing imported DSPx evidence viewing for DesignMD visual-source dossiers."
  - "Planning storage, validation, and review-record behavior for DSPx visual-dossier artifacts."
type: "implementation-plan"
system4d:
  container: "DesignMD imported-evidence viewer for DSPx visual-dossier gate/traceability/fitness artifacts."
  compass: "Make DSPx evidence inspectable while preserving review-only authority and no DesignMD-side execution."
  engine: "Operator imports DSPx JSON -> validate schema/non-authority/effects -> store private sidecars -> show summary -> record review-only evidence attachment."
  fog: "Risk that fitness_passed or generation_allowed becomes implicit dossier acceptance."
---

# Imported DSPx visual-dossier evidence viewer plan

Task: `AK-3176`
Direction: `SF-DESIGNMD-VDOS` / `IW-DV-06-IMPLEMENT-PREPARE-EVIDENCE`
Date: 2026-05-19

## Context

The packet export UX is complete in DesignMD Foundry commit `ab8e325`. It exposes the DesignMD-side requirements packet and copies operator-run DSPx commands without executing DSPx.

The next slice should let operators bring DSPx JSON evidence back into DesignMD for inspection. DesignMD still must not launch DSPx, accept dossier guidance, mutate `DESIGN.md`, or create AK/society authority from DSPx output.

## Target user flow

```text
Visual Sources dossier card
-> Export DSPx requirements
-> operator runs DSPx externally
-> Import DSPx evidence JSON files
-> DesignMD validates and stores review-only evidence sidecar
-> Dossier UI shows compact gate / traceability / fitness summary
-> Optional local review record notes evidence is attached
```

## Accepted inputs

First slice accepts exactly these JSON artifacts:

| File | Schema |
|---|---|
| `generation_gate_preflight.json` | `gen-generation-gate-preflight-v1` |
| `generation_traceability.json` | `gen-traceability-v1` |
| `generation_fitness_results.json` | `gen-fitness-results-v1` |

Optional later inputs:

- `generation_target_contract.json`
- `generation_fitness_suite.json`
- generated candidate `manifest.json`

## DesignMD data model additions

Add types in DesignMD Foundry:

```ts
export type DspxVisualDossierEvidenceArtifactKind =
  | 'generation_gate_preflight'
  | 'generation_traceability'
  | 'generation_fitness_results';

export interface DspxVisualDossierEvidenceSummary {
  schemaVersion: 'designmd.dspx-visual-dossier-evidence-summary.v1';
  id: string;
  sourceId: string;
  dossierDraftId: string;
  importedAt: string;
  artifactKinds: DspxVisualDossierEvidenceArtifactKind[];
  generationAllowed?: boolean;
  generationFailClosedReasons: string[];
  traceabilityCoveredCount?: number;
  traceabilityUncoveredCount?: number;
  fitnessStatus?: 'fitness_passed' | 'fitness_failed' | 'target_fidelity_unknown';
  renderedState?: string;
  warnings: string[];
  authority: ReviewEvidenceAuthority;
}
```

The exact type names can be adjusted to fit existing DesignMD conventions, but the summary must remain DesignMD-owned and review-only.

## Storage layout

Use private runtime storage under the visual source:

```text
data/projects/<project>/visual-sources/<sourceId>/dspx-evidence/<evidenceId>/
  manifest.json                       # DesignMD-owned evidence summary
  generation_gate_preflight.json       # optional if supplied
  generation_traceability.json         # optional if supplied
  generation_fitness_results.json      # optional if supplied
```

Implementation requirements:

- Create `dspx-evidence/<evidenceId>` with a generated id.
- Use existing atomic write helpers.
- On visual source delete, evidence is removed with the visual-source directory.
- Do not write imported evidence into `docs/design` or `DESIGN.md`.
- Redact absolute local paths from any public summary. Private raw JSON may retain operator-supplied content only inside runtime storage.

## API contract

Add endpoints under the existing visual-source API namespace:

```http
POST /api/visual-sources/:sourceId/dspx-evidence/:dossierId
GET  /api/visual-sources/:sourceId/dspx-evidence/:dossierId
```

POST body shape:

```json
{
  "generationGatePreflight": {},
  "generationTraceability": {},
  "generationFitnessResults": {},
  "operatorNote": "optional rationale"
}
```

GET response shape:

```json
{
  "dspxEvidence": [
    {
      "summary": {},
      "artifacts": {
        "generationGatePreflight": {},
        "generationTraceability": {},
        "generationFitnessResults": {}
      }
    }
  ]
}
```

If implementation cost is high, first slice may skip GET and include evidence summaries in the existing `getVisualSourceBundle(...)` response instead. Prefer bundle inclusion for UI simplicity if it does not over-bloat responses.

## Validation rules

Fail closed on import when:

- no supported artifact is supplied;
- supplied artifact is not an object;
- schema version is not the expected DSPx schema;
- `non_authority` is absent or any of these are not false:
  - `activation_authority`
  - `promotion_authority`
  - `oracle_authority`
  - `governance_authority`
  - `external_mutation`
- `effect` says any of these are true:
  - `canonical_target_mutated`
  - `ak_mutated`
  - `governance_mutated`
  - `shared_oracle_mutated`
- imported artifact has obvious `accepted_contract_truth`, `reviewed_dossier_guidance`, or `production_activation` posture in a DesignMD output posture field.

Record warnings, not hard failures, when:

- `generation_allowed` is false;
- `fitnessStatus` is not `fitness_passed`;
- traceability entries are uncovered;
- identity hashes cannot be fully matched to the current dossier due to missing optional target contract / manifest artifacts.

## Review record behavior

Do not use existing `accepted` review flow.

Add a review-only decision if needed:

```text
dspx_evidence_attached
```

Resulting state should be current dossier state or `review_evidence`, not `reviewed_accepted`.

The review record should include:

- `targetKind: 'dossier'`
- `targetId: <dossierId>`
- `decision: 'dspx_evidence_attached'`
- `rationale`: operator note or generated summary
- `blockers`: warnings / fail-closed reasons if any
- authority statement with no `DESIGN.md` mutation

If changing the review enum is too wide for first implementation, store the evidence summary without creating a review record and leave review-record integration as the second part of `IW-DV-06`. Do not fake it with `accepted`.

## UI contract

Add an import/view panel near the DSPx requirements export panel.

Allowed labels:

- `Import DSPx evidence JSON`
- `DSPx evidence attached`
- `Review evidence only`
- `Fitness passed — eligible for review`, not `accepted`

Disallowed labels:

- `Accept DSPx evidence`
- `Approve dossier`
- `Apply DSPx guidance`
- `Run DSPx`

Display summary:

- generation gate: allowed/blocked and reasons;
- traceability: covered vs uncovered counts;
- fitness: status and rendered state;
- warnings;
- imported timestamp;
- authority: `review_evidence_only`.

Raw JSON should be expandable/copyable.

## Tests

Minimum DesignMD tests:

- imports valid calicoach-shaped DSPx artifacts and stores a summary;
- rejects artifact with missing/invalid schema;
- rejects artifact whose `non_authority.activation_authority` is true or missing;
- rejects artifact whose `effect.ak_mutated` or `effect.governance_mutated` is true;
- imported `fitness_passed` does not transition dossier to `reviewed_accepted`;
- UI smoke still passes and shows Visual Sources boundary copy.

Useful fixture source:

- DSPx `tests/fixtures/program_gen/designmd_visual_dossier/requirements_calicoach.json`
- Generate gate/traceability/fitness artifacts from DSPx into a fixture or synthesize minimal JSON fixtures in DesignMD tests.

## Implementation task to create in DesignMD

Recommended next AK task:

```bash
cd /home/tryinget/ai-society/softwareco/owned/designmd-foundry
ak task create -r "$PWD" -P 1 \
  "Add review-only DSPx visual-dossier evidence import viewer" \
  --allowed src/core/types.ts \
  --allowed src/core/visual-sources.ts \
  --allowed src/server.ts \
  --allowed web/app.js \
  --allowed tests/visual-sources.test.ts \
  --allowed docs/project/2026-05-19-dspx-visual-dossier-evidence-import-viewer.md \
  --allowed governance/work-items.json \
  --required src/core/types.ts \
  --required src/core/visual-sources.ts \
  --required web/app.js \
  --required tests/visual-sources.test.ts \
  --require-scope
```

Adjust paths after inspecting DesignMD's current test and server route surfaces.

## Validation

For the DesignMD implementation:

```bash
npm test
npm run typecheck
npm run lint:design
npm run smoke:web
```

Add `npm run smoke:render` only if the UI change materially changes rendered checkpoint surfaces or if browser smoke coverage is insufficient.

## Plan conclusion

Proceed to DesignMD Foundry for the imported evidence viewer. Keep the first implementation review-only and import-based. Do not add local DSPx execution or orchestration in this wave.
