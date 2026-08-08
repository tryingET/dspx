---
summary: "Credential-free DSPy 3.3 compatibility probe and adoption decision packet for AK-4693."
read_when:
  - "Before changing DSPx's DSPy/DSPy-AI/GEPA dependency window."
  - "When planning the ProgramOfThought, generated-smoke, custom-LM, GEPA, or ReActV2 compatibility slices."
  - "When reviewing whether DSPx may move its canonical lock to DSPy 3.3."
type: "evidence"
---

# DSPy 3.3 compatibility probe and adoption decision packet

## Status and authority

Status: independently accepted AK-4693 compatibility report and adoption decision packet. Probe source HEAD: `d731f5eb064019885288c132224cc44635972a9b`; tree: `451b925d85cbc36c9da9fd27566d550359baeec3`. Final exact-report review: `ACCEPT`; adversarial falsification after reconstruction evidence: `PASS`.

This report is credential-free compatibility evidence for [DSPy 3.3 and trusted-local Core production implementation frame](dspy-3-3-trusted-local-core-production-frame.md). It is not a dependency change, architecture decision, release-readiness claim, provider-quality claim, or production authorization. AK owns the task and any later adoption decision.

AK-4693 changed only this report and `governance/task-scopes/AK-4693.snapshot.json` in the canonical checkout. All dependency, environment, build, installed-wheel, and executable probing occurred in one owned `TMPDIR`-backed local clone at the exact source HEAD. The canonical `pyproject.toml`, package metadata, `uv.lock`, source, tests, providers, receipts, peer-owned work, release state, and publication state were not changed.

## Selected decision

**Disposition: `cap_current_range_pending_repairs`.**

Do not move the canonical lock to DSPy 3.3 yet. First:

1. protect downstream consumers with exact currently proven DSPy/DSPy-AI 3.1.3 direct bounds rather than the current open alias lower bound;
2. complete separately attributable ProgramOfThought and generated-smoke compatibility repairs;
3. complete broader custom-LM bridge and GEPA 0.1.1 compatibility proofs against one exact 3.3 environment;
4. decide and encode the supported Python range;
5. re-run the canonical 3.3 transaction only after the supply-chain freshness gate admits the reviewed artifacts and every prerequisite proof is accepted.

This selects neither `migrate_to_exact_3_3_window` nor `pause_target`:

- immediate migration is rejected because the exact target matrix has 47 failures and the default resolver does not currently admit 3.3;
- permanent pause is rejected because the target environment resolves, Core builds and installs, 117 focused tests pass, the custom-LM subset passes, and a basic real GEPA compile/save/load/predict journey passes.

## Probe contract

### No-effect boundary

The probe performed:

- public package metadata reads and dependency artifact resolution/downloads;
- isolated local environment creation;
- credential-free local source tests;
- local package builds and a local installed-wheel import/CLI check.

It performed zero:

- live model/provider calls;
- health probes, auth flows, or credential inspection;
- external tool/retriever execution;
- shared-store writes;
- canonical dependency/source/lock mutation;
- release, publication, promotion, or activation operations.

### Exact source and baseline identities

| Identity | Value |
|---|---|
| Source commit | `d731f5eb064019885288c132224cc44635972a9b` |
| Source tree | `451b925d85cbc36c9da9fd27566d550359baeec3` |
| Baseline Core pyproject SHA-256 | `c05a582076a7ad7e0c4aa6afd2f143297a7765f506e99e41c7e818080f9babee` |
| Baseline Forge pyproject SHA-256 | `38911c13fd8a610ef43cd53251418cfcc7cafbb6e11fe09c026d6bec41fb9de5` |
| Baseline lock SHA-256 | `28c7397b6b2b63ba22b1f08ac3ffd5bf91b923868797fd3ae43d5675c232718e` |
| Baseline Python | CPython `3.13.12` |
| Baseline platform | Linux `7.0.8-arch1-1`, x86_64, glibc 2.43 |
| Baseline DSPy / DSPy-AI | `3.1.3` / `3.1.3` |
| Baseline GEPA | `0.0.26` |
| Baseline LiteLLM / OpenAI | `1.81.16` / `2.24.0` |

