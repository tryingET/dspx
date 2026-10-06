---
summary: "Revision 2 of the AK-6607 DESIGN ONLY proposal: explicit privacy, marker, admission, decoder, custody and image-only artifact algorithms. Not accepted or implemented."
read_when:
  - "Independently inspecting AK-6607 after hold dispatch-1791057571008/evidence13275."
  - "Designing bounded typed image transport through the sole DSPy LM adapter."
type: "proposal"
---

# Bounded typed images — revised pre-code contract

## 1. Status and authority

**Revision 2; proposal, not acceptance, implementation, execution proof or live
permission.** This replaces revision 1's unresolved descriptions. The independent
inspection **dispatch-1791057571008 / AK evidence13275** held implementation.
AK6607 scope entity_version=5 now includes `stub_provider.py` and optional modular
helpers; that removes the former *path permission* blocker, not the safety obligation.
This child changes only this document, design red cases and source-inspection proof.
Accepted **Decision118** and exact DSPy/dspy-ai **3.3.1** pins remain unchanged.
Evidence13245 still requires operator approval of exact endpoint/LLM/budgets before
ANY live provider call. No screenshot, runtime deployment, endpoint or LLM is
selected or exercised here. Six screenshots motivate limits, not fitness evidence.

Inspected HEAD: `82b0defacb44a0b9080e8061a9b6c6bf7b4bc1c3`. Ancestor/target
instructions, engineering.local and compact policy were rechecked; no nested context
files were found. Engineering-core v0.12.2/Python consumer policy remains local truth.
README/product posture/developer workflow/architecture/vision/Decision118 passport,
ADR and historical school synthesis were read in the first pass. No broader
verification admission, code, tests, dependency install, commit or task close follows.

## 2. Additional source findings driving this revision

Sources are checkout-relative; installed files are under the existing venv's
site-packages, not imported or executed during inspection. Exact hashes are in
`docs/proof/AK-6607/design/source-inspection.json`.

| Observed source | Finding and consequence |
|---|---|
| Installed `dspy/adapters/_legacy_type_markers.py` (SHA256 `4f7e13798a9bac3ae20d5216a1eef8b0204a5f4151ef538ee44a277de5edd1a5`) | Tries json.loads, doubly quoted decoding, then json_repair; non-list becomes text; image block keys/detail can be dropped; unknown blocks become empty text with metadata. **LM-entry validation alone is too late.** |
| Installed `dspy/adapters/base.py::format` | Expands marker strings before `_render_request`; `_coerce_lm_messages` expands them again. Guarded formatting must replace this expansion boundary, not validate only its output. |
| Installed `dspy/predict/predict.py::_forward_preprocess` | `warn_on_type_mismatch=True` logs the incompatible **value**. Postprocess can append full kwargs/prediction to settings.trace. Disable value warnings before the first Predict and independently check signature compatibility without formatting values. |
| Installed `dspy/primitives/module.py`, `dspy/utils/callback.py` | Module/Predict, Adapter.format/parse and LM callbacks can observe values before forward. Traverse nested object callbacks before invoking a generated program. |
| Installed `dspy/adapters/chat_adapter.py` | `use_json_adapter_fallback=True` by default; parse errors can cause a second LM call. Image formatter must explicitly set false and deny replacement adapters. |
| Installed `dspy/clients/base_lm.py`, `core/types.py` | Typed finalization outside current DSPx forward lock can store complete LMRequest/history. Typed DTO and history repr/model_dump expose source data. Guard public entry/finalization and use payload-excluding DSPx request **and result** repr. |
| Installed `mlflow/dspy/autolog.py` | Adds a global callback, enables tracking and safe-patches compile/evaluate. Disabling a callback alone is not proof that autolog patches/tracing are absent; do not call autolog(disable=True) as a cleanup workaround. |
| Installed `PIL/Image.py::open` | accepts `formats`; unrestricted discovery can initialize unrelated codecs. **Both** opens must pass the frozen restricted format tuple. |
| Installed PNG/JPEG plugins | PNG parses ancillary chunks before returning dimensions; JPEG SOF supplies dimensions before pixel decoding. Pre-scan bounded structure and dimensions before **any Pillow open**; exclude WebP/native allocation ambiguity. |
| `packages/dspx-core/src/dspx/services/program_service.py:1395–1665` | Creates outdir and resolves retrievers before `render_signature_surface`; raw intent/examples/harness writes occur later. First renderer guard can deny image generation before payload writes, but must not claim zero directory/retriever effects for arbitrary generation. |

Retained findings: the sole `DSPyTypedLMAdapter` accepts text only today; generic
providers are stub and IP-literal loopback OpenAI-compatible only, vision=false.
The existing provider performs one send without credentials/proxy/redirect/retry,
has 256-message/1,000,000-text-character and 2,000,000-response-byte bounds, and a
shared RLock/indeterminate latch. Its `Exception` catches do not cover every
BaseException; events are in-memory only. Episode descriptors and generated direct
DesignMD materialization are different implementations; raw runtime_inputs,
replay fixtures, traces and output echoes are not protected by current secret regexes.

Static metadata reports Pillow12.1.1; it is **not a direct Core requirement**.
Static source/AST/hash inspection is not dynamic API, codec/resource, import-origin,
RECORD/wheel, privacy or execution verification. Parent tests must prove these seams.

## 3. Owner architecture and nominal contracts

```text
trusted parent authenticates actual operator approval, binds caller/source/limits
 -> one private ImageCustodySession + supervised invocation (no resume)
 -> image_privacy outer context BEFORE inputs/materialization/program import
 -> shared image_input_contract and optional image_decoder (no fetch)
 -> helper-issued strings + ordered source/marker commitments
 -> guarded ChatAdapter formatter BEFORE permissive marker expansion
 -> installed LMRequest/LMImagePart -> sole DSPyTypedLMAdapter
 -> nominal DSPx parts -> existing admitted loopback provider -> one bounded send
 -> typed response/finalization under same lock -> durable terminal -> safe artifacts
```

DSPx owns decoding, admission-data checks, provider/effect/custody/receipt semantics;
DSPy owns module-facing typed API. AK owns authority/evidence/decisions. DesignMD
owns source semantics and receiver judgment. No generic dspy-lm-auth, specialty jury,
Soomfon route, second LM, provider inheritance bridge or foreign journal is introduced.

Nominal proposed DTOs (frozen/slots, no public payload repr):

- Existing `ProviderMessage(role,text)` remains the text-only message.
- `ProviderTextPart(text)`; `ProviderImagePart(media_type,data:bytes,sha256,
  byte_count,width,height,occurrence_id)`; `ProviderPartsMessage(role,parts:tuple)`.
  Image `data` and text are repr=false. PartsMessage has **no .text flattening**.
