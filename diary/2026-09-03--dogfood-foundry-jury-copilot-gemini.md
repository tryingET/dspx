---
summary: "AK-5346: first live receipt-bound foundry comparison jury through the GitHub Copilot family (gemini-3.7-flash); secret-free evidence projection written."
read_when:
  - "Writing or validating a secret-free evidence projection for a live foundry comparison jury."
  - "Checking how the AK-5346 Copilot lineage was built offline before the single live jury call."
type: "diary"
---

# Dogfood: foundry jury via GitHub Copilot (gemini-3.7-flash)

## What I Did

- Read the AK-5346 lineage root `misegraph-foundry-copilot-5346.DVXv7O` read-only: consumption
  receipt, candidate comparison, jury attempt/results/receipt, adjudication, execution receipt,
  three provider-outcome journals (reservation + 7 events each), both candidate manifests,
  `commands-run.txt`, `input-sha256.txt`, `exact-owner-source-root.txt`.
- Wrote `docs/project/2026-09-03-misegraph-foundry-copilot-full-dogfood-evidence.json` with the
  same top-level keys and projection discipline as the AK-5322 (gpt-5.4) file: every bound JSON
  artifact embedded with sha256 and serialization label, provider journals as event kinds and
  terminals only, closed juror outcomes, no prompts, responses, headers, tokened URLs, or
  exception text. Extra custody sub-keys record the AK evidence ids (8246, correction 8247),
  owner and DSPx commits, the two CLI outputs, and how the lineage was constructed.
- Added the dated AK-5346 section to `docs/project/2026-09-01-foundry-dspy-lm-auth-jury-integration.md`.

## Facts recorded

- Provider `foundry-dspy-lm-auth-github-copilot`, model `gemini-3.7-flash`, route
  `dspy-lm-auth:github-copilot:gemini-3.7-flash` -> `openai:gemini-3.7-flash:chat`, no reasoning
  effort, fallback and health probe disallowed, retries 0, sync only.
- Owner commit `777388ad9c692b0657e6b6e1d4820b15fcb6641d` (tree `a564fb03...`), DSPx commit
  `18db08c691db0e4a518d8d895d571eaafb5e6f70`. AK evidence 8246 carried a wrong `dspx_commit`;
  8247 corrects it without rewriting history.
- Lineage built offline: `DSPX_PROVIDER=stub`, `DSPX_ORACLE_SEMANTIC_BACKEND=fixture-replay`
  with a per-run authored fixture entry (re-keyed copy of the reference entry),
  `DSPX_REPLAY_FIXTURE_JSON` derived from the intent examples, `DSPX_TRUSTED_PROGRAM_ROOTS` on the
  lineage root. The consume step needed the operator-run hash-bound GEPA pickle opt-in
  (`optimizer_manifest_sha256` `54d02bad...`); earlier attempts are kept under
  `superseded-attempts/`. `commands-run.txt` stops before that consume step and the jury; the
  consume output and the two CLI outputs are bound by path and sha256 instead.
- Outcome: 3 jurors judged (correctness and instruction_following `supports_review_evidence`,
  robustness `request_more_evidence`), recommendation `request_more_evidence`, adjudication
  `require_review` / `held_for_local_review`. All journals end in `provider_response_completed`,
  HTTP 200, observed model `gemini-3.7-flash`, no replay.

## Verification

- JSON parses; no match for `Bearer |ghu_|PRIVATE KEY|gho_|sk-`; all 51 path/sha256 pairs in the
  file resolve to existing files with matching digests; every embedded projection re-hashes to
  its recorded sha256 under its recorded serialization.
- Nothing committed; no AK writes (only `ak task show` / `ak evidence show`); no network.

## Open

- The evidence file embeds bounded juror rationales and improvement requests verbatim, as the
  AK-5322 projection did. Both candidate manifests (~280 KB each) are bound by path and sha256
  only.