### Exact admitted target identities

The exact 3.3 target required two explicit probe-only changes:

- narrow both workspace package Python declarations from `>=3.13` to `>=3.13,<3.15` because DSPy 3.3 declares `<3.15`;
- use fixed dependency-admission timestamp `2026-08-04T23:59:59Z` because the workstation supply-chain policy excludes packages newer than seven days and DSPy 3.3.0 was only five days old at probe time.

| Identity | Value |
|---|---|
| Target Core pyproject SHA-256 | `d18e6ab6f73a138d6838c21ca79a2c0e8a99e6a16b5915a14a8244f1e792f410` |
| Target Forge pyproject SHA-256 | `0967ffd1aad7cdc4812eb9d51d4eb1043ffb4deef8dacce021af2d6496b83828` |
| Target lock SHA-256 | `3c1a67002a7b2a42afda6ff5bba6e2cb10e164badab5e81620504b05772034a9` |
| Hash-bound exported requirements SHA-256 | `d1b4841300d33c4569f854c1fbee7ac636ca361fc848fcc1f1995a9f4c68ad2d` |
| Built Core wheel SHA-256 | `389bdf0beb815cee5af6388e1c5ea956a43b7fca0d32ce23979f3e80a8827fc3` |
| Target Python | CPython `3.13.12` |
| Target DSPy / DSPy-AI | `3.3.0` / `3.3.0` |
| Target GEPA | `0.1.1` |
| Target LiteLLM / OpenAI | `1.81.16` / `2.24.0` |
| DSPy sdist/wheel hashes | `sha256:39aa9531…92754`, `sha256:358cbfb1…3e48c` |
| DSPy-AI sdist/wheel hashes | `sha256:b70d999a…b3227`, `sha256:386fafb5…d790` |
| GEPA sdist/wheel hashes | `sha256:643fda01…4aa1`, `sha256:71ead7c5…a0d6` |

The shortened display hashes above are orientation only; the target lock contains the complete artifact hashes and is identified by its full SHA-256.

### Durable raw evidence

AK evidence **6672** (`compatibility_probe_raw`, result `pass`) retains the complete machine-readable probe manifest:

- all 47 failed node IDs and their observed boundary classification;
- per-file baseline/target counts for all 164 collected tests;
- command families, `uv 0.11.14`, source/baseline/target identities, and non-effect fields;
- the complete 130-distribution installed environment with each name, version, and installed `.dist-info/RECORD` content SHA-256;
- installed-environment manifest SHA-256 `1ad4ecb566e77b683b7952794f0eb80a077ce458f7237535eb66a798d6b61169`;
- raw probe manifest SHA-256 `f8c9d3b91533e6019b10d61a9a13f497c290888cbab30c24a9c1067d8707d4e3`;
- target lock, requirements, wheel, native ReActV2, direct-guard, and package/install result identities.

AK evidence **6674** retains the exact reconstruction manifest: complete matrix file argv, baseline/target resolution/sync/test/build/export/install/proof/native-ReActV2 commands, source/tool identities, and results. Ordered evidence **6675–6679** retains the complete target `uv.lock` as hash-bound gzip+base64 chunks; **6680–6681** retains the complete hash-bound exported requirements the same way. Reconstruction verifies each chunk, compressed content, decompressed content, and the full lock/requirements hashes above.

AK evidence **6682** retains the exact built-wheel content manifest: filename, uncompressed size `1,082,880`, wheel SHA-256 `389bdf0b…7fc3`, compressed SHA-256 `56b110ab…fa20`, encoding, and 24-part reconstruction contract. Ordered evidence **6683–6706** retains every wheel byte as hash-bound gzip+base64 chunks. This preserves the exact installed subject without claiming a future rebuild will reproduce it or depending on the unconstrained build-backend range.