- `ProviderRequest(model,messages,image_binding=None)`: exact old/new message union,
  image_binding contains manifest/admission/request-plan commitments and in-memory
  session handle, not a caller-selected terminal verdict. Request repr shows only
  model/provider-safe counts/digests; never nested text or image values.
- `ProviderResult(text,model,effect_disposition,usage,provider_data)` excludes text
  and arbitrary usage/provider_data from repr. Only allowlisted scalar facts cross
  result validation; no upstream request/response repr/dump in diagnostics.
- `ImageContext`, `ImageCustodySession`, `LiveImageAuthority` and
  `SyntheticImageAuthority` are distinct nominal in-memory objects, not dictionaries
  that become live capability through a truthy field or `approval_ref` string.

Exact DTO type checks apply in both adapter and direct provider. Recompute hashes,
lengths and dimensions from bounded bytes; caller-supplied metadata is not proof.
Only user images; text roles remain system/user/assistant. Image detail **None only**;
metadata/name/tool/audio/video/document/binary/file_id/path, non-default generation
settings, async/streaming/tools/copy/state/fallback remain unsupported before send.
Mixed parts preserve every ordered text/image boundary. Image messages serialize
as ordered text/image_url blocks with canonical inline data URIs; text-only messages
keep existing string content. No text/filename/description substitute for pixels.

### Exact direct stub algorithm

Under StubProvider.operation_lock, before explicit_response_text or `_render`:
require exact ProviderRequest, matching model, image_binding=None, nonempty bounded
messages, **every message exact ProviderMessage**, accepted role and exact str text,
aggregate existing text bounds. Reject PartsMessage (even text-only PartsMessage),
ImagePart, malformed union or image binding with preflight_rejected/dispatch_count=0;
record one safe stub event, never completed_success. Adapter rejects any image to
stub **before invoke**, leaving stub events empty. Tests must distinguish these two
boundaries and include explicit_response_text fixture mode. Scope now permits this
minimal change; no stub vision advertising, image fixture success or decode occurs.

## 4. Limits, filesystem and restricted optional decoder

All are **code/test ceilings**, not live authorization; lower owner/policy ceilings
win. A positive integer must exclude bool. Proposed complete input/request ceilings:
6 image occurrences, 8MiB=8,388,608 file bytes each, 24MiB=25,165,824 sum,
16,000,000 pixels each, width/height 1..8192; raw JSON/HTTP body <=40MiB=41,943,040;
256 messages, 512 parts total, 1,000,000 text characters, depth16/4096 input nodes.
Per-response bytes <=existing 2,000,000, output text <=existing 1,000,000 characters;
total safe output artifacts <=4MiB; image invocation wall <=180,000ms, per-request
I/O timeout <=30,000ms and policy cap. These wall/I/O figures are proposed new image
ceilings, not an alteration of old text-only settings or selected live budgets.

Count occurrences, including duplicates/references in all fields. Per-request
repetition must match admission.request_plan and independently obey request image
sum/count. Sourcepackage accounting never deduplicates repeated bytes. Decode images
one at a time; discard pixel buffers before next image. 16MP can allocate ~64MB RGBA;
24MiB compressed-file budget is **not** an RSS bound. No native memory proof claimed.

### File/data algorithm before decoder or DSPy materialization

1. Enter outer privacy context (§5); byte-bound input JSON before parse, duplicate
   keys denied, exact descriptor keys, depth/node/whole-package accounting.
2. Base dir is the caller-supplied concrete input-parent fd, never cwd/search/~.
   Reject absolute/URI/NUL/backslash/empty/dot/dot-dot components, symlink ancestors
   and leaf, special files. Root and path get no-follow fd traversal; containment is
   an additional check, not a substitute. Final open uses
   `O_RDONLY|O_CLOEXEC|O_NOFOLLOW|O_NONBLOCK` **before** fstat. This prevents FIFO
   open blocking before regular-file rejection. Require regular file, bounded size,
   read limit+1 from this fd, before/after stat identity/size, then hash same bytes.
   Unsupported flags/primitives fail closed. No check-then-path-reopen by Image.
3. Strict source grammar: exactly one raw base64 source with explicit MIME, or
   `data:<MIME>;base64,<canonical RFC4648>` with MIME image/png or image/jpeg only.
   Reject whitespace, URL-safe alphabet, percent escapes, extra MIME params,
   header/source conflicts, invalid/missing padding and empty data. Precheck encoded
   length `4*ceil(per_image_bytes/3)`; decode(validate=True), byte bounds, exact
   re-encoding equality. Remote/file URLs never fetch; typed path/file_id deny.
4. Decode only after PNG/JPEG predimension scanner and package budgets pass.
   Every failure uses a fixed code/slot number, never path/input/Pydantic error repr.

### Frozen PNG/JPEG subset before either Image.open

Scanner reads bounded immutable bytes, not a file plugin. It never decompresses
metadata or image pixels. Reject unsupported structure instead of guessing MIME.

- PNG: exact 8-byte magic; first chunk IHDR length13 with CRC, positive bounded
  dimensions, color type 0/2/3/4/6, legal bit depths, compression/filter=0,
  interlace=0 in initial subset. Scan complete file with checked uint32 lengths,
  offsets <=file length, <=4096 chunks; verify CRC for **all** chunks; IHDR exactly
  once, contiguous IDAT, IEND length0 exactly last, PLTE/tRNS length/placement
  consistent. Allow only IHDR,PLTE,tRNS,IDAT,IEND plus fixed-size sRGB(1),gAMA(4),
  cHRM(32),pHYs(9). Reject acTL/fcTL/fdAT (including single-frame APNG), iCCP/zTXt/
  iTXt/tEXt/eXIf, unknown chunks and trailing bytes. No metadata decompression can
  occur in plugin `_open` before dimension admission. This intentionally excludes
  otherwise valid annotated/interlaced PNGs; no silent stripping/reencoding.
- JPEG: exact SOI; length-checked marker scan bounded by input bytes and <=4096
  segments; exactly one SOF0 with 8-bit samples, 1 or 3 components and bounded
  dimensions, complete component records; one baseline SOS with legal component
  membership and baseline scan fields; DQT/DHT/DRI lengths checked, tables/IDs bounded.
  Permit only canonical APP0 JFIF without thumbnail (bounded fixed structure);
  reject other APPn/COM, progressive/arithmetic/other SOF, DNL and extra scans.
  Scan entropy bytes without decoding: FF00 stuffed bytes and RST0..7 permitted,
  unexpected markers reject; EOI exactly at end. Reject ambiguous/truncated/header
  bombs before native JPEG initialization. Pillow load remains the actual pixel/
  entropy validity check, not this scanner's claim.

