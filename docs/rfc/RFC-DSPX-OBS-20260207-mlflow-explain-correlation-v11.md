---
summary: "DSPx-owned observability RFC draft for MLflow explain correlation contract v1.1 and opt-in remote lookup."
read_when:
  - "You need DSPx-side decision details for explain enrichment and MLflow correlation tags."
  - "You are implementing or reviewing `dspx run explain --with-mlflow` contract changes."
---

# RFC: DSPx Observability Next

## 0) Metadata

- RFC ID: `RFC-DSPX-OBS-20260207-mlflow-explain-correlation-v11`
- Status: `draft`
- Owner: `lightningralf (DSPx)`
- Reviewers: `DSPx core reviewers`, `MLflow liaison`, `DSPy liaison`
- Created: `2026-02-07`
- Target milestone: `2026-02-14 observability-architecture-kickoff`
- Related docs:
  - `docs/ARCH_DRAFT_DSPX_NEXT.md`
  - `docs/MLFLOW_OBSERVABILITY_PLAN.md`
  - `docs/RUN_REPLAY_EXPLAIN.md`

## 1) Problem statement

Current local-first explain behavior is stable, but MLflow enrichment still has two practical gaps:
- remote backend linkage is best-effort with low precision and limited operator insight
- run correlation schema is not standardized enough to keep matching deterministic as scale/cardinality grows

Impact:
- explain can only provide weak MLflow context for remote tracking setups
- operator diagnosis is slower when enrichment degrades
- downstream automation cannot rely on a stable machine-readable MLflow diagnostics contract

## 2) Scope / non-goals

### In scope
- DSPx correlation contract v1.1 (tags + receipt hints)
- deterministic explain enrichment pipeline ordering
- optional remote lookup path that never blocks explain baseline
- stable `mlflow_context` diagnostics taxonomy

### Out of scope
- patching MLflow internal callback/tracing behavior (upstream ownership)
- patching DSPy callback runtime contract (upstream ownership)
- making MLflow required for replay/explain correctness

### Invariants (must not break)
- replay/explain local-first baseline remains source of truth
- MLflow enrichment never blocks explain baseline
- boundary invariant: no `core -> apps/*` imports

## 3) Current state evidence

- existing behavior:
  - local sqlite-only tracking support implemented for DSPx alpha
  - unsupported filesystem-tracking diagnostics implemented for `file:...` and bare local path tracking URIs
  - sqlite custom artifact-root fallback via experiment metadata implemented
  - run metadata fallback via `MlflowClient.get_run(...)` when local artifact-side metadata is missing
- metrics/logs/tests proving gap:
  - remote URI path degrades by design, with no high-confidence correlation contract yet
  - no formalized diagnostics reason-code set for enrichment-specific degradations

## 4) Option analysis (A/B/C)

### Option A: Keep local-only enrichment and diagnostics hardening only
- Design: no remote lookup support; improve local diagnostics contract only.
- Pros:
  - lowest implementation and operational risk
  - no remote-query cost concerns
- Cons:
  - remote tracking users remain under-served
  - no path to higher-confidence remote context
- Risks:
  - repeated custom downstream scripts for remote environments

### Option B: Correlation contract v1.1 + opt-in remote lookup + deterministic diagnostics
- Design:
  - standardize DSPx tags (`dspx.run_kind`, `dspx.template_version`, `dspx.output_basename`, `dspx.cache_key`, `dspx.output_hash_prefix`)
  - enforce tag normalization + cardinality guardrails (fixed enums/length caps/hash prefixes; no raw paths)
  - add optional receipt hints (`mlflow_hints.*`) without breaking v1 receipt compatibility
  - add explicit remote lookup phase behind opt-in flag with deterministic candidate caps/time budgets
  - emit stable diagnostics fields in `mlflow_context`
- Pros:
  - balanced confidence vs complexity
  - keeps local-first guarantees intact
  - remote support available without forcing defaults
- Cons:
  - more implementation/test surface than Option A
  - conservative remote caps/timeouts can miss late-indexed runs on very large remote backends
- Risks:
  - false-negative enrichment if caps are tuned too tightly for tenant volume
  - automation churn if reason-code ordering/stability is not governed as a contract

