---
summary: "AK6607 Revision2 red matrix (159 cases) mapped to executing tests: all 158 in-scope cases covered by AK6756, with the production fixes, as-built deviations and follow-up tasks."
read_when:
  - "Executing or extending the Revision2 typed-image red matrix."
  - "Checking which typed-image safety cases have executed test proof, or why a case behaves as built."
type: "reference"
---

# Revision2 red matrix — executed-test traceability

Source matrix: `docs/proof/AK-6607/design/red-cases.feature` (local proof custody; 51
scenarios, 159 expanded cases; case ids from
`docs/proof/AK-6607/refusal-containment/full-target-status.csv`). AK6607 mapped the matrix
on 2026-10-06 (8 COVERED, 61 PARTIAL, 89 UNCOVERED). AK6756 (2026-10-07) executed every
open case. Strict class: a test counts only if it runs the scenario's Then-steps against
production code with a matching assertion; payload scenarios run inside the guarded clean
worker (declared `@worker_entry` functions) and publish only codes, counters and hashes.

| Class | Cases |
|---|---|
| COVERED | 158 (S11 by an earlier refusal by design, see below) |
| OUT_OF_SCOPE_BY_DECISION | 1 (S24: design/release acceptance statement) |

Each fixed row first failed against unchanged production code (red logs kept in local
proof custody, `docs/proof/AK-6756/<slice>/`). An independent review of the combined
production diff found nothing blocking; its should-fix items are fixed below.

## Production fixes the matrix found

- **Admission** (`image_admission`): the request plan must use every source occurrence,
  first uses in source order (S27-E03: a reordered plan was accepted). The provider
  binding checks the session authority's type, bytes and mode before any client exists
  (S28-E05; defence in depth, since in-worker tampering is outside the threat model).
- **Effects** (`image_effects`): a completed failure classified `privacy` (an echoed
  payload) reaches the caller as `image_privacy`, not `image_finalization` (S19).
- **Privacy** (`image_privacy`, `image_source_profile`): `adapter` and `lm` must be unset
  in the base settings and every override, so an observer hidden by
  `dspy.context(adapter=None)` refuses (S30, S31-E09). An import-time identity snapshot
  of the call-path classes' MROs detects class-level wraps of `ChainOfThought.__call__`/
  `forward`, `Adapter.__call__` and `Predict.__getattribute__` (S31-E10).
- **Source membrane and decoder** (`image_input_contract`, `image_decoder`): closed
  DesignMD envelope key set (S07-E14/E15, and an extra key holding raw base64 that
  reached the provider as text); `image_url` must be a `data:` URI (S08); verified
  decoder functions must be real functions bound to their own module (S39: a same-code
  clone with a foreign registry was accepted).
- **Custody** (`image_custody`, `image_records`, `image_record_validation`,
  `image_artifacts`):
  - the initializer claims the root with an `O_EXCL` lock before `ready.json`, so two
    contending workers cannot both proceed (S42);
  - read-only reconciliation (`reconcile_image_custody`): an intent without its terminal
    is `effect_indeterminate`, never success, and no terminal is minted (S22-E07,
    S43-E05/E06, S44-E05/E06, S47, S48);
  - `verify_image_run` refuses a non-success, residue-bearing or unclosed run with
    `image_spent` and no raw `FileNotFoundError` (S43, S44, S46);
  - `publish_image_run` refuses before its first write unless every planned attempt
    succeeded (an HTTP 500 used to publish a full receipt marked `completed`).
- **Receipts** (`image_record_validation.is_image_receipt`): a v1 receipt carrying any
  image-only receipt row is an image receipt, refused by check and replay (S49).
- **Review follow-ups**: reconciliation reports `preflight_rejected` (not
  `completed_failure`) when nothing dispatched, adds `planned_dispatches`, bounds the
  root before reading residue and ignores residue whose claim fields are not strings;
  `publish_image_run` checks the clean boundary and session type before reading custody;
  `close_run` closes only as `completed` (the only outcome a publishable run can have).

## As-built deviations and notes

- **Absent terminal** (S22-E07, S44-E06, S47): reported `effect_indeterminate` with
  `dispatch_count: null` (unknown), not 1: nothing durable recorded a send, and the
  report never mints one. A linked success terminal contradicted by complete residue for
  the same attempt (S44-E05) is also indeterminate.
