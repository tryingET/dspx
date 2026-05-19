---
summary: "Discovery map for DesignMD visual-source dossier integration with DSPx program-gen evidence."
read_when:
  - "Planning DesignMD visual-source dossier UI/API integration with DSPx."
  - "Working AK-3164 or later SF-DESIGNMD-VDOS waves."
type: "discovery"
system4d:
  container: "DesignMD visual-source dossier UI/API surfaces and DSPx prepare/program-gen evidence seams."
  compass: "Move from CLI-only handoff to product-safe review-evidence UX without authority drift."
  engine: "DesignMD packet -> DSPx prepare/gates -> candidate assembly -> traceability/fitness -> review evidence viewer."
  fog: "Risk of turning DSPx-generated evidence into DesignMD acceptance, DESIGN.md mutation, or production activation."
---

# DesignMD visual-source dossier integration discovery

Task: `AK-3164`
Direction: `SF-DESIGNMD-VDOS` / `IW-DV-01-DISCOVERY`
Date: 2026-05-19

## Current executable DSPx path

DSPx has an executable bounded path for DesignMD visual-source dossier requirements:

```text
designmd.dspx-visual-dossier-requirements.v1
-> dspx program-gen prepare --profile designmd-visual-dossier
-> generation_target_contract.json
-> generation_fitness_suite.json
-> generation_gate_preflight.json
-> optional program-intent-v2
-> dspx program-gen --generation-gate-preflight
-> generation_traceability.json
-> generation_fitness_results.json
```

Checked-in surfaces:

- `docs/project/designmd-visual-dossier-target-protocol-contract.md`
- `packages/dspx-core/src/dspx/services/program_generation_contract.py`
- `packages/dspx-core/src/dspx/cli/dspx.py`
- `tests/fixtures/program_gen/designmd_visual_dossier/requirements_calicoach.json`
- `tests/test_program_generation_contract.py`
- `tests/test_program_generation_contract_cli.py`

Dogfood status: the calicoach fixture runs through prepare, candidate materialization, traceability, and fitness-results with `generation_allowed: true` and `fitness_passed` when executed into `/tmp` output directories.

## Current DesignMD surfaces

DesignMD Foundry already owns the visual-source / dossier product workflow and packet handoff.

Observed files:

- `/home/tryinget/ai-society/softwareco/owned/designmd-foundry/web/index.html`
- `/home/tryinget/ai-society/softwareco/owned/designmd-foundry/web/app.js`
- `/home/tryinget/ai-society/softwareco/owned/designmd-foundry/src/server.ts`
- `/home/tryinget/ai-society/softwareco/owned/designmd-foundry/src/core/visual-sources.ts`
- `/home/tryinget/ai-society/softwareco/owned/designmd-foundry/src/core/types.ts`
- `/home/tryinget/ai-society/softwareco/owned/designmd-foundry/src/cli.ts`

Available DesignMD API / CLI handoff:

- `GET /api/visual-sources/:sourceId/dspx-requirements/:dossierId`
- `designmd-foundry visual-dossier dspx-requirements <source-id> <dossier-id> [--project default]`
- implementation: `buildDspxVisualDossierRequirementsPacket(...)`

DesignMD packet boundary already states:

- DesignMD defines requirements only.
- DSPx owns target-protocol review, program-gen, execution episodes, receipts, Oracle evidence, and promotion.
- Packet generation does not execute DSPx program-gen.
- Outputs are `proposal_context` / `review_evidence` only.

## UI incorporation status

The DesignMD UI has a visual-source workflow but does not yet surface the DSPx flow.

Existing UI capabilities in `web/app.js` include:

- visual-source upload/path-reference intake
- thumbnail display
- scaffold queue/complete actions
- dossier preview
- docs/design materialization
- dossier review request/reject/revise actions
- manual-edit-only contract proposal

Missing UI affordances:

- no visible button to view/copy/download the DSPx requirements packet
- no `fetch` call to `/dspx-requirements`
- no prepare/gate status panel
- no DSPx traceability/fitness evidence viewer
- no receipt or generated-candidate evidence import surface

## Integration seam map

