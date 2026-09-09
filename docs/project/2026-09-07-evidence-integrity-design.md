---
summary: "AK-5511 implementation wire contract: pinned stdlib-only complete-v1 historical closure verification and bounded task-local runtime repairs."
read_when:
  - "Provisioning the DSPx verifier or wiring the Misegraph consumer."
---

# AK-5511 evidence integrity — implementation contract

Implementation authorized by controller
`misegraph/docs/project/2026-09-07-evidence-integrity-implementation-plan.md`, following
second review SHIP of the bounded design. **Implementation/validation results are
reported separately; this specification is not a passing proof.** No model call,
acceptance, task completion, push/release or target/fork mutation is included.
The controller subsequently authorized the exact current-execution auth repin
recorded below; it is not historical verification or permission for a live call. Broad graphs, intermediate v2 versions, pre-jury context and deterministic
quality acceptance are NOT this repair. Only `after_jury` is supported.

## Exact wire API (DSPx leads; consumer must not invent another protocol)

Entrypoint: `packages/dspx-core/src/dspx/services/program_foundry_closure_check.py`.
Invoke an explicitly provisioned absolute CPython executable as:

```text
<absolute-reviewed-python> -I -S -B <absolute-installed-entrypoint>
```

One bounded UTF-8 JSON request on stdin; EOF required. No arguments in normal use.
One closed UTF-8 JSON response on stdout. Exit 0 means a complete report, **including
invalid/incomplete/unsupported**; nonzero means invocation/internal failure, never
trust stdout as a report then. Consumer caps output/time and verifies request hash
and independently provisioned profile identity. No shell/PATH/env-selected runner.

### Request: all fields required, closed recursively

```text
{
  schema_version: "dspx-foundry-closure-check-request-v1",
  phase: "after_jury",
  verifier_profile_sha256: Digest,
  subject: {
    schema_version: "misegraph-evidence-package-v1",
    manifest_sha256: Digest,
    package_sha256: Digest
  },
  expected: {
    package_manifest: Ref,
    import_binding: Ref,
    import_provenance: Ref,
    imported_intent: Ref,
    imported_inputs: Ref,
    jury_receipt: Ref,
    adjudication: Ref
  },
  roots: [absolute_directory],
  locators: [{sha256: Digest, bytes: UInt, root: UInt, path: Relative,
              aliases: [OriginalAbsolute]}],
  limits: {
    request_bytes: 262144, json_bytes: 2097152, artifact_bytes: 16777216,
    closure_bytes: 134217728, files: 256, json_depth: 64,
    path_depth: 16, jurors: 32
  }
}
Ref = {original_path: OriginalAbsolute, sha256: Digest}
```

Digest is exactly 64 lowercase hexadecimal characters; UInt excludes booleans and
floats. `limits` must equal the fixed values, not user-selected relaxation. At most
four distinct roots, 256 locator entries, eight aliases/entry. Each `root` indexes
`roots`; `path` is a normalized no-parent/no-backslash relative path. Original paths
are retained strings for existing hash/implicit-sibling identities, NEVER direct
filesystem read permissions. Every alias is unique; conflicting or repeated aliases
and physical locator duplicates reject. Same digest in different roles/locations is
legal. Consumer builds request from independently chosen identities, not an evidence
file selecting code/profile/root. All seven expected identities are required even
if the requested artifact later proves missing. No verifier filesystem search.

Paths are at most 4096 UTF-8 bytes, components at most 255 bytes. Reports fit a
64 KiB consumer output cap. Roots are descriptor-opened component by component,
no symlinks; roots, member directories and files must belong to current UID and
not be group/world writable. Reads are nonblocking,
regular-file-only, bounded while streaming, and checked before/after via descriptor
identity. Every inner evidence reader uses the same captured bytes. Unknown aliases
produce `incomplete`; no fallback to an embedded absolute path. Inventory excludes
unread optional logs, credentials, scripts and environment files.

### Response: all fields required, closed recursively

```text
{
  schema_version: "dspx-foundry-closure-verification-v1",
  request_sha256: Digest,
  verifier_profile_sha256: Digest,
  phase: "after_jury",
  status: "verified" | "invalid" | "incomplete" | "unsupported",
  subject: <request subject>,
  expected: <request expected>,
  identities: {
    program_intent_sha256: Digest|null,
    normalized_runtime_inputs_sha256: Digest|null,
    source_manifest_sha256: Digest|null,
    candidate_manifest_sha256: Digest|null,
    comparison_sha256: Digest|null,
    consumption_receipt_sha256: Digest|null
  },
  closure_inventory_sha256: Digest|null,
  captured_files: UInt,
  captured_bytes: UInt,
  quality: {origin: "injected_test_double"|"provider_claim_only"|"unknown",
            acceptance: "unknown"},
  origins: {
    source_generated: Origin, source_runtime: Origin, oracle: Origin,
    gepa_student: Origin, gepa_reflection: Origin,
    candidate_generated: Origin, candidate_runtime: Origin, jury: Origin
  },
  historical_authority: "unknown",
  claim_ceiling: "historical_bytes_only",
  review_eligible: false,
  reason_codes: [bounded_reason_code],
  limitations: [bounded_reason_code],
  non_authority: {
    acceptance_authority: false, release_authority: false,
    activation_authority: false, ak_called: false
  }
}
Origin = "fixture_record" | "local_effect_record" |
         "historical_owner_journal" | "unknown"
```