Decoder procedure: verify frozen decoder identity; under warnings-as-errors and
unchanged process-global limits open `BytesIO(raw)` with
`Image.open(..., formats=("PNG","JPEG"))`; require exact selected plugin class,
expected format/mode/size, n_frames=1 and no animation; verify(); close; reopen a
fresh BytesIO with **the same formats tuple**, repeat checks, load(), repeat size/
frame/mode checks; close/free pixel buffers. Never `.text`, EXIF processing,
resize/transcode/from_bytes/automatic codec discovery. LOAD_TRUNCATED_IMAGES must
be false; altered global decoder/plugin settings deny, not temporarily normalized.

Freeze identity as `decoder-profile-v1`: Pillow version/metadata hash; relative file
hash inventory for PIL Image/ImageFile/_binary/PNG/JPEG/ImagePalette support and
_imaging extension, bundled native libraries/selected runtime codec dependencies;
OPEN[PNG/JPEG] factory/accept qualified identities plus exact loaded function/code
origins, mode/format allowlists and unchanged security constants. Profile digest
belongs in sourcepackage/admission. Reject substituted functions/plugin classes,
missing members, changed inventory or constants, unsupported install/platform.
Revision2 proof hashes the newly inspected plugin/open/native files, not complete
runtime dependency closure; completing/falsifying the profile is a **provider-free
implementation test obligation**, not a claim that file hashes prove native safety.
An absent optional Pillow or frozen profile means image_decoder_unavailable before
materialization/invoke; text functionality unaffected. No imports/install/download to
repair availability. Core has no direct Pillow guarantee; no extra/pin is added.
**WebP, GIF, SVG, TIFF, AVIF, PDF and all other codecs are excluded.** WebP expansion
needs separately inspected predimension/native resource evidence and owner scope.

Same-UID hostile mutation/process logging is outside cooperative custody. The
supervised invocation/deadline below bounds process settlement, not syscall isolation
or a complete decoder sandbox. Actual resources and exact-wheel behavior remain open.

## 5. Outer privacy context: algorithm before values cross DSPy

Both entrypoints call the **one shipped** image_input_contract orchestrator. Direct
provider image calls also require its active context/session; they cannot bypass
privacy/admission by calling invoke. An image-capable invocation enters this context
before input loading, marker construction, generated import/build, **any Module/
Predict call**, provider initialization or diagnostics with values. JSON admission
parse is bounded and errors are fixed codes. No image helper calls upstream Image,
Image.from_path/from_url or Image.format; its LRU is neither populated nor relied on.

1. Require a parent-owned supervised invocation (§8), exact admitted runtime
   identities and cooperative serialized image-run lock. Reject ambient tracing
   or unknown instrumentation rather than turn it off globally. No parallel batch,
   GEPA, threading, async worker fallback or custom generated effects in this subset.
2. Inspect installed settings base **and context overrides**, not just resolved
   settings: callbacks must be exact empty sequences; send_stream=None and
   stream_listeners empty; usage_tracker/caller_predict/caller_modules absent,
   track_usage=false. Trace may only be the fresh exact empty default list or None;
   nonempty trace or substituted sink rejects. Reject nonempty existing global/LM/
   module histories/traces, configured conversation History fields and streaming.
3. Require MLFLOW_ENABLE=0 and no active MLflow run, DSPx observability, enabled
   autolog integrations, tracing provider or patched DSPy functions. Do not import
   MLflow just to check it: inspect loaded trusted modules' config/patch registries
   and function identities. A loaded unknown/uninspectable tracing/autolog state,
   MLflow DSPy safe-patch registrations (even with a disabled flag), or changed
   Module/Predict/Adapter/LM methods rejects. No `autolog(disable=True)`/unpatching
   mutation. Fresh image worker must omit observability initialization entirely.
4. Use dspy.context with callbacks=[], disable_history=True, max_history_size=0,
   trace=None, max_trace_size=0, warn_on_type_mismatch=False, provide_traceback=False,
   send_stream=None, stream_listeners=[], track_usage=False, usage_tracker=None,
   and the owned guarded formatter below. cache=False on sole LM; reject request
   cache override. Guard the specific installed value-warning setting BEFORE
   Module/Predict entry, not after its warning occurred.
5. Import/build only existing statically checked generated source, **without input
   values**. Bounded graph walk over concrete `vars` and exact list/tuple/dict members,
   visited identities <=4096/depth16, no arbitrary getter/iter/repr. Every root/nested
   Module/Predict, selected LM and formatter has exact empty callbacks/history/traces;
   every Predict has empty demos/train and no compiled state/config/LM override.
   Deny unchecked demos (including text-only), custom adapters/signatures with
   custom validators/renderers, custom Type instances, dynamic module creation and
   opaque object containers. Allowed first image graph is generated no-effect wrapper
   with exact installed Predict leaves (optional standard ChainOfThought container),
   source-bound signature/IO, no tools/retrievers/parallel topology or arbitrary
   overrides. Source profile denies runtime instrumentation/custom-module effects.
6. Signature compatibility is computed from annotation descriptors and the helper's
   bounded **shape tree** (kind, nullability, counts), never `_is_value_compatible`
   on unknown classes or repr(value). Allow fixed primitives and bounded containers
   only; image-bearing fields render as exact str. Compare declared IO keys/order,
   required/default fields, field types/containers and generated source/plan hashes.
   Reject before Predict with code signature_input_shape and numeric slot, no value
   or annotation repr. Signature instructions/default text also get marker checks.
7. Validate/issue materialized fields under context. Before invoking program walk
   graph again; before each formatter/LM/provider boundary recheck active context
   identity, callback/trace/history/streaming/settings and plan cursor. Changed
   observers deny, never repair silently. Image LM public __call__ guard runs BEFORE
   calling inherited decorated BaseLM.__call__; direct forward has same checks.
8. Keep context through response privacy checks, typed finalization, parsing and
   safe projection. Any sink/config drift becomes a fixed error; no exception
   chaining/value traceback. finally drop payload references and restore local
   context/locks. No secure erasure claim; caller intentionally printing upstream
   objects and malicious arbitrary same-process patching are outside this membrane.

No production live authentication is fabricated by this context. Its operator/caller
binding is supplied by the trusted parent; callbacks can't authenticate that act.

## 6. Strict helper-issued markers BEFORE permissive expansion

