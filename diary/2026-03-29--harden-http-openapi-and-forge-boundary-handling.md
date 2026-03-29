---
summary: "Hardened redirect-safe HTTP allowlist enforcement, OpenAPI JSON body handling, Forge issue identity matching, and rate-limit token accounting under AK-517."
read_when:
  - "You need the implementation record for AK-517."
  - "You are checking why DSPx now guards redirect hops and preserves non-dict OpenAPI JSON bodies."
---

# 2026-03-29 — Harden HTTP/OpenAPI and Forge Boundary Handling

## What I Did
- Created and claimed `AK-517` for a repo-scoped hardening slice across HTTP/OpenAPI/Forge boundary behavior.
- Extracted a shared `dspx.http_guard` helper so OpenAPI spec loading, OpenAPI operation calls, and generic web fetches validate each redirect hop against the configured host allowlist before following it.
- Hardened the Forge GitLab client to reject redirects that escape the configured host allowlist.
- Fixed rate-limit middleware token accounting so a request rejected by one bucket no longer burns tokens from sibling buckets.
- Widened OpenAPI request/response body handling from dict-only payloads to arbitrary JSON values so arrays and other falsey payloads survive transport unchanged.
- Tightened Forge issue sync identity by suffixing local IDs with the workorder fingerprint digest and resolving existing issues by fingerprint instead of title-only labels.

## Why It Mattered
- Redirect-following clients could previously validate only the initial URL and then trust the final location after the fact, which leaves a fail-open gap at the exact boundary we intended to guard.
- Dict-only DTO typing silently dropped valid JSON array payloads and falsey request bodies for OpenAPI operations.
- The rate-limit middleware could over-consume tokens when one bucket rejected a request after another bucket had already decremented, creating noisy quota drift.
- Forge issue sync could collide when different workorders shared the same human title.

## Validation
- `uv run -m pytest -q tests/test_openapi_url_loading.py tests/test_web_tools_allowlist.py tests/test_openapi_toolpack.py -k 'redirect or allowlist'` ✅
- `uv run -m pytest -q tests/test_forge_gitlab_client.py` ✅
- `uv run -m pytest -q tests/test_server_rate_limit.py` ✅
- `uv run -m pytest -q tests/test_openapi_registry_tools.py tests/test_openapi_toolpack.py -k 'array or falsey or bulk or redirect'` ✅
- `uv run -m pytest -q tests/test_forge_mvp.py` ✅
- `just task-scope-check task_id=517 mode=working-tree` ✅
- `just verify-full` ✅
- `ak task complete 517 ...` ✅
- `ak work-items export --repo /home/tryinget/ai-society/softwareco/owned/dspx --path governance/work-items.json` ✅
- `ak work-items check --repo /home/tryinget/ai-society/softwareco/owned/dspx` ✅

## Next
- Reuse `dspx.http_guard` for any future HTTP entrypoint that needs redirect-safe host validation instead of re-implementing local allowlist checks.
- Keep OpenAPI transport surfaces typed for arbitrary JSON values unless a narrower schema is enforced at a higher layer.
- If another Forge sync identity rule is introduced, keep the fingerprint marker as the final disambiguation authority.