Scratch logs were intentionally not promoted as repo authority. Evidence 6672 and 6674–6706 provide the bounded AK-owned reconstruction/audit surface; this report provides the human-readable interpretation.

## Resolver findings

### R1 — freshness policy caused the observed default 3.2.1 resolution

Observed command shape:

```text
uv lock --upgrade-package dspy --upgrade-package dspy-ai --upgrade-package gepa
```

With canonical workspace metadata and the workstation supply-chain policy, this resolved:

- DSPy `3.2.1`;
- DSPy-AI `3.2.1`;
- GEPA `0.0.27`.

Intermediate lock SHA-256: `e71a4a64eefed0467231497c267744e7917b525fc8b42ccd32e699969274108c`.

The isolated single-variable result is decisive: restoring the canonical Python declarations and applying only fixed admission timestamp `2026-08-04T23:59:59Z` resolved DSPy/DSPy-AI `3.3.0` and GEPA `0.1.1` from the baseline lock. Therefore the observed 3.2.1 default selection was caused by workstation `uv` policy `exclude-newer = "7 days"`, not by the Python declaration. DSPy 3.3.0 was uploaded on 2026-08-03 and had not aged through that policy on 2026-08-08.

Classification: **supply-chain admission gate**. The fixed timestamp was explicit and isolated. A canonical migration should normally wait for the freshness policy rather than bypass it merely to gain features.

### R2 — Python support metadata still requires an explicit truth decision

Both DSPx workspace packages declare Python `>=3.13`, while DSPy 3.3.0 publicly declares `>=3.10,<3.15`. This mismatch did not cause the observed resolver selection: `uv` can resolve the exact 3.3 target with the canonical Python declaration when the fixed timestamp admits it. It does mean DSPx would advertise Python 3.15+ support while a required dependency rejects that runtime.

Classification: **required support-metadata/adoption decision**, not a resolver root cause or observed runtime defect. Any canonical 3.3 transaction must either narrow DSPx to `<3.15` or provide separately proven dependency/runtime support; this probe proposes narrowing but does not authorize it.

### R3 — current wheel metadata can resolve an untested DSPy

Core declares only:

```toml
"dspy-ai>=3.1.3"
```

DSPy-AI is an alias distribution and its own constraint does not tightly bound the underlying `dspy` package. Downstream wheel consumers do not inherit this repository's lock or workstation freshness policy. They may therefore resolve DSPy 3.3.0 even though this source has not passed the 3.3 compatibility matrix.

Classification: **current consumer-safety defect**.

Required immediate successor: direct exact DSPy and DSPy-AI 3.1.3 bounds, with lock/package/installed proof. A range that admits untested 3.1.x or 3.2.x versions is not justified by this probe.

## Executed matrix

The same twelve-file credential-free source matrix was run against both environments:

```text
tests/test_program_topology_intent_pipeline.py
tests/test_program_topology_intent_react_v2.py
tests/test_program_generated_policy.py
tests/test_program_runtime_traces.py
tests/test_program_execution_replay.py
tests/test_provider_v4.py
tests/test_dspy_lm_auth_response_identity.py
tests/test_optimize_gepa_stub.py
tests/test_optimize_gepa_metric_hooks.py
tests/test_program_refinement_gepa.py
tests/test_program_refinement_gepa_candidate.py
tests/test_mlflow_gepa_tracing.py
```

Exact execution:

```text
uv run --frozen --no-sync pytest -q <the twelve exact files above>
```

Environment: source commit/tree above; CPython 3.13.12; Linux x86_64; `uv 0.11.14`; test-specific stub/local providers; `MLFLOW_ENABLE=0` where configured; zero live provider/model calls.

