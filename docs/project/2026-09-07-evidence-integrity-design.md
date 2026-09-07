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
acceptance, task completion, push/release, target/fork mutation or auth repin is
included. Broad graphs, intermediate v2 versions, pre-jury context and deterministic
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

Deploy only the fixed `program_foundry_closure_*.py` module set named by the
entrypoint's installation manifest, as ordinary reviewed files in a separate
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

## Finite owner profiles; no concurrent repin

Frozen old/current source tuples, dependency identities and supported family
route/timeout/alias/reducer semantics are packaged as finite reviewed constants.
History does not require current owner installation/task lease/catalog/credentials.
Only current execution pin may authorize new calls after normal owner/AK checks.

Current DSPx observation `8cedfb9d377e16643dc35041b40a9d2db0445083`, tree
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
identity cannot enable execution. AK-5512 repin waits for controller's reviewed
exact commit; this work does not change current owner pin.

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

## Implementation baseline observations (not acceptance or release)

Frozen pure-verifier profile:
`0e891173b651032a74e720a88b649ebf895e369bc0d70c727e7154d538d15107`.
Module basenames below share prefix `program_foundry_closure_` and suffix `.py`:

| Module | Raw SHA-256 |
|---|---|
| check | `919b0a9fcf88e9422735eb34576ef50bca21297206fca8dd55759f459d85c974` |
| core | `35e543771ff306b0278db077958e7a91715fab13434a6ce6added8f4887d5477` |
| gepa | `1a9ca77835604b8ca0278243d527778ad1d6edf50920237ba8b4270338df4705` |
| import | `d603a4f0d7e0573a587211d7c7ed42c42be0b829c6455fa85168aee06633620c` |
| io | `28a556f0b2fc30a55ed198a36cb091f342120698a92d99fd87e0b7ea42db535d` |
| journal | `bc75534be0f3893229542e19f7a1958155ef63461d55fdc1720cc47a27010c35` |
| jury | `bb1e65e00bfe00030a600b0e91728eafba6e1fcc4c74205c9b6359cc2f7396be` |
| profiles | `58e745dc2bd2d61fc274112ddd89ff1a8c844477e26906a185f51f55e8d04a09` |

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

Validation observed:
- 50 focused closure/provenance tests passed with Espresso and Copilot explicitly
  selected. Imported-vLLM closure/boundary slice: 40 passed.
- Foundry-wide slice: 569 passed, 2 failed. One failure is the intentionally unchanged
  current owner pin versus the concurrent fork checkout; the other is an unchanged
  test's false assumption that every retained projection predates `metric_honesty`.
- `UV_OFFLINE=1 just verify-fast` passed (workflow, direction, governance projection,
  exact task-scope binding and installed offline hooks).
- `UV_OFFLINE=1 just ci-quality`: workflow/format/lint passed; nine type diagnostics
  remain on unchanged test lines in local-vLLM, OpenCode Go, xAI, Z.ai,
  metric-honesty and Oracle semantic tests. Changed verifier/runtime/CLI checks pass.
- No full gate pass, independent implementation review or cross-owner acceptance
  is claimed. Do not repin, release or complete AK-5511 from these local results.

Tests are opt-in for saved roots through `DSPX_CLOSURE_SAVED_ROOT` and, for the
journal-only case, `DSPX_CLOSURE_JOURNAL_ROOT`. They hash original evidence before/
after; mutants live only in separate owned scratch. Relocated stdlib-only execution,
ignored unreviewed siblings/current-policy modules, strict JSON, aliases, FIFO/
symlink and write permissions, substitutions/rehashed leaves, all-failed reduction,
profile mismatch, streaming overflow and explicit wheel-independent context are
covered. These tests do not replay consumed attempts or contact a provider.
