---
summary: "Canonical developer workflow contract for setup, hooks, validation, and session-safe changes."
read_when:
  - "You are changing setup, hooks, validation, or contributor workflow docs."
  - "You need the one supported local workflow path for DSPx."
---

# Developer Workflow

This document is the canonical workflow contract for local setup, hooks, validation, and session-safe changes in DSPx.

If another repo doc disagrees with this file, update the other doc to match this one and add/adjust workflow contract checks.

## Golden Path

### 1. Install dependencies

```bash
just install
just dev-install   # optional: editable installs for console scripts during dev
```

### 2. Install hooks

```bash
just hooks-install
```

Implementation detail: this uses `uvx pre-commit install` for both `pre-commit` and `pre-push` hooks.

### 3. Validate before push

```bash
./scripts/ci/smoke.sh
just verify-full
```

Validation contract:
- `./scripts/ci/smoke.sh`
  - protects `docs/_core/**`
  - verifies workflow contract integrity
  - validates `governance/work-items.json` against `governance/work-items.cue`
- `just verify-full`
  - re-checks workflow contracts
  - runs `uvx pre-commit run --all-files`
  - runs governance validation
  - runs monorepo/typecheck/test gates

## Governance + session planning

`governance/work-items.json` is the project planning backlog.
Use it to choose the next slice unless the operator gives a more specific priority.
Do not treat it as a scheduler or a substitute for explicit execution receipts/session capture.

## Documentation contract

The following docs must stay aligned with this file:
- `AGENTS.md`
- `CONTRIBUTING.md`
- `README.md` (workflow snippets)
- `docs/tech-stack.local.md`
- `next_session_prompt.md`

Any command referenced in those files must resolve to a real script or `just` recipe.

## Local artifact boundaries

The repo root `.gitignore` must ignore Python cache artifacts at minimum:
- `__pycache__/`
- `*.py[cod]`

Additional local-only outputs may be ignored when they are reproducible or clearly machine-generated.