Verified requires every identity/inventory digest non-null and the complete
required closure. Echoed `subject`/`expected` are independently checked by the
consumer, not proof merely because echoed. Nonverified reports may contain partial
computed identities; they never grant eligibility. Invalid outer requests are
invocation errors (nonzero), not fabricated well-shaped reports. Unknown provenance
stays unknown. Origin means retained support, NEVER a derived authenticated-live
label. Even verified owner journals lack response-text/parsed-output authentication
and saved lease observations. Acceptance is unknown without an actual independently
bound acceptance source; adjacent derivation prose cannot strengthen it.

`request_sha256` hashes the exact stdin bytes, including whitespace/newline.
`closure_inventory_sha256` hashes domain bytes
`b"dspx-foundry-captured-closure-v1\0"` followed by compact UTF-8 sorted-key JSON of
rows sorted by original path; each row is exactly
`{original_path, sha256, bytes}`. Same captured physical file can serve multiple
original aliases; captured byte/file counts count physical locators once. Existing
path-dependent closure hashes are separately checked; relocation changes access
only, not original identity strings or historical hashes.

## Provisioning trust (outside the evidence bundle)

Deploy only the fixed **16 files** named by the entrypoint's installation manifest
below (not a wildcard glob), as ordinary reviewed files in a separate
non-writable-by-untrusted-user directory. No package installation, pip/uv resolution,
editable checkout/site hooks or model dependencies are needed. `-I -S -B` excludes
user/site startup and bytecode writes; it is not an OS sandbox claim. The entrypoint
loads only the fixed captured current modules; it never adds its installation to
`sys.path`, so an extra sibling cannot shadow the trusted standard library. This
executes reviewed current verifier code, never historical code or evidence scripts.

Installation profile digest is SHA-256 of
`b"dspx-foundry-verifier-profile-v1\0" + C([{path: basename, sha256: file_hash}, ...])`,
with fixed module names sorted, compact UTF-8 sorted-key JSON and no newline.
`--profile` prints this manifest/profile for provisioning convenience; its output
is **not the trust anchor**. Provisioner independently hashes the reviewed source
files and CPython real executable/runtime, copies the files offline, verifies the
installed copies, and records approved interpreter/module/profile identities in
consumer-managed policy outside evidence. Consumer verifies these before launch.
The returned profile hash alone cannot authenticate a compromised executable.
No arbitrary profile/data module paths or historical source imports are admitted.
Final module/profile hashes must be frozen after formatting/testing; until then the
wire shape is fixed but the installation identity is not a release artifact.

Misegraph performs target package/schema/fidelity checks and invokes this pinned
DSPx reconstruction with independent expected roots. It rejects detached supplied
reports, mismatched request/profile hashes, nonverified closure and false authority.
Verified historical bytes are useful inspection evidence, **not new live-supported
review recommendations**. All outputs keep review_eligible=false in this repair.

## Existing closure and normalization obligations

Required import/package files join to accepted quality candidate and source
manifest intent; source/candidate surfaces, runtime meta receipts, normalized inputs,
behavior/traces/outputs, Oracle request/result, GEPA proposal/attempt/result/optimizer
inventory, consumption/candidate comparison, and jury/attempt/results/journals plus
adjudication are verified without executing any artifact (including program.pkl).
Do not infer closure from whichever `_path` keys happen to exist. Fixed role
collectors require the existing edges, using exact old builders/reducers as semantics.
Metadata cache paths and owner source paths confer no read permissions.

The missing accepted-intent equality is restored, not bypassed by stripping
provenance. For supported v1 normalization, compare ProgramIntent payloads under
the pinned exclude-none/default rules; saved source intent omits `examples_path:null`.
Examples/criteria/options cannot be silently dropped. Unsupported shapes fail
unsupported rather than guessing a new normalization contract.

Hash domains:
- Import/file/receipt references: SHA-256 of captured original bytes.
- Program intent: sorted Python-default JSON of normalized exclude-none payload
  (ASCII escaping, spaces, no newline), matching receipt evidence.intent_hash.
- Quality identity: compact UTF-8 sorted-key JSON; reproduce envelope identity,
  candidate/proposal and derived-pending decision-source hashes. These algebraic
  equalities do not prove an actual acceptance invocation.
- Runtime inputs: one `inputs` unwrap if mapping, then `{"inputs": value}`, sorted
  UTF-8 indent 2 plus newline; bind both runtime episodes to that hash/source.
- Candidate closure and optimizer tree retain their own original ordered rows,
  paths, serializers and exclusions. Do not conflate these with report inventory.

Generic code verifies identity/equality and metric binding. Misegraph owns recipe
IR/schema/fidelity semantics; lexical concept coverage is not culinary correctness.
No new recipe-specific derivation algorithm is added to DSPx.

## Frozen historical profiles and separately authorized current execution pin

Frozen old/current source tuples, dependency identities and supported family
route/timeout/alias/reducer semantics are packaged as finite reviewed constants.
History does not require current owner installation/task lease/catalog/credentials.
Only current execution pin may authorize new calls after normal owner/AK checks.

Pre-repair DSPx observation `8cedfb9d377e16643dc35041b40a9d2db0445083`, tree
`2d64e6b1f52b3f38e06dd4a28c99c0c351faae5a`, owner 6c3473ca17bf03325698e3e1a8419a8abc915938.
Pre-AK5512 owner policy blob `d6504369e69f2cd27fc60067cc7ee2886a823c8b`, SHA-256
`5f52d12ca189abccd6c55e69d8d1d2f04f5384b454add886de8bfef114462087`;
family blob `38f76cfa09f272b9e6c629072e8e95de01eac10e`, SHA-256
`d87a59e13b34a981a0e9b553b23f8451941f0c40f7e6defd601677a87345695a`.
These preserve complete owner/dependency/extra-file data before repin.

