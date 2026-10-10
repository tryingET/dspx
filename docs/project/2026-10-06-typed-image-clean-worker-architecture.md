---
summary: "As-built architecture of DSPx typed image transport: guarded clean -I -S worker, refusal everywhere else, synthetic and live modes with admission-bound request controls, owner decisions that refine Revision 2, and what remains open."
read_when:
  - "Changing or reviewing DSPx image transport, the image worker, its guard or the decoder profile."
  - "Reading the Revision 2 design (2026-10-03-typed-image-contract.md) and needing what was actually built."
type: "reference"
---

# Typed image transport — as-built architecture

Revision 2 (`2026-10-03-typed-image-contract.md`) remains the design rationale. This page
records what was built (AK6607, re-landed by AK6760) and where owner decisions refined it.

## Boundary

- **Only the guarded clean worker reads pixels.** `supervise_image_worker` spawns
  `sys.executable -I -S -c BOOT` (fixed env allowlist, `pass_fds`, new session, stdio to
  /dev/null). BOOT's first statement registers an audit guard; no site, `.pth`,
  sitecustomize or `PYTHON*`-selected code runs before it (owner decision AK13975).
- **Poison is irreversible.** A later audit-hook, trace, profile or monitoring
  registration, a ctypes `dlsym` of a native observer API, `gc`/`_current_frames`
  introspection, or tampering with the guard writes one fixed `image_privacy` frame and
  `_exit`s the worker inside the audit call.
- **Unaudited channels are checked, not prevented.** Signal handlers, gc callbacks,
  hooks, monitoring tools and threads must be interpreter defaults when the entry
  starts; the guard holds that digest and compares it at every boundary probe.
- **Native closure.** No executable mapping other than the interpreter may reference
  `PySys_AddAuditHook` or the other observer APIs (NULL-thread-state registration skips
  notification). memfd/deleted mappings refuse. The worker is non-dumpable.
- **Everywhere else, refusal.** Materialization, privacy entry, provider binding and
  construction, typed LM call/forward and artifact binding call
  `require_clean_boundary()` first: any process without the guard (callers, forks of
  callers) gets `image_execution_unavailable` before arguments are inspected.
- **Closed control.** The parent names a `@worker_entry`-declared `module:function` and
  passes closed, integer-only JSON. No pickle, callable or transport object crosses.
- **Bound handshake (AK6766).** The parent writes a one-use 32-byte grant only to the
  anonymous permit pipe. It publishes `ready.json` (custody ready v2) only for a ready
  frame on its private status pipe whose PID, start identity, original deadline and
  grant hash equal those of the child it spawned; `verify_image_run` re-checks the
  binding's shape. A control document copied into another process, or a process holding
  neither the parent's nor the worker's pipe ends, cannot make this parent publish. The
  worker itself, its descendants and same-uid processes able to reopen
  `/proc/<pid>/fd` are outside this guarantee (threat-model limits); a self-made
  parent can only produce its own, separate ready record.

## Shipped routes

`prepare_image_execution` and `execute_image_program` (used by the runtime episode and the
generated `direct_run.py`) type-check in the parent, reserve the nominal authority, and
run declared entries in the worker. Both modes share this one route (AK6918):

- **Synthetic.** A `SyntheticImageAuthority` needs a closed `SyntheticTransportFixture`;
  the worker builds the exact `httpx.MockTransport` and publishes only send ordinal,
  block kinds, image hashes/media, request hash and the sent request controls (wire
  observation v2). The worker status reports `fixture_evidence: true`,
  `live_authorized: false`; the mode-free preparation reports both false.
