---
summary: "Active operating-plan layer for the current tactical goal."
read_when:
  - "When choosing the next one-context-window slice"
  - "When mapping the active tactical goal to authoritative AK tasks"
---

# Operational Goals

Active tactical goal: `TG25`

Authoritative live execution: Agent Kernel tasks for repo `/home/tryinget/ai-society/softwareco/owned/dspx`

## Active operating slices

1. `AK-835` — **Atomic hardening cleanup across config, runtime, policy, and task-scope guards**
   - close the already-grounded follow-on fixes for config-managed env refresh, secret rejection in config TOML, provider health/result sanitization, policy bypass audit logging, registry locking, retry boundaries, refine TTY gating, receipt env-hash redaction, bounded previews, generated-code/task-scope guardrails, and their matching regressions
   - keep the slice bounded to the files already named in the AK scope instead of turning TG25 into a generic cleanup queue
   - status: ready
2. **Blocked promotion step — no AK task yet**
   - once `AK-835` is complete and the repo returns to a truthful validated baseline, promote `TG26` and freeze the explicit human-governed promotion-eligibility contract
   - until then, do not materialize contract-freezing work as if the trust-boundary prerequisites were already closed
   - status: blocked on `AK-835`

## Recently completed in this wave

- `AK-834` — landed the adversarial NEXUS hardening slice across Forge sanitize/workorder handling, the shared `dspx.security.confine_path()` primitive, replay path resolution, `parallel_first` success/readiness semantics, auth-provider structured error signaling, and Oracle frontier/territory correctness; exported `governance/task-scopes/AK-834.snapshot.json`, refreshed the checked-in AK projection, and added targeted regressions.
- `AK-800` — added request body size limits middleware to the DSPx server that rejects requests whose `Content-Length` exceeds a configurable limit (default 10 MiB) before the body is read, with human-friendly size parsing (`DSPX_MAX_BODY_SIZE`), enabled-by-default fail-closed semantics, extended the stats counter with `status_413`, and added 21 new regression tests.
- `AK-799` — flipped server auth to required-by-default, added `DSPX_AUTH_SKIP_FOR_DEV` as the explicit local-only bypass, refreshed server docs, and tightened server-side regressions so unauthenticated startup no longer happens by accident.
- `AK-798` — replaced contract-expression `eval()` with a tiny AST interpreter over a narrowed helper namespace plus a read-only embedding view, rejected arbitrary method calls / non-allowlisted helpers / arbitrary attribute traversal, and refreshed regressions.
- `AK-797` — confined `optimize_service._import_program_module()` to trusted program roots (`cwd`, the system temp root, plus `DSPX_TRUSTED_PROGRAM_ROOTS` overrides), added rejection/allowlist regressions, and refreshed the checked-in AK projection after completion.

## Notes

- `TG25` now has one truthful ready slice left in the repo-scoped queue: `AK-835`.
- Keep the `AK-834` sanitize/workorder, shared path-confinement, replay-path, provider-racing, auth-provider, and frontier/territory correctness boundaries closed unless a smaller follow-up explicitly proves a regression.
- Keep the `AK-800` request body size limit boundary closed unless a smaller follow-up explicitly widens it.
- Keep the `AK-799` required-by-default server auth boundary closed unless a smaller follow-up explicitly widens it.
- Keep the `AK-797` trusted-program-root boundary closed unless a smaller follow-up explicitly widens it.
- Keep the `AK-798` narrowed contract-expression boundary closed unless a smaller follow-up explicitly widens the helper/attribute contract.
- Do not start live predictive ranking, candidate pruning, promotion blocking, or strategy/policy mutation while `TG25` hardening is still open; wait until `TG26` is explicitly promoted.
- Older deferred/provider/runtime follow-ons (`AK-224`, `AK-235`–`AK-239`) remain non-active backlog and were intentionally not resumed in this wave.
- After AK task mutations for this wave, refresh the checked-in projection with `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` and verify with `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx`.
- Task-scope validation is now snapshot-backed for `AK-834`; keep isolating each slice so working-tree validation stays truthful.
