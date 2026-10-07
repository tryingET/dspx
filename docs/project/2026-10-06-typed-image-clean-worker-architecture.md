---
summary: "As-built architecture of DSPx typed image transport: guarded clean -I -S worker, refusal everywhere else, owner decisions that refine Revision 2, and what remains open."
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
generated `direct_run.py`) type-check in the parent, reserve the nominal
`SyntheticImageAuthority`, and run declared entries in the worker. The synthetic transport
is a closed `SyntheticTransportFixture`; the worker builds the exact `httpx.MockTransport`
and publishes only send ordinal, block kinds, image hashes/media and request hash. Live
authority is never executed: a first live call still needs a worker-side Live authority
mirror and the owner's exact endpoint/model/budget approval (AK6610).

## Owner decisions that refine Revision 2

| Evidence | Decision |
|---|---|
| AK13975 | Clean isolated interpreter; an already-hooked caller is outside the boundary |
| AK14132 | Detectable caller observers (trace, profile, MLflow, callbacks, LM history) are also outside the boundary (deviation from proposal item 1; CI runs under coverage) |
| AK14133 | The 159-case red matrix moves to AK6756 (executed: `2026-10-06-typed-image-revision2-traceability.md`) |
| AK14193 | Decoder profile v2 pins Pillow 12.1.1's own modules, `_imaging` and bundled codecs, formats and limits, but not OS C libraries (trusted platform like the interpreter) |

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
- **Publication follows success.** `publish_image_run` refuses before its first write
  unless every planned attempt succeeded, and `close_run` closes only as `completed`.
- **Closed envelope.** The DesignMD image envelope has a closed key set, so no extra key
  can carry payload text to the provider (narrower than Revision 2's "safe metadata").

## Open work

The Revision 2 red matrix is executed (AK6756,
`2026-10-06-typed-image-revision2-traceability.md`). AK6610 (first live call after owner
approval) remains; AK6810-AK6812 track the matrix's smaller follow-ups. Receipt-domain
routing (AK6767) was closed as superseded: receipts are hash-only projections and image
receipts are refused before any output read.