- **S11**: demos are refused at graph binding and in the formatter (`image_privacy`), so
  the demo-repetition precondition cannot be reached; repetition inside the actual
  request is refused with `image_budget`.
- **S09-E11/E12** (fixed by AK6810): inputs exactly at the declared depth (16) and node
  (4096) limits are accepted, by the materializer and by production prepare; limit+1
  still refuses with `image_input_invalid` before any decode. The derived commitments
  used to re-nest the input (each container added two shape levels and three nodes,
  each string four source-package nodes), so `canonical()` refused beyond input depth
  8 or about 1,000 strings. The shape now mirrors the input node for node (a leaf
  is its kind name; domain `shape-v2`), and `plain_text_slots` has one row per
  text-bearing field slot: `text_sha256` is SHA-256 over `text-slot-v1\0` and the
  slot's texts (dict keys included) in visit order, each prefixed by its 8-byte big-endian UTF-8 length;
  `char_count` is their sum. The source package now grows with the declared fields,
  not with the input, and fits one 64 KiB custody record at the limits.
- **Caller codes**: post-send failures surface as `image_finalization` (S22, S51; the
  design says "safe interruption", tests accept either fixed code). At the provider
  port a pre-reserve refusal keeps its own fixed code (E07/E08:
  `image_admission_invalid`); every custody-transaction failure is raised with no cause
  or context (AK6812, `test_image_refusal_chains`).
- **S21**: with logging forced to DEBUG, httpx writes its request line with the admitted
  endpoint, never the `Location` URL or body; default worker logging emits nothing.
- **Envelope metadata**: Revision 2 §4 keeps "safe metadata JSON"; as built, the
  envelope key set is closed (`images` only; `imageDataBase64`, `imageDataMimeType`,
  `pixelInspectionInputStatus`, an equal `mimeType`), so that segment carries no extra
  metadata. No in-repo producer sends extra keys. Widening needs a vetted payload-free
  key list.
- **Plan order**: holds for the shipped single-predictor routes; a future plan whose
  later predictor re-reads an earlier field would be refused (fail closed).
- **Reconciliation** is a parent-side read-only report; shipped routes raise their fixed
  failure code and do not call it. A root left with a lock but no settled `ready.json`
  reports spent with no attempt (`ready_present: false`, terminal effect `none`); a
  record left with two links by a kill inside publication, the other its own pending
  twin, reports its attempt `effect_indeterminate` (`publication_unsettled`), never
  success; `verify_image_run` refuses both. Image transfers check the wall deadline and
  one `per_request_io_timeout_ms` window from dispatch at every chunk: a trickle past
  the window is an `io` `effect_indeterminate` terminal written by the worker itself
  (AK6811, `test_image_settlement`).

## Test shorthands

ADM `test_image_admission`, TLM `test_dspy_typed_lm`, STUB `test_stub_provider`,
SIO `test_image_source_io`, ICT `test_image_input_contract`, PROF
`test_image_source_profile`, PRIV `test_image_privacy`, EFF `test_image_effects`, CUS
`test_image_custody`, EXE `test_image_execution`, SURF `test_program_surfaces_image_inputs`,
RDB `test_receipt_domain_boundary`, IIL `test_image_input_limits`, SET `test_image_settlement`
(all under `tests/`).

- ADM: BND `test_s03_parent_refuses_bounds_outside_the_admission`; HELD
  `test_s03_parent_refuses_drift_against_held_expectations`; WRK
  `test_s03_send_time_drift_outside_the_admission_is_refused_before_send` (named worker
  probes); SHIP `test_s03_shipped_route_refuses_body_or_source_drift_before_send`; T27
  `test_s27_closed_admission_rejects_altered_or_omitted_bound`.
- TLM: AFF `test_image_mode_unsupported_affordance_rejects_before_transport`.
- SIO: MAL `test_s07_malformed_image_data_never_enters_effects`; DEC
  `test_s07_decoder_faults_reject_inside_the_frozen_decoder`; AMB
  `test_s07_ambiguous_descriptors_reject_before_any_read`.
- ICT: BUD `test_s09_image_budgets_are_request_global_and_fail_closed`; JSN
  `test_s09_input_json_bytes_depth_nodes_and_text_are_bounded`; REQ
  `test_s09_s10_s11_actual_request_occurrences_and_bytes_are_counted`; LOC
  `test_s12_local_reads_stay_inside_the_explicit_input_parent`; STR
  `test_s38_s40_structure_and_dimensions_refuse_before_any_pillow_open`.