We need an owned **formatter**, not a second LM/provider. Proposed
`BoundedImageChatAdapter(ChatAdapter)` in image_privacy.py sets
use_json_adapter_fallback=False, native_function_calling=false, native_response_types
empty and callbacks empty. It is the **only** allowed image formatter; deny arbitrary
settings.adapter, JSONAdapter/custom overrides or per-Predict substitutes. Constructor,
format and call boundaries check the context and signatures; acall rejects. It does
not invoke `_legacy_type_markers`, json_repair or the old Adapter.format pipeline.

Algorithm shared by source materialization and formatter:

1. Compute admission-independent ordered sourcepackage (§7) after bounded validation.
   Assign occurrence_id `s000001..s000006` in deterministic declared field order
   then list order; no path/name data in public IDs. Helper context holds immutable
   occurrence records/raw bytes, not caller dictionaries with trusted hashes.
2. Reject any marker start/end sentinel, unissued image block/data URI or reserved
   descriptor in original non-image strings, candidate instruction/default text,
   aliases, demos or conversation history. Two sentinel kinds must be absent before
   helper issuance, not just a well-formed regex match. Reject malformed DesignMD
   reserved JSON/status/sources, rather than treat as ordinary text.
3. Issue marker bytes **once**: fixed start sentinel + canonical compact JSON
   `[{'type':'image_url','image_url':{'url':canonical_data_uri}}]` + fixed end sentinel.
   Use actual JSON double quotes; one block, exact key sets, no metadata/detail,
   duplicate keys, escaping alternatives, repair, nested markers or extra blocks.
   Store marker SHA256 -> ordered occurrence entry, URI/data hash and allowed slot
   in the context registry; source bytes are validated *before* constructing strings.
4. Generic descriptor lists become ordered plain str segments/issued markers only.
   DesignMD `visual_image_inputs_json` becomes a versioned transient envelope:
   safe metadata JSON WITHOUT payload or marker, followed by ordered slot labels
   and standalone issued markers (not markers double-quoted/escaped inside JSON).
   Its image-input-envelope-v1 status is explicit; this field remains annotated str,
   not a claim that the whole envelope is JSON. Only newly generated compatible
   runners use it; no hand retrofit of old kits or DesignMD owner mutation.
5. Guarded format uses inherited ChatAdapter.format_system_message and
   format_user_message_content only for the admitted simple signature/no-demo/no-
   history subset. It **does not call Adapter.format**, which expands markers.
   Scan the raw system/user result with a single linear balanced-sentinel parser:
   every start has one end, no nested/orphan sentinel; strict json.loads with
   duplicate-key denial; exact canonical serialization equals registered bytes;
   exact occurrence sequence equals the plan for this Predict/call. Any added,
   moved, changed, doubled-quoted or unregistered marker rejects before upstream
   `_render_request`. No fallback to raw text or unknown empty metadata part.
6. Emit explicit ordered text/image blocks from this validated scan, or equivalently
   concrete LMTextPart/LMImagePart values. Then use installed LMRequest construction
   with NO remaining marker strings. Override formatter `_render_request` to use
   these exact messages, not upstream `_coerce_lm_messages` repair paths, and
   `_call_lm` to call sole LM with `request=`. Return response outputs through
   installed typed/public parsing helpers, not a fake provider response envelope.
7. Sole LM validates normalized user parts against source manifest/plan again:
   count, order, content hash, MIME/dimensions, forbidden detail/metadata. Direct
   LM calls accept only helper-bound typed requests; raw messages use the same
   strict scan/block parser **before** upstream normalization. Image data cannot
   be accepted based solely on upstream stripping of the data-URI header.

Text-only execution does not use this formatter or change its historical behavior.
A helper registry is invocation-local source validation, **not an AK permission
registry**. It cannot mint operator approval. Independent falsifiers must use actual
newly generated program/Predict, not a replacement runtime or marker-count test.

## 7. Closed admission schema and non-circular commitments

For all new closed records use canonical UTF8 JSON (sorted keys, compact separators,
ensure_ascii=True, integers only, no duplicate keys/nonfinite numbers/unknown keys).
`H(domain,record)=SHA256(domain ASCII + NUL + canonical_json(record))`.
Digests are external fields in enclosing records, never self-hashed inside the
record that defines them. UUIDs are canonical lowercase UUID4; hashes 64 lowercase
hex; opaque refs have fixed UUID/hash shapes, no URLs/local paths/credentials.

**Sourcepackage S**, schema `dspx-image-source-package-v1`, exact fields:
`schema_version, candidate_manifest_sha256, candidate_source_sha256,
raw_input_file_sha256, input_shape_sha256, decoder_profile_sha256,
source_occurrences, plain_text_slots`.
Each source occurrence exactly `{occurrence_id, field_slot, list_ordinal, media_type,
content_sha256, byte_count, width, height}`; each text slot `{field_slot,text_sha256,
char_count}`. Declared IO order determines slots; byte-equivalent duplicates stay
separate. S contains **no admission, custody, marker or inputmanifest digest**.
`source_package_sha256=H(source-v1,S)` freezes exact source independently.

**Admission A**, schema `dspx-image-admission-v2`, exact fields:
`schema_version, mode, provider_kind, model, canonical_base_endpoint,
source_package_sha256, candidate_manifest_sha256, runtime_identity_sha256,
decoder_profile_sha256, request_plan, limits, deadlines, custody, approval_binding`.

- mode is synthetic or live; provider_kind=openai-compatible; exact model and
  canonical IP-literal loopback base, derived chat endpoint checked identically.
  No DNS/auth/proxy/credentials. Endpoints are symbolic/unselected in this design.
- request_plan is ordered, nonempty, <=64 entries. Each exactly
  `{plan_ordinal,predictor_slot,request_shape_sha256,image_occurrence_sequence}`.
  Request shape commits model and ordered roles/part kinds/text hashes/image IDs/
  file hashes, **without A/M/attempt IDs**. Repetition explicitly appears here and
  is counted again per request. No implicit demos/history/tool calls/probes.
  Source-to-plan mapping must cover declared intended inputs; missing/extra/
  reordered input use rejects. First future live proposal targets one request,
  not six calls; no such proposal/approval is made here.
- limits exactly `{max_source_images,max_request_images,max_image_bytes,
  max_source_image_bytes,max_request_image_bytes,max_pixels,max_width,max_height,
  max_input_json_bytes,max_request_body_bytes,max_text_chars,max_messages,max_parts,
  max_depth,max_nodes,max_response_bytes,max_output_chars,max_output_artifact_bytes,
  total_dispatch_allowance}`. All positive int<=§4 ceilings;
  total_dispatch_allowance=len(request_plan)<=64. Each request shape obeys bounds.
