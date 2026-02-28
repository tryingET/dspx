---
summary: "Runtime-test gate conventions for owned Node+Convex tool repos."
read_when:
  - "Adding runtime-heavy tests"
  - "Configuring CI lanes for Convex/runtime checks"
---

# Runtime test gate conventions

## Principle

Runtime-heavy checks are **explicitly gated** and off by default.

This keeps `test:ci-targeted` fast/deterministic on standard CI lanes while still allowing runtime contract verification when requested.

## Gate envs

- `RUN_CONVEX_RUNTIME_TESTS` enables runtime-heavy checks.
- Set either `CONVEX_URL` or `CONVEX_DEPLOYMENT` when the gate is enabled.

Accepted truthy values for `RUN_CONVEX_RUNTIME_TESTS`:

- `1`
- `true`
- `yes`
- `on`

## Baseline commands

```bash
npm run lint
npm run test:ci-targeted
npm test
RUN_CONVEX_RUNTIME_TESTS=1 npm run test:ci-targeted
RUN_CONVEX_RUNTIME_TESTS=1 node --test tests/convex_runtime_contract_enforcement.test.mjs
```
