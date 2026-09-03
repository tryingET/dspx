---
summary: "AK-5352: first live receipt-bound foundry comparison jury through the local vLLM family (local/Qwen3.8-27B-AEON-NVFP4-FP8, loopback, no credential); secret-free evidence projection written."
read_when:
  - "Writing or validating a secret-free evidence projection for a live foundry comparison jury."
  - "Checking how the AK-5352 local vLLM lineage was built offline and why it followed the failed AK-5350 one-shot."
type: "diary"
---

# Dogfood: foundry jury via local vLLM (Qwen3.8-27B-AEON-NVFP4-FP8)

## What I Did

- Read the AK-5352 lineage root `misegraph-foundry-local-vllm-5352.5V8vH2` read-only: consumption
  receipt, candidate comparison, jury attempt/results/receipt, adjudication, execution receipt,
  three provider-outcome journals (reservation + 7 events each), both candidate manifests,
  `commands-run.txt`, `input-sha256.txt`, `exact-owner-source-root.txt`, `consume-output.json`.
- Wrote `docs/project/2026-09-03-misegraph-foundry-local-vllm-full-dogfood-evidence.json` with the
  same twelve top-level keys, `schema_version`, and projection discipline as the AK-5346 Copilot
  file: every bound JSON artifact embedded verbatim with sha256 and serialization label, provider
  journals as event kinds, status codes, and terminals only, closed juror outcomes, no prompts,
  responses, headers, credentials, or exception text. Custody records AK evidence 8251 (and 8248
  for the failed predecessor), owner and DSPx commits, the adapter fix commit, the two CLI outputs,
  and how the lineage was constructed.
- Added the dated AK-5352 section to `docs/project/2026-09-01-foundry-dspy-lm-auth-jury-integration.md`,
  including the AK-5349 xAI HTTP 429 one-shot (evidence 8250) and the staged AK-5353 xAI lineage.

## Facts recorded

- Provider `foundry-dspy-lm-auth-local-vllm`, model `local/Qwen3.8-27B-AEON-NVFP4-FP8`, route
  `dspy-lm-auth:local-vllm:local:Qwen3.8-27B-AEON-NVFP4-FP8` ->
  `openai:local:Qwen3.8-27B-AEON-NVFP4-FP8:chat`, endpoint origin `http://127.0.0.1:2456`
  (base URL `/v1`), `auth_provider: none`, `credential_mode: no-refresh`, no reasoning effort,
  fallback and health probe disallowed, retries 0, sync only, 60 s timeout. The local-vllm family
  builds the owner request without `response_format`, so that field is `null` in the projection.
- Owner commit `777388ad9c692b0657e6b6e1d4820b15fcb6641d` (tree `a564fb03...`), DSPx commit
  `1c120c3b07b4e9b191089413673d7e64dc95affd`, which contains the bare-judgment tolerance fix
  `caf9a1abb528eb947cb448242ba2699334cec9ce`. The preceding one-shot AK-5350 (evidence 8248,
  DSPx `18db08c6...`) completed one HTTP 200 call and then failed in the JSON adapter because the
  model returned the judgment object bare; this lineage is the first local vLLM run after the fix.
- Lineage built offline: `DSPX_PROVIDER=stub`, `DSPX_ORACLE_SEMANTIC_BACKEND=fixture-replay`
  with a per-run authored fixture entry (`5d9f445f...`, reference entry re-keyed on
  `request_sha256`, earlier keys retained), `DSPX_REPLAY_FIXTURE_JSON` derived from the intent
  examples, `DSPX_TRUSTED_PROGRAM_ROOTS` on the lineage root. The consume step was operator-run
  with the hash-bound GEPA pickle opt-in (`optimizer_manifest_sha256`
  `0af3fe4127acbcc1d894ff9749ad7cdc183b2001fe7215f758538dad437e0019`); the first foundry attempt
  (missing fixture entry, rc 2) is kept under `superseded-attempts/`. `commands-run.txt` stops
  before the consume step and the jury; the consume output and the two CLI outputs
  (`jury-vllm2.json`, `adjudication-vllm.json`) are bound by path and sha256 instead.
- Outcome: 3 jurors judged `supports_review_evidence` (all three at `medium`
  confidence), recommendation
  `supports_review_evidence_only`, adjudication `promote_locally` / `eligible_local_candidate`,
  reason `all_jurors_support_review_evidence`. All journals end in `provider_response_completed`,
  HTTP 200, observed model `local/Qwen3.8-27B-AEON-NVFP4-FP8`, no replay, loopback only.
- `promote_locally` is recorded in `non_authority` as a bounded local disposition: no Misegraph
  acceptance, release, or activation is granted, no winner is selected, nothing is applied.

## Verification

- JSON parses; no match for `Bearer |ghu_|PRIVATE KEY|gho_|sk-`; all 51 unique path/sha256 pairs
  in the file resolve to existing files with matching digests; all 31 embedded projections
  re-hash to their recorded sha256 under their recorded serialization.
- Nothing committed; no AK writes (only `ak task show` / `ak evidence show`); no network.

## Open

- The evidence file embeds bounded juror rationales and improvement requests verbatim, as the
  AK-5346 projection did. Both candidate manifests are bound by path and sha256 only.
- AK-5353 (xAI, `grok-4.6`) is claimed with a fresh lineage staged; it runs only once xAI capacity
  is stable.