- deadlines exactly `{not_before_utc_ms,expires_utc_ms,total_wall_ms,
  per_request_io_timeout_ms}`. UTC epoch milliseconds valid int, expires>not_before;
  wall<=180000, I/O<=30000 and policy cap, I/O<=wall. Parent checks wall-clock
  interval; worker uses parent-established monotonic absolute deadline (clock
  rollback cannot extend it). Entire decoding/formatting/send/finalization/artifact
  publication must settle before it. No budget refreshed by object construction.
- custody exactly `{custody_id,caller_run_id,caller_binding_sha256,root_dev,
  root_ino,caller_expectation_sha256}`. Private root supplied as held fd, not a
  manifest-selected filesystem path. Parent independently holds expected binding;
  validate inode/owner/mode/no-follow against the fd and this record.
- approval_binding exactly `{owning_ak_task,operator_evidence_ref,
  parent_confirmation_sha256}` for live; synthetic values are null, fixed mode
  separates types. Existing AK refs are **opaque provenance**, not authenticated
  permissions or a new lookup registry. No evaluated program mutates/queries AK.

`a=H(admission-v2,A)`. **Inputmanifest M**, schema
`dspx-image-input-manifest-v2`, exactly `{schema_version,source_package_sha256,
admission_sha256,marker_entries}`; entries exactly `{occurrence_id,marker_sha256}`
in source order; `m=H(manifest-v2,M)`. Dependency order **S -> A -> M -> actual
request commitment R** eliminates the former admission/manifest circularity.
Actual R hashes `{admission_sha256,input_manifest_sha256,plan_ordinal,
request_shape_sha256}` after comparing actual normalized shape to the plan.

Preparation order is explicit: a **provider-free prepare-only supervised context**
checks runtime/privacy, reads/decodes source, builds S/marker hash entries and previews
strict formatted request shapes without Module/Predict/LM execution or provider/client
construction. It returns safe commitments, not payloads or permission. Parent can bind
an empty private root fd/identity, present exact S/plan/limits to the operator, and only
after actual approval freeze A and derive M from those marker hashes. Live worker
rederives S/markers/M from held source inputs and must match caller-held commitments
before parent initializes ready.json or releases any dispatch. Prepare-only has no
LiveImageAuthority; no failed preparation or copied preview can advance to send.
Parent actually authenticates the operator act out-of-band, checks all exact data,
source disclosure/retention and caller expectations, then supplies nonserializable
LiveImageAuthority to the one owning invocation. Code verifies data identity and
custody, **not** operator identity from JSON. Copied JSON cannot deserialize this
capability. Cooperative trusted-parent control is the explicit trust boundary;
malicious Python code manufacturing internal objects is not cryptographic security.
One authority object can bind/create only its exact one session; existing directory
is not a fresh session. Changing model/root/limits/nonce requires new owner approval.

Synthetic authority cannot select `_default_transport`, HTTPTransport or a custom
network transport: factory requires **exact httpx.MockTransport**, supplied by the
provider-free test harness, rejects subclasses/default transport before client
creation; synthetic result always fixture_evidence=true, live_authorized=false.
No serialized synthetic/live flag upgrade, generic environment selector or TOML
can mint live authority. Live image direct-provider invocation requires live nominal
session + supervised context; if absent reject before opening HTTP client/send.

Name-only capabilities stay vision=false. Instance reports transport supported,
admission present and model_vision_verified separately; the last remains unknown.
Network.mutate/provider/capability policy and timeout caps still apply, but are never
operator approval. Operator must approve exact input package, endpoint/LLM,
request/repetition plan, deadlines, output and call budgets **before any live call**.

## 8. Durable custody: exact records, atomic budget and state machine

Image custody lives in image_custody.py, shared by direct provider and both runtimes.
No copied jury/AK permission state. Private root: concrete held fd, owner euid,
mode0700; files regular mode0600 nlink1, no symlink/special file/foreign ownership.
Parent holds fd and independently expected admission/source/caller identity before
worker entry. Root writes are bounded canonical safe JSON only, no raw request or
response; no nested caller-selected names. Reject unknown entries or stale temp files.

Closed **ready.json**, `dspx-image-custody-ready-v1`: exactly schema_version,
custody_id,caller_run_id,caller_binding_sha256,caller_expectation_sha256,
admission_sha256,source_package_sha256,input_manifest_sha256,
runtime_identity_sha256,root_dev,root_ino,total_dispatch_allowance,
request_plan_sha256,creator_pid,created_utc_ms. Provider does not create a new root
from raw admission. Parent initializes this no-replace after authenticating binding;
worker verifies every field. lock file is inert/private; cooperative flock on its fd.

Closed **intent-N.json**, `dspx-image-dispatch-intent-v1`: exactly schema_version,
custody_id,caller_run_id,caller_binding_sha256,admission_sha256,
input_manifest_sha256,attempt_id,attempt_ordinal,plan_ordinal,request_sha256,
request_shape_sha256,image_occurrence_sequence,validated_image_count,
validated_image_bytes,reserved_utc_ms,deadline_utc_ms. attempt_id UUID4 is issued by
**provider**, not caller/request hash; caller retains independent expected context/
provider binding. Ordinal N is 1-based consumed dispatch slot, plan_ordinal=N.

Closed **terminal-N.json**, `dspx-image-dispatch-terminal-v1`: exactly schema_version,
custody_id,caller_run_id,attempt_id,attempt_ordinal,intent_sha256,request_sha256,
dispatch_count,provider_disposition,observed_model,response_sha256,
response_byte_count,finalization_kind,result_finalization_completed,
typed_finalization_completed,failure_code,terminal_utc_ms.
Dispositions are completed_success/completed_failure/effect_indeterminate/
preflight_rejected; dispatch_count 0/1; response facts null unless fully observed.
finalization_kind is dspy_lm or direct_provider, chosen by the protected entry, not
request data. result_finalization_completed requires full nominal result validation;
typed_finalization_completed additionally requires DSPy typed construction and LM
finalization (false for direct_provider; do not invent typed execution). Codes are
closed fixed enums (validation, budget, policy, io, response, interruption,
finalization, durability, privacy), never provider exception strings.

Closed **closure.json**, `dspx-image-run-closure-v1`: exactly schema_version,
custody_id,caller_run_id,admission_sha256,input_manifest_sha256,
consumed_dispatches,terminal_commitments,artifact_manifest_sha256,
local_outcome,closed_utc_ms. Each commitment exactly ordinal/attempt_id/terminal_sha256;
local_outcome completed/failed/effect_indeterminate. Artifact manifest contains only
versioned image artifact names/hashes/sizes; no paths or payload. Successful provider
outcome is not successful local publication. Missing closure is not a reusable run.

### Publication primitive and atomic consumption