| File | Baseline pass | Target pass | Target fail |
|---|---:|---:|---:|
| `tests/test_dspy_lm_auth_response_identity.py` | 7 | 7 | 0 |
| `tests/test_mlflow_gepa_tracing.py` | 1 | 1 | 0 |
| `tests/test_optimize_gepa_metric_hooks.py` | 2 | 2 | 0 |
| `tests/test_optimize_gepa_stub.py` | 5 | 5 | 0 |
| `tests/test_program_execution_replay.py` | 16 | 5 | 11 |
| `tests/test_program_generated_policy.py` | 33 | 31 | 2 |
| `tests/test_program_refinement_gepa.py` | 9 | 0 | 9 |
| `tests/test_program_refinement_gepa_candidate.py` | 29 | 6 | 23 |
| `tests/test_program_runtime_traces.py` | 10 | 9 | 1 |
| `tests/test_program_topology_intent_pipeline.py` | 11 | 10 | 1 |
| `tests/test_program_topology_intent_react_v2.py` | 4 | 4 | 0 |
| `tests/test_provider_v4.py` | 37 | 37 | 0 |

| Probe | Result |
|---|---|
| Baseline sync | passed |
| Baseline focused tests | **164 passed** in 307.54 seconds |
| Baseline Core build | sdist + wheel passed |
| Target 3.3 sync | passed |
| Target 3.3 focused tests | **117 passed, 47 failed** in 40.82 seconds |
| Target 3.3 Core build | sdist + wheel passed |
| Target hash-bound requirements install | passed after using the same fixed admission timestamp as target resolution |
| Target exact wheel install/import | passed with `PYTHONPATH` empty |
| Target `dspx --help` | passed |

The first installed-environment requirements invocation inherited the seven-day cutoff and correctly rejected DSPy 3.3.0. It performed no partial DSPy installation. The corrected invocation applied the target lock's fixed admission timestamp, installed the hash-bound requirements, then installed the exact Core wheel with `--no-deps`; import and CLI proof passed.

### Failed-node appendix

Evidence 6672 retains these exact 47 target failures and maps only the first to confirmed C1. The remaining 46 map to **C2 candidate boundary / downstream assertion not reached**, not to one proven root cause:

