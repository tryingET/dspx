---
summary: "Many-of-the-greats review and hardening receipt for bounded Obsidian/PDF generated-program runtime activation."
read_when:
  - "You are deciding whether bounded Obsidian/PDF generated-program runtime activation may proceed."
  - "You need the activation-gate hardening evidence after the many-of-the-greats review."
type: "review"
---

# Review — bounded Obsidian/PDF generated-program runtime activation

Date: 2026-05-10
Task: AK-2760
Prompt: `many-of-the-greats`

## Question

Should bounded Obsidian/PDF generated-program runtime activation proceed, given the current DSPx activation packet code, Obsidian adapter code, and supporting docs?

## Mode 1 — many of the greats

### School 1: Authority membrane maximalism

- Core claim: production activation must not proceed until authority is machine-verifiable.
- Premises:
  - Evidence systems are not authority systems.
  - Strings are not bindings.
  - Local decision sidecars are not domain governance.
- Strongest case:
  - A non-empty `canonical_binding_ref` must never by itself unlock rollout preflight.
  - A decision record must be tied to the configured domain authority owner.
  - Oracle and behavior evidence must be identity/hash-bound to the candidate.
- What it sees that others miss: a fake activation can look procedurally complete if the final membrane is text-only.

### School 2: Evidence-loop product pragmatism

- Core claim: the system is useful because it exposes blockers instead of pretending activation happened.
- Premises:
  - Dogfood should advance through explicit packets.
  - Review admission and production activation are separate states.
  - The packet's job is to make the next missing thing visible.
- Strongest case:
  - The current candidate is truthfully `ready_for_domain_adjudication`.
  - `production_activation_applied=false` is preserved.
  - Obsidian receives review/proposal packets only.
- What it sees that others miss: product legibility improves when each blocker is made concrete rather than hidden behind architecture caution.

### School 3: Runtime safety / adversarial input discipline

- Core claim: even a review-only adapter must treat generated output as adversarial.
- Premises:
  - Path confinement must happen before writes.
  - Admission flags must be internally consistent.
  - Generated behavior must not be accepted by silent fallback.
- Strongest case:
  - `doc_id` path traversal must be rejected before output construction.
  - Target judgment must exactly support domain review.
  - Candidate-root behavior must include passed evidence.
- What it sees that others miss: review admission can still be a real runtime vulnerability if input confinement is weak.

## Mode 2 — confrontation

### Authority membrane vs evidence-loop pragmatism

- Fundamental contradiction: pragmatism wants to move to domain decision; authority maximalism refuses to let fake strings become rollout readiness.
- What pragmatism explains better: why the current packet is valuable and not fake.
- What authority maximalism explains better: why final activation cannot be allowed to depend on unchecked text fields.
- Residual tension: a future AK/current-authority verifier is still needed before true rollout preflight.

### Evidence-loop pragmatism vs runtime safety

- Fundamental contradiction: evidence-loop pragmatism trusts sidecars enough to stage review; runtime safety asks whether malformed sidecars can escape confinement.
- What pragmatism explains better: why `doc:cd25bf38` may stay review-admitted.
- What runtime safety explains better: why arbitrary generated candidates must not route through the adapter until path and consistency checks are hardened.
- Residual tension: generated review packets can be useful before they are production-runtime safe.

## Mode 3 — decision

Chosen path: contextual dominance.

Result:

```text
DSPx candidate -> target-fidelity check -> DSPx/meta adjudication -> Obsidian review packet -> ready_for_domain_adjudication
```

is valid.

```text
DSPx candidate -> unchecked local decision/string binding -> production runtime rollout
```

is invalid.

## Hardening implemented

DSPx activation packet hardening:

- Oracle report must contain a record matching candidate identity.
- Behavior evidence hashes must match manifest-declared hashes.
- Target-aware candidate state must carry `target_protocol_fidelity_judgment.present=true`.
- Target-aware candidate state must carry `target_protocol_fidelity_judgment.blocking=false`.
- Target-aware candidate state judgment must equal `supports_domain_review`.
- Decision record `decided_by` must match `authority_owner`.
- A non-empty `canonical_binding_ref` no longer unlocks `ready_for_rollout_preflight`; it moves only to `ready_for_canonical_binding_verification` with `canonical_binding_verification` still listed as a blocker.

Obsidian adapter hardening was applied in the vault adapter surface:

- `doc_id` must match `doc:[A-Za-z0-9_.-]+` before any output path is created.
- Output directory must resolve under `_System/review/proposals/pdf-transition/` before any write.
- Candidate-root `behavior_results.json` must include a passed example; the previous fallback to the first example is removed.
- Candidate-state target fitness status/rendered state must match `generation_fitness_results.json`.
- Candidate-state downstream evidence review eligibility must be true.
- Target-protocol judgment must be present, non-blocking, and exactly `supports_domain_review`.
- Validator now covers path-traversal doc IDs, target judgment mismatch, and non-passed behavior rejection.

## Dogfood after DSPx hardening

Command rerun:

```bash
uv run dspx program-promote activation-packet \
  --manifest /tmp/dspx-target-fidelity-next-pdf.ZCg2c0/program/manifest.json \
  --owning-domain "obsidian/pdf-transition" \
  --activation-target "obsidian-pdf-transition-generated-program-runtime" \
  --authority-owner "obsidian-pdf-transition-governance" \
  --oracle-report /tmp/dspx-target-fidelity-next-pdf.ZCg2c0/runtime/program_oracle_report.json \
  --jury-results /tmp/dspx-target-fidelity-next-pdf.ZCg2c0/activation/jury_results.json \
  --review /tmp/dspx-target-fidelity-next-pdf.ZCg2c0/activation/promotion_review_refined.json \
  --candidate-state /tmp/dspx-target-fidelity-next-pdf.ZCg2c0/meta_adjudication/program_candidate_state.target_fidelity.json \
  --obsidian-review-adapter-receipt /home/tryinget/Documents/Obsidian/_System/review/proposals/pdf-transition/doc:cd25bf38/adapter-receipt.json \
  --require-obsidian-review-adapter \
  --rollout-owner "obsidian-pdf-transition-runtime-operator" \
  --rollback-plan "Disable the generated DSPy PDF-transition runtime route and return to deterministic review-packet materialization only." \
  --out /tmp/dspx-target-fidelity-next-pdf.ZCg2c0/activation/obsidian_pdf_activation_packet.hardened.json \
  --json
```

Observed summary:

```json
{
  "next_required_action": "record_domain_decision",
  "production_activation_applied": false,
  "remaining_activation_blockers": [
    "domain_decision_record",
    "canonical_binding_ref"
  ],
  "status": "ready_for_domain_adjudication",
  "target_review_admission_status": "review_admitted"
}
```

## Practical consequence

Do not production-activate yet.

The next legal step is still a domain decision, but after this hardening that decision cannot safely advance to rollout by pairing it with a fake binding string. A real AK/current-authority binding verifier remains the next membrane before rollout preflight.