- **Live.** A `LiveImageAuthority` takes no fixture (a fixture, or a synthetic authority
  over a live admission and vice versa, refuses before spawn) and needs
  `DSPX_POLICY_ALLOW_NETWORK_MUTATE=1`, checked in the parent before spawn and again in
  the worker before send. The endpoint is the admitted `canonical_base_endpoint`, which
  must be an IP-literal loopback `http` origin. The parent passes closed scalar params
  (`mode`, caller expectation, custody root and the approval binding
  `owning_ak_task`, `operator_evidence_ref`, `parent_confirmation_sha256`); the worker
  (`image_live.mirror_authority`) mirrors only the admitted mode with every field
  present, and its custody session re-runs `validate_admission`, which compares every
  approval field with the admission (see Live approval binding). No transport is
  injected, so the provider builds
  `HTTPTransport(trust_env=False, retries=0)`. The status reports
  `fixture_evidence: false`, `live_authorized: true`, and `verify_image_run` checks the
  same custody intent, terminal and closure as for synthetic runs. An
  `effect_indeterminate` attempt is never retried, repeated or re-dispatched: the root
  is spent.

Tests reach the live path only through a test-owned loopback server
(`tests/test_image_live_execution.py`): double-forked into its own session, because the
supervising parent must stay single-threaded and childless, and every process it owns
is settled. No test contacts a real provider.

## Request controls (AK6918)

Admission `dspx-image-admission-v3` (commitment domain `admission-v3`) adds a closed,
required `request_controls` section in every mode:
`{"max_output_tokens": N, "thinking": "off"}` with `1 <= N <= 8192`
(`MAX_OUTPUT_TOKENS`; at up to 16 characters per token and 6 JSON bytes per character,
8192 tokens stay inside the 2 MB response and 1 M character output ceilings, which
remain independently bounded; the admitted IO window bounds wall time). Unknown keys,
booleans, strings, nulls, out-of-range values and any other thinking value refuse with
`image_admission_invalid`; floats refuse with `image_input_invalid` (integer-only
records). The image request body is the formatted `{model, messages}` plus exactly
`max_tokens = N` and the vLLM chat-template switch
`chat_template_kwargs: {"enable_thinking": false}`, both from the admission
(`image_live.controlled_body`). Caller controls are refused before send: typed LM
config or call kwargs, and a formatted body that already carries a control. Before
reservation and send, `require_admitted_controls` re-parses the exact request bytes and
refuses any drift (changed, missing, boolean, extra or duplicated keys). The body-size
limit applies to the controlled body. Text (non-image) provider requests are unchanged,
and no pinned provider module changed.

