---
summary: "Active operating-plan layer for the current tactical goal."
read_when:
  - "When choosing the next one-context-window slice"
  - "When mapping the active tactical goal to authoritative AK tasks"
---

# Operational Goals

Active tactical goal: `unmaterialized`

Authoritative live execution: Agent Kernel tasks for repo `/home/tryinget/ai-society/softwareco/owned/dspx`

## Active operating slices

- No repo-scoped implementation slice is currently pinned in AK.
- The operator-pulled `program-gen` foothold is complete and has been sharpened into a bounded deterministic composition path: DSPx can materialize `program-plan-v1`, separate signature/module/program/eval surfaces, typed/described field specs, and optional inline/example-file binding evidence from structured intent into a program-shaped candidate assembly.
- `TG28` is closed by `docs/adr/20260410-human-governed-review-decision-contract-v1.md`, which freezes the bounded human-governed decision contract for nominated governance-only policy variants.
- The first truthful follow-on is a bounded `human_review_decisions` receipt wave grounded in promotion-eligibility nominations, governed policy-evaluation receipts, runtime-spine provenance, and explicit human decision metadata, but it remains unmaterialized until a later direction-to-execution pass selects it.

## Recently completed in this wave

- `AK-1827` — materialized the first bounded one-intent `program-gen` MVP from structured JSON/YAML intent to deterministic program-shaped candidate assembly, initially emitting `program.py`, `eval_smoke.py`, normalized `intent.json`, `manifest.json`, and a standard `program-gen` run receipt while keeping live ranking, pruning, promotion, Oracle, and governance-policy authority unchanged; exported `governance/task-scopes/AK-1827.snapshot.json` and refreshed the checked-in AK projection. The current `program-gen` implementation preserves that authority boundary while materializing `plan.json`, separate `signature.py`, `module.py`, `program.py`, `eval_smoke.py`, typed/described field specs, and optional `examples.json` / `eval_examples.py` surfaces from inline `examples` or `examples_path` with plan provenance, generator provenance, example-binding evidence, and per-surface hashes.
- `AK-1106` — froze `docs/adr/20260410-human-governed-review-decision-contract-v1.md`, refreshed the tactical / operational / handoff stack to close `TG28` truthfully, exported `governance/task-scopes/AK-1106.snapshot.json`, re-exported the checked-in AK projection, and left the repo with no next pinned slice instead of guessing the post-contract implementation task.
- `AK-1105` — promoted `TG28` into the active tactical slot after `TG27` landed, created `AK-1106` as the next ready repo-scoped contract slice, refreshed the strategic/tactical/operational/handoff stack around the review-decision wave, exported `governance/task-scopes/AK-1105.snapshot.json`, and re-exported the checked-in AK projection.
- `AK-1102` — emitted the first bounded `promotion_eligibility_nominations` receipts from governed policy-evaluation receipts plus current-run runtime-spine provenance, extended receipt-side historical diagnostics extraction for the new nomination surface, refreshed the tactical/operational/handoff stack around the completed `TG27` implementation slice, exported `governance/task-scopes/AK-1102.snapshot.json`, and re-exported the checked-in AK projection.
- `AK-1101` — promoted `TG27` into the active tactical slot after `TG26` closed, created `AK-1102` as the next ready repo-scoped implementation slice, refreshed the strategic/tactical/operational/handoff stack around the nomination-receipt wave, exported `governance/task-scopes/AK-1101.snapshot.json`, and re-exported the checked-in AK projection.
- `AK-1047` — froze `docs/adr/20260409-human-governed-promotion-eligibility-contract-v1.md`, refreshed the tactical / operational / handoff stack to close `TG26` truthfully, exported `governance/task-scopes/AK-1047.snapshot.json`, re-exported the checked-in AK projection, and left the repo with no next pinned slice instead of guessing the post-contract implementation task.
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

- `AK-1827` is complete, `AK-1106` is complete, `TG28` is complete, and no next repo-scoped implementation slice is pinned yet.
- Do not invent the post-`TG28` implementation slice just to avoid an empty ready queue; let a later direction-to-execution pass or explicit operator pull pin the next bounded receipt wave.
- Do not treat repeated governed policy-evaluation receipts, repeated promotion-eligibility nominations, or repeated human review decisions as de facto live policy authority.
- Keep the `AK-1085` candidate-assembly / execution-episode / receipt-bundle runtime semantics closed unless a smaller follow-up proves a regression or explicitly widens the contract.
- Keep the `AK-835` config/runtime/policy/registry/refine/receipt/task-scope hardening boundaries closed unless a smaller follow-up explicitly proves a regression.
- Keep the `AK-834` sanitize/workorder, shared path-confinement, replay-path, provider-racing, auth-provider, and frontier/territory correctness boundaries closed unless a smaller follow-up explicitly proves a regression.
- Keep the `AK-800` request body size limit boundary closed unless a smaller follow-up explicitly widens it.
- Keep the `AK-799` required-by-default server auth boundary closed unless a smaller follow-up explicitly widens it.
- Keep the `AK-797` trusted-program-root boundary closed unless a smaller follow-up explicitly widens it.
- Keep the `AK-798` narrowed contract-expression boundary closed unless a smaller follow-up explicitly widens the helper/attribute contract.
- Do not start live predictive ranking, candidate pruning, promotion blocking, strategy/policy mutation, or the post-contract implementation follow-on while the repo-scoped queue is still unmaterialized.
- Older deferred/provider/runtime follow-ons (`AK-224`, `AK-235`–`AK-239`) remain non-active backlog and were intentionally not resumed in this wave.
- After AK task mutations for this wave, refresh the checked-in projection with `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` and verify with `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx`.
- Task-scope validation is now snapshot-backed for `AK-1827`, `AK-1106`, `AK-1105`, `AK-1102`, `AK-1101`, `AK-1094`, `AK-1093`, `AK-1085`, `AK-834`, and `AK-835`; keep isolating each slice so working-tree validation stays truthful.
