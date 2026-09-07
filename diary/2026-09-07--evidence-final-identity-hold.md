---
summary: "AK-5511 final identity HOLD: preserve parent patch, canonical precedence regressions and corrected 16-file profile."
read_when:
  - "Reviewing the final comparison identity correction after f460b082."
---

# Final identity correction — SHIP candidate, not provisioning approval

Inspected the dirty diff at dispatch start: only the parent's
program_foundry_closure_gepa.py patch was present. Preserved it unchanged. Both
comparison identities now use canonical identity(manifest), with explicit
comparison_manifest_identity rejection, instead of selecting receipt_bundle alone.
No other source implementation, schema, policy or historical profile changed.

Added 52 tests across source/candidate and all four precedence-bearing fields:
request_id, candidate_id, assembly_id, episode_id. Every fallback matches the
original comparison and model-jury producers. Canonical identities succeed despite
lower-priority shadow fields. Shadow comparison identities fail; shadow jury results
cannot agree with canonical comparison identity; even a mutually agreeing shadow
comparison/jury pair fails the canonical manifest gate.

Proof distinction: identity-only component tests use a labelled in-memory snapshot
view and execute the real GEPA/jury functions. Original hashes do not bind that
altered view; successes are not claimed as byte-closure proof. Separate isolated
capsule mutants modify copied sidecars and preserve subject/seven expected roots.
Those assert custody rejection, not a proxy for the semantic identity check.

Observed validation:
- New identity tests: 52 passed.
- Focused closure/comparison: 300 passed.
- Expanded foundry/runtime/trace/GEPA/comparison/quality slice: 960 passed.
- Imported-vLLM optional audit: 13 passed; no original evidence changed.
- CI-quality passed including package/test typechecking and format/lint.
- Verify-fast passed, including exact task-scope binding and all-file hooks.
- All 16 module hashes match the updated single protocol manifest.
- Full offline heavy-job gate was not rerun or bypassed; its previously recorded
  protected-process reference-inspection blocker remains unresolved. No full-gate
  pass or independent corrected SHIP is inferred from selected-suite results.

Source delta: -9 LOC; tests +182 LOC. No new runtime code beyond the parent patch.
Current profile: 726ad977b188bbaa57e72f59cdec2ca485fbde299fe7e7e019927c5d8d2d678f.
Only the GEPA module hash changed in the existing 16-file installation. Entry point,
wire protocol and claim ceilings remain unchanged. Prior held profiles must not be
provisioned; independent review of the committed candidate precedes consumer trust.
No live effects, auth repin change, target mutation, push or task completion.