- IIL: PREP `test_s09_e11_e12_production_prepare_reaches_the_declared_depth_and_node_limits`.
- PROF: OBS `test_configured_observer_refuses_before_materialization`; MRK
  `test_marker_defect_rejects_before_repair_or_lm`.
- PRIV: HTTP `test_actual_generated_predict_typed_image_to_ordered_fake_http`.
- CUS: PRE `test_presend_publication_fault_inside_real_reservation_prohibits_send`; POST
  `test_post_send_failure_latches_and_never_publishes_early_success`.

## Per-case table

| case | class | executing test nodes | production |
|---|---|---|---|
| AK6607-S01 | COVERED | ADM::test_s01_code_defaults_without_owner_bound_admission_refuse_before_effects | proof-only |
| AK6607-S02 | COVERED | ADM::test_s02_copied_live_admission_file_is_not_operator_authority | proof-only |
| AK6607-S03-E01 | COVERED | ADM::BND[E01]; HELD[E01]; WRK (e01 probes) | proof-only |
| AK6607-S03-E02 | COVERED | ADM::BND[E02]; HELD[E02]; WRK (e02 probes) | proof-only |
| AK6607-S03-E03 | COVERED | ADM::BND[E03]; HELD[E03] | proof-only |
| AK6607-S03-E04 | COVERED | ADM::BND[E04]; WRK (e04_send_timeout) | proof-only |
| AK6607-S03-E05 | COVERED | ADM::BND[E05]; HELD[E05] | proof-only |
| AK6607-S03-E06 | COVERED | ADM::BND[E06]; SHIP[AK6607-S03-E06] | proof-only |
| AK6607-S03-E07 | COVERED | ADM::HELD[E07]; SHIP[AK6607-S03-E07] | proof-only |
| AK6607-S03-E08 | COVERED | ADM::HELD[E08]; WRK (e08 probes, parent re-initialization) | proof-only |
| AK6607-S04 | COVERED | STUB::test_native_typed_image_to_stub_is_not_a_text_canary[*] | proof-only |
| AK6607-S05 | COVERED | STUB::test_stub_denies_nominal_parts_even_in_direct_fixture_mode; STUB::test_direct_stub_rejects_malformed_image_union_before_fixture | AK6607 |
| AK6607-S06-E01 | COVERED | TLM::AFF[E01-remote_https_url] | proof-only |
| AK6607-S06-E02 | COVERED | TLM::AFF[E02-loopback_image_url] | proof-only |
| AK6607-S06-E03 | COVERED | TLM::AFF[E03-file_url] | proof-only |
| AK6607-S06-E04 | COVERED | TLM::AFF[E04-file_id] | proof-only |
| AK6607-S06-E05 | COVERED | TLM::AFF[E05-typed_local_path] | proof-only |
| AK6607-S06-E06 | COVERED | TLM::AFF[E06-image_metadata] | proof-only |
| AK6607-S06-E07 | COVERED | TLM::AFF[E07-assistant_image] | proof-only |
| AK6607-S06-E08 | COVERED | TLM::AFF[E08-system_image] | proof-only |
| AK6607-S06-E09 | COVERED | TLM::AFF[E09-detail_high] | proof-only |
| AK6607-S06-E10 | COVERED | TLM::AFF[E10-detail_auto] | proof-only |
| AK6607-S06-E11 | COVERED | TLM::AFF[E11-audio_part] | proof-only |
| AK6607-S06-E12 | COVERED | TLM::AFF[E12-document_part] | proof-only |
| AK6607-S06-E13 | COVERED | TLM::AFF[E13-tool_call] | proof-only |
| AK6607-S06-E14 | COVERED | TLM::AFF[E14-async_invocation] | proof-only |
| AK6607-S06-E15 | COVERED | TLM::AFF[E15-generation_override] | proof-only |
| AK6607-S07-E01 | COVERED | SIO::MAL[E01-invalid-alphabet] | proof-only |
| AK6607-S07-E02 | COVERED | SIO::MAL[E02-url-safe] | proof-only |
| AK6607-S07-E03 | COVERED | SIO::MAL[E03-whitespace] | proof-only |
| AK6607-S07-E04 | COVERED | SIO::MAL[E04-noncanonical-padding] | proof-only |
| AK6607-S07-E05 | COVERED | SIO::MAL[E05-empty] | proof-only |
| AK6607-S07-E06 | COVERED | SIO::MAL[E06-mime-mismatch] | proof-only |
| AK6607-S07-E07 | COVERED | SIO::MAL[E07-svg] | proof-only |
| AK6607-S07-E08 | COVERED | SIO::MAL[E08-animated-png] | proof-only |
| AK6607-S07-E09 | COVERED | SIO::MAL[E09-webp] | proof-only |
| AK6607-S07-E10 | COVERED | SIO::MAL[E10-truncated-jpeg] | proof-only |
| AK6607-S07-E11 | COVERED | SIO::DEC[E11-decoder-warning] (warning injected into the native decoders) | proof-only |
| AK6607-S07-E12 | COVERED | SIO::DEC[E12-absent-codec] | proof-only |
| AK6607-S07-E13 | COVERED | SIO::test_s07_e13_absent_or_unfrozen_decoder_is_unavailable | proof-only |
| AK6607-S07-E14 | COVERED | SIO::AMB[E14-alias-conflict] | fixed (closed envelope) |
| AK6607-S07-E15 | COVERED | SIO::AMB[E15-multiple-sources] | fixed (closed envelope) |
| AK6607-S07-E16 | COVERED | SIO::AMB[E16-duplicate-key] | proof-only |
| AK6607-S08 | COVERED | SIO::test_s08_image_url_without_canonical_base64_header_is_never_laundered | fixed (`data:` only) |
| AK6607-S09-E01 | COVERED | ICT::BUD[E01-occurrences] | proof-only |
| AK6607-S09-E02 | COVERED | ICT::BUD[E02-image-bytes] | proof-only |
| AK6607-S09-E03 | COVERED | ICT::BUD[E03-summed-bytes] | proof-only |
| AK6607-S09-E04 | COVERED | ICT::BUD[E04-pixels] | proof-only |
| AK6607-S09-E05 | COVERED | ICT::BUD[E05-width] | proof-only |
| AK6607-S09-E06 | COVERED | ICT::BUD[E06-height] | proof-only |
| AK6607-S09-E07 | COVERED | ICT::JSN (raw input JSON bytes) | proof-only |
| AK6607-S09-E08 | COVERED | ICT::REQ (HTTP body bytes) | proof-only |
| AK6607-S09-E09 | COVERED | ICT::JSN (text characters) | proof-only (closed envelope counts all text) |
| AK6607-S09-E10 | COVERED | ICT::REQ (total parts) | proof-only |
| AK6607-S09-E11 | COVERED | ICT::JSN (input depth, at limit and limit+1); IIL::PREP[depth-*] | fixed (AK6810) |
| AK6607-S09-E12 | COVERED | ICT::JSN (input nodes, at limit and limit+1); IIL::PREP[nodes-*] | fixed (AK6810) |
| AK6607-S10 | COVERED | ICT::REQ | proof-only |
| AK6607-S11 | COVERED | ICT::REQ; refusal at graph binding and formatter (see notes) | proof-only |
| AK6607-S12-E01 | COVERED | ICT::LOC; ICT membrane[outside] and paths[/absolute.png] (AK6607) | proof-only |
| AK6607-S12-E02 | COVERED | ICT::LOC | proof-only |
| AK6607-S12-E03 | COVERED | ICT::LOC | proof-only |
| AK6607-S12-E04 | COVERED | ICT::LOC | proof-only |
| AK6607-S12-E05 | COVERED | ICT::LOC | proof-only |
| AK6607-S12-E06 | COVERED | ICT::LOC | proof-only |
| AK6607-S12-E07 | COVERED | ICT::LOC | proof-only |
| AK6607-S12-E08 | COVERED | ICT::LOC | proof-only |
| AK6607-S12-E09 | COVERED | ICT::LOC; ICT ancestor (AK6607) | proof-only |
| AK6607-S12-E10 | COVERED | ICT::LOC | proof-only |
| AK6607-S13 | COVERED | SIO::test_s13_same_filename_with_new_pixels_gets_new_identity | proof-only |
| AK6607-S14 | COVERED | PRIV::HTTP[original]; EXE shipped wire block kinds | AK6607 |
| AK6607-S15 | COVERED | SURF::test_s15_designmd_envelope_and_descriptor_share_one_membrane_in_both_routes; SURF::test_s15_envelope_materializer_parity_inside_the_clean_worker; SURF::test_s15_malformed_envelope_rejects_in_both_preparation_paths; SURF::test_s15_missing_image_helper_import_never_falls_back; EXE::test_s25_changed_source_after_prepare_refuses_before_ready_publication[malformed-envelope-*]; SIO::test_s15_extra_envelope_key_is_refused_before_any_decode | fixed (closed envelope) |
| AK6607-S16 | COVERED | PROF::OBS[S16-global-callback, S16-instance-callback, S16-S31E06-substituted-trace-list, S16-S31E04-global-lm-history] | proof-only |
| AK6607-S17 | COVERED | PROF::MRK[S17-interrupted-marker-scan] and every S34 case (post-run state) | proof-only |
| AK6607-S18 | COVERED | RDB::test_s18_replay_capture_with_image_execution_refuses_before_any_work[poison, prepared] | proof-only |
| AK6607-S19 | COVERED | EFF::test_s19_echoing_completion_is_completed_privacy_failure_with_nothing_written[base64, data_uri, marker] | fixed (`image_privacy`) |
| AK6607-S20 | COVERED | EFF::test_s20_identical_requests_get_distinct_attempts_and_reject_duplicates | proof-only |
| AK6607-S21 | COVERED | EFF::test_s21_redirect_is_one_completed_failure_without_location_logging | proof-only |
| AK6607-S22-E01 | COVERED | EFF::test_s22_uncertain_image_effect_terminalizes_and_latches[send_error] | proof-only |
| AK6607-S22-E02 | COVERED | EFF::test_s22_…[read_error] | proof-only |
| AK6607-S22-E03 | COVERED | EFF::test_s22_…[send_interrupt] | proof-only |
| AK6607-S22-E04 | COVERED | EFF::test_s22_…[read_exit] | proof-only |
| AK6607-S22-E05 | COVERED | EFF::test_s22_…[typed_error] | proof-only |
| AK6607-S22-E06 | COVERED | EFF::test_s22_…[finalize_error] | proof-only |
| AK6607-S22-E07 | COVERED | CUS::POST[terminal_missing-None-3] | fixed (reconciliation) |
| AK6607-S23 | COVERED | EFF::test_s23_projection_tampering_cannot_create_success_or_no_effect[7 tampers] | proof-only |
| AK6607-S24 | OUT_OF_SCOPE_BY_DECISION | design/release acceptance statement; receiver/release/full-gate acceptance not authorized | - |
| AK6607-S25 | COVERED | EXE::test_s25_prepare_only_runs_no_module_lm_provider_session_or_ready[False, True]; EXE::test_s25_changed_source_after_prepare_refuses_before_ready_publication[pixels-*] | proof-only |
| AK6607-S26 | COVERED | EXE::test_s26_commitments_run_s_a_m_r_and_a_changed_occurrence_breaks_every_link | proof-only |
| AK6607-S27-E01 | COVERED | ADM::T27[AK6607-S27-E01-*] | proof-only |
| AK6607-S27-E02 | COVERED | ADM::T27[AK6607-S27-E02-*] (refused through the preparation binding) | proof-only |
| AK6607-S27-E03 | COVERED | ADM::T27[AK6607-S27-E03-*] | fixed (plan order) |
| AK6607-S27-E04 | COVERED | ADM::T27[AK6607-S27-E04-*] | proof-only |
| AK6607-S27-E05 | COVERED | ADM::T27[AK6607-S27-E05-*] | proof-only |
| AK6607-S27-E06 | COVERED | ADM::T27[AK6607-S27-E06-*] | proof-only |
| AK6607-S27-E07 | COVERED | ADM::T27[AK6607-S27-E07-*] | proof-only |
| AK6607-S27-E08 | COVERED | ADM::T27[AK6607-S27-E08-*] | proof-only |
| AK6607-S27-E09 | COVERED | ADM::T27[AK6607-S27-E09-*] | proof-only |
| AK6607-S27-E10 | COVERED | ADM::T27[AK6607-S27-E10-*] | proof-only |
| AK6607-S27-E11 | COVERED | ADM::T27[AK6607-S27-E11-*] | proof-only |
| AK6607-S27-E12 | COVERED | ADM::T27[AK6607-S27-E12-*] | proof-only |
| AK6607-S27-E13 | COVERED | ADM::T27[AK6607-S27-E13-*] | proof-only |
| AK6607-S28-E01 | COVERED | PRIV::HTTP[original] (transport None; default transport and Client spies) | AK6607 |
| AK6607-S28-E02 | COVERED | PRIV::HTTP[original] (HTTPTransport) | AK6607 |
| AK6607-S28-E03 | COVERED | PRIV::HTTP[original] (BaseTransport()) | AK6607 |
| AK6607-S28-E04 | COVERED | PRIV::HTTP[original] (MockTransport subclass) | AK6607 |
| AK6607-S28-E05 | COVERED | ADM::test_s28_e05_synthetic_to_live_flag_is_refused_before_provider_factory[*]; WRK (s28 probes) | fixed (authority binding) |
| AK6607-S29 | COVERED | PROF::OBS[S29-nested-predict-instance-callback] | proof-only |
| AK6607-S30 | COVERED | PROF::OBS[S30-base-callback-hidden-by-override, S30-base-adapter-callback-hidden, S30-base-lm-callback-hidden] | fixed (unset adapter/lm) |
| AK6607-S31-E01 | COVERED | PROF::OBS[S31E01-mlflow-imported, S31E01-mlflow-autolog] | proof-only |
| AK6607-S31-E02 | COVERED | PROF::OBS[S31E02-disabled-retained-safe-patch, S31E02-retained-sdk-wrapper] | proof-only |
| AK6607-S31-E03 | COVERED | PROF::OBS[S31E03-active-mlflow-run] | proof-only |
| AK6607-S31-E04 | COVERED | PROF::OBS[S16-S31E04-global-lm-history] | proof-only |
| AK6607-S31-E05 | COVERED | PROF::OBS[S31E05-module-history] | proof-only |
| AK6607-S31-E06 | COVERED | PROF::OBS[S16-S31E06-substituted-trace-list, S31E06-substituted-trace-override] | proof-only |
| AK6607-S31-E07 | COVERED | PROF::OBS[S31E07-send-stream] | proof-only |
| AK6607-S31-E08 | COVERED | PROF::OBS[S31E08-stream-listener] | proof-only |
| AK6607-S31-E09 | COVERED | PROF::OBS[S31E09-custom-adapter, S31E09-custom-adapter-hidden] | fixed (hidden variant) |
| AK6607-S31-E10 | COVERED | PROF::OBS[S31E10-class-predict-call, -chain-of-thought-call, -chain-of-thought-forward, -adapter-call, -predict-getattribute] | fixed (class snapshot) |
| AK6607-S32 | COVERED | PROF::test_incompatible_image_annotation_never_reaches_value_warning[int, list[int]] | proof-only |
| AK6607-S33 | COVERED | STUB::test_nominal_dtos_and_fixed_errors_never_format_payloads; TLM::test_image_mode_nominal_repr_and_parse_failure_are_payload_free | proof-only |
| AK6607-S34-E01 | COVERED | PROF::MRK[S34E01-json-repair-recoverable-missing-quote] | proof-only |
| AK6607-S34-E02 | COVERED | PROF::MRK[S34E02-doubly-quoted-payload] | proof-only |
| AK6607-S34-E03 | COVERED | PROF::MRK[S34E03-orphan-start] | proof-only |
| AK6607-S34-E04 | COVERED | PROF::MRK[S34E04-orphan-end] | proof-only |
| AK6607-S34-E05 | COVERED | PROF::MRK[S34E05-nested-marker] | proof-only |
| AK6607-S34-E06 | COVERED | PROF::MRK[S34E06-added-image-block-key] | proof-only |
| AK6607-S34-E07 | COVERED | PROF::MRK[S34E07-dropped-field] | proof-only |
| AK6607-S34-E08 | COVERED | PROF::MRK[S34E08-multiple-blocks-in-one-marker] | proof-only |
| AK6607-S34-E09 | COVERED | PROF::MRK[S34E09-unregistered-marker-in-plain-text] | proof-only |
| AK6607-S34-E10 | COVERED | PROF::MRK[S34E10-registered-marker-moved-to-other-slot] | proof-only |
| AK6607-S34-E11 | COVERED | PROF::MRK[S34E11-repeated-marker-outside-request-plan] | proof-only |
| AK6607-S34-E12 | COVERED | PROF::MRK[S34E12-changed-canonical-marker-bytes] | proof-only |
| AK6607-S35 | COVERED | PRIV::HTTP[original] and the other success views (repair, expansion and JSONAdapter spies at zero) | proof-only |
| AK6607-S36 | COVERED | PROF::OBS[S36-text-only-demos, S36-conversation-history-demo] | proof-only |
| AK6607-S37 | COVERED | PRIV::HTTP[unparsable] | proof-only |
| AK6607-S38 | COVERED | ICT::STR (JPEG 8193×1, 1×8193, 4001×4000) | proof-only |
| AK6607-S39 | COVERED | ICT::test_s39_frozen_formats_and_plugin_identity_cannot_be_widened | fixed (decoder identity) |
| AK6607-S40 | COVERED | ICT::STR; ICT::test_unsupported_png_chunks_refused_without_native_open[iTXt] | proof-only |
| AK6607-S41 | COVERED | ICT::test_fifo_open_is_nofollow_nonblocking_before_fstat; ICT::LOC (FIFO) | proof-only |
| AK6607-S42 | COVERED | CUS::test_two_contending_workers_cannot_both_claim_one_custody_root | fixed (root claim) |
| AK6607-S43-E01 | COVERED | CUS::PRE[intent_create] | fixed (verify code) |
| AK6607-S43-E02 | COVERED | CUS::PRE[intent_partial] | fixed (verify code) |
| AK6607-S43-E03 | COVERED | CUS::PRE[intent_fsync_file] | fixed (verify code) |
| AK6607-S43-E04 | COVERED | CUS::PRE[intent_exists] | fixed (verify code) |
| AK6607-S43-E05 | COVERED | CUS::PRE[intent_fsync_dir] | fixed (reconciliation) |
| AK6607-S43-E06 | COVERED | CUS::PRE[intent_readback] | fixed (reconciliation) |
| AK6607-S44-E01 | COVERED | CUS::POST[provider_interrupt-…] | fixed (verify code) |
| AK6607-S44-E02 | COVERED | CUS::POST[typed_interrupt-…] | fixed (verify code) |
| AK6607-S44-E03 | COVERED | CUS::POST[finalization-…] | fixed (verify code) |
| AK6607-S44-E04 | COVERED | CUS::POST[terminal_write-…] | fixed (verify code) |
| AK6607-S44-E05 | COVERED | CUS::POST[terminal_dir_fsync-…] | fixed (residue contradiction) |
| AK6607-S44-E06 | COVERED | CUS::test_worker_killed_after_send_is_reconciled_indeterminate | fixed (reconciliation) |
| AK6607-S45 | COVERED | EFF::test_s45_direct_provider_invoke_records_direct_provider_finalization | proof-only |
| AK6607-S46 | COVERED | CUS::test_artifact_or_closure_fault_burns_the_run[artifact, closure]; CUS::test_completed_failure_is_spent_and_publishes_no_artifact | fixed (verify code, publish guard) |
| AK6607-S47 | COVERED | CUS::test_trickling_response_cannot_extend_the_original_wall_deadline; SET::test_io_timeout_bounds_a_trickling_read_and_settles_inside_the_worker | fixed (reconciliation, IO window AK6811) |
| AK6607-S48 | COVERED | CUS::test_spent_completed_root_admits_only_read_only_verification | fixed (reconciliation) |
| AK6607-S49 | COVERED | RDB::test_s49_image_episode_keeps_new_names_and_rejects_mixed_v1_rows | fixed (image-only rows) |
| AK6607-S50 | COVERED | SURF::test_s50_whole_materialization_refuses_before_any_surface_or_harness_write[*]; SURF::test_s50_direct_renderer_guard_refuses_with_no_writes_or_generation[*] | proof-only |
| AK6607-S51 | COVERED | RDB::test_s51_echoed_payload_leaves_no_copy_in_files_streams_caches_or_traces[*] | proof-only |

Review follow-up tests outside the matrix: CUS::test_reconcile_labels_no_dispatch_and_ignores_malformed_residue,
CUS::test_publish_checks_the_boundary_before_reading_custody,
CUS::test_an_all_success_run_closes_only_as_completed.