Needed old owners: 80cc409da976028263da884ed633bef0806cd986 (DSPx 2ccfbe65,
owner blob 2e879cb5f9f5a7fe3f1bd28c92608b0612275e63) and
777388ad9c692b0657e6b6e1d4820b15fcb6641d (owner blob
f948cad2a472ac972e2ca6aca55933798cc2ad2b). Family policy recovered at exact
originating DSPx commits, not arbitrary dynamic old code. Accepted historical
identity cannot enable execution. Historical 6c3473ca/80cc409/777388a constants
remain byte-for-byte unchanged. No new historical profile was added.

Controller now explicitly authorizes AK-5512-reviewed implementation source commit
`a893382e3a7abc06de0814f29709b9143b930826` (review `dispatch-1788781092679`), tree
`a4c4b050e2bace57586119d2e8ae9865511484d8`, version `0.1.6`, lock
`d24ee392e2846b3baac33e16a67ff3e9094b3b021c67e32e50a1f1d11b077648`.
Current DSPx execution policy is repinned to these exact bytes. All eight receipt
modules and all extra owner files were collected and checked from a clean detached
local clone; later docs HEAD `15867b52` was not used as source authority. The default
integration test consumes the local Git object store, checks out the exact source
commit in test-owned scratch and verifies the complete source policy. It does not
require mutable maintained HEAD to equal the source pin and makes no network fetch.
Unavailable object store skips only this integration proof, never weakens runtime
verification. Non-strict jury model projection preserves observed `None` for aliases
or prefixed models; requested text is never substituted for an unknown observation.

## Saved proof target and validation

Known roots under `/home/tryinget/.local/state/pi-quests/tmp/`:
`misegraph-foundry-honest-5366.RZzphH` (132 foundry files/2,952,169 bytes),
`misegraph-foundry-imported-vllm.RByYoY` (130/2,842,856), and Copilot
`misegraph-foundry-copilot-5346.DVXv7O` (130/2,877,783; family-only, no package import).
Initial design observations were not a verifier pass. The implementation results
below now include executable positives. 5366 remains connected-byte evidence with
injected quality/unknown acceptance and A-to-A limitations, never a fake live fixture.

5366 selected vectors:
- Imported intent raw: `6acb0d91f3fb16c5344ff72b28affa02cb019165c2298a95ecd94ebe72b298bc`.
- Program-intent domain: `93ef681c3b4bdbc9460a28803c36970fbb6c9fc88a0cb7d3a894eba95bca450f`.
- Quality candidate compact: `195b4f5bbf478dc864877a5551bbe2ba055ca46b028d6e2f942e99223c1abe6d`.
- Runtime inputs: `0aee8c5222b752649c009f8c2f3a7cf460d440c164ce6f4b5840639982bc2570`.
- Jury receipt: `634a9fe4aeab7cc14d2172788af1c3b20e9ed7a9d901c828c0631247b94457de`.
- Adjudication: `7745f7477ee4f012b57d140caa067492d548c5003b854b2f288fc692c90b1c7d`.

Tests must cover package/intent/inputs/proposal/jury substitutions, changed local
hashes versus independent roots, strict JSON/types/aliases, missing siblings,
symlink/FIFO/size/depth bounds, historical profiles after pin upgrade, limited
origins, all-failed versus mixed results, request/profile mismatch, relocated
installed stdlib-only execution and denied effects. Hash originals before/after;
negative modifications only in memory/separate owned TMPDIR. No original replay.

Runtime slices separately repair explicit execution repo (no parents[5]), truthful
per-check preflight (remote catalog GET is an effect), and streaming bounded jury/
probe stdout with bounded cleanup and no-replay preservation. Full gate failures
remain visible; scope or new acceptance prerequisites stop the affected slice.

Growth baseline 12347dec→8cedfb9d: source +8,901/-589 (net +8,312), tests
+12,865/-60 (+12,805), docs including evidence JSON +16,447/-1 (+16,446).
Foundry subsets overlap: service/CLI net +6,433; three Misegraph-named source files
+1,416. Existing 35 foundry service files total 12,667 LOC. New source/test sizes and
actual validation/commit outcomes are reported below and in the scoped diary,
not inferred from this plan.

## Corrective capsule after implementation HOLD (review pending)

Independent HOLD `dispatch-1788781092681` invalidated the completeness claim for
baseline `7fbb491a`: runtime-manifest, GEPA lineage and comparison semantic joins
were missing. Do not bind the obsolete profile
`0e891173b651032a74e720a88b649ebf895e369bc0d70c727e7154d538d15107`.
The next baseline `9e78cca2` / profile
`dc27f425513ed616ffbc21ff80ed9460ea0f773628acebd0878e6dfad483b91e` also remained on
HOLD: rehashed trace source and Oracle dependencies could pass direct `runtime()`.
Both profiles are obsolete. The following capsule requires independent corrected
SHIP before target trust. The separately authorized auth repin above is not that
SHIP. Wire versions and hash domains are unchanged.

The runtime-graph baseline `f460b082` / profile
`e17c2ef0390b1c3783b477654c858672b4bd8c850b7014874ca9bf407ab7b7ea` subsequently
retained an identity HOLD: comparison identities incorrectly preferred the receipt
bundle over canonical manifest precedence. That profile is also obsolete. The
controller's minimal correction and regression evidence are recorded below.

Current pure-verifier profile (corrected SHIP candidate, review still required):
`726ad977b188bbaa57e72f59cdec2ca485fbde299fe7e7e019927c5d8d2d678f`.
Exact module basenames (16, previously 11):

