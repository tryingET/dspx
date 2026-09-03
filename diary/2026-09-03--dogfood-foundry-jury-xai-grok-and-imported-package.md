---
summary: "AK-5358 (local vLLM through preflight + isolated child), AK-5360 (first jury on an imported Misegraph evidence package), AK-5361 (first live xAI grok-4.6 jury after AK-5349/5353 burned); three secret-free evidence projections written."
read_when:
  - "Writing or validating a secret-free evidence projection for a live foundry comparison jury, especially for the xAI family or an imported Misegraph package."
  - "Checking why AK-5349 and AK-5353 burned and what changed before AK-5361 completed."
type: "diary"
---

# Dogfood: foundry juries via xAI grok-4.6 and an imported Misegraph package

## What I Did

- Read three lineage roots read-only (`misegraph-foundry-local-vllm-5358.CYMSb7`,
  `misegraph-foundry-imported-vllm.RByYoY`, `misegraph-foundry-xai-5361.ErwrBQ`): consumption
  receipt, candidate comparison, jury attempt/results/receipt, adjudication, execution receipt,
  three provider-outcome journals each (reservation + 7 events), both candidate manifests,
  `commands-run.txt`, `consume-output.json`, fixtures and replay env; for the imported root also
  `package/`, `import/`, `answers.json`, `quality-proposal.json`, `import-output.json`,
  `import-sha256.txt`. AK reads only (`ak task show`, `ak evidence show`); no network.
- Wrote three projections with the same twelve top-level keys, `schema_version`
  `dspx-misegraph-foundry-full-dogfood-evidence-v2`, and discipline as the AK-5352 file (every
  bound JSON artifact embedded with sha256 and serialization label; journals as event kinds,
  status codes and terminals; closed juror outcomes; no prompts, responses, headers, credentials
  or exception text):
  - `docs/project/2026-09-03-misegraph-foundry-local-vllm-subprocess-dogfood-evidence.json`
  - `docs/project/2026-09-03-misegraph-foundry-imported-package-dogfood-evidence.json`
  - `docs/project/2026-09-03-misegraph-foundry-xai-full-dogfood-evidence.json`
- Generator: a scratch script adapted from the AK-5352 one (`build_3run_evidence.py` in the
  job tmp dir, not in the repo). New per-run custody blocks: `execution_path` (preflight facts
  from the live `--json` output, preflight/subprocess commits), `misegraph_import`,
  `quality_proposal_derivation`, `misegraph_recommendation_record`, `family_timeout`,
  `preceding_failed_one_shots`. `misegraph_source` for the imported run comes from
  `build_misegraph_source_projection` over the emitted binding; its `source`/`canonical`/`render`
  hashes equal the checked-in conformance fixtures used by the earlier files.
- Appended three dated sections to `docs/project/2026-09-01-foundry-dspy-lm-auth-jury-integration.md`
  and a dated posture line to `docs/project/product-posture.md`.

## Facts recorded

- AK-5358 (evidence 8255, DSPx `1ce51274`): first live jury through the pre-marker preflight
  (`54568ce2`) and the fresh `-I -B` child (`1ce51274`). Local vLLM, loopback, no credential.
  3/3 `supports_review_evidence`, `promote_locally` / `eligible_local_candidate`.
- AK-5360 (evidence 8258, DSPx `9ac6dc26`): Phase 2 closed once end-to-end. Package
  `0be06d8d5617...` exported by the committed Misegraph CLI; `dspx foundry import-misegraph-evidence`
  (`ff4b7af3`) emitted intent `959cec33...`, binding `ca97a9c1...`, provenance; answers file is a
  byte copy of the checked-in fixture (`ed24fdd6...`). The quality proposal was derived from the
  AK-5346 proposal (examples replaced, three hashes recomputed, criteria untouched) because no
  repo tool emits one offline for an existing intent. Local vLLM jury 3/3
  `supports_review_evidence`, `promote_locally`. Misegraph's `evidence verify-receipt` wrote the
  non-deciding recommendation record (`review_recommended`, `decision: null`), committed in the
  Misegraph repo at `7b884ba4`; bound by path and sha256.
- AK-5361 (evidence 8259, DSPx `9ac6dc26`): first live xAI jury, `grok-4.6`, `auth_provider: xai`,
  `credential_mode: no-refresh`, endpoint origin `https://api.x.ai`, 180 s family timeout
  (`36444b43`), no `reasoning_effort` / `response_format`. 3 calls, HTTP 200, observed model
  `grok-4.6`, no replay. 3/3 `request_more_evidence`, blocking concerns present, adjudication
  `require_review` / `held_for_local_review`, reason `jury_requests_more_evidence`.
- Burned xAI one-shots: AK-5349 (evidence 8250) HTTP 429 after one call; AK-5353 (evidence 8256)
  60 s transport timeout on the first juror, child exit 1, results object lost. Both zero
  judgments, no replay; the second motivated the result-retention and per-family-timeout fix.
- Every disposition is a bounded local one; no Misegraph acceptance, release or activation is
  granted, no winner selected, nothing applied.

## Verification

- All three JSON files parse; zero matches for `Bearer |ghu_|PRIVATE KEY|gho_|sk-`; every
  path/sha256 pair resolves to an existing file with matching digest (48, 58 and 48 unique
  pairs); all 31 embedded projections per file re-hash to their recorded sha256 under their
  recorded serialization.
- Nothing committed; no AK writes; no network.

## Open

- For the imported root the pre-authoring fixture copy could not be re-derived byte-exact from
  the current fixture (key insertion order); the projection says so and relies on
  `commands-run.txt` for that fact.
- The xAI jury's uniform `request_more_evidence` asks for more example-backed cases, edge-case
  and failure-mode evidence and hash reconciliation between behavior and runtime artifacts; this
  is review input, not a defect finding.
- AK-5358's executing DSPx commit (`1ce51274`) predates HEAD; the projection records both.
