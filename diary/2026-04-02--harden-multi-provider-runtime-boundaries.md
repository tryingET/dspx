---
summary: "Implement AK-708 by hardening multi-provider runtime boundaries without widening live policy authority."
read_when:
  - "You are resuming after AK-708 implementation."
  - "You need the exact boundary and validation story for the multi-provider TG24 landing."
---

# 2026-04-02 — Harden Multi-Provider Runtime Boundaries

## What I Did
- Kept the second `TG24` landing bounded to multi-provider orchestration, provider-capability reporting, request/policy isolation, dirty-worktree-safe isolation, and loser cleanup.
- Restored the missing repo-local `scripts/ak.sh` wrapper so repo-scoped AK claim/complete/export flows can run through a deterministic repo helper again, and taught the direction/task-scope validation paths to prefer that wrapper over a stale global `ak` when the repo provides it.
- Changed `providers capabilities` to derive its payload from runtime-resolved provider metadata instead of the registry's static capability placeholder, so the `multi` provider now reports the real aggregate capability surface of its configured children.
- Materialized request messages before provider fan-out so generator-backed/message-iterator inputs stay identical across all providers, and threaded typed DTO messages through `provider.generate()` so generate-only providers no longer lose conversation history.
- Scoped policy alignment overrides to a single multi-provider run, restoring provider-local `dangerously_bypass`, `auto_mode`, `permission_mode`, tool allow/deny lists, and appended system prompts after the run finishes.
- Hardened isolated git-worktree mode to fail closed back to mirror isolation when the base repo is dirty, preventing hidden uncommitted edits from disappearing in detached worktrees.
- Added a bounded async-loser cleanup path that force-kills stubborn lingering processes before tearing down isolated workdirs.
- Exported `governance/task-scopes/AK-708.snapshot.json` so the slice can bind deterministically through the AK-native task-scope path.

## Why It Mattered
- `TG24` needs trustworthy multi-provider boundaries before the final parser/strictness slice can close the wave.
- Before this slice, the CLI capability surface for `multi` could lie relative to runtime reality, message iterators could be consumed by the first provider only, and temporary policy overrides could leak across later calls.
- Dirty detached worktrees also risked hiding local edits, while hung async losers could strand isolated cleanup indefinitely.

## Risk Boundaries
- No live policy widening: the slice only hardens orchestration/reporting boundaries around existing provider behavior.
- No server or parser bundling: `AK-707` behavior stays unchanged and `AK-709` remains the parser/strictness follow-on.
- No silent dirty-tree masking: git-worktree isolation falls back to mirror mode when it cannot safely represent the working tree truth.

## Validation
- `uv run --no-sync -m pytest -q tests/test_multi_provider_caps.py tests/test_multi_provider_parallel_semantics.py tests/test_provider_registry.py tests/test_provider_v4.py` ✅
- `./scripts/ci/smoke.sh` ✅
- `just task-scope-check task_id=708 mode=working-tree` ⚠️ skipped (`governance/task-scopes/AK-708.snapshot.json` explicitly says repo-default scope applies)
- `just verify-full` ✅
- `./scripts/ak.sh task complete 708 --result '{...}'` ✅
- `./scripts/ak.sh work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅
- `./scripts/ak.sh work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅
- `./scripts/ak.sh task ready -F json | jq 'map(select(.repo=="/home/tryinget/ai-society/softwareco/owned/dspx")) | map({id,title})'` ✅ (`AK-709` ready)

## Next
- Claim `AK-709`.
- Keep the final `TG24` landing bounded to SG2 receipt/explain/openapi/rate-limit parsing strictness plus only the directly supporting regressions.
- Close `TG24` without jumping early to the later governance-to-live promotion contract.