```text
tests/test_program_topology_intent_pipeline.py::test_bounded_reasoning_primitives_materialize_without_external_tools[ProgramOfThought-dspy.ProgramOfThought-config1]
tests/test_program_generated_policy.py::test_program_gen_writes_and_replay_checks_generated_module_policy
tests/test_program_generated_policy.py::test_program_gen_policy_failure_blocks_manifest_write
tests/test_program_runtime_traces.py::test_program_gen_writes_hash_bound_runtime_traces_and_replay_checks
tests/test_program_execution_replay.py::test_program_runtime_receipt_replays_single_module_and_confines_output
tests/test_program_execution_replay.py::test_program_runtime_episode_rejects_candidate_root_overlap_before_writes
tests/test_program_execution_replay.py::test_program_runtime_replay_rejects_stale_evidence_before_subprocess
tests/test_program_execution_replay.py::test_program_runtime_replay_timeout_is_bounded_and_writes_nothing
tests/test_program_execution_replay.py::test_program_runtime_replay_preserves_failed_behavior_as_nonapproval
tests/test_program_execution_replay.py::test_program_runtime_replay_preserves_declared_quality_failure
tests/test_program_execution_replay.py::test_program_runtime_replay_preserves_review_contract_and_quality_semantics[review_packet0-True-executed_valid_review_only-executed_valid_review_only-passed]
tests/test_program_execution_replay.py::test_program_runtime_replay_preserves_review_contract_and_quality_semantics[review_packet1-True-executed_valid_review_only-failed_quality-failed]
tests/test_program_execution_replay.py::test_program_runtime_replay_preserves_review_contract_and_quality_semantics[review_packet2-False-failed_boundary-failed_boundary-not_declared]
tests/test_program_execution_replay.py::test_program_runtime_replay_rejects_contract_mode_downgrade_before_execution
tests/test_program_execution_replay.py::test_program_runtime_replay_policy_is_unsupported_without_safe_stub_fixture
tests/test_program_refinement_gepa.py::test_program_refine_optimize_gepa_rejects_paths_that_overlap_source_candidate
tests/test_program_refinement_gepa.py::test_program_refine_optimize_gepa_rejects_symlinked_output_into_source_candidate
tests/test_program_refinement_gepa.py::test_program_refine_optimize_gepa_inline_examples_writes_sidecar_only
tests/test_program_refinement_gepa.py::test_program_refine_optimize_gepa_degrades_when_optimizer_manifest_unverified[missing-optimizer_output_manifest_missing]
tests/test_program_refinement_gepa.py::test_program_refine_optimize_gepa_degrades_when_optimizer_manifest_unverified[{not json-optimizer_output_manifest_invalid_json]
tests/test_program_refinement_gepa.py::test_program_refine_optimize_gepa_degrades_when_optimizer_manifest_unverified[output_manifest2-optimizer_output_manifest_not_object]
tests/test_program_refinement_gepa.py::test_program_refine_optimize_gepa_uses_manifest_dataset_splits
tests/test_program_refinement_gepa.py::test_program_refine_optimize_gepa_explicit_jsonl_paths_and_malformed_failure
tests/test_program_refinement_gepa.py::test_program_refine_optimize_gepa_degrades_without_examples
tests/test_program_refinement_gepa_candidate.py::test_program_refine_materialize_gepa_candidate_creates_local_non_authoritative_candidate
tests/test_program_refinement_gepa_candidate.py::test_program_refine_materialize_and_compare_gepa_candidate_writes_local_workflow
tests/test_program_refinement_gepa_candidate.py::test_gepa_workflow_result_revalidates_generation_effect_flags_before_write
tests/test_program_refinement_gepa_candidate.py::test_gepa_workflow_result_revalidates_current_candidate_lineage_before_write
tests/test_program_refinement_gepa_candidate.py::test_program_refine_materialize_and_compare_gepa_candidate_rejects_sidecars_inside_source_root_before_generation[comparison_out-comparison_out output path must not be inside source_root]
tests/test_program_refinement_gepa_candidate.py::test_program_refine_materialize_and_compare_gepa_candidate_rejects_sidecars_inside_source_root_before_generation[gepa_candidate_result_out-gepa_candidate_result_out output path must not be inside source_root]
tests/test_program_refinement_gepa_candidate.py::test_program_refine_materialize_and_compare_gepa_candidate_rejects_sidecars_inside_source_root_before_generation[workflow_out-workflow_out output path must not be inside source_root]
tests/test_program_refinement_gepa_candidate.py::test_program_promote_decide_comparison_feeds_local_plan_for_gepa_candidate
tests/test_program_refinement_gepa_candidate.py::test_program_promote_decide_comparison_rejects_promote_and_spoofed_authority
tests/test_program_refinement_gepa_candidate.py::test_gepa_materialize_and_compare_workflow_rejects_outdir_over_protected_input
tests/test_program_refinement_gepa_candidate.py::test_program_refine_materialize_and_compare_gepa_candidate_fails_closed_before_comparison
tests/test_program_refinement_gepa_candidate.py::test_program_refine_materialize_gepa_candidate_rejects_spoofed_or_stale_sidecars[mutator0-identity does not match]
tests/test_program_refinement_gepa_candidate.py::test_program_refine_materialize_gepa_candidate_rejects_spoofed_or_stale_sidecars[mutator1-manifest must be valid]
tests/test_program_refinement_gepa_candidate.py::test_program_refine_materialize_gepa_candidate_rejects_spoofed_or_stale_sidecars[mutator2-widens effect flags]
tests/test_program_refinement_gepa_candidate.py::test_program_refine_materialize_gepa_candidate_rejects_spoofed_or_stale_sidecars[mutator3-widens non-authority flags]
tests/test_program_refinement_gepa_candidate.py::test_program_refine_materialize_gepa_candidate_rejects_spoofed_or_stale_sidecars[mutator4-source program hash does not match]
tests/test_program_refinement_gepa_candidate.py::test_program_refine_materialize_gepa_candidate_rejects_drifted_source_root
tests/test_program_refinement_gepa_candidate.py::test_program_refine_materialize_gepa_candidate_rejects_external_program_surface
tests/test_program_refinement_gepa_candidate.py::test_copy_optimizer_output_rechecks_copied_manifest_hash
tests/test_program_refinement_gepa_candidate.py::test_materialized_gepa_candidate_rejects_payload_tampering_before_pickle_load
tests/test_program_refinement_gepa_candidate.py::test_materialized_gepa_candidate_rejects_manifest_and_payload_rewrite_before_pickle_load
tests/test_program_refinement_gepa_candidate.py::test_program_refine_materialize_gepa_candidate_rejects_tampered_optimizer_payload
tests/test_program_refinement_gepa_candidate.py::test_program_refine_materialize_gepa_candidate_rejects_path_overlap_and_symlinks
```

