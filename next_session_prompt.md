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
- Objective (one sentence): Execute `DSPX-M4-02` by live-validating the mixed-provider runtime v4 profile (`vllm-local` student + `dspy-lm-auth` reflection).
- Constraints (hard limits): Keep the repo green under `just verify-full`; do not leak credentials in docs/receipts; keep scope on live runtime verification rather than broad new provider work.
- Assumptions (max 3): `DSPX-M4-01` is complete and the local unblock decision is now accepted; provider runtime v4 docs/config are the current source of truth; a local vLLM endpoint and auth-backed Codex route are available to probe when the next operator is ready.
- Blockers (none or list): Requires access to the real local/auth-backed provider endpoints for live probes.

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
- Slice executed: `DSPX-M4-01` — reassess the dspy-template-adapter unblock path.
- Outcome: Adopted DSPx-local provider runtime v4 as the unblock path instead of waiting on or vendoring `dspy-template-adapter` immediately; shipped explicit `vllm-local`, `openai-compatible`, and `dspy-lm-auth` providers, provider resolve/health/benchmark commands, optimize provider defaults, and receipt-safe provider metadata, while keeping exact-fidelity template-adapter work optional/upstream-blocked.
- Files changed: `packages/dspx-core/src/dspx/{provider_runtime.py,openai_compatible_lm.py,dspy_lm_auth_lm.py,providers_register_openai_compatible.py,providers_register_dspy_lm_auth.py,provider_registry.py,config_loader.py,run_receipts.py,services/optimize_service.py}`, `packages/dspx-core/src/dspx/cli/commands/{providers.py,optimize.py}`, `packages/dspx-core/pyproject.toml`, `tests/{test_provider_v4.py,test_config_loader.py}`, `config.provider-runtime-v4.example.toml`, `docs/project/provider-runtime-v4.md`, `README.md`, `docs/adr/{20260322-provider-runtime-v4.md,README.md}`, `NEXT_STEPS.md`, `docs/{system4d/container.md,system4d/fog.md,org_context/org-summary.md,owned/purpose.md}`, `governance/work-items.json`, `diary/2026-03-22--provider-runtime-v4-decision.md`, `next_session_prompt.md`, `uv.lock`, and removal of `docs/dev/status.md`.
- Validation commands + results: `uv run -m pytest -q tests/test_provider_v4.py tests/test_config_loader.py` ✅; `uv run -m pytest -q tests/test_run_receipts.py` ✅; `./scripts/ci/smoke.sh` ✅; `./scripts/ci/full.sh` ✅; `just verify-full` ✅.
- Deferred tasks updated in `governance/work-items.json`: completed `DSPX-M4-01`; queued `DSPX-M4-02` for live mixed-provider verification.
- Next-session starting point: Use `config.provider-runtime-v4.example.toml`, then run `dspx providers health --probe` and `dspx providers benchmark` against the real `vllm-local` + `dspy-lm-auth` environment to complete `DSPX-M4-02`.

## END-OF-SESSION
Run `/commit` and ensure this file reflects the real checkpoint for the next operator/agent.