| Seam | Current owner | Current state | Next question |
|---|---|---|---|
| Visual source storage and dossier records | DesignMD | implemented local-first | How much DSPx evidence should DesignMD store vs reference? |
| Requirements packet | DesignMD | API/CLI implemented, UI not exposed | Should UI provide copy/download/runbook first? |
| Prepare gate artifacts | DSPx | CLI implemented and tested | Should DesignMD invoke prepare or only instruct operator? |
| Program generation | DSPx | CLI implemented and tested for bounded candidate | Should product UX ever launch generation, or only accept imported evidence? |
| Traceability / fitness | DSPx | CLI implemented and tested | What minimal viewer is useful without acceptance drift? |
| Dossier acceptance | DesignMD / human review | UI keeps acceptance unavailable | What review record type can cite DSPx evidence without accepting it automatically? |
| AK/society authority | AK / governance | explicitly out of DSPx output authority | Keep out of DesignMD UI except references to existing task/evidence IDs. |

## Research questions for `IW-DV-02-RESEARCH`

1. Packet-download-only model:
   - Is a UI action that displays/downloads the requirements packet enough for the next product slice?
   - Pros: low risk, preserves owner boundaries, no subprocess/security bridge.
   - Cons: operator must manually run DSPx and re-import/read evidence elsewhere.

2. Prepare-only bridge:
   - Should DesignMD server call DSPx prepare locally and show gate artifacts, while still not running program-gen?
   - Requires path confinement, executable discovery, output custody, failure UX, and clear non-authority copy.

3. Full local orchestration:
   - Should DesignMD launch prepare + program-gen + traceability + fitness-results?
   - Higher UX value but highest risk: subprocess policy, runtime dependency, temp/output retention, secret/provider posture, cancellation, and evidence trust boundaries.

4. Evidence custody:
   - Should DesignMD copy DSPx evidence into project-local runtime records, reference external paths, or accept uploaded JSON artifacts?
   - Public dossier docs must redact local absolute paths.

5. Review lifecycle:
   - What DesignMD review state can cite DSPx evidence without marking guidance accepted?
   - Candidate: `dspx_evidence_attached` / `proposal_context_available`, not `accepted`.

## Design constraints for `IW-DV-03-DESIGN`

- DSPx evidence must not mutate `DESIGN.md`.
- DSPx evidence must not approve `docs/design` materialization or dossier guidance.
- DesignMD UI copy must distinguish requirements, candidate generation, traceability, fitness, and human review.
- If orchestration is selected, it must be explicit operator action, local-only, path-confined, cancellable, and no hidden provider calls.
- Evidence display should prefer summarized status plus expandable JSON references, not automatic natural-language acceptance.

## Proposed implementation waves after research/design

### `IW-DV-05-IMPLEMENT-PACKET-UX`

Smallest product slice:

- Add UI action on dossier card: "Export DSPx requirements".
- Fetch existing `/dspx-requirements` endpoint.
- Show schema, source id, dossier id, freshness, accepted output posture, and forbidden claims.
- Offer copy/download JSON and exact DSPx CLI command snippet.
- Add UI/API tests in DesignMD.

### `IW-DV-06-IMPLEMENT-PREPARE-EVIDENCE`

Evidence viewer slice:

- Add import/view path for DSPx gate artifacts and fitness results.
- Show `generation_allowed`, fail-closed reasons, traceability coverage, and `fitness_passed`/withheld state.
- Keep evidence as review-only sidecar; no acceptance transition.

### `IW-DV-07-IMPLEMENT-ORCHESTRATION`

Optional only after explicit design decision:

- Local server-side bridge or workbench action to run DSPx prepare/program-gen.
- Must include executable/path confinement, output dir custody, timeout/cancel, no secret leakage, no automatic AK/DesignMD mutation, and deterministic validation fixtures.

## Discovery conclusion

The next safest product step is not full orchestration. It is `IW-DV-05-IMPLEMENT-PACKET-UX` after a short research/design pass confirms the custody model: expose the existing DesignMD requirements packet in the UI with a copy/download/runbook affordance, then add a review-only evidence viewer for imported DSPx artifacts. Full orchestration should remain optional until the security and authority boundaries are explicitly designed.