Every record: validate canonical bytes<=64KiB; create random `.pending-UUID` via
O_CREAT|O_EXCL|O_NOFOLLOW mode0600; bounded write loop; fsync file; publish with an
atomic no-replace link/rename primitive under held root fd, never overwrite target;
remove only this own settled temp; fsync directory; re-read exact final bytes/hash.
Temporary hardlink is an internal publication step only; after cleanup verify nlink1.
If publication/fsync/verification status is unknown, **do not send** (before send)
or latch indeterminate (after send); preserve residue for inspection, no retry/delete
of unsettled records. Platform lacking these primitives rejects image invocation.

Provider RLock -> custody flock is the fixed lock order; hold both through validation,
reservation, send, typed response construction, LM finalization and terminal fsync.
An ImageAttemptTransaction is reentrant only for the same active session/thread:
outer LM __call__ holds RLock/flock while provider invoke returns a provisional
result, and releases only after LM finalization plus terminal publication. Provider
cannot publish early success in this mode. Direct invoke owns its transaction through
nominal result validation/terminal publication; it does not claim DSPy finalization.
Native flock is acquired once per transaction; nested entries reuse ownership rather
than open a second lock fd. No nested opposite-order acquisition. Under flock scan all existing intents and terminals (<=64); verify
contiguous ordinals, distinct UUIDs, exact bindings/hashes/plan, no unknown/residue/
closure/open intent/indeterminate terminal. N=number of published intents+1. If N
exceeds allowance reject. **Publishing intent-N is the atomic consumption of one
dispatch allowance and issuance of its attempt identity.** No separate mutable count
can drift; every reservation remains consumed even if known zero send or interrupted.
Prevalidation failures before reservation consume no send slot and return fixed
local rejection; they cannot relabel any existing attempted operation.

Do not send until this intent is durable and caller expectation binding verified.
Install in-memory dispatch-entered flag immediately before calling send; dispatch
count1 means local effect-capable entry, not billing/model processing. Check monotonic
remaining wall and request I/O budget before send and throughout response consumption.
Parent watchdog is authoritative for hard wall (§below). Exactly one native send;
redirect fully received => completed_failure, zero followups. Send/read uncertainty,
BaseException, cancellation or unexpected typed construction/finalization failure
=> indeterminate same UUID/slot, latch adapter/provider/session. After validated full
response/typed finalization, publish terminal **once**. No earlier completed-success
terminal that must be overwritten to repair finalization. In-memory provisional
event may be replaced for same UUID; durable terminal is immutable.

On post-send BaseException: latch first, attempt bounded safe indeterminate terminal
publication while locks held, settle response/client/child cleanup; rethrow safe
interruption with no value traceback. Terminal-write failure leaves intent open and
session poisoned, never a success/no-effect receipt. Pre-send cancellation **after
reservation** may publish preflight_rejected/count0; slot consumed and run closes
failed, no reattempt. After typed finalization, guarded formatter parse/known privacy
rejection can close local failed with completed provider terminal; no parse fallback
or next dispatch. Unknown post-send processing/durability failures retain conservative
uncertainty, not inferred no-effect. Artifact publication failure closes failed if
safe closure can publish; otherwise missing closure is retained and invocation denies.

### Supervision, reconstruction, and no continued work

For cumulative wall bounds, per-read HTTP timeout alone is insufficient. Image mode
requires a parent-owned **short-lived supervised worker** (candidate or direct-port
mode), with exact existing executable/package identity, fixed safe environment and
no observer/provider preloads. Source inputs held via confined fds; IPC for payloads
is bounded anonymous memory/pipe, not stdout/temp-file capture. Parent receives safe
status commitments only; worker owns the shared provider operation lock and writes
private records. No thread-based "timeout" leaving live HTTP work behind.

Parent records worker PID/start identity and monotonic deadline before allowing work;
waits/reaps its owned process group. On deadline/EOF without final status, signal
owned worker/group TERM then bounded KILL/reap; never dispatch a successor. If child
settlement cannot be proven, retain IDs/custody and report unsettled indeterminate,
not a completed bounded run. Parent reconciliation under flock trusts only exact
owning records + independent expected bindings; absence of terminal yields unknown
facts, not no-effect. No extra network probe/retry to learn the outcome. A fully
observed pre-send refusal is distinguishable only with attributable parent evidence.
This is proposed process custody, not full-host/syscall isolation or admitted Docker.

Reconstruction API is **read-only verification only**, never a new dispatch handle.
Existing ready/root UUID cannot bootstrap live/synthetic session from disk or reset
allowance. It rejects open/missing/malformed/foreign terminal, missing closure,
publication residue/failure, mixed bindings, duplicate UUIDs or indeterminate state;
no repair/overwrite/resume. Even an all-completed closed run is spent. Within the
one originally active authenticated run, subsequent calls may only consume its
remaining predeclared plan slots after all earlier terminals are durably valid.
New object construction over that same session shares ledger/locks; new empty root,
request hash or copied admission is not permission for a new run. Fresh experiments
require a new actual owner-approved caller/authority/custody binding.

Safe **effect envelope v2**: schema_version=dspx-provider-effect-evidence-v2,
image_contract_version=dspx-bounded-image-contract-v2; closed fields schema_version,
image_contract_version,admission_sha256,input_manifest_sha256,custody_id,
caller_run_id,attempt_total,attempts_truncated,terminal_effect,attempts.
Image-mode events have exact existing provider/model/count/disposition fields plus
attempt_id/attempt_ordinal/plan_ordinal/request_sha256/intent_sha256/terminal_sha256/
validated_image_count/validated_image_bytes/failure_code. Retain<=64 events; totals
from durable consumed slots, explicit truncation (allowance<=64 initially), terminal
precedence, unique ordinals and null terminal commitment when not durable. Do not
claim a complete envelope while an intent is open. Adapter pre-invoke denial creates
no provider attempt; a local rejection is kept in image run outcome separately.
Text-only effect-v1 and consumed historical outcomes stay byte/meaning compatible.

## 9. Both materializers, versioned artifacts and no raw durability

One shared orchestrator implements privacy -> source/decoder -> S/A/M -> marker
issuance -> guard -> custody -> execution -> projection. Episode _materialize_*
and generated run.py `_load_inputs` import it; generated run.py contains no alternate
base64/data-URI/DesignMD validator. Missing helper/decoder/version denies, never
permissive fallback. Newly generated direct runner receives only explicit
parent-bound admission/context, not environment/TOML-based vision permission.

Image-run artifacts use a **separate** branch, not changed meanings of old paths:

