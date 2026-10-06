---
summary: "AK6607 Revision2 red matrix (159 cases) mapped to executing tests after the clean-worker slice; scope source for the follow-up matrix task."
read_when:
  - "Executing or extending the Revision2 typed-image red matrix after AK6607."
  - "Checking which typed-image safety cases have executed test proof."
type: "reference"
---


# Revision2 red matrix — executed-test traceability (2026-10-06)

Source matrix: `docs/proof/AK-6607/design/red-cases.feature` (local proof custody) (51 scenarios, 159 expanded cases; case ids
from `docs/proof/AK-6607/refusal-containment/full-target-status.csv`). Mapped by an independent read-only
agent against the first-review clean-worker tree (manifest `80905a6c…`, local proof), using
the 23-file regression selection. Strict classes: a test counts only if it executes the
asserted behavior against production code with a matching assertion.

| Class | Cases |
|---|---|
| COVERED | 8 (S05, S12-E01, S12-E09, S14, S28-E01..E04) |
| PARTIAL | 61 |
| UNCOVERED | 89 |
| OUT_OF_SCOPE_BY_DECISION | 1 (S24: design/release acceptance statement) |

The hardening after review adds executed coverage that bears on S16/S31 (observer
channels: settrace, setprofile, monitoring, signal handlers, gc callbacks, frame
introspection, all ending the worker before materialization) and S35 (typed
`LMImagePart` at the sole adapter with exact pixels). Those rows remain PARTIAL until
re-mapped case by case; no row is promoted here by inference.

## Gaps by owning module (effort: S small, M moderate, N new mechanism)

- **Typed adapter** (`dspy_typed_lm`, `provider_contract`): S04 (S); S06-E01..E15
  unsupported affordances via a worker entry with a send counter (M); S33 image DTO repr (S).
- **Source membrane** (`image_source_io`, `image_input_contract`): S07 descriptor
  defects through the materializer with effect spies (S); S09 request-global budgets incl.
  >8 MiB / >24 MiB fixtures (S–M); S10 (S); S12 symlink/ancestor/socket/oversize leaves
  with read spies (S); S13/S25 changed source after prepare (S); S15 envelope parity (M,
  import-fault half N).
- **Decoder**: S38 JPEG, S40 iTXt (S); S07-E08..E12 WebP/truncated/warning/codec (S–M);
  S39 frozen formats/plugins/`LOAD_TRUNCATED_IMAGES` (M).
- **Admission** (`validate_admission` runs in the parent): S27 all bound rows, S03-E03/
  E05/E07, S02, S28-E05 (S); S03-E01/E02/E04/E06/E08 drift inside the worker (M); S01 (S–M).
- **Privacy**: S16, S29, S30, S31-E02/E05..E10, S36 (S); S31-E01/E03 MLflow inside the
  clean worker (M); S32, S34 ×12 marker-repair spies, S37, S17 (M); S35 spies (S);
  S11 demo repetition is refused earlier by graph binding (design question).
- **HTTP effects** (`image_effects`): S21 image redirect, S22-E01..E04, S19 echo,
  S45 direct-provider finalization, S09-E07/E08/E10 (M); S22-E05/E06, S44-E01/E02 (S);
  S51 echo (M; worker stdout/stderr half N); S47 trickle + absent-terminal
  reconciliation (N — no reconciliation code exists).
- **Custody/records**: S43/S44 publication faults inside a real transaction (M);
  S20/S23 scan tampering (S); S23 artifact-chain tamper, S26 (M); S46 (M), S48 (S);
  S42 two-worker contention, S22-E07, S44-E06 kill-after-intent reconciliation (N).
- **Episode/replay/artifacts**: S18 `capture_replay_fixture=True` refusal (S); S49 mixed
  rows (S–M). Explicit-anchor receipt check/replay stays refused (AK6717).
- **Generation preflight/surfaces**: S50 inline examples/dataset/reserved keys (S);
  retriever/pre-render accounting (M).

Owner decision AK14133 (2026-10-06) completed AK6607 on its done contract and moved
execution of this matrix to one follow-up task. Owner decision AK14132 excludes
detectable parent observers from the boundary (deviation from proposal item 1), so rows
that assumed a parent-side refusal must be read with that decision.

## Per-case table

