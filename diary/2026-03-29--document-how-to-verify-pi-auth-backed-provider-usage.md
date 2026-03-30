---
summary: "Documented how to prove DSPx is using the Pi auth-backed dspy-lm-auth route and where that auth store lives by default."
read_when:
  - "You need to verify whether DSPx is actually using your Pi/Codex-backed auth instead of a local provider path."
  - "You want the exact commands and fields that prove the auth-backed route is reading ~/.pi/agent/auth.json."
---

# 2026-03-29 — Document How to Verify Pi Auth-Backed Provider Usage

## What I Did
- Added a short verification guide to the README provider section so operators can quickly check whether DSPx is using the auth-backed `dspy-lm-auth` route.
- Added a fuller explanation to `docs/project/provider-runtime-v4.md` covering:
  - the default auth-store path (`~/.pi/agent/auth.json`)
  - the `providers resolve` command for checking configured runtime details
  - the `providers health --probe` command for proving the route can actually use those credentials
  - the mixed-provider split where `vllm-local` stays local and only `dspy-lm-auth` uses the auth-backed route
  - the fact that receipts record safe provider details for after-the-fact confirmation
- Refreshed the operating/handoff artifacts to record the operator-directed docs slice without displacing active task `AK-562`.

## Why It Mattered
- The operator question was not really about imports anymore; it was about how to *prove* which billing/auth route a run is using.
- DSPx supports both local and auth-backed providers, so “did this use my subscription?” depends on the active provider route, not just on whether `dspy-lm-auth` exists in the repo.
- The docs now make the decisive checks explicit instead of leaving them implicit in code or scattered across prior discussion.

## Validation
- `just task-scope-check task_id=567 mode=working-tree` ✅
- `./scripts/ci/smoke.sh` ✅
- `just verify-full` ✅
- `just dspx providers resolve --provider dspy-lm-auth --json` ✅
- `just dspx providers health --provider dspy-lm-auth --probe --json` ✅
- `node ~/ai-society/core/agent-scripts/scripts/docs-list.mjs --docs . --strict` ⚠️ expected failure from pre-existing repo-wide metadata debt tracked separately via `AK-239`
- `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅
- `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅

## Next
- Keep `AK-562` as the next active SG2 implementation slice.
- When checking whether a run is using the auth-backed route, use the documented `resolve` + `health --probe` pair before assuming a local or subscription-backed path.