| Module | Raw SHA-256 |
|---|---|
| program_foundry_closure_check.py | `511c59bf850ef0638a432468bc1ad00d9880c30899e60e744e1f738fe1d74db7` |
| program_foundry_closure_comparison.py | `3992421d62059d7ec3740a20c4e4b8e4f712ff9723e83d51e9d5b70d589f24d5` |
| program_foundry_closure_contracts.py | `3a5b99e510e3163352d45c34479d46e2a3a3f86de872c7a38011618695d18c25` |
| program_foundry_closure_core.py | `f908d2a184ae3427682552e22e23ed40a2fba8bbda2c9419fa4c4cc27cfefd17` |
| program_foundry_closure_gepa.py | `4f9c8ef6b618237a583b559228fe531ad1dfef0f97e022c9784ca5f4a2d6cd5d` |
| program_foundry_closure_import.py | `d603a4f0d7e0573a587211d7c7ed42c42be0b829c6455fa85168aee06633620c` |
| program_foundry_closure_io.py | `28a556f0b2fc30a55ed198a36cb091f342120698a92d99fd87e0b7ea42db535d` |
| program_foundry_closure_journal.py | `bc75534be0f3893229542e19f7a1958155ef63461d55fdc1720cc47a27010c35` |
| program_foundry_closure_jury.py | `bb1e65e00bfe00030a600b0e91728eafba6e1fcc4c74205c9b6359cc2f7396be` |
| program_foundry_closure_profiles.py | `58e745dc2bd2d61fc274112ddd89ff1a8c844477e26906a185f51f55e8d04a09` |
| program_foundry_closure_reducers.py | `3620e262692e187980bc88d66e1f07b3884ecef37479b9f2bd9892e237bfbfcc` |
| program_foundry_closure_runtime.py | `b4656531db49d29ea0ccdd6b375ce8e27082e3d28737fe257b46aa8fd0fcfbff` |
| program_quality_evaluation.py | `ead816876c7abc6b65e08858fd468fbfde175671bdc4a5ca43e9c540e5e2abf7` |
| program_refinement_gepa_metric_honesty.py | `09ac15ec0f45a95be1203814c20541d60e83e93f84cd125a52b7887de0b93afc` |
| program_runtime_trace_coverage.py | `950da6bb7ef8e546c1da67ee5fc757b0f6b77c7d687059c7b82c83b0577cca08` |
| program_runtime_traces.py | `ac1bc69eead6cf34393eae5754d074131e8a057f8b5c47143a951629a43ce162` |

Tested CPython real executable:
`/home/tryinget/.local/share/uv/python/cpython-3.13.12-linux-x86_64-gnu/bin/python3.13`,
SHA-256 `2fa13dc1ef5d30c51d34c276448eadbacc769d50d14ae0b0ad3ed812691bbc7e`.
This is an observed executable digest, **not an attestation of the entire stdlib/
native runtime**; provisioning must independently approve that complete runtime.
The fixed module set can be copied offline without installing DSPx/DSPy/auth packages.

Observed complete saved byte inventories (the advisory lock file is not evidence):

| Saved root | Files / bytes | Captured inventory SHA-256 |
|---|---|---|
| honest-5366 | 146 / 3,053,461 | `0e7240536a4ae27d62c97e6c785da540655a255c4c020ddfca8858a3e50f23b1` |
| imported-vllm | 145 / 2,937,554 | `eeb1449be9a28fdd30eaae87011e9dc2fb08855b8720df43fdd17e5500cd6962` |

Both report `verified`, injected-test-double quality, unknown acceptance and
`review_eligible=false`. Both runtime stages retain local effect records, not
independent live authentication; generated behavior and both GEPA model stages
remain unknown. Jury origin is historical owner journal. Espresso Oracle remains
unknown; imported-vLLM Oracle is a fixture record. Copilot has a passing journal-only
fixture and is deliberately not a package/import closure positive.

Additional existing-v1 distinctions are preserved: materialization refreshes the
embedded execution episode while retaining its separately hashed generated episode
file; its stale generated Oracle artifact is explicitly removed. These are not
silently normalized into one payload. Receipt cache keys and saved replay identities
are recomputed without reading cache paths or requiring this interpreter to match
historical execution identity. Captured comparison facts are verified/bound, not
rerun as new optimizer performance or target-domain judgments. Oracle/jury transport
request bodies and provider response text are not fully retained/authenticated.

Runtime API adds `execution_repo_root: Path | None` and CLI `--execution-repo`.
It is mandatory for a new task-local execution, retained in its attempt/request,
and never derived from source/wheel layout or cwd. Legacy requests without it still
have inspection semantics; generic registry execution retains its one-shot path.
Preflight records checked/not-applicable/not-checked facts and never claims
unprobed credential validity, reachability or completion capacity. Jury and credential
probe transports share a selector-based bounded duplex helper; overflow/timeout kills
and reaps the child group without `communicate()` buffering. This is not a sandbox.

Corrective implementation:
- Runtime manifest schema, candidate identity, embedded episode id/schema, contract
  mode, fixed input/behavior paths and both hashes are checked for both runtimes.
- GEPA materialization source identity/paths/hashes, result hash, optimizer manifest
  and payload inventory/count, metric honesty, status, refresh and authority flags
  are checked; execution-tree and optimizer-payload hash domains remain distinct.
- Nineteen pure comparison helpers are now shared with the current producer instead
  of maintaining divergent approximate reducers. Finite 777388a pre-label/exact,
  80cc409 label-era, and 6c3473ca label-era/conservative dialects reconstruct all three
  semantic projections. Historical `live` labels are checked as old assertions,
  never projected as authenticated provenance. No recipe or model rerun occurs.