| case | class | executing test nodes or reason | missing piece |
|---|---|---|---|
| AK6607-S01 | PARTIAL | EXE::refusal[execute,episode,generated-execute,request-execute]; EPI::test_runtime_input_materialization_denies_unadmitted_image_file_descriptors; SURF::test_production_direct_runner_denies_unadmitted_image_before_import | no 6 valid ceiling-sized images with network.mutate on; no probe/fallback spies |
| AK6607-S02 | PARTIAL | EXE::sessions[*-session4]; RDB::test_anchored_receipt_refusal_before_parent_access[*-copied-*] | no schema-valid live admission-v2 JSON through validate_admission/execute |
| AK6607-S03-E01 | PARTIAL | OCP::test_endpoint_is_revalidated_immediately_before_dispatch (text path) | admission-bound image endpoint drift |
| AK6607-S03-E02 | PARTIAL | STUB::test_stub_preflight_rejection_records_zero_dispatch_attempt (stub text) | admitted-model drift on image path |
| AK6607-S03-E03 | UNCOVERED | - | request image count > admission limit |
| AK6607-S03-E04 | PARTIAL | PRIV::fake_http[wall_drift]; SUP::deadline[wall] | per-request IO timeout > admitted |
| AK6607-S03-E05 | UNCOVERED | - | max_image_bytes drift |
| AK6607-S03-E06 | UNCOVERED | - | max_request_body_bytes drift |
| AK6607-S03-E07 | UNCOVERED | - | source changed vs admission/preparation |
| AK6607-S03-E08 | PARTIAL | PRIV::fake_http[binding],[replacement] | no rejection of foreign/reused binding before send |
| AK6607-S04 | UNCOVERED | - (TLM tests only text metadata/config) | LMRequest[text,image,text] into DSPyTypedLMAdapter(StubProvider) |
| AK6607-S05 | COVERED | STUB::test_stub_denies_nominal_parts_even_in_direct_fixture_mode; STUB::test_direct_stub_rejects_malformed_image_union_before_fixture | - |
| AK6607-S06-E01 | PARTIAL | INC::membrane[remote] | https; typed adapter (image_request_from_lm) |
| AK6607-S06-E02 | PARTIAL | INC::b64[https://127.0.0.1/image.png] (primitive) | typed adapter + send counter |
| AK6607-S06-E03 | UNCOVERED | - | file:// image part |
| AK6607-S06-E04 | UNCOVERED | - | file_id part |
| AK6607-S06-E05 | UNCOVERED | - | LMImagePart(path=) |
| AK6607-S06-E06 | UNCOVERED | - | image part metadata |
| AK6607-S06-E07 | UNCOVERED | - | assistant-role image |
| AK6607-S06-E08 | UNCOVERED | - | system-role image |
| AK6607-S06-E09 | UNCOVERED | - | detail=high |
| AK6607-S06-E10 | UNCOVERED | - | detail=auto |
| AK6607-S06-E11 | UNCOVERED | - | audio part |
| AK6607-S06-E12 | UNCOVERED | - | document part |
| AK6607-S06-E13 | UNCOVERED | - | tools in request |
| AK6607-S06-E14 | PARTIAL | TLM::test_async_rejects_before_provider_effect_without_thread_fallback (text) | image-mode acall/aforward |
| AK6607-S06-E15 | PARTIAL | TLM::test_unsupported_typed_features_reject_before_provider_effect[config-generation_config] (text) | image-mode config override |
| AK6607-S07-E01 | PARTIAL | INC::b64[-_==],[https://127.0.0.1/image.png] | not via materializer/typed adapter; no error/log/receipt payload check |
| AK6607-S07-E02 | PARTIAL | INC::b64[-_==] | same |
| AK6607-S07-E03 | PARTIAL | INC::b64["QUJD "],["QUJD\n"] | same |
| AK6607-S07-E04 | PARTIAL | INC::b64[QQ],[QQ===],[QR==] | same |
| AK6607-S07-E05 | PARTIAL | INC::b64[<empty string>] | same |
| AK6607-S07-E06 | UNCOVERED | - | PNG bytes declared image/jpeg (or reverse) |
| AK6607-S07-E07 | UNCOVERED | - | image/svg+xml |
| AK6607-S07-E08 | PARTIAL | INC::chunks[acTL] (scanner) | via materializer; log/receipt check |
| AK6607-S07-E09 | UNCOVERED | - | WebP |
| AK6607-S07-E10 | UNCOVERED | - (baseline JPEG test covers trailing bytes only) | truncated JPEG |
| AK6607-S07-E11 | UNCOVERED | - | decompression warning |
| AK6607-S07-E12 | UNCOVERED | - | absent codec |
| AK6607-S07-E13 | UNCOVERED | - | non-Frozen decoder -> image_decoder_unavailable |
| AK6607-S07-E14 | UNCOVERED | - | alias conflict (mimeType vs imageDataMimeType, extra keys) |
| AK6607-S07-E15 | UNCOVERED | - | descriptor with two sources |
| AK6607-S07-E16 | PARTIAL | ADM::test_admission_rejects_forged_or_noncanonical_identity (shared parse_json) | duplicate key in input descriptor |
| AK6607-S08 | PARTIAL | INC::b64[data:image/png,QUJD],[data:image/png;foo=x;base64,QUJD] | via protected entry with callback/send spies |
| AK6607-S09-E01 | UNCOVERED | - | 7th occurrence |
| AK6607-S09-E02 | UNCOVERED | - | per-image bytes +1 |
| AK6607-S09-E03 | UNCOVERED | - | summed bytes +1 |
| AK6607-S09-E04 | PARTIAL | INC::dims[size2] (scanner) | exactly +1 over admitted pixels; no-partial-dispatch |
| AK6607-S09-E05 | PARTIAL | INC::dims[size0] (scanner) | admission/request level; no-partial-dispatch |
| AK6607-S09-E06 | PARTIAL | INC::dims[size1] (scanner) | same |
| AK6607-S09-E07 | UNCOVERED | - | raw input JSON bytes |
| AK6607-S09-E08 | UNCOVERED | - | HTTP body bytes |
| AK6607-S09-E09 | UNCOVERED | - | text chars |
| AK6607-S09-E10 | UNCOVERED | - | total parts |
| AK6607-S09-E11 | UNCOVERED | - | input depth |
| AK6607-S09-E12 | UNCOVERED | - | input nodes |
| AK6607-S10 | UNCOVERED | - (membrane[positive] uses 2 identical images) | 7 identical occurrences |
| AK6607-S11 | UNCOVERED | - | demo repetition (demos refused earlier at graph binding) |
| AK6607-S12-E01 | COVERED | INC::membrane[outside]; INC::paths[/absolute.png] | - |
| AK6607-S12-E02 | PARTIAL | INC::paths[../escape.png],[a/../escape.png] | existing forbidden target + read spy |
| AK6607-S12-E03 | PARTIAL | INC::paths[~/input] | same |
| AK6607-S12-E04 | UNCOVERED | - | symlink leaf pointing outside root |
| AK6607-S12-E05 | PARTIAL | INC::symlink | read spy on target |
| AK6607-S12-E06 | UNCOVERED | - | symlinked ancestor dir |
| AK6607-S12-E07 | PARTIAL | INC::fifo | os.read spy |
| AK6607-S12-E08 | UNCOVERED | - | socket leaf |
| AK6607-S12-E09 | COVERED | INC::ancestor | - |
| AK6607-S12-E10 | UNCOVERED | - | file > limit |
| AK6607-S13 | UNCOVERED | - | changed bytes, same name -> new commitments; old admission rejects |
| AK6607-S14 | COVERED | PRIV::fake_http[original]; EXE::shipped wire block kinds | - |
| AK6607-S15 | PARTIAL | EXE::shipped[*-episode],[*-direct] (shared _prepare) | envelope parity; malformed envelope both paths; missing-import fallback |
| AK6607-S16 | PARTIAL | INC::history[True]; WRK::observer falsifiers; PRIV::fake_http[original]; EXE::real_provider_session_mutation | DSPy global/instance callback inside worker; repr/model_dump |
| AK6607-S17 | PARTIAL | EPI::...denies_unadmitted_image_file_descriptors; SURF::...denies_unadmitted_image_before_import | after-materialization Image.format cache spy, LM cache, context cleared |
| AK6607-S18 | PARTIAL | EXE::shipped (no replay fixture; replay refused); RDB ordinary tests; OCR::test_pre_ak4778_stub_runtime_remains_valid_and_replay_readable | capture_replay_fixture=True with image_execution -> image_replay_unsupported |
| AK6607-S19 | UNCOVERED | - | echoing completion -> completed_failure(privacy), nothing written |
| AK6607-S20 | PARTIAL | INC::membrane[positive]; REC::noreplace | two attempts with distinct UUIDs; duplicate/foreign attempt_id rejection |
| AK6607-S21 | PARTIAL | OCP::test_fully_read_non_success_is_completed_failure_without_retry[302]; OCP::test_owned_client_has_no_ambient_auth_cookies_redirects_or_retry (text) | image path; Location header; no-logging check |
| AK6607-S22-E01 | PARTIAL | OCP::test_transport_and_read_failures_are_indeterminate_without_retry; OCP::test_indeterminate_latches_without_a_second_attempt_or_dispatch (text) | image custody/terminal path |
| AK6607-S22-E02 | PARTIAL | same (FailingStream, text) | same |
| AK6607-S22-E03 | UNCOVERED | - | KeyboardInterrupt in send |
| AK6607-S22-E04 | UNCOVERED | - | SystemExit in read |
| AK6607-S22-E05 | PARTIAL | PRIV::fake_http[typed_interrupt] | later call/retry/fallback denial; no-score |
| AK6607-S22-E06 | PARTIAL | PRIV::fake_http[validation_interrupt],[cleanup_interrupt] | same |
| AK6607-S22-E07 | UNCOVERED | - (no parent-side reconciliation) | absent terminal -> indeterminate |
| AK6607-S23 | PARTIAL | REC::scan[count,result,typed,response,bytes,model,time]; OCP::test_attempt_history_is_bounded_and_truncation_is_explicit (text) | attempt-id/hash tamper in receipt or artifact chain; image truncation |
| AK6607-S24 | OUT_OF_SCOPE_BY_DECISION | design/release acceptance statement; receiver/release/full-gate acceptance not authorized | - |
| AK6607-S25 | PARTIAL | INC::membrane[positive]; EXE::shipped | Module/Predict counters on production prepare; changed source -> reject before ready.json |
| AK6607-S26 | PARTIAL | EXE::shipped (S->A->M->R; verify_image_run ok) | source change invalidates downstream; cyclic/self-hash rejection |
| AK6607-S27-E01 | UNCOVERED | - | source_package_sha256 alter/omit |
| AK6607-S27-E02 | PARTIAL | PRIV::fake_http[plan] (detached view) | altered/omitted admission bytes rejected; unknown keys/bools/floats |
| AK6607-S27-E03 | PARTIAL | PRIV::fake_http[plan] | same |
| AK6607-S27-E04 | UNCOVERED | - | max_response_bytes |
| AK6607-S27-E05 | UNCOVERED | - | max_output_artifact_bytes |
| AK6607-S27-E06 | PARTIAL | PRIV::fake_http[limits] | same as E02 |
| AK6607-S27-E07 | UNCOVERED | - | not_before_utc_ms |
| AK6607-S27-E08 | PARTIAL | SUP::deadline[expiry]; PRIV::fake_http[deadlines] | omission/type laundering |
| AK6607-S27-E09 | PARTIAL | PRIV::fake_http[wall_drift]; SUP::deadline[wall] | same |
| AK6607-S27-E10 | UNCOVERED | - | caller_expectation_sha256 |
| AK6607-S27-E11 | UNCOVERED | - | root_ino |
| AK6607-S27-E12 | UNCOVERED | - | runtime_identity_sha256 |
| AK6607-S27-E13 | UNCOVERED | - | decoder_profile_sha256 |
| AK6607-S28-E01 | COVERED | PRIV::fake_http[original] (transport None; default transport and Client spies) | - |
| AK6607-S28-E02 | COVERED | PRIV::fake_http[original] (HTTPTransport) | - |
| AK6607-S28-E03 | COVERED | PRIV::fake_http[original] (BaseTransport()) | - |
| AK6607-S28-E04 | COVERED | PRIV::fake_http[original] (MockTransport subclass) | - |
| AK6607-S28-E05 | UNCOVERED | - (sessions[*-session4] is parent-only) | live-mode record with SyntheticImageAuthority |
| AK6607-S29 | UNCOVERED | - (SPR drift test related) | nested Predict instance callback |
| AK6607-S30 | UNCOVERED | - | callback in base settings hidden by override |
| AK6607-S31-E01 | UNCOVERED | - | MLflow autolog |
| AK6607-S31-E02 | UNCOVERED | - | retained safe_patch / SDK __wrapped__ |
| AK6607-S31-E03 | UNCOVERED | - | active MLflow run |
| AK6607-S31-E04 | PARTIAL | INC::history[True] | worker history not-cleared assertion |
| AK6607-S31-E05 | UNCOVERED | - | nonempty module history |
| AK6607-S31-E06 | UNCOVERED | - | substituted dspy trace list |
| AK6607-S31-E07 | UNCOVERED | - | send_stream |
| AK6607-S31-E08 | UNCOVERED | - | stream_listeners |
| AK6607-S31-E09 | UNCOVERED | - | custom dspy.settings.adapter |
| AK6607-S31-E10 | PARTIAL | SPR::drift[instance_forward] | class-level Predict.__call__ wrapping |
| AK6607-S32 | UNCOVERED | - | incompatible annotation + warn_on_type_mismatch logger spy |
| AK6607-S33 | PARTIAL | STUB::test_provider_text_dtos_do_not_format_payload_repr; SURF::test_image_loader_exception_has_no_payload_context_chain; OCP::test_adapter_failure_is_constant_redacted_and_cause_free | repr of image DTOs/parts/echo response |
| AK6607-S34-E01 | UNCOVERED | - | marker defect + json_repair/expansion spies |
| AK6607-S34-E02 | UNCOVERED | - | same |
| AK6607-S34-E03 | UNCOVERED | - | same |
| AK6607-S34-E04 | UNCOVERED | - | same |
| AK6607-S34-E05 | UNCOVERED | - | same |
| AK6607-S34-E06 | UNCOVERED | - | same |
| AK6607-S34-E07 | UNCOVERED | - | same |
| AK6607-S34-E08 | UNCOVERED | - | same |
| AK6607-S34-E09 | UNCOVERED | - | same |
| AK6607-S34-E10 | UNCOVERED | - | same |
| AK6607-S34-E11 | UNCOVERED | - | same |
| AK6607-S34-E12 | UNCOVERED | - | same |
| AK6607-S35 | PARTIAL | PRIV::fake_http[original]; EXE::shipped | marker-expansion/json_repair spies; typed-boundary part spy (typed spy since restored in PRIV) |
| AK6607-S36 | UNCOVERED | - | demos/History refusal |
| AK6607-S37 | UNCOVERED | - | unparsable response + JSONAdapter spies |
| AK6607-S38 | PARTIAL | INC::dims[size0,size1,size2] | JPEG header case; load/decompress spy |
| AK6607-S39 | UNCOVERED | - | formats arg / plugin / LOAD_TRUNCATED / WebP |
| AK6607-S40 | PARTIAL | INC::chunks[iCCP,tEXt,acTL,eXIf,zTXt] | iTXt |
| AK6607-S41 | PARTIAL | INC::fifo | os.read spy |
| AK6607-S42 | UNCOVERED | - | two contending workers on one custody root |
| AK6607-S43-E01 | UNCOVERED | - | pending-file create fault |
| AK6607-S43-E02 | UNCOVERED | - | partial write |
| AK6607-S43-E03 | UNCOVERED | - | file fsync fault |
| AK6607-S43-E04 | PARTIAL | REC::noreplace | inside real intent-1 reservation; no-send; reconstruction |
| AK6607-S43-E05 | PARTIAL | REC::dirfsync | same |
| AK6607-S43-E06 | UNCOVERED | - | readback mismatch |
| AK6607-S44-E01 | PARTIAL | PRIV::fake_http[validation_interrupt],[cleanup_interrupt] | read-only reconstruction refusal |
| AK6607-S44-E02 | PARTIAL | PRIV::fake_http[typed_interrupt] | same |
| AK6607-S44-E03 | UNCOVERED | - | BaseLM finalization fault |
| AK6607-S44-E04 | UNCOVERED | - | terminal write fault |
| AK6607-S44-E05 | PARTIAL | REC::dirfsync (terminal-1.json) | real post-send tx; latch/reconstruction |
| AK6607-S44-E06 | PARTIAL | SUP::reaped[signal] | durable intent + send entered; reconciliation |
| AK6607-S45 | UNCOVERED | - | direct provider.invoke in image mode -> finalization_kind direct_provider |
| AK6607-S46 | UNCOVERED | - (PRIV close_run token check related) | artifact/closure publication fault burns run |
| AK6607-S47 | PARTIAL | SUP::reaped[deadline]; SUP::descendant[*]; SUP::parent_initialization_watchdog; SUP::monotonic_origin | trickling response; absent-terminal reconciliation (not implemented) |
| AK6607-S48 | PARTIAL | EXE::shipped (verify spent; check/replay refused) | re-initialize over spent roots -> image_spent (since added in PRIV register_* views) |
| AK6607-S49 | PARTIAL | EXE::shipped; RDB::test_ordinary_*; OCR::test_pre_ak4778_stub_runtime_remains_valid_and_replay_readable | mixed v1/image rows rejection; anchored check refused by AK6717 |
| AK6607-S50 | PARTIAL | SURF image examples/loader tests; SIO::test_attachment_privacy_branch_does_not_redefine_text_attachments | inline examples/dataset keys; direct render_signature_surface guard; retriever accounting |
| AK6607-S51 | PARTIAL | EXE::shipped (artifact/custody payload scans, benign response) | echo response; stdout/stderr/cache/MLflow/_last_runtime_trace |