## Compatibility classification

### C1 — ProgramOfThought constructor is a confirmed required migration

Current generated code calls:

```python
dspy.ProgramOfThought(..., interpreter=dspy.PythonInterpreter(...))
```

Target behavior:

```text
TypeError: ProgramOfThought.__init__() got an unexpected keyword argument 'interpreter'
```

DSPy 3.3 expects a zero-argument `interpreter_factory`. The target source signature observed was:

```text
(self, signature, max_iters=3, interpreter_factory=PythonInterpreter)
```

Classification: **required migration**. Renderer and generated static policy must move together while retaining empty filesystem/network/environment/tool access. ProgramOfThought remains excluded from the first production matrix because LM-produced runtime code is not made owner-reviewed by reviewing the surrounding artifact.

### C2 — guarded generated-module smoke is the common observed boundary, not a proven single root cause

The remaining 46 failures terminate at or depend on module synthesis rejecting candidates after guarded smoke reports:

```text
forward_error:PermissionError
```

Representative failures reproduce individually in fresh target processes across generated policy materialization, runtime receipt/replay candidate materialization, and GEPA refinement source-candidate materialization. A supplemental direct guard run produced **21 passed, 5 failed** across `test_synthesis_runtime_smoke.py` and `test_generated_code_guard_adversarial.py`; the same PermissionError displaced expected valid, input-drift, redacted Exception, SystemExit, and timeout outcomes.

A direct isolated `_run_module_worker` diagnostic over a retained generated module can pass after target imports are warm, while the synthesis/guard path rejects candidates. Viable hypotheses include new lazy import/filesystem/process behavior, import-warmth dependence, or a guard lifecycle/cache interaction. The exact denied operation and per-node root cause remain unresolved; they were not widened or bypassed.

Classification: **required generated-smoke compatibility investigation and candidate common boundary**. Gate B must attribute each failure after repairing the first guard incompatibility, then rerun all downstream assertions. The repair must preserve fail-closed import/filesystem/network/subprocess policy; suppressing PermissionError, pre-warming imports by convenience, or disabling smoke is forbidden.

C2 blocks ordinary candidate materialization, so many replay/refinement/GEPA-specific assertions were not reached. The report does not claim those 46 nodes are one defect or independently compatible.

### C3 — selected synchronous wrapper behavior passes; the DSPy bridge remains largely unproved

Within the same target run, no failures occurred in:

- `tests/test_provider_v4.py`;
- `tests/test_dspy_lm_auth_response_identity.py`.