- Both stripped-runtime mutants and field-level contradictions execute through the
  isolated capsule. GEPA/comparison tests additionally check exact inner-contract
  rejection and transitive rehashes while preserving subject/seven expected roots.
  Root-anchored mutants may reject at the outer hash boundary; the direct contract
  tests separately prove the new inner checks, not a misleading passing proxy.

Validation observations and final deltas are recorded in the scoped HOLD-repair
session diary. `just ci-quality` now passes, including the nine baseline type errors
repaired with explicit test-double casts and type-narrowing assertions. The retained
metric-honesty test now distinguishes and validates both legacy and extended v1
projections without rewriting historical artifacts. The subsequently authorized
exact-source repin and detached-clone test repair the former owner-pin failure.
The full offline heavy-job attempt was denied by workstation retained-run process
reference inspection; no bypass or unrelated scratch cleanup was performed.
`just verify-full` also includes live/infrastructure residual tests outside this
no-live authorization. No full-gate pass or independent SHIP is claimed.

Tests now default to repo-owned, frozen, selected credential-free Espresso closure
and Copilot journal-only bytes. Archive SHA-256 values are checked before extraction;
original absolute paths are inert aliases, and scripts/pickles are never executed.
The selected fixture excludes credentials, env files, caches, derivation scripts and
mutable lock files. Compression is storage only, not executable fixture generation.
`DSPX_CLOSURE_SAVED_ROOT` / `DSPX_CLOSURE_JOURNAL_ROOT` optionally select immutable
external roots for additional audit; they are no longer needed by default positives
or mutants. Tests hash evidence before/after; mutants live in separate owned scratch. Relocated stdlib-only execution,
ignored unreviewed siblings/current-policy modules, strict JSON, aliases, FIFO/
symlink and write permissions, substitutions/rehashed leaves, all-failed reduction,
profile mismatch, streaming overflow and explicit wheel-independent context are
covered. These tests do not replay consumed attempts or contact a provider.

## Readback parity inventory — residual runtime-graph HOLD

Audit basis: the complete `program_runtime_episode.py` readback validator
(1663–2030), stable bundle loader (2031–2098), identity/path/provider helpers and
pure Oracle/trace builders; `program_refinement_gepa_candidate_contracts.py`
(400–921 and adjacent path/inventory helpers); and
`program_refinement_comparison.py` (691–943 plus behavior loaders and reducers).
The runtime remains unexecuted: this is parity of **captured readback dependencies
for the finite supported closures**, not proof of replay, historical execution,
quality acceptance, model authenticity or isolation. The inventory classifies
coverage and intentional boundary differences rather than silently dropping checks.

| ID | Existing dependency / check | Captured implementation and proof |
|---|---|---|
| R01 | Episode schema/status/execution status, nonempty id | `core.runtime`, `contracts.runtime_graph`; id additionally re-derived from source manifest hash, inputs hash and mode |
| R02 | Candidate path/current source hash; runtime manifest path/schema | `runtime`, `runtime_manifest`; exact aliases to one captured snapshot, both runtimes' stripped-manifest capsule mutants |
| R03 | Full manifest candidate identity, source ref path/hash, embedded episode schema/id/mode | `runtime_manifest`; direct and isolated rehashed field mutants |
| R04 | Fixed input/behavior paths and hashes; all four runtime artifact hashes | `runtime_manifest` + `runtime`; normalized input bytes bound to import, not locator hashes alone |
| R05 | Behavior schema/id/evidence-only authority, one record | `runtime_manifest` + `runtime_graph`; input/output fields and record inputs also joined to source intent/captured inputs |
| R06 | Normalized criteria, top/record quality evaluation, execution/quality status and exact summary | Same current `program_quality_evaluation.py` pure functions as producer; record/quality/summary semantic mutants |
| R07 | Behavior's nine false authority flags | `runtime_graph`; authority mutant, no new meaning assigned to the historical assertions |
| R08 | Trace schema/counts/hash arrays, every trace hash, effects/trajectory/tool-intent/scheduler/linkage/non-authority, coverage and source-record coverage | Same current `validate_program_runtime_traces` and coverage code as producer; bounded source/count checks precede coverage loops; semantic trace mutants rehash per-record hashes too |
| R09 | `traces.sources[].content_hash` to captured behavior | Exact source descriptor and full current pure trace reconstruction from captured behavior/module surfaces; failing-before/passing-after regressions for both runtimes with episode/meta/cache/replay rehashes |
| R10 | Oracle schema/kind/authority, five candidate ids plus runtime id, false flags, complete source-artifact paths/hashes, behavior result ref/summary/statuses, facet status/counts | `runtime_graph` compares every current pure Oracle-builder output field. Mutants include each source artifact, missing inventory, identity, refs, summaries and facets |
| R11 | Adjacent Oracle input evaluation-source refs, trace projection, runtime id/mode, IO/intent/text summaries | Same frozen pure Oracle builder, complete function-AST differential against current producer, plus exact field mutants; no Oracle request/response rerun |
| R12 | Required receipt/replay fields, output bytes/hash, cache kind/basename/key, provider and saved replay identity hashes | `core.meta`; runtime cache-enabled receipts fail closed because caches are outside the captured closure. Cache-disabled existence is informational in original readback, not inspected here |
| R13 | Runtime/behavior/receipt provider equality, metadata/effect envelope, capabilities, endpoint/model/timeout, attempt counts/truncation/dispatch/terminal, receipt details and legacy stub rule | `runtime_graph` + `runtime.provider`; direct receipt tests and 22 malformed-provider vectors also rejected by the original producer validator |
| R14 | Bundle readback stability, confined paths | Descriptor-captured immutable `Snapshot` bytes replace original live double-read/resolve; budgets, relocation and alias/link/race boundaries retain their tests |
| G01 | GEPA result schema/source identity/null candidate, effect/non-authority, readiness dependencies/completed attempt | `contracts.gepa_result` + `gepa.verify_gepa`; added exact base-contract mutants |
| G02 | Optimizer manifest hash, no symlinks, exact inventory/size/count/tree, program binding | `Snapshot`, `optimizer`, `verify_gepa`; opaque payloads only, complete mapped inventory including copy equality |
| G03 | Concept-coverage metric honesty, source/criteria/wrapper binding and byte-exact wrapper re-derivation | Same current pure `render_concept_coverage_program`; compare rendered bytes/hash with captured wrapper and copied optimizer payload, never import/execute the wrapper |
| G04 | Materialization result schema/status, created-from paths, source/candidate ids, candidate root and not-promoted state | `materialization`, `candidate_declarations`, `verify_gepa`; prior materialization tests retained |
| G05 | Candidate lineage schema/status/source ids/paths/hashes/GEPA result hash/non-authority | `materialization`; direct semantic and transitive outer-capsule mutants |
| G06 | Copied optimizer confinement, metric block, manifest/tree/count cross-joins; wrapper not used as materialized program | `materialization` + optimizer copy inventory; payload hash excludes manifest, execution tree includes it |
| G07 | Behavior-refresh paths/hash pairs, effect and non-authority | `materialization`; refreshed embedded execution episode stays distinct from the retained generated episode file; stale generated Oracle removal preserved |
| C01 | Comparison schema/status, local-only effects and false authority flags | `verify_gepa` + `verify_comparison`; newly added authority mutants |
| C02 | Both manifest schemas/identities/paths/hashes; declared generated behavior and behavior-episode schemas/paths/all redundant hashes | `candidate_declarations`, `candidate`, comparison created-from joins; request, embedded episode, artifact, receipt evidence and surfaces remain separately bound |
| C03 | Both runtime bundle references/readback and hashes | `runtime` for both branches, then comparison runtime hash joins; not a summary-only shortcut |
| C04 | Status plus exact behavior comparison, runtime comparison and interpretation | Nineteen shared reducers with finite historical dialects and saved/frozen differential vectors; no score or optimizer rerun |

