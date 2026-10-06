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

## Shipped routes

`prepare_image_execution` and `execute_image_program` (used by the runtime episode and the
generated `direct_run.py`) type-check in the parent, reserve the nominal
`SyntheticImageAuthority`, and run declared entries in the worker. The synthetic transport
is a closed `SyntheticTransportFixture`; the worker builds the exact `httpx.MockTransport`
and publishes only send ordinal, block kinds, image hashes/media and request hash. Live
authority is never executed (first live call needs AK6766 and owner budget approval).

## Owner decisions that refine Revision 2

| Evidence | Decision |
|---|---|
| AK13975 | Clean isolated interpreter; an already-hooked caller is outside the boundary |
| AK14132 | Detectable caller observers (trace, profile, MLflow, callbacks, LM history) are also outside the boundary (deviation from proposal item 1; CI runs under coverage) |
| AK14133 | The 159-case red matrix moves to AK6756 (`2026-10-06-typed-image-revision2-traceability.md`) |
| AK14193 | Decoder profile v2 pins Pillow 12.1.1's own modules, `_imaging` and bundled codecs, formats and limits, but not OS C libraries (trusted platform like the interpreter) |

## Threat model limits

Deliberately hostile code executing inside the worker (raw function pointers from parsed
ELF symbols, memory or module-state tampering) is not contained; it could read pixels
directly. Hooks registered before BOOT's first statement require an untrusted
interpreter or loader and are outside the boundary.

## Open work

AK6756 (red matrix and three new custody mechanisms), AK6766 (live-call prerequisites:
PID/start/deadline-bound handshake), AK6767 (receipt-domain routing for unanchored
receipts; explicit image anchors are refused before path access today).
