---
summary: "Freeze the first ranked-synthesis evidence retrieval contract for SG2."
read_when:
  - "You are implementing V8 evidence retrieval or ranked-synthesis priors."
  - "You need the exact receipt, replay, and Oracle surfaces SG2 consumes first."
---

ADR 20260323 — Synthesis Evidence Retrieval Contract V1
=======================================================

Status
------
Accepted

Context
-------
`SG1` is materially complete: `module-gen` now runs through an explicit V7 synthesis runtime, emits ranked-selection receipts, and is guarded by deterministic quality checks.

The next active strategic goal (`SG2`) is to turn receipts, replay, and Oracle history into the evidence substrate for future V8/V9 behavior. But those surfaces are broad enough that implementation could easily drift:
- receipts now contain both generic replay metadata and synthesis-specific ranked-selection details,
- replay/explain exposes local integrity facts and drift status,
- Oracle can search many indexed executions, not all of which should influence ranked synthesis first.

Before DSPx implements any predictive ranking or policy evolution, it needs a frozen, dated contract for **which evidence surfaces ranked module synthesis will retrieve first**, in what order, and under what health rules.

Decision
--------
Adopt **Synthesis Evidence Retrieval Contract V1** as the first SG2 evidence bundle for ranked module synthesis.

## Scope

This contract applies only to the first evidence-aware extension of the existing `module-gen` synthesis runtime.

It is intentionally:
- local-first,
- read-only,
- module-generation-specific,
- replay-health-gated,
- non-predictive.

It does **not** authorize predictive ranking, automatic policy mutation, or self-evolving strategy changes.

## Retrieval unit

The retrieval unit is a **module synthesis evidence bundle** keyed by the current request tuple taken from `receipt.replay_inputs`:
- `name`
- `description`
- `inputs`
- `outputs`
- `use_signature`
- `template_version`

V1 retrieval starts with exact request matching on that tuple.
Semantic expansion is allowed only as a secondary Oracle step after exact-match receipt retrieval.

## Surface 1 — module-gen receipt evidence

The first evidence source is prior local `module-gen` run receipts whose `run_summary.backend == "synthesis_runtime"`.

V1 must retrieve, at minimum, these fields from each eligible receipt:
- receipt identity/path:
  - `receipt_path`
  - `created_at`
  - `run_kind`
  - `provider`
  - `template_version`
- request match inputs:
  - `replay_inputs.name`
  - `replay_inputs.description`
  - `replay_inputs.inputs`
  - `replay_inputs.outputs`
  - `replay_inputs.use_signature`
  - `replay_inputs.template_version`
- artifact linkage:
  - `output_path`
  - `hash`
  - `cache_key`
- ranked-synthesis summary:
  - `run_summary.selected_candidate_id`
  - `run_summary.selected_candidate_rank`
  - `run_summary.ranked_candidate_ids`
  - `run_summary.ranking_policy_id`
  - `run_summary.ranking_policy_version`
  - `run_summary.validation_pass_count`
  - `run_summary.validation_total`
  - `run_summary.smoke_pass_count`
  - `run_summary.smoke_total`
  - `run_summary.evaluation_status`
  - `run_summary.promotion_status`
  - `run_summary.promotion_outcome`
- synthesis detail surfaces already emitted into the receipt extra payload when present:
  - `synthesis`
  - `synthesis_request_id`
  - `synthesis_candidate_ids`
  - `synthesis_evaluation_ids`
  - `synthesis_selection_policy`
  - `synthesis_ranked_candidates`
  - `synthesis_promotion_shell`
  - `synthesis_promotion_decision`

### Receipt eligibility rule

A receipt is eligible for V1 retrieval only if all of the following hold:
- `run_kind == "module-gen"`
- `run_summary.backend == "synthesis_runtime"`
- the request tuple matches exactly
- a selected candidate is recorded
- ranked-selection fields are present enough to explain the winner

## Surface 2 — replay verification evidence

For every retrieved receipt, V1 must also retrieve replay-health facts from the existing local replay services (`check_run_receipt()` and/or `explain_run_receipt()`).

The minimum replay evidence is:
- `replay_status`
- `replay_checks`
- `local_facts.output_path`
- `local_facts.output_hash`
- `local_facts.cache_key`
- `local_facts.cache_file`
- `local_facts.failed_replay_checks`
- `replay_error_codes`
- `replay_error_details`

### Replay health rule

Only receipts with `replay_status == "ok"` and no failed replay checks count as **positive evidence** for later ranking/pruning.

Receipts with degraded or failed replay state may still be returned in the bundle for diagnostics, but they must be marked as unhealthy and must not silently influence future predictive scoring.

## Surface 3 — Oracle evidence

After exact-match receipts are collected, V1 may expand context with Oracle neighbors derived from the same request text that Oracle embeddings already extract from `replay_inputs`.

V1 Oracle retrieval is limited to `module-gen` executions and returns, at minimum:
- `run_id`
- `similarity`
- `distance`
- `embedding.run_kind`
- `embedding.provider`
- `embedding.template_version`
- `embedding.source_path`
- `embedding.metadata.cache_key`
- `embedding.metadata.receipt_identity`

### Oracle role in V1

Oracle neighbors are **contextual hints**, not authority.
They help the future V8 layer find nearby prior executions, but in V1 they do not override exact-match receipt evidence and they do not trigger policy changes.

## Retrieval order and trust model

V1 ranked synthesis must consume evidence in this order:
1. exact-match `module-gen` synthesis receipts,
2. replay verification facts for those receipts,
3. Oracle neighbors constrained to `module-gen`.

Trust is monotonic:
- receipt summary explains what happened,
- replay verification proves the receipt still matches the artifact/cache state,
- Oracle adds similarity context only after the first two surfaces are available.

## Explicit exclusions

This contract explicitly defers:
- MLflow remote lookup as a required evidence surface,
- Oracle territory/attractor/frontier analysis in the critical path,
- Oracle behavioral-contract evaluation as ranking input,
- predictive ranking or candidate pruning from priors,
- strategy/policy mutation or any V9-style self-evolution.

## First execution slice aligned to this contract

The first AK-backed implementation slice after this ADR is:
- `AK-274` — **Synthesis evidence substrate: implement the v1 evidence retrieval bundle for ranked module synthesis**

That slice should materialize a read-only retrieval service/helper that returns contract-shaped evidence bundles without changing ranked-selection behavior yet.

Consequences
------------
Positive:
- SG2 now has a dated, referenceable contract for the first evidence bundle instead of relying on oral history.
- Future implementation can stay local-first by reusing existing receipt, replay, and Oracle surfaces.
- Replay health is promoted to an explicit trust boundary before any predictive use of history.
- Oracle is kept useful but bounded: contextual evidence first, not autonomous scoring authority.

Costs / tradeoffs:
- The first evidence-aware slice is narrower than the total Oracle/replay surface area available in the repo.
- Exact request matching may miss semantically similar historical runs until later iterations refine the retrieval policy.
- Some existing evidence sources stay intentionally unused for now to keep the contract stable and auditable.