DSPy 3.3 reports the `BaseLM` default `forward_contract` as `legacy` and exposes new capability properties. These tests primarily cover wrapper construction/import and selected synchronous wrapper-owned `forward()`/`generate()` behavior with mocked inner transports. They do not directly prove DSPy 3.3 `BaseLM.__call__`, typed-request adaptation, async, streaming, cancellation, callback lineage, copy/state/history, normalized errors, capability properties, or every provider implementation.

Classification: **selected synchronous wrapper behavior passes; custom-LM bridge compatibility remains largely unproved and requires S3**.

### C4 — basic real GEPA 0.1.1 journey passes

`test_gepa_optimize_saves_loadable_program` passed under the target and exercised:

- real `dspy.teleprompt.gepa.GEPA` construction;
- credential-free stub optimization;
- compile;
- whole-program save;
- `dspy.load(..., allow_pickle=True)`;
- prediction.

Metric-hook tests also passed. GEPA refinement/candidate tests failed before reaching their GEPA-specific assertions because source candidate materialization hit C2.

Classification: **basic compatibility observed; broader refinement/materialization proof blocked by C2**. Pickle-backed whole-program loading remains compatibility evidence and outside the first production target.

### C5 — ReActV2, Flex, and typed LM become visible but are not adopted

Target runtime exposes:

```text
dspy.Flex = present
dspy.ReActV2 = present
dspy.LMRequest = present
dspy.LMResponse = present
```

The ReActV2 contract/policy test file passed, but it primarily proves DSPx's rendering and metadata seams. A supplemental credential-free native runtime constructed `dspy.ReActV2(..., tools=[], max_iters=1)` with the DSPx echo stub and invoked it once. Upstream added its internal `submit` tool; the call returned a `Prediction` with `termination_reason='parse_error'` after the echo stub failed the structured `ToolCalls` contract. No user tool or external effect ran. This is a retained runtime result, not a quality pass or adoption proof.

Current DSPx source accepts an intent option or `DSPX_PROGRAM_GEN_ENABLE_REACT_V2` plus public symbol availability. S5 must change the canonical 3.3 transaction so neither stale option/environment state nor symbol availability can enable ReActV2 before S6 records an accepted adoption state.

Classification:

- ReActV2: **native credential-free runtime executed but terminated parse_error; experimental and canonically disabled pending separate Gate C/S6 proof**;
- typed LM: **available; separate provider-by-provider Gate E work**;
- Flex: **available; separately authorized Gate F pilot only**.

### C6 — package construction and basic installed operation are compatible

The target built Core sdist and wheel. A fresh Python 3.13 environment installed the hash-bound target requirements and exact Core wheel outside the checkout with `PYTHONPATH` empty. AK evidence 6672 retains the complete installed distribution/version/RECORD-hash manifest. These passed:

- imports of `dspx` and `dspy` from that environment;
- exact version readback;
- `dspx --help`.

Classification: **import/CLI package smoke observed only**. The substantive installed golden path, exact payload/RECORD verification, replay/product journey, and package policy gates were not run. This smoke cannot offset the 47 focused source failures.

## Decision alternatives

### Rejected: `migrate_to_exact_3_3_window`

Rejected now because:

- the freshness policy has not admitted 3.3 normally;
- the Python support metadata is wider than DSPy 3.3's declared runtime window and requires an explicit truth decision;
- 47 of 164 focused tests fail;
- ordinary generated-module materialization is blocked by guarded smoke;
- ProgramOfThought uses a removed constructor contract;
- current consumer metadata needs correction before widening compatibility.

### Selected: `cap_current_range_pending_repairs`

Selected because:

- exact 3.1.3 has a clean 164-test baseline;
- downstream consumers are not protected by the repo lock;
- 3.3's environment, package build, basic install, custom-LM subset, and basic GEPA journey are promising but insufficient;
- failures are bounded enough to seed independently attributable repair/proof tasks.

