---
summary: "Added a one-command helper for proving the active dspy-lm-auth import path and auth-backed route in DSPx."
read_when:
  - "You want one command that shows both the imported dspy_lm_auth module path and the auth-backed route proof."
  - "You are checking whether DSPx is using the expected Pi auth-backed dspy-lm-auth path without manually chaining multiple commands."
---

# 2026-03-29 — Add a One-Command dspy-lm-auth Route Check

## What I Did
- Added `just show-dspy-lm-auth-route` to the repo Justfile.
- Made the helper print, in order:
  - the imported `dspy_lm_auth` module path
  - `just dspx providers resolve --provider dspy-lm-auth --json`
  - `just dspx providers health --provider dspy-lm-auth --probe --json`
- Updated the README and provider-runtime docs to point operators at the one-command helper first, while preserving the explicit manual commands as the underlying equivalent checks.
- Refreshed the handoff/operating artifacts without displacing active task `AK-562`.

## Why It Mattered
- The prior docs explained the proof but still made the operator remember two JSON commands plus, optionally, the import-path check.
- The new helper collapses that into one stable command while staying transparent about the underlying checks.
- This keeps the verification path easy for operators without inventing a new hidden source of truth.

## Validation
- `just show-dspy-lm-auth-route` ✅
- `just task-scope-check task_id=570 mode=working-tree` ✅
- `./scripts/ci/smoke.sh` ✅
- `just verify-full` ✅
- `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅
- `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅

## Next
- Keep `AK-562` as the next active SG2 implementation slice.
- When checking the auth-backed route interactively, use `just show-dspy-lm-auth-route` first.