### Deliberate limits and maintenance membrane

- Complete connected successful-execution, concept-coverage-quality historical
  closures remain the supported runtime subset. Arbitrary failing/review-mode
  executions, Soomfon-specific provider schemas, absent runtime evidence and new
  historical owner tuples are not generalized; unsupported/malformed shapes cannot
  return `verified`. Current auth execution repin does not expand historical profiles.
- Current trace reconstruction is a deliberately stricter subset of old validators
  that tolerated omitted optional coverage or unused fields. Future historical
  dialects need reviewed vectors, not a permissive fallback.
- Original materializer write-time checks (destination emptiness, copy permissions,
  overlap with a mutable source worktree) become captured confinement/inventory
  checks; no write/copy action is replayed. Non-ready GEPA results cannot represent
  a complete materialized closure. Cache file contents, source-generation cache
  availability and current-machine replay capability are outside the historical
  byte claim. Source-generation cached code is not read or executed.
- No static generated-code safety or OS sandbox proof is inferred from stored false
  flags. Trace reconstruction establishes what the local producer would project
  from saved records, not what a provider/network actually did.
- Four existing current pure modules are shared by inclusion in the fixed capsule;
  only their pure reducers are called. Oracle builder copies are guarded against
  producer drift by full function-AST equality tests and frozen positive bytes.
  Adding a new producer readback dependency requires updating this inventory and
  a semantic mutant/differential vector before publishing another profile.

### Proof separation and observed gates

`test_program_foundry_closure_runtime_graph.py` first reproduced direct acceptance
of the zeroed trace behavior-source hash in **both** runtime capsules after local
locator/episode/receipt/cache/replay rehashing. It now checks exact semantic rejection
both directly and through the isolated capsule with subject/seven expected roots
unchanged. The reanchored annotation-positive tests separately pass local `runtime()`
but fail the unchanged outer historical anchors: internally consistent fixture
bytes are explicitly not original-root proof. Receipt/provider/base-GEPA tests are
labelled direct contract tests, not substitutes for end-to-end custody validation.

Observed runtime-graph baseline broad slice: **908 passed**, including foundry, closure, comparison,
Oracle backend, runtime episodes/traces, GEPA candidate and quality evaluation tests.
The focused closure/comparison slice had **248 passed**; optional imported-vLLM audit
had **13 passed**. The broadened first attempt timed out and exposed two stale
owner-tree assertions; these were updated to the exact reviewed tree and the full
selected slice rerun. No partial/timed-out run is counted as a passing gate.
Full offline heavy-job wrapper remains blocked by eight kernel-protected same-UID
processes preventing retained-run reference inspection. No bypass or cleanup was
performed. Final quality/fast/scope checks and commit evidence are recorded in the
runtime-graph session diary; independent corrected SHIP and full-gate proof remain
separate requirements before consumer trust/release decisions.

### Final identity HOLD correction

The only subsequent source change is the controller-supplied GEPA comparison loop:
compare each source/candidate sidecar identity to `identity(s.json(manifest_path))`,
not to a receipt-bundle-only projection. It reduces source by nine LOC. Canonical
precedence matches both original comparison and model-jury producers:

- `request_id`: request → candidate assembly → execution episode → receipt bundle.
- `candidate_id`, `assembly_id`: candidate assembly → execution episode → receipt bundle.
- `episode_id`: execution episode → receipt bundle.
- `receipt_bundle_id`: receipt bundle only (no competing precedence).

`tests/test_program_foundry_closure_identity.py` adds **52 regressions**: both source
and candidate, all four precedence fields, every fallback, canonical vs shadow
comparison identities, jury agreement, and a mutually agreeing shadow comparison/
jury pair that must still fail the canonical-manifest gate. The component tests
use an explicitly labelled in-memory identity view; their original byte hashes
are not claimed to bind the altered view. No production guards are disabled.
Separate isolated-capsule mutants alter copied comparison/jury bytes and preserve
subject/seven expected roots, proving custody rejection without mislabelling it as
inner semantic proof. Original evidence is untouched.

Final selected validation: **300 focused closure/comparison tests passed** and
**960 expanded tests passed**; CI-quality including test typechecking passed.
The 16-file interface, schemas, fixed historical profiles, auth pin and claim
ceilings are unchanged. Only the GEPA module hash/profile changed, frozen after
formatting and tests. The full-gate heavy-job blocker is not bypassed or represented
as passing; no held profile is approved for provisioning by these results.

## Bounded test-gate repair plan (recorded before code, 2026-09-09)

Controller dispatch reports independent design acceptance
`dispatch-1788933214927` of the amended tests-only plan. Observed starting HEAD:
`92443fbee2ceb72c8844482215342ac76ed3211a`; AK-5511 is claimed by the existing
session through `2026-09-10T05:57:39.169144884+00:00`, scope entity version 5.
The parent-modified scope snapshot is retained untouched. This is the sole
implementation owner for this bounded slice; no other work is displaced.
Acceptance of design is not implementation review or a passing gate.

1. In the existing Oracle live test, require exact `DSPX_ORACLE_LIVE_VLLM=1`
   and `DSPX_POLICY_ALLOW_NETWORK_MUTATE=1`, reject policy-enabled bypass using
   the policy's own normalization, then check `openai-compatible` provider and
   both `network.read` / `network.mutate` capabilities before availability HTTP.
   Denied/missing permission skips without probe, preflight, resolution or analysis.
   Remove live-test self-grants and restriction clearing; keep the credential-free
   key removal, fixed loopback endpoint/model and offline MockTransport helper.
2. Add unconditional `tests/test_program_oracle_live_gate.py` calling the actual
   live test entrypoint. Count HTTP/preflight/resolution/analysis attempts (not
   exception sentinels alone: availability catches Exception). Exercise absent,
   malformed and partial opt-ins, policy bypass spellings, provider/capability
   allow and deny restrictions, allowed-but-unavailable skip and a complete fake
   successful analysis. Check permission before probe and preserve caller policy.
3. Move real BERTScore optional import into its smoke-test body, behind exact
   `DSPX_BERTSCORE_REAL_MODEL=1`; retain real/model markers only on that smoke.
   Unconditional fake-module tests cover import/score absence by default,
   argument order, forwarded defaults/options, tensor and iterable aggregation,
   empty/mismatched inputs and macro delegation. No torch/model download needed.
4. Run only these three test files, explicit-file ruff and focused typechecking
   with existing installed tools, offline namespace (`unshare -Urn` available),
   no dependency sync/download or blanket marker exclusion. Record exact commands,
   counts and limits separately. Full gate waits for independent implementation
   review. No production, Justfile, shared conftest, historical evidence, source
   pins, ontology, AK state, commit/push or lifecycle mutation.

Engineering contract read locally; immutable upstream guidance is not fetched
because this dispatch forbids remote effects. This plan does not assert a full
suite/network-isolation proof beyond the specific observed namespace runs.


## Bounded baseline characterization repair (plan before code, 2026-09-09)

Observed admission: AK-5511 claimed, scope entity version 6, evidence **8669**
(`synthetic_fixture_repair_admission`, pass), following independent design review
`dispatch-1788935571657`. Effective routing remains uninitialized; the exact task
and admission bind this slice. The prior full gate remains FAIL/HOLD, not retried.
No production repin, new live eligibility, AK mutation, commit or release is admitted.

Decision: characterize the source-only loader with a **synthetic current-source
private repository**, not a newly reviewed live runtime. In
`tests/test_dspy_lm_auth_lm.py` only, copy the required source/manifest members,
v10 contract and runner. Bind the original runner to immutable SHA-256
`f593be0834cb370806a8b5c18ac5a157e6438cf1fcaa7628ee920e47c6e868c6`.
Validate its 46-member preledger and the fixed historical/current pairs below;
patch exactly one full path/hash literal per delta (three total) in the copy only.
All copied source bytes must match the historical pins or these three fixed
current hashes. Never derive replacement pins from arbitrary current bytes.

| Source under packages/dspx-core/src/dspx/ | Historical SHA-256 | Fixed current SHA-256 |
|---|---|---|
| model_roles.py | `a7a4dc03afcbc2726d62ab4b11b951bf8d32c069652d34423c3ec08e751015a2` | `30c8f3c935e9a59b03f386d6f1525b2fa66bc36735ef611c3b75ae97b1cef8c2` |
| openai_compatible_provider.py | `df4ed50f569b4e04757592468a7f908f940b8629eef796932423357b688e5241` | `f923b5149683dd78cecc61f1b14752ddbccb7cdaeb275acc29d2c8433037b76c` |
| services/program_oracle_semantic_backend.py | `ba4c983f12f478f58ef17590b22a68ee241fa8a249f79918de8a2622f6dc60f2` | `7f44fdfd6cf71f6137ab223595d1339a2135a1c61b76594e4250e162b003598b` |