### Option C: Require explicit MLflow run IDs in receipts for correlation
- Design: enforce receipt linkage to MLflow run id for all logged runs.
- Pros:
  - maximal correlation precision when available
- Cons:
  - couples replay/explain UX too tightly to MLflow lifecycle details
  - harms offline/backfill and non-MLflow flows
- Risks:
  - contract rigidity and migration burden for historical artifacts

## 5) Decision

- Chosen option: `B`
- Rationale:
  - delivers meaningful remote improvement while preserving local-first invariants
  - avoids hard MLflow coupling in core replay contract
  - keeps migration additive via optional hints + stable diagnostics schema
- Rejected alternatives and why:
  - `A` rejected: insufficient for remote-operating teams
  - `C` rejected: too coupled to MLflow identity semantics

## 6) Target architecture

### 6.1 Interfaces/contracts

Contract deltas:
- run tags schema (new standard keys + value contract):
  - `dspx.run_kind`: required enum (`signature-gen|signature-refine|module-gen|codegen|other`); unknown values normalize to `other`
  - `dspx.template_version`: required normalized slug (`[a-z0-9._-]`, max 32 chars); invalid/missing normalize to `unknown`
  - `dspx.output_basename`: required basename only (no directory separators, max 64 chars); invalid/missing normalize to `unknown`, overflow uses deterministic truncate + 8-hex suffix
  - `dspx.cache_key`: optional deterministic hash key (expected 64 hex); high-cardinality, never used as first-pass remote filter
  - `dspx.output_hash_prefix`: required fixed 12 hex chars; disambiguation-only field (not broad listing)
- cardinality/query guardrails:
  - remote search must include at least one low-card filter (`dspx.run_kind`) before applying high-card discriminators
  - first-pass remote filter set is limited to `dspx.run_kind`, `dspx.template_version`, and (if present) `dspx.output_basename`
  - `dspx.cache_key` and `dspx.output_hash_prefix` are candidate-verification fields, not paging keys
  - tag contract violations sanitize/drop offending values and emit `mlflow_tag_contract_violation`; explain baseline still succeeds
- receipt hints block (optional):
  - `mlflow_hints.tracking_uri_observed`
  - `mlflow_hints.output_hash_prefix`
  - `mlflow_hints.expected_tags`
- remote lookup execution contract (opt-in only):
  - default `candidate_cap=25`, hard max `100`
  - max remote page fetches per explain: `5`
  - per-call timeout budget: `1000ms`; end-to-end remote lookup budget: `3000ms`
  - deterministic candidate order: `start_time desc`, then `run_id asc`
  - budget exhaustion degrades enrichment (never baseline explain) with explicit reason code
- `mlflow_context` fields:
  - `lookup_mode` (`local-scan|remote-search|disabled`)
  - `lookup_steps` (ordered list)
  - `degrade_reason_codes` (stable ordered unique list)
  - `reason_code_version` (`v1`)
  - `candidate_count`
  - `matched_count`
  - `remote_candidate_cap`
  - `remote_time_budget_ms`
  - `remote_elapsed_ms`
- reason-code taxonomy (v1 precedence order):
  - `mlflow_disabled`
  - `mlflow_remote_lookup_not_enabled`
  - `mlflow_remote_auth_unavailable`
  - `mlflow_remote_time_budget_exceeded`
  - `mlflow_remote_search_failed`
  - `mlflow_remote_candidate_cap_reached`
  - `mlflow_remote_no_candidate`
  - `mlflow_remote_multi_candidate`
  - `mlflow_tag_contract_violation`
- reason-code governance policy:
  - codes are immutable contract strings; no semantic reuse
  - `degrade_reason_codes` is ordered-unique; first code is primary automation key
  - when multiple degradations apply, emit codes by the v1 precedence table above (never by exception arrival order)
  - v1 additions are append-only (no reorder/removal for existing codes)
  - deprecation requires replacement mapping + dual-emit window of `>=2` minor releases
  - rename/removal requires `reason_code_version` bump with migration notes

### 6.2 Data model / payload examples

Before (excerpt):
```json
{
  "mlflow_context": {
    "status": "degraded",
    "notes": ["remote uri mode is best-effort"]
  }
}
```