| Artifact | Exact schema and content |
|---|---|
| `image_source_package.json` | S, `dspx-image-source-package-v1`; hashes/shape/occurrences only |
| `image_input_manifest.json` | M, `dspx-image-input-manifest-v2`; no marker/URI/base64 values |
| `runtime_image_inputs.json` | `program-runtime-image-inputs-v1`, exactly schema_version/source_package_sha256/input_manifest_sha256/input_shape_sha256/plain_text_commitments; no input values |
| `image_behavior_results.json` | `program-image-behavior-results-v1`, exactly schema_version/caller_run_id/candidate_manifest_sha256/source_package_sha256/execution_status/local_outcome/output_commitments/quality_status/failure_code; commits output field slots/hashes/sizes only |
| `image_program_runtime_traces.json` | `program-image-traces-v1`, exactly schema_version/caller_run_id/predictor_plan_ordinals/attempt_ids; never kwargs/prediction/last_runtime_trace copies |
| `image_oracle_evidence.json` | `program-image-oracle-evidence-v1`, exactly schema_version/caller_run_id/source_package_sha256/artifact_manifest_sha256/authority; authority=local_non_authoritative, no raw output/index publication |
| `runtime_image_episode.json` | `program-runtime-image-episode-v1`, exactly schema_version/caller_run_id/candidate_manifest_sha256/source_package_sha256/input_manifest_sha256/admission_sha256/effect_evidence/artifact_manifest_sha256/local_outcome/non_authority; all non_authority flags false for authority/mutation |
| `runtime_image_episode.json.meta.json` | new run_kind=program-runtime-image and image-contract receipt extra; replay claim integrity-only, execution unsupported |
| `direct_image_run_receipt.json` | `generated-dspy-direct-image-v1`, same source/admission/effect/artifact commitments and local outcome/non-authority, never old direct-run-v1 relabeled |

Two named manifest records use schema `dspx-image-artifacts-v1`, exactly
schema_version/caller_run_id/artifacts; entries exact `{name,schema_version,sha256,
byte_count}`. `image_content_artifacts.json` lists sourcepackage/inputmanifest,
projected inputs/behavior/traces and safe output slots only. Oracle/episode/receipt
reference its digest, never their own hash. `image_published_artifacts.json` is built
last and lists content manifest plus those subjects and Oracle/episode/receipt;
closure.artifact_manifest_sha256 commits its bytes. Neither manifest lists itself;
closure is not a manifest member. Integrity readback starts from independently held
closure hash and follows published -> content -> subjects; receipt alone cannot
prove closure. These two names and closure are additionally in the closed artifact
name allowlist; no arbitrary paths or cyclic/self-hash definitions. Source episode/run identity includes S/M and
caller_run_id; changed pixels at same filename yield changed identity.

Image receipt exact fields: schema_version=dspx-image-run-receipt-v1,
run_kind=program-runtime-image, caller_run_id,candidate_manifest_sha256,
source_package_sha256,admission_sha256,input_manifest_sha256,
content_artifact_manifest_sha256,effect_evidence,local_outcome,replay_policy,
non_authority. run_receipts returns this closed branch rather than copying arbitrary
legacy extras. direct_image_run_receipt uses the same fields with its tabled schema
and run_kind=generated-direct-image; it adds no paths/observability/error text.
replay_policy has exactly receipt_integrity_check_supported=true,
execution_reproduction_supported=false,semantic_reproduction_claim=false,
quality_reproduction_claim=false,reason=image_execution_replay_unsupported.
non_authority exactly promotion_authority,activation_authority,governance_mutated,
external_authority_mutated,shared_oracle_mutated,release_authority (all false).
quality_status remains not_evaluated; transport/parse completion is not visual quality.

Validators in episode service select exact schema branch; verify closed keys,
canonical bytes/bounds/non-authority, source->admission->manifest chain, artifact
names/hashes, expected candidate/caller commitments, all effect ordinals/UUIDs/
intent/terminal/closure bindings, planned order/repetitions, totals and indeterminate
precedence. Integrity checks never decode inputs, execute a model or accept metadata
as authenticated authority. Unknown version or mixed v1/image-v1 rows reject.
Old program-runtime-v1, runtime_inputs.json hashes, direct-run-v1, text effect-v1 and
stub replay validators remain **unchanged**, not heuristically upgraded.

Image mode never writes raw runtime_inputs.json/replay fixture/input copies, source
paths, payload-bearing cached kwargs/history, _last_runtime_trace or model/exception
repr. Source owner input files already supplied are not copied, overwritten or
claimed erased. capture_replay_fixture/image execution replay rejects **before**
materialization/provider setup. run_receipts explicit program-runtime-image branch
reports image_execution_replay_unsupported with no strategy; no stub substitution
or fresh provider call on check-only. Image integrity replay checks only safe records.

Before any response hits parser/durable output, validate strict bounded str and a
privacy deny scanner: reject sentinel strings/data:image URIs/reserved payload keys,
full source base64 in raw/JSON-escaped form and canonical re-encoded byte equivalents;
any long base64-shaped run (>=128 characters, alphabet/padding syntax) rejects rather
than attempting to persist a "sanitized" semantic answer. Strict bounded recursive
output objects use whitelisted scalar/container shapes; no arbitrary object stringify.
If provider echoes raw bytes/base64/markers, keep only fixed privacy_failure and
safe provider outcome/response digest/length, never raw output or diagnostic text.
This conservative filter can reject legitimate code strings; arbitrary transformed/
semantic secret leakage is **not** solved. Owner disclosure review, bounded explicit
output schema and private retention remain separate. Default no MLflow/Oracle sink
or output logging; allowed safe receiver outputs are private no-replace files after
privacy check, within total output budget. No credential content is supplied/read.

### Generation-time image exclusion is an executable refusal, not a promise

First operation of `render_signature_surface` (before topology branch/import), plus
all standalone surface/harness render functions in program_surfaces, invokes a
no-effect generation preflight. Deny nonempty inline examples/demos or any dataset/
examples_path in an **image-enabled candidate profile**; deny image descriptor keys,
base64/data-URI/marker/payload status anywhere in bounded intent/examples/options/
default instructions. Text-only generation with ordinary examples remains unchanged.
No bytes become an image-capable generation artifact; no silent raw example retention.
For old candidate input, outer image context rejects examples/datasets/compiled/demos
and reserved payloads in candidate artifacts before import/execution. Direct tests
of renderer and whole materialization must prove no raw intent/examples/harness/
manifest writes. program_service currently can create then clean an empty failed
dir/resolve retrievers before renderer; zero generation-filesystem/retriever effects
is **not** claimed. Image profile forbids retrievers; if tests find pre-render raw
persistence or unrelated effects, stop and request exact owner scope for an earlier
preflight instead of widening to program_service silently.

## 10. File responsibilities and reviewer-adjudicable tests