The response must show the controls took effect, in both modes
(`image_live.honoured_controls`, after the provider's own validation): every choice
finishes with `stop` or `length` and carries no reasoning (`reasoning`,
`reasoning_content` absent or null), and `usage.completion_tokens` is an integer within
the admitted cap. Anything else, including a missing `usage` or finish reason, is one
completed failure `response`: never success, no artifact. The owner fixture answers
with such a controlled completion.

## Live approval binding (AK6918 review)

`validate_admission` (parent and worker session) requires, for a live admission:

- `owning_ak_task` a positive int, `operator_evidence_ref` matching
  `ak://evidence/N`, and the parent `LiveImageAuthority` holding exactly these values
  with exact types (`int`, `str`, `str`; `True` is not a task number);
- `parent_confirmation_sha256 == live_confirmation_sha256(record)`, which is
  `digest("live-confirmation-v1", A')` with A' the admission record whose
  `operator_evidence_ref` and `parent_confirmation_sha256` are null. The evidence
  reference stays outside the digest so the owner's AK evidence can carry the digest
  and the admission can then name that evidence without a cycle; the parent still
  binds the reference. One recorded confirmation therefore fits only the endpoint,
  model, controls, limits, deadlines, custody and task it was computed for;
- a validity window `expires_utc_ms - not_before_utc_ms <= 1_800_000` (30 minutes), so
  a copied live admission cannot be replayed for long.

Retained custody is read only for `dspx-image-admission-v3`; any other admission
schema refuses with `image_admission_invalid`.

## Owner decisions that refine Revision 2

| Evidence | Decision |
|---|---|
| AK13975 | Clean isolated interpreter; an already-hooked caller is outside the boundary |
| AK14132 | Detectable caller observers (trace, profile, MLflow, callbacks, LM history) are also outside the boundary (deviation from proposal item 1; CI runs under coverage) |
| AK14133 | The 159-case red matrix moves to AK6756 (executed: `2026-10-06-typed-image-revision2-traceability.md`) |
| AK14193 | Decoder profile v2 pins Pillow 12.1.1's own modules, `_imaging` and bundled codecs, formats and limits, but not OS C libraries (trusted platform like the interpreter) |
| AK14879, AK14880 | Live image path (AK6918): an owner-bound `max_output_tokens` with thinking off in the admission; the later live harness targets a direct loopback vLLM; no live model call until a run's endpoint, model and budget are approved as AK evidence (AK6610) |

## Threat model limits

Deliberately hostile code executing inside the worker (raw function pointers from parsed
ELF symbols, memory or module-state tampering) is not contained; it could read pixels
directly. Hooks registered before BOOT's first statement require an untrusted
interpreter or loader and are outside the boundary.

## Custody settlement (AK6756)

- **One root, one claimant.** The parent initializer creates the root's `lock` with
  `O_EXCL` before `ready.json`; a contending parent fails before any write, and a root
  that was ever claimed stays spent.
- **Read-only reconciliation.** `reconcile_image_custody` classifies a settled root from
  its records only: an intent without its terminal is `effect_indeterminate` with an
  unknown dispatch count, never success, and nothing is written. `verify_image_run`
  accepts only a closed, residue-free, all-success run; anything else is `image_spent`.
- **Unsettled roots (AK6811).** A root with its `lock` but no settled `ready.json` (the
  initializer died after its claim) reconciles as spent with no attempt, terminal
  effect `none` and `ready_present: false`, from names and inode metadata only;
  `verify_image_run` still refuses it with `image_custody`. A record left with two links
  by a kill between `os.link` and `os.unlink` in publication, the other its own
  `.pending-<uuid4>` twin, is read but never settled: its attempt is
  `effect_indeterminate` (`publication_unsettled: true`, unknown dispatch count) and
  such a closure is not present. Any other extra link refuses with `image_custody`.
- **One IO window per request (AK6811).** The response read is bounded by the admitted
  `per_request_io_timeout_ms` from dispatch, checked at every raw transport chunk and at
  the end of the body, besides the worker's wall deadline. The request asks for and the
  read requires an identity coding; a coded body is never inflated and is a completed
  failure. A response that trickles past the window makes the worker itself write one
  `effect_indeterminate` terminal with failure code `io`, latch, and raise the fixed
  `image_finalization`, without retry or fallback. Between chunks only the per-read
  timeout (at most the IO timeout) runs; the wall deadline is the hard bound.
- **Publication follows success.** `publish_image_run` refuses before its first write
  unless every planned attempt succeeded, and `close_run` closes only as `completed`.
- **Closed envelope.** The DesignMD image envelope has a closed key set, so no extra key
  can carry payload text to the provider (narrower than Revision 2's "safe metadata").
- **Exact PNG data (AK6938).** Before any Pillow open the scan inflates the IDAT stream,
  bounded at the IHDR scanline size, and refuses unless it ends exactly at the last IDAT
  byte and inflates to exactly that size: no bytes beyond the exact zlib stream and
  scanline size are admitted. Encoder choices, padding bits and unused palette entries
  can still carry a few bits; the decoder does not claim otherwise.

## Open work

The Revision 2 red matrix is executed (AK6756,
`2026-10-06-typed-image-revision2-traceability.md`); its follow-ups AK6810-AK6812 are
fixed. Live image execution with admission-bound output controls exists in code (AK6918,
owner decisions AK14879/AK14880: bounded output, thinking off, direct loopback vLLM) and
is exercised only against a test-owned loopback server. AK6610 is the first live call.
Every live run still needs a per-run owner admission and its approval binding
(owning AK task, operator evidence `ak://evidence/N`, the confirmation digest of that
admission), with the exact endpoint, model, budget and confirmation digest recorded as
AK evidence before the run; code verifies data identity only and never authenticates
the operator. Receipt-domain
routing (AK6767) was closed as superseded: receipts are hash-only projections and image
receipts are refused before any output read.
