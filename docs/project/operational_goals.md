---
summary: "Active operating-plan layer for the current tactical goal."
read_when:
  - "When choosing the next one-context-window slice"
  - "When mapping the active tactical goal to authoritative AK tasks"
---

# Operational Goals

Active tactical goal: `TG26`

Authoritative live execution: Agent Kernel tasks for repo `/home/tryinget/ai-society/softwareco/owned/dspx`

## Active operating slices

1. **`AK-1047` — freeze the first human-governed promotion-eligibility contract for governance-only policy variants**
   - ground the next governance contract in the runtime-spine objects emitted by `AK-1085` rather than older synthesis-local ambiguity
   - keep the slice bounded to the ADR/doc contract surface, the supporting tactical/operational/handoff/projection refresh, and the frozen task-scope snapshot
   - status: ready / unclaimed
2. **Later follow-on implementation slice — keep deferred until the contract lands**
   - after the contract is frozen, materialize only the next bounded implementation slice that the contract explicitly justifies
   - do not widen authority or invent the post-contract implementation step early just to keep the queue non-empty
   - status: deferred / blocked on `AK-1047`

## Recently completed in this wave

- `AK-1094` — activated the next bounded governance-contract wave after the runtime-spine direction refresh, released `AK-1047` from deferral under explicit operator direction, refreshed the tactical/operational/handoff stack around the active governance slice, re-exported the checked-in AK projection, and left `AK-1047` as the single ready repo-scoped task.
- `AK-1093` — refreshed the vision/strategic/tactical/architecture direction stack into the runtime-spine language now backed by `AK-1085`, salvaged the boundary doc that explains the candidate-surface / candidate-assembly / execution-episode / receipt-bundle ontology, re-exported the checked-in AK projection, and kept the next governance slice deferred while the ready queue stayed empty.
- `AK-1085` — bridged `dspx.synthesis` to explicit runtime-spine semantics by emitting candidate assemblies, execution episodes, and receipt bundles alongside the existing synthesis records, threading those objects through workspace manifests, promotion metadata, and run summaries, exporting `governance/task-scopes/AK-1085.snapshot.json`, re-exporting the checked-in AK projection, and covering the bounded path with direct regressions.
- `AK-835` — closed the remaining atomic hardening cleanup across config-managed env refresh, config TOML secret rejection, provider/runtime health+result sanitization, policy bypass audit logging, provider/tool registry locking, Pi RPC retry boundaries, refine TTY gating, receipt env-hash redaction, bounded data previews, generated-code worker fail-closed handling, and task-scope claim fallback; exported `governance/task-scopes/AK-835.snapshot.json`, re-exported the checked-in AK projection, and restored the full validation baseline.
- `AK-834` — landed the adversarial NEXUS hardening slice across Forge sanitize/workorder handling, the shared `dspx.security.confine_path()` primitive, replay path resolution, `parallel_first` success/readiness semantics, auth-provider structured error signaling, and Oracle frontier/territory correctness; exported `governance/task-scopes/AK-834.snapshot.json`, refreshed the checked-in AK projection, and added targeted regressions.
- `AK-800` — added request body size limits middleware to the DSPx server that rejects requests whose `Content-Length` exceeds a configurable limit (default 10 MiB) before the body is read, with human-friendly size parsing (`DSPX_MAX_BODY_SIZE`), enabled-by-default fail-closed semantics, extended the stats counter with `status_413`, and added 21 new regression tests.
- `AK-799` — flipped server auth to required-by-default, added `DSPX_AUTH_SKIP_FOR_DEV` as the explicit local-only bypass, refreshed server docs, and tightened server-side regressions so unauthenticated startup no longer happens by accident.
- `AK-798` — replaced contract-expression `eval()` with a tiny AST interpreter over a narrowed helper namespace plus a read-only embedding view, rejected arbitrary method calls / non-allowlisted helpers / arbitrary attribute traversal, and refreshed regressions.
- `AK-797` — confined `optimize_service._import_program_module()` to trusted program roots (`cwd`, the system temp root, plus `DSPX_TRUSTED_PROGRAM_ROOTS` overrides), added rejection/allowlist regressions, and refreshed the checked-in AK projection after completion.

## Notes

- `AK-1094` promoted the next bounded governance-contract wave into active repo truth and left `AK-1047` as the single ready repo-scoped slice.
- `AK-1047` is now the pinned `TG26` operating slice.
- Keep the `AK-1085` candidate-assembly / execution-episode / receipt-bundle runtime semantics closed unless a smaller follow-up proves a regression or explicitly widens the contract.
- Keep the `AK-835` config/runtime/policy/registry/refine/receipt/task-scope hardening boundaries closed unless a smaller follow-up explicitly proves a regression.
- Keep the `AK-834` sanitize/workorder, shared path-confinement, replay-path, provider-racing, auth-provider, and frontier/territory correctness boundaries closed unless a smaller follow-up explicitly proves a regression.
- Keep the `AK-800` request body size limit boundary closed unless a smaller follow-up explicitly widens it.
- Keep the `AK-799` required-by-default server auth boundary closed unless a smaller follow-up explicitly widens it.
- Keep the `AK-797` trusted-program-root boundary closed unless a smaller follow-up explicitly widens it.
- Keep the `AK-798` narrowed contract-expression boundary closed unless a smaller follow-up explicitly widens the helper/attribute contract.
- Do not start live predictive ranking, candidate pruning, promotion blocking, strategy/policy mutation, or the post-contract implementation follow-on while `AK-1047` remains open.
- Older deferred/provider/runtime follow-ons (`AK-224`, `AK-235`–`AK-239`) remain non-active backlog and were intentionally not resumed in this wave.
- After AK task mutations for this wave, refresh the checked-in projection with `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` and verify with `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx`.
- Task-scope validation is now snapshot-backed for `AK-1094`, `AK-1093`, `AK-1085`, `AK-834`, and `AK-835`; keep isolating each slice so working-tree validation stays truthful.
