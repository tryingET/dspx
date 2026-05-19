---
summary: "Research decision support for DesignMD ↔ DSPx visual-dossier orchestration and evidence custody."
read_when:
  - "Choosing the DesignMD / DSPx visual-dossier custody model."
  - "Before designing UI/API affordances for DSPx requirements, prepare artifacts, or generated evidence."
type: "research"
system4d:
  container: "Custody and orchestration options for DesignMD visual-source dossier evidence from DSPx."
  compass: "Select the smallest useful product path that preserves owner boundaries and avoids authority drift."
  engine: "Requirements packet UX -> optional imported evidence viewer -> optional explicitly designed local orchestration."
  fog: "Risk of a convenient UI button becoming hidden subprocess execution, persistent path leakage, or implicit dossier acceptance."
---

# DesignMD visual-dossier custody model research

Task: `AK-3170`
Direction: `SF-DESIGNMD-VDOS` / `IW-DV-02-RESEARCH`
Date: 2026-05-19

## Inputs

- Discovery: `docs/project/2026-05-19-designmd-visual-dossier-integration-discovery.md`
- DSPx target contract: `docs/project/designmd-visual-dossier-target-protocol-contract.md`
- DesignMD accepted boundaries:
  - `docs/decisions/ADR-0002-visual-source-dossier-authority-boundary.md`
  - `docs/decisions/ADR-0004-visual-source-workflow-state-and-review-records.md`
  - `docs/decisions/ADR-0005-docs-design-dossier-document-convention.md`
  - `docs/decisions/ADR-0006-dspx-visual-dossier-target-protocol-handoff-boundary.md`
- DesignMD current handoff surfaces:
  - `GET /api/visual-sources/:sourceId/dspx-requirements/:dossierId`
  - `designmd-foundry visual-dossier dspx-requirements <source-id> <dossier-id>`
- DSPx current executable path:
  - `program-gen prepare --profile designmd-visual-dossier`
  - `program-gen`
  - `program-gen traceability`
  - `program-gen fitness-results`

## Options evaluated

### Option A — packet export UX only

DesignMD UI exposes the already implemented requirements packet and gives the operator a copy/download/runbook affordance.

DesignMD does:

- fetch `dspx-requirements` for a source/dossier;
- render schema, identity, freshness, role coverage, forbidden claims, and accepted output posture;
- provide copy/download JSON;
- provide exact DSPx CLI command snippets;
- record no DSPx execution state.

DSPx does:

- remain the owner of prepare, generation, traceability, and fitness-results;
- write gate/evidence artifacts outside DesignMD unless the operator later imports them.

Pros:

- Uses existing DesignMD API/CLI packet generator.
- No subprocess execution from DesignMD.
- No new executable trust boundary.
- No path custody problem beyond JSON download/copy.
- Lowest chance of implying DesignMD has accepted DSPx fitness.

Cons:

- Operator still switches to DSPx CLI.
- DesignMD cannot show prepare status unless artifacts are manually returned later.
- Evidence review remains split across tools.

### Option B — packet export plus imported evidence viewer

DesignMD UI first exposes packet export, then accepts operator-supplied DSPx JSON artifacts for review-only display.

DesignMD does:

- everything in Option A;
- accept imported `generation_gate_preflight.json`, `generation_traceability.json`, and `generation_fitness_results.json` as local evidence sidecars;
- validate schema/version/identity/hash compatibility where available;
- display summarized status and expandable raw JSON;
- store evidence under local visual-source runtime records with public redaction rules;
- create a review record such as `dspx_evidence_attached` / `proposal_context_available` rather than acceptance.

DSPx does:

- continue to own execution and artifact creation;
- optionally provides a future export bundle command to make import ergonomic.

Pros:

- Gives DesignMD product value without DesignMD launching DSPx.
- Creates an evidence viewer and review trail that can later support orchestration.
- Keeps evidence custody explicit: imported artifact, not generated-in-place authority.
- Fits existing DesignMD state model: review records with evidence and explicit non-authority.

Cons:

- Requires import validation and storage schema.
- Requires operator to move JSON artifacts manually.
- Must prevent imported evidence from unlocking acceptance controls automatically.

### Option C — prepare-only local bridge

DesignMD server invokes DSPx `program-gen prepare`, stores gate artifacts, and displays generation preflight status, but does not run full program generation.

Pros:

- Better UX for the first gate.
- No generated candidate execution yet.
- Could remain deterministic and provider-free if bounded to prepare.

Cons / requirements:

- Introduces subprocess execution in DesignMD.
- Needs executable discovery and version pinning.
- Needs output directory custody and cleanup policy.
- Needs path confinement and public redaction.
- Needs timeout/cancel/error UX.
- May still imply DesignMD owns target-protocol gate truth unless copy is very clear.

### Option D — full local orchestration bridge

DesignMD launches prepare, program-gen, traceability, and fitness-results from the UI/API.

Pros:

- Best single-button UX.
- Can produce complete evidence from one DesignMD action.

Cons / requirements:

- Highest security and authority risk.
- Subprocess and generated-code materialization from a product server.
- Output retention and deletion semantics become product concerns.
- Must prove no provider/secret use and no hidden external mutation.
- Requires progress, cancellation, log redaction, and rollback design.
- Increases chance of treating `fitness_passed` as dossier acceptance.

## Recommendation

Choose **Option B as the target product path**, reached incrementally:

1. `IW-DV-05-IMPLEMENT-PACKET-UX`: implement Option A first.
2. `IW-DV-06-IMPLEMENT-PREPARE-EVIDENCE`: implement imported evidence viewer from Option B.
3. Keep Option C/D out of scope until a later explicit design decision.

Rationale:

- Option A is the smallest truthful next slice and uses an already accepted packet boundary.
- Option B solves the biggest product gap — DesignMD cannot inspect DSPx evidence — without introducing subprocess orchestration.
- Option C/D can still be designed later if operator friction remains high, but they should not be the first UI integration.

## Custody model selected for design

Initial custody model:

```text
DesignMD owns requirements packet display and imported evidence review records.
DSPx owns prepare, program-gen, traceability, and fitness artifact generation.
Operator transfers DSPx JSON artifacts back to DesignMD until/unless orchestration is explicitly designed.
```

DesignMD storage posture for imported evidence:

- Store as runtime/private project evidence, not as `DESIGN.md` or accepted `docs/design` content.
- Public/committed dossier materialization may cite summarized evidence only after redaction.
- Absolute local paths from DSPx artifacts must be redacted or stored only in private manifests.
- Evidence attachment creates review context only; it does not change dossier state to accepted.

## Required design contract for `IW-DV-03-DESIGN`

The design wave should freeze:

1. UI labels and allowed actions:
   - `Export DSPx requirements`
   - `Copy DSPx CLI command`
   - later: `Import DSPx evidence JSON`
   - not: `Run DSPx` or `Accept DSPx guidance` in the first product slice.
2. Evidence validation contract:
   - accepted schema versions;
   - required identity links to source id, dossier id, source index hash, and DESIGN.md hash;
   - allowed missing fields and fail-closed reasons.
3. Evidence storage contract:
   - runtime/private sidecar path;
   - redacted public summary shape;
   - retention/deletion behavior when visual source is archived/deleted.
4. Review record contract:
   - new review decision/status names for evidence attachment;
   - explicit no-acceptance semantics;
   - how evidence appears in dossier preview without changing `DESIGN.md`.
5. CLI copy/runbook contract:
   - exact command snippets for DSPx prepare/program-gen/traceability/fitness;
   - placeholders and output directory guidance;
   - warning that commands are operator-executed outside DesignMD UI.

## Explicit deferrals

Full orchestration is deferred by design, not abandoned.

Deferral contract:

- Owner: DSPx + DesignMD jointly, through `IW-DV-07-IMPLEMENT-ORCHESTRATION`.
- Trigger: after `IW-DV-03-DESIGN` and imported evidence viewer prove operator friction or repeated demand for one-click execution.
- Required unblockers: path-confinement design, subprocess policy, output retention policy, timeout/cancel UX, log redaction, no-provider-call proof, and authority-boundary copy.
- Blast radius if skipped permanently: operator remains responsible for running DSPx CLI manually; product still supports packet export and imported evidence review.
- Blast radius if implemented too early: hidden execution and authority drift from a DesignMD UI control.

## Research conclusion

Proceed to `IW-DV-03-DESIGN` with Option B as the target architecture and Option A as the first implementation slice. The next implementation should expose the existing requirements packet in DesignMD UI with copy/download/runbook affordances. Imported DSPx evidence viewing should follow. Full local orchestration should remain optional and explicitly gated by a later design decision.
