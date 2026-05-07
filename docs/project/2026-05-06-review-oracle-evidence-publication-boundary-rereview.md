---
summary: "Re-review memo for the revised Oracle evidence publication boundary RFC, concluding it is ready for ADR after the revise_rfc fixes."
read_when:
  - "You are reviewing the revised Oracle evidence publication boundary RFC."
  - "You need the controlling re-review closure for AK decision #31."
  - "You are deciding whether the revised RFC can proceed to ADR."
---

# Re-review memo — Oracle evidence publication boundary RFC

- Date: 2026-05-06
- Decision: `#31 Review Oracle evidence publication boundary from initial RFC`
- Reviewed artifact: `docs/rfc/RFC-DSPX-ORACLE-20260506-evidence-publication-boundary.md`
- Review kind: `re-review after revise_rfc`
- Review prompt: `review-rfc-multi` / `layer12-070-decision-rfc-review`
- Review outcome: `ready_for_adr`
- Legal next move: open ADR pack; do not implement shared writes.

## System4D summary

- boundary: DSPx publication of Oracle-readable generated-program evidence from local candidate artifacts into shared Oracle empirical memory.
- primary driver: retain useful shared behavioral memory without creating a second authority database or publishing scratch caches.
- main risks: Oracle as de facto authority, shared evidence leakage, survivor bias, local cache migration, and premature shared writes.

## Review chain status

- review kind: `re-review after revise_rfc`
- reviewed artifact: `docs/rfc/RFC-DSPX-ORACLE-20260506-evidence-publication-boundary.md`
- supporting docs read:
  - `docs/project/2026-05-06-review-oracle-evidence-publication-boundary-many-greats.md`
  - `docs/adr/20260505-shared-oracle-coordinate-backend.md`
  - `docs/project/generated-program-activation-boundary.md`
  - `docs/project/program-gen-walkthrough.md`
  - `docs/project/product_posture.md`
  - `~/ai-society/holdingco/governance-kernel/docs/dev/decision-lifecycle.md`
- required lifecycle artifacts present:
  - initial RFC draft;
  - adversarial review attempt with `revise_rfc`;
  - revised RFC addressing the review blockers;
  - this re-review memo.
- missing or unclear lifecycle artifacts: problem/evidence notes may be generated as ADR-pack support, but they do not block the revised RFC's review closure.
- ADR legal now?: yes, once this review memo is attached to AK decision `#31` as the latest review closure.
- reason: the revised RFC addresses the prior blockers and limits the next implementation to preflight-only.

## Overall verdict

- ready for ADR
- The revised RFC preserves the strong central direction and now closes the redaction, publisher responsibility, authority-mirror label, and retention/retraction gaps that blocked the first review.

## Lens 1 — Runtime authority / platform boundary

- strengths:
  - Clearly separates `society.v2.db` / AK authority from shared Oracle empirical memory.
  - Splits labels into empirical labels and authority-mirror labels.
  - Requires `authority_ref` for authority-mirror labels and states Oracle only mirrors the ref.
  - Preserves `program-loop` local default and blocks shared publication convenience until standalone publish/preflight are proven.
- risks:
  - Authority-mirror labels will still need careful UI/CLI wording because they can look normative.
  - Later implementation must not validate authority refs by string shape alone and imply canonical truth.
- must-fix issues: none before ADR.
- evidence quality: sufficient; boundaries cite existing shared backend ADR and activation boundary docs.

## Lens 2 — Data stewardship / publication custody

- strengths:
  - Adds required `publisher_id`, `publisher_role`, and `publisher_assertion`.
  - Defines legal redaction statuses and fails closed on missing, `unknown`, or `contains_sensitive_material` posture.
  - Defines retention classes and explicitly warns that physical deletion from Postgres/backups is infra-governed and may lag logical retraction.
  - Treats initial publisher identity as declared, not authenticated authority.
- risks:
  - `checked` remains a custody assertion, not a deterministic DLP proof.
  - Retraction implementation will need exact receipt/tombstone semantics.
- must-fix issues: none before ADR; deterministic redaction checks can remain future work because the RFC is explicit about declared status limits.
- evidence quality: sufficient for ADR; implementation validation requirements are concrete enough to test.

## Lens 3 — Implementation sequencing / verification

- strengths:
  - Phase 1 is now explicitly the only legal first implementation slice.
  - Phase 1 writes preflight packets only and no shared records.
  - Validation plan includes negative tests for missing artifacts, widened non-authority flags, missing labels, missing publisher fields, invalid redaction status, missing retention class, authority-mirror labels without refs, and secret redaction.
  - Shared writes are deferred behind explicit backend configuration and passing preflight/equivalent validation.
- risks:
  - The exact schema name for the preflight packet is not yet fixed, but the required fields/effects are clear enough for ADR.
  - Publication event vs append-only event model remains open.
- must-fix issues: none before ADR.
- evidence quality: strong enough for a decision; unresolved questions are implementation choices, not direction blockers.

## Cross-cutting contradictions

- Empirical labels are necessary for behavior memory; authority-mirror labels are necessary for retrieval around lifecycle events. The revised RFC resolves the contradiction by requiring authority refs for authority-mirror labels and preserving Oracle's non-authority posture.
- Shared publication is useful, but shared writes are risky. The revised RFC resolves this by making preflight-only the first legal implementation slice.
- Redaction is necessary, but deterministic redaction tooling does not exist yet. The revised RFC resolves this by treating redaction status as a declared custody assertion and failing closed on unknown/sensitive posture.

## Must-fix before ADR

- None.

## Nice-to-have improvements

- Add a concrete preflight packet JSON example in the ADR or first implementation task.
- Define first-slice label subset, likely `retained`, `rejected`, and `request_more_evidence` before activation-mirror labels.
- Consider adding a later deterministic redaction checklist/tool task.

## Questions reviewers should force the authors to answer

- Should first implementation support authority-mirror labels at all, or defer them until empirical labels work?
- Should publication events be append-only under one evidence identity or label-specific records?
- What exact DS1621 retention class maps to `activation_evidence_reference` once production readiness is pursued?

## Workflow result

- review_outcome: `ready_for_adr`
- next legal move: `open_adr_pack`
- controlling rationale:
  - prior `revise_rfc` blockers were addressed in the revised RFC;
  - the boundary keeps Oracle empirical and AK/governance authoritative;
  - first implementation is constrained to no-shared-write preflight;
  - remaining open questions are implementation details, not ADR blockers.
- missing artifacts or gates:
  - ADR not yet recorded;
  - implementation plan and validation/rollout/rollback notes should be produced with the ADR pack;
  - no shared publication implementation is authorized yet.
- notes on legality vs quality:
  - This re-review supports ADR progression for the revised RFC.
  - It does not authorize Phase 2 shared writes or `program-loop --publish-to-shared`.

## Final recommendation

- approve RFC as ADR basis
- reasons:
  - central Option C remains the strongest direction;
  - redaction and publisher-custody gaps are now explicit;
  - authority-mirror labels now require refs and stay non-authoritative;
  - retention/retraction posture is defined enough for architecture acceptance;
  - first implementation is safely bounded to publication preflight only.