After (excerpt):
```json
{
  "mlflow_context": {
    "status": "degraded",
    "lookup_mode": "remote-search",
    "lookup_steps": [
      "baseline-local-replay",
      "remote-tag-search",
      "candidate-artifact-check"
    ],
    "degrade_reason_codes": ["mlflow_remote_no_candidate"],
    "reason_code_version": "v1",
    "candidate_count": 0,
    "matched_count": 0,
    "remote_candidate_cap": 25,
    "remote_time_budget_ms": 3000,
    "remote_elapsed_ms": 412
  }
}
```

## 7) Rollout plan

### Global rollout guardrails
- remote lookup remains default-off for the full RFC rollout window
- each phase requires explicit go/no-go from RFC owner + one core reviewer
- rollback trigger (any phase): local-first explain baseline regression or nondeterministic diagnostics under fixed fixtures

### Phase 1 (target: 2026-02-10)
- implementation:
  - add standardized `dspx.*` tags at run-start/log call sites
  - enforce tag normalization/sanitization at emit-time
  - add optional receipt `mlflow_hints` emission
- tests:
  - tag emission coverage for signature/module/codegen paths
  - tag contract violation tests (sanitize/drop + reason code emission)
  - receipt compatibility tests (legacy + v1)
- docs:
  - update `docs/MLFLOW_OBSERVABILITY_PLAN.md` and `docs/RUN_REPLAY_EXPLAIN.md`
- exit gate:
  - `dspx.output_hash_prefix` fixed at 12 hex in all writer fixtures
  - no raw path separators in `dspx.output_basename` fixtures
  - legacy receipt readers pass unchanged

### Phase 2 (target: 2026-02-12)
- implementation:
  - add `--mlflow-remote-lookup` opt-in phase in explain service
  - implement bounded remote lookup (`candidate_cap`, `page_cap`, `time_budget_ms`, per-call timeout)
  - apply deterministic candidate ordering (`start_time desc`, `run_id asc`)
- tests:
  - mocked `MlflowClient` pagination/auth/timeout/failure tests
  - explicit cap/time-budget degrade reason assertions
  - deterministic degrade-reason ordering assertions
- docs:
  - CLI examples in `README.md`
- exit gate:
  - remote lookup adds `<=3000ms` in bounded-path integration benchmark
  - page iteration bounded (`<=5` pages) under adversarial fixtures
  - timeout/cap exhaustion degrades enrichment only (never baseline explain)

### Phase 3 (target: 2026-02-14)
- implementation:
  - stabilize diagnostics taxonomy + JSON examples
  - finalize operator troubleshooting notes with first-look triage order
- tests:
  - regression tests pin reason-code set/order + `reason_code_version`
  - golden snapshot tests for deterministic `mlflow_context` payloads
- docs:
  - update `PROJECT_STATUS.md` + `NEXT_STEPS.md`
- exit gate:
  - Section 9 deterministic diagnostics acceptance criteria all pass
  - automation-consumer smoke test passes against v1 reason-code snapshot

## 8) Compatibility and migration

- backward compatibility strategy:
  - all new receipt hints are optional and additive
  - legacy top-level receipt keys remain unchanged
  - new `mlflow_context` fields are additive; consumers must ignore unknown fields/codes
- feature flags / defaults:
  - remote lookup remains opt-in (`off` by default)
  - bounded remote lookup knobs (`candidate_cap`, time budgets) tune opt-in path only
- diagnostics compatibility posture:
  - `reason_code_version` starts at `v1`
  - unknown future reason codes must not fail explain consumers; treat as degraded-but-parseable
- deprecation plan (if any):
  - none in this RFC (only additive v1.1 changes)

## 9) Validation plan

Required checks:
- `pre-commit run --all-files`
- `just monorepo-check`
- `just test`

Add focused tests:
- `tests/test_run_explain_service.py`: remote lookup opt-in/off, cap/timeout handling, deterministic reason ordering
- `tests/test_mlflow_tracking_uri_modes.py`: remote URI + tag correlation narrowing behavior
- `tests/test_run_explain_diagnostics_contract.py`: snapshot `reason_code_version`, allowed code set, and ordered-unique invariants