All three historical file hashes were independently recovered from Git commit
`6ea779d0f1af7e8adb2f0a7a4bc499c450b1f890`; later source changes are at
`c617826c` and `c9a52177`. Historical source/constants remain untouched.

Route the stale-PYTHONPATH positive/allowlist/origin checks, post-preparation
drift check, malicious timestamp-valid pyc check and both parametrized preledger
corruption cases through the helper. Preserve downstream checks and assert the
exact corrupted relative path in each rejection. Add a separate immutable real
runner hash/pin and fail-closed assertion, rather than counting synthetic success
as historical eligibility. These cases load actual computation-only entry modules
and use the provider-free candidate/task-binding path; no live entry is invoked
(the existing loader tests do not mock the loader itself).

Prepend only truthful summary/read_when YAML frontmatter to the three admitted
September 3 foundry-jury diaries (child-retention-and-xai-timeout,
fresh-subprocess-and-split, preflight-and-catalog). Preserve every original byte as
an exact suffix. No other diaries or reviewed gate tests change.

Validation plan: source-bound before/after inventory and exact suffix comparison;
only the focused loader/immutable-contract tests, explicit-file ruff/typecheck,
and metadata parsing. Use installed offline tools, sanitized provider-disabled
environment, no downloads/provider calls/full gate/retries. A focused namespace
run does not establish a compatible full-suite isolation posture. Record results
separately; stop for independent implementation review before any commit.


### First focused execution finding (not a pass)

The single focused pytest invocation returned **9 passed, 1 failed, 17 deselected**.
The candidate positive failed because the synthetic copy omitted the code-semantics
manifest; inspection of `load_candidate` also identified its required v9 contract.
The helper now explicitly includes `SEMANTICS_PATH` and `V9_PATH` alongside v10.
No production bytes or historical pins changed. **No pytest retry is performed**
under this dispatch. The corrected positive/allowlist/origin sequence remains
unverified and must not be described as a passing baseline repair. Static checks
and preservation evidence are reported separately.


## Foreign-origin attribution repair — parent decision before code, 2026-09-09

Parent dispatch adopts independent reviewer `dispatch1788937030933`'s minimal
follow-up within the same admitted test file. The reviewer issued bounded SHIP
for the previous repair and executed its final source: **10 passed, 17 deselected**,
plus five separately labelled scratch probes. Its source hash was
`9aa4ccff89845e274e7fdc70c4f3bfd079ba5009bfac9ae6ed49edc965bfbc2c`.
This supersedes the prior unexecuted-final-source status without erasing the
original **9 passed / 1 failed** attempt. Full-gate HOLD and non-authority remain.
Review: `/home/tryinget/.local/state/pi-quests/tmp/ak5511-independent-review.VFhg9H/review.md`.

The old foreign-backend test can pass by rejecting the ordinary `dspx.__cached__`
before inspecting the substituted backend. Decision: replace it with Gate4/Gate5
parametrized private copied-fixture subprocess checks. Establish a successful
actual source-loader baseline with the backend present, retain the same manifest,
then mutate only that backend's `__file__`. Require the exact existing diagnostic
AND the innermost rejection frame's backend-relative path and module identity.
Production exceptions do not include paths; traceback attribution tests the actual
rejection without changing those diagnostics. Restore that single origin and
require verification to pass again. Never clear modules, cached attributes,
allowlists or manifest inputs to manufacture a positive baseline.

Only `tests/test_dspy_lm_auth_lm.py` may change source; production runner and all
pins remain byte-identical. Record a dated review/result addendum in the existing
scoped diary, preserving its complete earlier bytes as a prefix. Run focused final
loader/origin regressions and explicit-file static checks offline in owned scratch
with network isolation; deterministic fixture regression reruns are explicitly
admitted, unlike mechanical retries of effect-indeterminate live/full runs. No
provider call, full gate, AK mutation or commit. Stop for final independent review.


## Bounded durable disposition — 2026-09-09 (not full-gate/lifecycle closeout)

The controller now authorizes a normal main commit of only the reviewed four test
files, exact three frontmatter-only September3 diaries, native scope-v6 export,
and scoped design/evidence docs. No new source change is authorized or performed.
Independent gate/BERT SHIP `dispatch1788934614753` reports 101-pass/2-skip plus
38-case premature-probe mutant evidence. Final synthetic/origin correction SHIP
`dispatch1788937030933` independently executed final hash
`df5191a4d26295ce0cff1e9adaed9138beed7dae5065b230c7fe3cb2c36dcdf9`: 11-pass/17-deselected,
plus four expected-rejection counterfactual characterizations. The production runner
remains `f593be0834cb370806a8b5c18ac5a157e6438cf1fcaa7628ee920e47c6e868c6`.

Fresh bounded checks total **112 passed / 2 skipped / 17 deselected** across three
complete files and the previously accepted loader selection in the fourth. Native
strict docs metadata and package/test static checks pass separately. Earlier failed
attempts and pending-review statements above are preserved as historical prefixes.
See `diary/2026-09-07--evidence-finalization.md` and its command/hash receipt for
source identities, retention inventory and exact coverage limits.

**Current full gate: HOLD.** Actual run1788935170 remains exit1; corrected metadata
and synthetic positives do not turn the 82-case isolation attribution into a
retroactive pass. A separately admitted compatible no-live variant must preserve
UID/permission/ancestor semantics, allow only isolated fixture loopback, and exclude
host-provider/model effects without weakening tests or guards. No such variant was
implemented or executed here. No task close, AK evidence/parent-record mutation,
production repin, consumer trust activation, release, push or full retry is granted.
