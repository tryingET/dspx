---
summary: "Implement AK-707 by persisting server-generated artifacts/receipts and enforcing confirmation boundaries across signature, module, and mermaid endpoints."
read_when:
  - "You are resuming after AK-707 implementation."
  - "You need the exact boundary and validation story for the first TG24 landing."
---

# 2026-04-02 — Persist Server Artifacts and Confirmation Boundaries

## What I Did
- Kept the first `TG24` landing bounded to `packages/dspx-core/src/dspx/server/app.py`, `packages/dspx-core/src/dspx/cli/utils.py`, server-facing docs, and the directly supporting regression surface.
- Added server-side artifact persistence for `/signature` and `/module`, writing generated code under `generated/server/` (or `DSPX_SERVER_OUTPUT_DIR`), emitting run receipts, surfacing stable public `output_path`/`receipt_path` refs, and returning `output_hash` even when persistence degrades.
- Added server-side persistence for `/mermaid` by copying the generated directory to a stable server artifact root and returning stable `output_dir`, `manifest_path`, and `produced` refs.
- Enforced the `X-DSPX-Confirm: 1` confirmation gate across all mutating server endpoints when `DSPX_CONFIRM_MUTATIONS=1` instead of only gating Mermaid generation.
- Kept persistence truthful: signature/module responses degrade cleanly to `null` refs when artifact persistence fails, while Mermaid returns `artifact_persistence_failed` because its response contract is the persisted artifact set itself.
- Threaded `run_summary` through `write_receipt_for_output()` so server-generated module receipts preserve synthesis-runtime summary metadata.
- Updated `docs/SERVER.md` so the server runtime contract now documents the persistence root, returned artifact refs, mutation-confirmation gate, and standardized error shapes.
- Exported `governance/task-scopes/AK-707.snapshot.json` with repo-default scope so `just verify-full` can bind deterministically without reviving hand-authored manifest coupling.

## Why It Mattered
- SG2 needs trustworthy receipt-bearing boundaries before multi-provider hardening or later governance-to-live policy contracts can stand on them.
- Before this slice, the server could generate outputs but did not consistently return stable artifact refs or enforce confirmation boundaries across the full mutating surface.
- The first TG24 landing now gives server consumers durable receipt/artifact handles without changing live V7 ranking, tie-breaking, pruning, or promotion behavior.

## Risk Boundaries
- No live V7 behavior widening: the slice only hardens server persistence/confirmation boundaries around existing generation flows.
- No silent persistence lies: when signature/module persistence fails, the response withholds artifact refs instead of fabricating them; when Mermaid persistence fails, the request fails explicitly.
- No multi-provider or parser/strictness bundling: those follow-ons remain staged behind `AK-708` and `AK-709`.

## Validation
- `uv run --no-sync -m pytest -q tests/test_server_api.py tests/test_server_confirm_mutations.py` ✅
- `./scripts/ci/smoke.sh` ✅
- `just task-scope-check task_id=707 mode=working-tree` ✅ (repo-default snapshot exported)
- `just verify-full` ✅
- `ak task complete 707 --result '{...}'` ✅
- `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅
- `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅
- `ak task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx")) | map({id,title})'` ✅ (`AK-708` ready)

## Next
- Claim `AK-708`.
- Keep the next landing bounded to multi-provider runtime hardening: dynamic capability aggregation, request/policy isolation, dirty-worktree-safe isolation, and loser cleanup.
- Leave the parser/strictness follow-on for `AK-709` unless a smaller shared dependency truly forces it.
