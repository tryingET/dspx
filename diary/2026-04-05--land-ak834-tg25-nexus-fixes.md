# 2026-04-05 — Land AK-834 TG25 NEXUS fixes

## Why this slice existed

`AK-834` was the first truthful `TG25` hardening slice after the adversarial review crystallized concrete fail-closed gaps across Forge, replay, provider racing, auth-backed provider signaling, and Oracle semantics.

The repo already had the bounded findings and most of the implementation clustered in the working tree; this session isolated that slice, validated it, and closed it in AK.

## What landed

- fixed Forge sanitization so secret regexes match real whitespace/token patterns instead of doubled-backslash theater
- stopped persisting `raw_input` in Forge work orders and confined `wo.id` under the selected output root
- added `dspx.security.confine_path()` / `PathEscapeError` as the shared path-confinement primitive
- confined replay receipt path resolution under the receipt root while preserving the explicit absolute-cache-file escape hatch
- hardened `MultiProviderLM` so `parallel_first` waits for successful/ready results instead of letting fast failures win, and so shared provider instances keep cwd/policy overrides isolated
- marked non-strict `dspy-lm-auth` failures with structured error payloads and raised on those payloads when downstream extraction treats them as normal completions
- fixed Oracle frontier nearest-neighbor attribution and territory membership lookup beyond the display sample
- added targeted regressions in `tests/test_tg25_nexus_fixes.py` and extended `tests/test_multi_provider_parallel_semantics.py`

## Validation

- `uv run --no-sync -m pytest -q tests/test_tg25_nexus_fixes.py tests/test_multi_provider_parallel_semantics.py` ✅
- `uv run --no-sync -m pytest -q tests/test_provider_v4.py` ✅
- `./scripts/ak.sh work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅
- `./scripts/ak.sh work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅
- `./scripts/ci/smoke.sh` ✅
- `just task-scope-check 834 working-tree` ✅
- `just verify-full` ❌ (`tests/test_task_scope.py` still fails on repo-wide task-scope resolution behavior that matches the remaining `AK-835` slice)
- exported `governance/task-scopes/AK-834.snapshot.json` ✅

## Source-of-truth updates

- completed `AK-834` in AK with a result summary
- refreshed `docs/project/operational_goals.md` so only `AK-835` remains active
- refreshed `next_session_prompt.md` to start from the post-`AK-834` queue truth
- re-exported `governance/work-items.json`

## Next truthful step

Claim `AK-835` and close the remaining bounded `TG25` hardening slice before promoting `TG26`.