### Rejected: `pause_target`

Rejected because the target resolves with canonical Python metadata when the fixed artifact timestamp admits it; package/build/import/CLI smoke passes; most focused tests pass; and the observed blockers are concrete rather than indeterminate. The Python upper bound remains a separate support-metadata decision.

## Required successor dependency graph

```text
AK-4693 accepted report/decision
        |
        +--> S0 proposed consumer-safety exact 3.1.3 bounds
        |      - requires an AK-accepted variance/update to the frame's no-canonical-lock-before-proofs rule
        |      - direct dspy==3.1.3 and dspy-ai==3.1.3
        |      - exact lock, wheel metadata, fresh installed proof
        |      - retained rollback baseline for S5
        |
        +--> S1 ProgramOfThought isolated constructor/policy proof --------+
        |                                                                |
        +--> S2 generated-smoke 3.3 attribution/repair proof -------------+--> S1 full synthesis acceptance
        |                                                                |
        +--> S3 custom-LM legacy-bridge full proof -----------------------+--> S5 canonical 3.3 transaction
        |                                                                |      - depends on S0-S4 acceptance
        +--> S4a GEPA unblocked compile/save/load proof ------------------+      - S4b materialization acceptance depends on S2
                  +--> S4b GEPA refinement/materialization proof ---------+      - depends on freshness/security admission
                                                                                - decides exact Python support metadata
                                                                                - disables option/env/symbol ReActV2 activation
                                                                                - one rollback unit
                                                                                       |
                                                                                       +--> S6 no-user-tool ReActV2 adoption decision
                                                                                                  |
                                                                                                  +--> trusted-local Core evidence gate
```

S1 isolated constructor/policy work, S2, S3, and S4a may run in parallel only in disjoint worktrees/scopes while binding the same exact target identity. S1 full synthesis acceptance and S4b depend on S2 because generated materialization is currently blocked at the guard. S5 depends on S0 through S4, the accepted Python metadata decision, and freshness/security admission. S6 depends on S5; the trusted-local Core evidence gate depends on S6 recording supported or unsupported status.

S0 is an urgent proposal, not yet execution authority: the accepted frame currently says no canonical lock moves before compatibility proofs. AK must first accept a narrow consumer-safety variance or update that frame contract. If accepted, S0 becomes the exact 3.1.3 rollback baseline consumed by S5.

Decision 115 and deferred AK-4694 propose one bounded generated-ReActV2 declared-corpus tool. They remain separate architecture/tool-effect work and must not execute from current symbol availability. Any later implementation must depend on S5's canonical 3.3 transaction, S6's accepted no-user-tool adoption state, and Decision 115's own terminal ADR/implementation/validation readiness; otherwise it stays deferred. Typed-LM and Flex remain downstream as defined by the frame.

## Stop conditions carried forward

Stop the 3.3 transaction when any successor requires:

- weakening generated-code import/filesystem/network/subprocess guards;
- enabling ReActV2, Flex, typed LM, external tools, runtime-generated Python production support, or pickle-backed GEPA production support by dependency availability alone;
- treating different DSPy/GEPA versions or artifact hashes as replay-equivalent;
- bypassing the accepted supply-chain freshness policy without a separate explicit security decision;
- allowing an installed dependency graph outside the exact retained resolved environment;
- losing provider/model identity, failure, cancellation, stream, receipt, or non-authority truth;
- using technical evidence as release, publication, promotion, or activation authority.

## Validation and review required for AK-4693

- strict docs validation for `docs/project`;
- exact working-tree scope validation in an isolated same-HEAD clone containing only this report and `AK-4693.snapshot.json`;
- `git diff --check` for the exact two files;
- independent review of baseline/target comparability, classifications, decision selection, successor dependencies, production exclusions, and authority boundaries;
- AK task contract, guardrails, evidence classes, direction link, and lifecycle reconciliation.
