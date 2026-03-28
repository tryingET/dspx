---
summary: "Complete AK-436 by hardening generated-code smoke validation and fail-closing server trust boundaries."
read_when:
  - "You are resuming after AK-436."
  - "You need the implementation notes behind the generated-code/server guardrail hardening slice."
---

# 2026-03-24 — Harden Generated-Code Validation and Server Trust Boundaries

## What I Did
- Claimed `AK-436` and replaced host-side/generated-code smoke execution with `packages/dspx-core/src/dspx/generated_code_guard.py`, which runs signature/module smoke checks in isolated subprocesses with a minimal environment.
- Added AST/runtime guardrails so smoke checks reject unsafe top-level behavior, block filesystem mutation, block subprocess spawning, and block outbound socket connects while still allowing deterministic DSPy shape validation.
- Made auth configuration fail closed in `packages/dspx-core/src/dspx/server/security.py` when `DSPX_SERVER_TOKEN_FILE` is unreadable/empty or when auth is required without any configured tokens.
- Hardened rate-limit identity handling so only validated tokens receive token-scoped identity, token keys are hashed instead of stored raw, and identity state is bounded/cleaned instead of growing per bogus bearer string.
- Tightened `packages/dspx-core/src/dspx/synthesis/runtime.py` promotion so only the selected, passed candidate can be promoted.
- Added/updated regression coverage in `tests/test_signature_native_pipeline.py`, `tests/test_synthesis_runtime_smoke.py`, `tests/test_server_auth.py`, `tests/test_server_rate_limit.py`, and `tests/test_synthesis_contracts.py`.

## Why It Mattered
- Validation paths were acting like privileged execution paths, which let untrusted generated code mutate host state during smoke checks.
- Server auth/rate-limit behavior could silently degrade under config drift or token spray, weakening the trust boundary before endpoint logic ran.
- Promotion needed to preserve the explicit V7 winner boundary instead of letting callers override it after evaluation.

## Patterns
- Treat generated-code validation as a trust-boundary problem, not a convenience helper.
- Fail closed when auth material cannot be loaded; config ambiguity is a security failure, not a warning.
- Rate limiting should bind to validated principals or bounded network identity, never arbitrary untrusted token strings.
- Promotion helpers must enforce selected/passed state rather than trusting caller-supplied candidate IDs.

## Validation
- `.venv/bin/ruff check packages/dspx-core/src/dspx/generated_code_guard.py packages/dspx-core/src/dspx/server/app.py packages/dspx-core/src/dspx/server/security.py packages/dspx-core/src/dspx/services/signatures_service.py packages/dspx-core/src/dspx/synthesis/runtime.py tests/test_server_auth.py tests/test_server_rate_limit.py tests/test_signature_native_pipeline.py tests/test_synthesis_contracts.py tests/test_synthesis_runtime_smoke.py` ✅
- `.venv/bin/pytest -q tests/test_module_service.py tests/test_server_auth.py tests/test_server_rate_limit.py tests/test_server_api.py tests/test_signature_native_pipeline.py tests/test_signatures_service_dto.py tests/test_synthesis_contracts.py tests/test_synthesis_runtime_smoke.py` ✅
- `python scripts/check_task_scope.py --task-id 436 --mode working-tree` ✅
- `./scripts/ci/smoke.sh` ✅
- `just verify-full` ✅
- `ak task complete 436 ...` ✅
- `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅
- `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅

## Next
- Refresh the checked-in work-item projection from AK after task completion.
- Resume `AK-386`, which remains the active TG14 planning slice for freezing the next SG2 contract without widening evidence authority or changing V7 ranking/promotion behavior.