Acceptance criteria (deterministic diagnostics):
- same receipt + same mocked MLflow responses produce byte-stable `mlflow_context` payloads
- `lookup_steps` is emitted from a fixed allow-list and in pipeline order only
- `degrade_reason_codes` is ordered-unique and uses the v1 precedence table
- cap exhaustion emits `mlflow_remote_candidate_cap_reached`; time budget exhaustion emits `mlflow_remote_time_budget_exceeded`
- deterministic candidate tie-break (`start_time desc`, `run_id asc`) is covered by tests
- remote-disabled path performs zero remote client calls and still returns baseline explain output
- explain exit-code contract remains unchanged (`0` success/degraded, `2` invalid input/receipt)

## 10) Operational impact

- expected runtime/storage cost impact:
  - no cost increase on default path
  - remote lookup costs are bounded when opt-in is used (`candidate_cap=25` default, `<=5` pages, `<=3000ms` budget)
- failure/degraded modes:
  - remote auth/network/timeout/cap failures degrade enrichment only
  - local-first replay/explain baseline remains available regardless of MLflow state
- operator diagnostics (first-look triage order):
  1. `mlflow_context.lookup_mode`
  2. `mlflow_context.degrade_reason_codes[0]` (primary reason)
  3. `mlflow_context.lookup_steps` (last completed phase)
  4. `mlflow_context.candidate_count` vs `matched_count`
  5. `mlflow_context.remote_elapsed_ms` vs `remote_time_budget_ms`
- quick triage map:

| Primary reason code | Likely cause | First operator action |
|---|---|---|
| `mlflow_remote_lookup_not_enabled` | flag omitted/default-off | re-run with `--mlflow-remote-lookup` if remote context is needed |
| `mlflow_remote_auth_unavailable` | missing/expired remote creds | validate MLflow auth env/secret mount |
| `mlflow_remote_time_budget_exceeded` | high remote latency/backend load | re-run once, then increase budget only if repeated and justified |
| `mlflow_remote_candidate_cap_reached` | query still too broad | tighten low-card tags; inspect `dspx.template_version`/`dspx.output_basename` quality |
| `mlflow_remote_no_candidate` | no matching run in bounded set | verify tags on producer side; confirm tracking URI scope |
| `mlflow_remote_multi_candidate` | ambiguous matches | use `output_hash_prefix` + artifact checks; inspect candidate set |
| `mlflow_tag_contract_violation` | malformed/surprising tag value | fix emitting call site normalization; keep explain baseline as source of truth |

## 11) Risk register

| Risk | Trigger | Mitigation | Rollback |
|---|---|---|---|
| high-cardinality tags | unbounded/path-derived tag values | strict tag value contract + sanitize/drop + `mlflow_tag_contract_violation` | disable remote lookup path; keep local-first baseline |
| remote query overhead/latency | broad run listing or slow remote backend | low-card filter-first + candidate/page/time caps + timeout reason codes | keep remote lookup opt-in/off; lower caps to safe defaults |
| deterministic diagnostics drift | ad-hoc reason-code additions/reordering | governance policy + snapshot tests + `reason_code_version` pinning | block release; revert to prior reason-code snapshot |
| false-negative enrichment | caps/time budgets too strict for tenant volume | expose cap/time diagnostics; allow opt-in tuning within hard max | tenant-local override on opt-in path only |

## 12) Cross-team dependencies

- Upstream MLflow dependency:
  - issue placeholder: `mlflow/mlflow#TBD-span-noop-safety`
  - issue placeholder: `mlflow/mlflow#TBD-dspy-callback-concurrency`
- Upstream DSPy dependency:
  - issue placeholder: `stanfordnlp/dspy#TBD-callback-metadata-envelope`
- Sequencing constraints:
  1. finalize DSPx tag/hint schema
  2. open upstream issues with schema references
  3. implement remote lookup using stable DSPx-owned tags first
  4. tighten defaults only after upstream fixes are released/validated

## 13) Open questions / decisions needed

- Q1 (resolved for v1.1): `dspx.output_hash_prefix` is fixed at 12 hex; revisit only if collision evidence appears in production telemetry.
- Q2: Should remote lookup remain CLI-flag-only, or gain env-based default for remote URIs?
- Q3: Should explain expose enrichment confidence thresholds (`warn/error`) in a strict mode?

## 14) Execution checklist

- [x] implementation PRs scoped
- [ ] tests added/updated
- [ ] docs synced (`README`, `PROJECT_STATUS`, `NEXT_STEPS`, domain docs)
- [x] rollout owner assigned
