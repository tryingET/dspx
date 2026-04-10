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

1. **No repo-scoped implementation slice is pinned right now**
   - the first `dspx.synthesis` runtime spine now lands candidate assembly, execution episode, and receipt bundle semantics end-to-end, and the repo-scoped ready queue is empty again
   - keep the completed runtime-spine slice closed instead of turning it into an open-ended cleanup bucket
   - status: closed / waiting for the next explicitly materialized slice
2. **Later governance contract — keep deferred until AK truth names it**
   - the later human-governed review-eligibility / promotion-eligibility contract still needs an explicit repo task before implementation work resumes
   - do not guess or pre-write that governance slice as active authority while the ready queue is empty
   - status: deferred / no ready repo task

## Recently completed in this wave

- `AK-1093` — refreshed the vision/strategic/tactical/architecture direction stack into the runtime-spine language now backed by `AK-1085`, salvaged the boundary doc that explains the candidate-surface / candidate-assembly / execution-episode / receipt-bundle ontology, re-exported the checked-in AK projection, and kept the next governance slice deferred while the ready queue stayed empty.
- `AK-1085` — bridged `dspx.synthesis` to explicit runtime-spine semantics by emitting candidate assemblies, execution episodes, and receipt bundles alongside the existing synthesis records, threading those objects through workspace manifests, promotion metadata, and run summaries, exporting `governance/task-scopes/AK-1085.snapshot.json`, re-exporting the checked-in AK projection, and covering the bounded path with direct regressions.
- `AK-835` — closed the remaining atomic hardening cleanup across config-managed env refresh, config TOML secret rejection, provider/runtime health+result sanitization, policy bypass audit logging, provider/tool registry locking, Pi RPC retry boundaries, refine TTY gating, receipt env-hash redaction, bounded data previews, generated-code worker fail-closed handling, and task-scope claim fallback; exported `governance/task-scopes/AK-835.snapshot.json`, re-exported the checked-in AK projection, and restored the full validation baseline.
- `AK-834` — landed the adversarial NEXUS hardening slice across Forge sanitize/workorder handling, the shared `dspx.security.confine_path()` primitive, replay path resolution, `parallel_first` success/readiness semantics, auth-provider structured error signaling, and Oracle frontier/territory correctness; exported `governance/task-scopes/AK-834.snapshot.json`, refreshed the checked-in AK projection, and added targeted regressions.
- `AK-800` — added request body size limits middleware to the DSPx server that rejects requests whose `Content-Length` exceeds a configurable limit (default 10 MiB) before the body is read, with human-friendly size parsing (`DSPX_MAX_BODY_SIZE`), enabled-by-default fail-closed semantics, extended the stats counter with `status_413`, and added 21 new regression tests.
- `AK-799` — flipped server auth to required-by-default, added `DSPX_AUTH_SKIP_FOR_DEV` as the explicit local-only bypass, refreshed server docs, and tightened server-side regressions so unauthenticated startup no longer happens by accident.
- `AK-798` — replaced contract-expression `eval()` with a tiny AST interpreter over a narrowed helper namespace plus a read-only embedding view, rejected arbitrary method calls / non-allowlisted helpers / arbitrary attribute traversal, and refreshed regressions.
- `AK-797` — confined `optimize_service._import_program_module()` to trusted program roots (`cwd`, the system temp root, plus `DSPX_TRUSTED_PROGRAM_ROOTS` overrides), added rejection/allowlist regressions, and refreshed the checked-in AK projection after completion.

## Notes

- `AK-1093` refreshed the direction stack into runtime-spine truth without materializing a new ready implementation slice.
- `AK-1085` closed the first bounded runtime-spine slice for `TG25` and left no new repo-scoped ready task in AK.
- Keep the `AK-1085` candidate-assembly / execution-episode / receipt-bundle runtime semantics closed unless a smaller follow-up proves a regression or explicitly widens the contract.
- Keep the `AK-835` config/runtime/policy/registry/refine/receipt/task-scope hardening boundaries closed unless a smaller follow-up explicitly proves a regression.
- Keep the `AK-834` sanitize/workorder, shared path-confinement, replay-path, provider-racing, auth-provider, and frontier/territory correctness boundaries closed unless a smaller follow-up explicitly proves a regression.
- Keep the `AK-800` request body size limit boundary closed unless a smaller follow-up explicitly widens it.
- Keep the `AK-799` required-by-default server auth boundary closed unless a smaller follow-up explicitly widens it.
- Keep the `AK-797` trusted-program-root boundary closed unless a smaller follow-up explicitly widens it.
- Keep the `AK-798` narrowed contract-expression boundary closed unless a smaller follow-up explicitly widens the helper/attribute contract.
- Do not start live predictive ranking, candidate pruning, promotion blocking, strategy/policy mutation, or the deferred governance contract while the repo-scoped ready queue is empty; wait for AK truth to materialize the next bounded slice.
- Older deferred/provider/runtime follow-ons (`AK-224`, `AK-235`–`AK-239`) remain non-active backlog and were intentionally not resumed in this wave.
- After AK task mutations for this wave, refresh the checked-in projection with `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` and verify with `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx`.
- Task-scope validation is now snapshot-backed for `AK-1093`, `AK-1085`, `AK-834`, and `AK-835`; keep isolating each slice so working-tree validation stays truthful.
