---
summary: "Implementation plan splitting DesignMD and DSPx visual-dossier integration work by owner surface."
read_when:
  - "Materializing AK tasks for DesignMD visual-dossier DSPx integration."
  - "Planning packet export UX, DSPx evidence import, or optional orchestration work."
type: "implementation-plan"
system4d:
  container: "Owner-scoped implementation plan for DesignMD visual-source dossier DSPx integration."
  compass: "Turn discovery/research/design into bounded AK tasks without crossing source-owner boundaries."
  engine: "Design contract -> owner-scoped tasks -> packet UX -> evidence viewer -> optional orchestration decision."
  fog: "Risk of implementing UI orchestration before packet/evidence custody is proven."
---

# DesignMD visual-dossier integration implementation plan

Task: `AK-3173`
Direction: `SF-DESIGNMD-VDOS` / `IW-DV-04-PLAN`
Date: 2026-05-19

## Inputs

- Discovery: `docs/project/2026-05-19-designmd-visual-dossier-integration-discovery.md`
- Research: `docs/project/2026-05-19-designmd-visual-dossier-integration-research.md`
- Design contract: `docs/project/2026-05-19-designmd-visual-dossier-integration-design.md`

## Selected implementation sequence

1. **DesignMD packet export UX** — first product slice.
2. **DesignMD imported DSPx evidence viewer** — second product slice.
3. **DSPx support refinements** — only if the evidence viewer needs bundle/export ergonomics or schema summaries.
4. **Optional orchestration decision + implementation** — deferred until packet/evidence UX proves need and a separate decision accepts subprocess custody.

## Owner split

| Work | Owner repo | Why |
|---|---|---|
| Visual-source dossier UI button, packet summary, copy/download JSON, runbook commands | `softwareco/owned/designmd-foundry` | DesignMD owns visual-source workflow and operator UX. |
| Imported evidence storage, validation, review-only record/status, evidence summary UI | `softwareco/owned/designmd-foundry` | DesignMD owns dossier review records and local visual-source runtime storage. |
| `program-gen prepare`, target contracts, traceability, fitness-results generation | `softwareco/owned/dspx` | DSPx owns target-protocol gates and generated-program evidence. |
| Optional DSPx evidence bundle/export command | `softwareco/owned/dspx` | DSPx owns artifact packaging if manual import becomes too awkward. |
| Local orchestration bridge | Joint, later | Requires explicit subprocess/security/authority design; not in first implementation. |

## Materialized tasks

### DesignMD implementation task 1 — packet export UX

Recommended AK title:

```text
Add DSPx visual-dossier requirements export UX
```

Repo:

```text
/home/tryinget/ai-society/softwareco/owned/designmd-foundry
```

Scope:

- `web/app.js`
- `web/index.html` if needed for static UI anchors
- relevant CSS/assets if the UI requires styling
- tests/smoke surfaces for Visual Sources UI
- docs if DesignMD local docs require user-facing runbook update

Requirements:

- Add a dossier-card action labeled `Export DSPx requirements`.
- Fetch `GET /api/visual-sources/:sourceId/dspx-requirements/:dossierId`.
- Render compact packet summary:
  - schema version;
  - project/source/analysis/dossier ids;
  - freshness/hash status;
  - role coverage;
  - accepted output posture;
  - forbidden claims;
  - fail-closed blockers.
- Provide copy full JSON.
- Provide download JSON with deterministic filename.
- Provide copyable DSPx CLI command snippet.
- State clearly that commands are operator-run outside DesignMD and no DSPx execution occurs from the browser/server.

Out of scope:

- importing DSPx evidence;
- running DSPx;
- changing dossier acceptance state;
- mutating `DESIGN.md`.

Suggested validation:

```bash
npm test -- --runInBand visual-sources
npm run smoke:web
npm run check
```

Use the actual repo-local test commands after inspecting DesignMD's current scripts.

### DesignMD implementation task 2 — imported evidence viewer

Recommended AK title:

```text
Add review-only DSPx visual-dossier evidence import viewer
```

Repo:

```text
/home/tryinget/ai-society/softwareco/owned/designmd-foundry
```

Scope:

- `src/core/types.ts`
- `src/core/visual-sources.ts`
- `src/server.ts`
- `web/app.js`
- storage fixtures/tests/docs as needed

Requirements:

- Accept/import JSON artifacts:
  - `gen-generation-gate-preflight-v1`
  - `gen-traceability-v1`
  - `gen-fitness-results-v1`
- Validate schema, non-authority, and effect fields.
- Store private runtime sidecars under visual-source storage.
- Show compact evidence summary in the dossier UI.
- Add review-only record/status such as `dspx_evidence_attached` or `proposal_context_available`.
- Do not transition dossier state to `reviewed_accepted`.
- Do not set authority posture to `reviewed_dossier_guidance`.
- Redact absolute local paths from public summaries.

Out of scope:

- launching DSPx;
- generated candidate code display beyond safe artifact summaries;
- accepting dossier guidance.

Suggested validation:

```bash
npm test -- --runInBand visual-sources
npm run smoke:web
npm run smoke:render
npm run check
```

Use the actual repo-local test commands after inspecting DesignMD's scripts and runtime cost.

### DSPx support task — optional bundle ergonomics

Recommended AK title:

```text
Add DSPx visual-dossier evidence bundle summary for DesignMD import
```

Repo:

```text
/home/tryinget/ai-society/softwareco/owned/dspx
```

Trigger:

Only create/execute this if DesignMD evidence import needs a simpler single-file bundle or canonical redacted summary.

Possible scope:

- `packages/dspx-core/src/dspx/services/program_generation_contract.py`
- `packages/dspx-core/src/dspx/cli/dspx.py`
- tests around `program-gen` evidence bundle/summary

Possible behavior:

- Read gate, traceability, fitness-results, and optional manifest.
- Emit a redacted `dspx.designmd-visual-dossier-evidence-bundle.v1` summary.
- Preserve non-authority/effect fields.
- Avoid absolute local path leakage by default.

Out of scope:

- DesignMD storage or review-state mutation;
- Oracle publication or AK evidence creation.

## Task creation posture

Because first implementation belongs in DesignMD Foundry, create DesignMD AK tasks from that repo root before mutation. Keep DSPx tasks as support-only unless a DSPx-owned artifact change is actually needed.

Minimum next task to create/claim in DesignMD:

```bash
cd /home/tryinget/ai-society/softwareco/owned/designmd-foundry
ak task create -r "$PWD" -P 1 \
  "Add DSPx visual-dossier requirements export UX" \
  --allowed web/app.js \
  --allowed web/index.html \
  --allowed docs/project/2026-05-19-dspx-visual-dossier-requirements-export-ux.md \
  --allowed governance/work-items.json \
  --required web/app.js \
  --require-scope
```

Adjust allowed/required paths after inspecting the exact DesignMD test/doc surfaces. Do not include unrelated dirty release-automation files.

## Validation posture

For DSPx-side planning docs:

```bash
node ~/ai-society/core/agent-scripts/scripts/docs-list.mjs --docs . --strict
ak direction check --repo /home/tryinget/ai-society/softwareco/owned/dspx --format json
ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx
./scripts/ci/smoke.sh
```

For DesignMD implementation:

- inspect dirty git state first;
- claim a DesignMD AK task before mutation;
- run the smallest truthful UI/API tests for Visual Sources;
- avoid committing unrelated release automation files already dirty in the DesignMD checkout;
- preserve `DESIGN.md` and `data/projects/default/DESIGN.md` unless intentionally changing design-system contract.

## Plan conclusion

The next implementation should move to DesignMD Foundry and land `IW-DV-05-IMPLEMENT-PACKET-UX`: a UI action that exposes the already implemented DSPx requirements packet with copy/download/runbook affordances. DSPx should not change further unless DesignMD implementation discovers a concrete support need.
