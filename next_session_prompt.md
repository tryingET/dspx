---
summary: "Single-file session handoff to avoid stale status/next-steps docs."
read_when:
  - "At the start of every work session"
  - "When resuming after a pause"
---

# Next Session Prompt

## SESSION TRIGGER (AUTO-START)
Reading this file is authorization to begin immediately.
Do not ask for permission to start.

## ANTI-STALE RULES (HARD)
- Keep this file short and current.
- Keep only the active handoff window (not a history log).
- Move finished session narrative to `diary/`.
- Crystallize durable patterns in `docs/learnings/` and decisions in `docs/decisions/`.
- Track deferred work in `governance/work-items.json` (not in ad-hoc TODO notes).

## SOURCE-OF-TRUTH MAP
- Repo operating contract: `AGENTS.md`
- Mission and goals: `docs/project/`
- Planned active/deferred work map: `governance/work-items.json`
- Prior decisions: `docs/decisions/`
- Crystallized learnings: `docs/learnings/`
- Raw session capture: `diary/`

## SESSION PREFLIGHT (FILL BEFORE EXECUTION)
- Objective (one sentence): Execute `DSPX-M4-03` by running one live end-to-end `dspx optimize gepa` smoke on the mixed-provider runtime defaults (`vllm-local` student + `dspy-lm-auth` reflection).
- Constraints (hard limits): Keep the repo green under `just verify-full`; do not leak credentials in docs/receipts; keep scope on one end-to-end optimize proof rather than broad new provider expansion.
- Assumptions (max 3): `DSPX-M4-02` is complete and the mixed-provider health/benchmark path is already live-verified; provider runtime v4 docs/config remain the current source of truth; a local vLLM endpoint and auth-backed Codex route are still available when the next operator starts.
- Blockers (none or list): Requires access to the real local/auth-backed provider endpoints and enough quota/runtime headroom for one live optimize smoke.

## READ-FIRST ALLOWLIST (STARTUP BUDGET)
1. `AGENTS.md`
2. `README.md`
3. `governance/work-items.json`
4. `docs/project/mission.md`
5. `docs/project/tactical_goals.md`
6. Most recent `diary/YYYY-MM-DD--type-scope-summary.md`

## EXECUTION MODE (ONE SESSION = ONE SLICE)
1. Choose one highest-leverage actionable slice from `governance/work-items.json` unless operator direction overrides it.
2. Implement end-to-end on a branch.
3. Validate:
   - `./scripts/ci/smoke.sh`
   - `./scripts/ci/full.sh` (when CI/policy/ontology/contracts changed)
4. Update source-of-truth artifacts before commit.

## SESSION CHECKPOINT (UPDATE BEFORE /commit)
- Slice executed: `DSPX-M4-02` — live-verify the provider runtime v4 mixed-provider profile.
- Outcome: Live-validated the mixed-provider runtime with `DSPX_CONFIG=config.provider-runtime-v4.example.toml`; `vllm-local` (`Qwen/Qwen3.5-27B`) and `dspy-lm-auth` (`codex/gpt-5.4`) both passed `providers health --probe`, the mixed benchmark succeeded for both providers, and the known-bad `codex/gpt-5.4-nano` failure was reproduced and documented as a ChatGPT/Codex-account limitation.
- Files changed: `docs/project/provider-runtime-v4.md`, `README.md`, `NEXT_STEPS.md`, `governance/work-items.json`, `diary/2026-03-22--mixed-provider-runtime-live-verification.md`, and `next_session_prompt.md`.
- Validation commands + results: `DSPX_CONFIG=config.provider-runtime-v4.example.toml just dspx providers resolve --provider vllm-local --json` ✅; `DSPX_CONFIG=config.provider-runtime-v4.example.toml just dspx providers resolve --provider dspy-lm-auth --json` ✅; `DSPX_CONFIG=config.provider-runtime-v4.example.toml just dspx providers health --provider vllm-local --probe --json` ✅; `DSPX_CONFIG=config.provider-runtime-v4.example.toml just dspx providers health --provider dspy-lm-auth --probe --json` ✅; `DSPX_CONFIG=config.provider-runtime-v4.example.toml just dspx providers benchmark --provider vllm-local --provider dspy-lm-auth --repeats 3 --warmup 1 --json` ✅; `DSPX_CONFIG=config.provider-runtime-v4.example.toml DSPX_LM_AUTH_MODEL=codex/gpt-5.4-nano just dspx providers health --provider dspy-lm-auth --probe --json` ❌ expected compatibility failure; `./scripts/ci/smoke.sh` ✅; `./scripts/ci/full.sh` ✅; `just verify-full` ✅.
- Deferred tasks updated in `governance/work-items.json`: completed `DSPX-M4-02`; queued `DSPX-M4-03` for one live end-to-end optimize smoke.
- Next-session starting point: Keep using `config.provider-runtime-v4.example.toml`, then run one small `dspx optimize gepa` smoke with `vllm-local` student + `dspy-lm-auth` reflection defaults to complete `DSPX-M4-03`.

## END-OF-SESSION
Run `/commit` and ensure this file reflects the real checkpoint for the next operator/agent.
