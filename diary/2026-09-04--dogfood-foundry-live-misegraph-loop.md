---
summary: "AK-5365: first fully live Misegraph foundry loop (package-derived import, live program-run, live Oracle, concept-coverage GEPA with metric_honesty, live local vLLM jury); secret-free projection written with the two preceding hollow/burned attempts bound."
read_when:
  - "Writing or validating a secret-free evidence projection for a fully live foundry loop, or checking which link of the Misegraph loop is still hollow."
  - "Checking why the AK-5362 and first AK-5365 lineages did not reach a jury and what AK-5364 and AK-5366 fixed."
type: "diary"
---

# Dogfood: first fully live Misegraph foundry loop (AK-5365)

## What I Did

- Read lineage root `misegraph-foundry-honest-5366.RZzphH` read-only: `package/`, `import/`
  (binding, provenance with `answers.origin: package_derived`, emitted intent and inputs),
  `foundry/foundry.json`, the live Oracle sidecar `foundry/runtime/program_oracle_semantic.json`,
  the GEPA proposal, `gepa-experiment/` (execution receipt, consumption receipt, candidate
  comparison, jury attempt/results/receipt, adjudication, optimizer manifest with its
  `metric_honesty` block, materialized candidate lineage, three provider-outcome journals with
  reservation plus seven events each), `commands-run.txt`, `run_all.sh`, `env.sh`,
  `consume-output.json`, the quality-proposal derivation script and output. Also the CLI outputs
  `jury-honest.json` / `adjudication-honest.json` in the job tmp dir, the Misegraph live
  recommendation record, and the two preceding roots `misegraph-foundry-honest-5362.NtdPDD` and
  `misegraph-foundry-honest-5365.uMYFWr`. AK reads only (`ak task show 5365`, `ak evidence show
  8265`, plus 5360/5362/5364/5366 task reads); no network; nothing committed.
- Wrote `docs/project/2026-09-04-misegraph-foundry-live-loop-dogfood-evidence.json` with the same
  twelve top-level keys, `schema_version` `dspx-misegraph-foundry-full-dogfood-evidence-v2` and
  discipline as the AK-5360 file (every bound JSON artifact embedded with sha256 and serialization
  label; journals as event kinds, status codes and terminals; closed juror outcomes; no prompts,
  responses, headers, credentials or exception text). Generator: a scratch script
  (`build_honest_evidence.py` in the job tmp dir, not in the repo) adapted from the AK-5358/5360/5361
  one, with assertions tying the AK evidence hashes, the CLI outputs, the receipts, the optimizer
  manifest and the Misegraph record together.
- New custody blocks for this run: `provider_evidence_kind` (program_run, oracle_semantic, GEPA
  receipt, comparison links, jury execution_request: all `live`; foundry.json's gepa link is null
  because it is written before GEPA executes), `oracle_semantic` (closed sidecar facts; the
  model-authored analysis is bound by path and sha256 only), `gepa_execution` (`metric_honesty`
  plus the four cross-checks, closed run stats, candidate-equals-source evidence),
  `preceding_attempts` (AK-5360 hollow stub lineage via its projection, AK-5362 blocked lineage
  with both sidecars bound, the burned `5365.uMYFWr` consume with its attempt marker, execution
  receipt and optimizer manifest bound), `caveats`, and a `lineage_construction` whose fixture and
  replay bindings are explicitly null with `mode: live_end_to_end_lineage`.
- Appended a dated section to `docs/project/2026-09-01-foundry-dspy-lm-auth-jury-integration.md`
  and a dated posture bullet to `docs/project/product-posture.md`.

## Facts recorded

- Every link live: import with package-derived expectations (binding `e97f0080...`, intent
  `6acb0d91...`), program-gen/program-run on the loopback vLLM through the typed openai-compatible
  port, Oracle `succeeded` with one recommended experiment and `fixture_sha256: null`, GEPA
  `completed` with four metric calls under the `concept_coverage` metric bound to
  `misegraph_recipe_fidelity`, consume verifying `metric_honesty` (`wrapper` `2454e901...`,
  `source` `ecbb8c7c...`, `criteria` `57e44042...`, optimizer manifest `8d5701c2...`), jury via
  dspy-lm-auth 0.1.6 (`80cc409d`) through preflight and the isolated child: 3 calls, HTTP 200,
  `provider_response_completed`, no replay, zero retries; 3/3 `supports_review_evidence`
  (`medium`), `promote_locally` / `eligible_local_candidate`. Jury receipt `634a9fe4...`,
  adjudication `7745f747...`, both equal to AK evidence 8265's details.
- Misegraph record: `espresso-brownies-0be06d8d5617-jury-recommendation-live.json` (`9c880c61...`,
  Misegraph commit `12fd8810`), policy `live_evidence_required_v1`, `review_recommended`,
  `decision: null`, `requires_owner_action: true`.
- Caveats: GEPA retained one candidate and accepted nothing (every score 1.0), so the
  materialized candidate is a loader wrapper over the unchanged base program (module.py
  byte-identical to the source; program.py files differ because the wrapper loads the optimizer
  output) and the jury compared A to A. The quality-proposal envelope's `model_execution` is the
  AK-5346 injected test double re-bound to the package-derived intent: the remaining hollow link.
  `differs:answer` persists non-blocking on both sides; `needs_more_evidence: true`.
- Preceding attempts: AK-5362 lineage blocked at the Oracle stage (canonical sidecar
  `indeterminate` at 180 s; 600 s retry sidecar `failed_before_live_success` because the typed
  port rejected vLLM 0.27 reply shapes; foundry exit 2; fixed by AK-5364 `c9a52177`). First AK-5365
  lineage `uMYFWr` completed live through GEPA (three recommended experiments, four metric
  calls, no candidate) and burned at consume: attempt marker `effect_possible`, no receipt, empty
  consume output, optimizer manifest hashing the generated wrapper rather than the source
  program (fixed by AK-5366 `e629be74`). Neither replayed anything.
- DSPx commit at jury and projection time `2ccfbe65` (AK evidence); lineage constructed at
  `d8348fce` plus the then-uncommitted AK-5366 fix, recorded in `commands-run.txt`.
- Bounded local disposition only; no Misegraph acceptance, release or activation granted.

## Verification

- JSON parses (131,424 bytes); zero matches for the five secret patterns (bearer prefix, GitHub
  user/OAuth token prefixes, private-key marker, OpenAI-style key prefix);
  all 71 unique path/sha256 pairs resolve to existing files with matching digests; all 31 embedded
  projections re-hash to their recorded sha256 under their recorded serialization.
- `uvx prek run --files` over the four changed files.
- Nothing committed; no AK writes; no network.

## Open

- The quality-proposal acceptance envelope is still a re-bound test double; a live
  quality-criteria model call for an imported intent needs a repo tool that does not yet exist
  offline.
- A GEPA budget of four metric calls cannot propose a candidate when every subsample already
  scores 1.0 on the package-derived criterion; a real improvement comparison needs either a larger
  budget or a criterion the base program does not already satisfy.
- The jury's uniform improvement requests (more examples, diff analysis for `differs:answer`,
  failure-mode logs) are review input, not defect findings.
