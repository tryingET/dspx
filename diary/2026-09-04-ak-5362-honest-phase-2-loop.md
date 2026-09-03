---
summary: "Session note for AK-5362: live typed Oracle backend, package-derived Misegraph projection, concept_coverage GEPA metric, provider_evidence_kind labelling, and the vLLM response-shape blocker on the typed port."
read_when:
  - "You are continuing the honest Misegraph->DSPx foundry loop or debugging why a live lineage over the loopback vLLM ends at failed_before_live_success."
type: "diary"
---

# 2026-09-04 — AK-5362 honest Phase 2 loop

Scope: `program_oracle_semantic_backend.py`, `model_roles.py`, `program_foundry*.py`,
`program_refinement*.py`, `program_runtime_oracle_semantic.py`, the misegraph import CLI, tests,
docs. No commit, no AK mutation, loopback-only network.

What landed (all with tests):

1. `TypedProviderOracleSemanticBackend` — live Oracle semantics over the typed
   `openai-compatible` port only; strict `_parse_analysis_text` enforcing the response-format
   enums (evidence_refs included); pre-effect rejection of bad env, disallowed providers,
   credentials, non-loopback endpoints; indeterminate effects raise and latch.
2. `derive_misegraph_expected` — concept groups and the example answer come from the package
   (`canonical.json`, `check.json`); `--answers` optional; provenance records the origin.
3. `concept_coverage` GEPA metric bound through a generated wrapper program; `exact` refused for
   concept-coverage intents; `differs:` replaces `mismatch:` for non-exact intents.
4. `provider_evidence_kind` across sidecar, foundry.json, GEPA receipt, comparison, jury request
   (weakest link); retained receipts revalidate unchanged.

Blocker found while running the honest lineage: vLLM 0.27's chat completion carries extra null
message keys and `usage.prompt_tokens_details`; `openai_compatible_provider._validated_response`
(outside this task's edit scope) rejects the shape as `completed_failure`, so every typed-port
call (program-run, Oracle, GEPA student/reflection) fails before live success. The live test
xfails with that reason; the lineage under `$ROOT/commands-run.txt` records it. Follow-up owner
surface: relax the port's message/usage key allowlist (ignore-null extras) as its own reviewed
change; until then the honest loop cannot be closed live on this server.