No implementation authorized in this revision pass. Optional helpers now in exact
scope avoid exceeding code500LOC/50KB and separate owners without duplicating logic:

| Proposed Core file | Responsibility |
|---|---|
| image_input_contract.py | One orchestrator, closed descriptor/source/marker/S/M algorithms, both materializers |
| image_admission.py | Closed A, non-circular hashes, nominal live/synthetic parent capabilities, exact plan checks |
| image_decoder.py | Optional frozen PNG/JPEG scanner/decoder profile, both restricted opens, confined O_NONBLOCK reads |
| image_privacy.py | Outer/nested observer/shape guard, owned formatter and no unchecked normalization/fallback |
| image_custody.py | Private records/no-replace fsync/atomic consumed slots, supervision/reconciliation/read-only reconstruction |
| provider_contract.py | Ordered nominal union, payload-excluding request AND result repr |
| stub_provider.py | Direct strict old-message validation before fixture success |
| dspy_typed_lm.py | Sole LM raw/typed guard, same lock through finalization/terminal, post-send BaseException handling |
| openai_compatible_provider.py | Direct admission/privacy/custody checks, one bounded send/response, provisional facts and UUID |
| provider_registry.py/provider_runtime.py | Explicit admission constructor, synthetic transport separation, closed truthful v1/v2 projections |
| services/program_runtime_episode.py | Shared image orchestration and new closed artifact/effect validators, no old-v1 meaning changes |
| services/program_surfaces.py | Generation refusal + new runner helper import/image branch; no validator copies |
| run_receipts.py | Separate image run_kind integrity-only replay policy, no image execution replay |

Tests: image_admission (S->A->M/R circularity/order/repetition/wall/output/caller drift,
copy/synthetic-to-live denial); image_custody (two-process concurrent reservations,
fsync/link/terminal/closure failure at every phase, killed workers, UUID/slot/reset/
read-only reconstruction); image_privacy (global+nested observers, autolog patches,
warn_on_type_mismatch logger spy, incompatible shape without value log, custom
adapters/demos, recheck drift); image_input_contract (PNG/JPEG structure/±1 bounds,
all-input sum, O_NONBLOCK FIFO/symlink/race, marker strictness, absent decoder).
Decoder tests may live in test_image_input_contract.py (no new unauthorized test path).

Existing test_dspy_typed_lm/openai_compatible/stub verify actual installed 3.3.1,
request/result repr, direct and adapter pre-effect distinctions, structured part
order, exactly one send, no ChatAdapter fallback after parse error, finalization+
BaseException+queued call latches. test_program_runtime_episode and
new test_program_surfaces_image_inputs/test_program_service_cli_examples execute
**actual generated Predict/ChainOfThought subset** with exact MockTransport only:
malformed/DQ/repaired/missing/extra-key marker, unregistered plain-text marker,
wrong signature, demo/custom adapter must reject BEFORE installed marker normalizer/
observer/invoke/send; valid fixture must show actual LMImagePart and exact wire bytes.
Separate spies on json_repair, `_legacy_type_markers`, callbacks, logger, forbidden
file open/fetch, send, artifact/cache/MLflow/Oracle writes prevent passing proxies.

Future feature path tests/features/typed-image-runtime.feature consumes the detailed
red cases in design/red-cases.feature only after independent disposition. Fault tests
must check raw durable bytes including partial publication/closure and console; empty
logs alone don't prove that no observer ran. Missing optional-library/API coverage
is a hold, not an acceptance skip. Full-host/wheel/resource/live/receiver proof require
separate admission; no verification profile is activated by this proposal.

## 11. Schools, confrontation, preference and effects

Author analysis drawing on Decision118 schools, **not new independent reviews or a
formal Prompt Vault dispatch** (vault tools unavailable in this harness):

- Upstream-native: native parts eliminate facsimiles; counterexample is permissive
  marker normalization before LM and value-logging before translation.
- Ports/adapters: nominal bytes/identities retain DSPx authority; extra formatter is
  an upstream formatting membrane, not a second LM or restored provider bridge.
- Runtime safety: immutable consumed slots and late durable terminal beat in-memory
  counters; unknown publication/worker settlement beats presumed no-effect/resume.
- Vertical slice: six screenshots, PNG/JPEG, one existing loopback port and default
  one separately approved request beat broad codec/routes/parallel campaigns.
- Privacy: private digest artifacts and observer refusal beat convenient raw replay;
  conservative echoes can impair outputs and need receiver fitness inspection.

Confrontations resolved by **proposed preference, no verdict**: pre-materialization
privacy beats late LM-only redaction; owned strict formatting beats permissive repair;
sourcepackage before admission beats circular commitments; direct stub checks beat
fixture success; atomic intent consumption beats resettable counters; restricted
predimension PNG/JPEG beats WebP breadth; spent reconstruction beats automatic retry.
No unanimous school approval is asserted. Parent can reject these algorithms.

First-order effects: bounded pixels reach ordered typed request; decoder/shape/marker
refusals and private custody add CPU/process/IO costs. Second-order effects: both
materializers share one membrane; no demos/custom formats/raw replay, narrower image
formats/signatures and private outputs change debugging/generation compatibility.
Third-order effects: explicit source/request/attempt separation enables later empirical
comparison without granting authenticity/semantic quality; digests can correlate
sensitive sources and supervised process proof can be overclaimed as sandboxing.
Transport success does not prove visual analysis, WCAG, model quality, production,
DesignMD receiver acceptance, release/publication or activation.

## 12. Parent adjudication questions and stop boundary

For each evidence13275 hold, inspect the corresponding concrete algorithm and red
cases: privacy §5; pre-normalizer markers §6; custody/budget/finalization §8; admission
§7; direct stub §3; restricted decoder/fds §4; shared helper/image artifacts §9.

Required independent questions: Can safe generated formatting/annotation checks be
implemented without calling the old repair pipeline? Is nested graph/no-autolog
admission sufficient for the frozen exact runtime? Are code budgets achievable with
these scoped helpers? Does every fault preserve consumed budget/late terminal and
settle the worker? Does generation refusal truly precede raw writes? Can the frozen
optional decoder profile/resource tests support the narrowed subset? Does parent
operator/caller custody remain an actual authenticated act rather than local JSON?
Are sourcepackage/artifact definitions acyclic and old schemas truly untouched?

**Stop before code pending independent architecture/runtime-safety disposition.**
No reviewer acceptance is recorded by this child. Stop on scope/source/API/profile
mismatch or unproved earlier raw persistence; request exact owner scope, no workaround.
Stop before any live call without exact separate operator approval. Any uncertain
effect/durability/worker settlement is terminal; no retry/relabel/resume/fallback/later
case. This revision returns with own claim released, task pending, no commit.
