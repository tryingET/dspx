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

### Optional local auth-provider checkout

When DSPx should use the local `dspy-lm-auth` checkout rather than a published wheel or an unrelated clone, install the contrib repo in editable mode from this workspace:

```bash
just link-dspy-lm-auth
# optional explicit override:
# just link-dspy-lm-auth path=~/ai-society/softwareco/contrib/dspy-lm-auth
```

The helper defaults to `~/ai-society/softwareco/contrib/dspy-lm-auth`, installs it with `uv pip install -e`, and fails if `import dspy_lm_auth` still resolves somewhere else.

### 3. Validate before push

Standardized owned-lane outer surface available in this repo:

```bash
just help
just check
just ci
just doctor
just run              # falls back to DSPx CLI help when called without args
```

First local product loop smoke, useful after setup or before demonstrating the base layer:

```bash
just smoke-base       # offline temp-dir signature -> module -> program -> eval -> authority-plan loop
```

This uses the stub provider, disables MLflow, writes to a temp directory by default, and does not call AK or mutate external authority. See `docs/project/first-local-loop.md`.

```bash
./scripts/ci/smoke.sh
just task-scope-check task_id=<AK-ID> mode=working-tree   # before commit, for the current slice
just verify-impact-plan                                   # deterministic changed-file validation plan
just verify-impact                                        # run the bounded/expanded impact-aware plan when it is not wide
just verify-impact-receipt                                # run impact-aware validation and write generated/ci/verify-impact-result.json
just verify-pre-push                                      # matches the pre-push hook
just verify-full                                          # explicit full gate before merge/release or when needed
```

Validation contract:
- `./scripts/ci/smoke.sh`
  - protects `docs/_core/**`
  - verifies workflow contract integrity
  - validates `governance/work-items.json` against `governance/work-items.cue`
- `./scripts/ci/full.sh`
  - runs `./scripts/ci/smoke.sh`
  - runs the deterministic replay provenance check (`uv run -q python scripts/check_replay_provenance.py`)
  - runs repo ontology validation when ROCS metadata is present
- `just verify-fast`
  - re-checks workflow contracts
  - runs governance validation
  - runs `just task-scope-check`, which auto-selects working-tree validation when the repo is dirty and otherwise validates the full committed attested task slice from the first task-scope artifact introduction through `HEAD`, using an explicit `task_id`, an active AK claim, or changed task-scope snapshot/legacy-scope-file paths, and otherwise fails closed
  - when no explicit AK task-scope snapshot (or brownfield legacy scope file) exists for the task, the checker skips cleanly and applies repo-default scope instead of failing on missing repo-local scaffolding
  - `next_session_prompt.md` remains handoff context only and does not participate in task-scope binding
  - runs `uvx pre-commit run --all-files`
- `just verify-pre-push`
  - runs `just verify-fast`
  - is the hook-facing pre-push gate
- `just verify-runtime`
  - runs replay provenance, monorepo boundary, module synthesis quality, and `just boundary-contract-check`
  - `just boundary-contract-check` executes the repo boundary contract matrix from `docs/project/boundary-contract-matrix.md` plus docs strict validation
- `just verify-impact-plan`
  - runs `scripts/ci/verify_changed.py --plan-only` to produce a deterministic changed-file validation plan from `scripts/ci/verification-impact.yml`
  - does not execute checks and does not replace `just verify-full`
  - fails wide in the plan for unknown, CI/dependency, broad shared, or cross-domain changes
- `just verify-impact`
  - runs the selected impact-aware commands when the plan is bounded or expanded
  - refuses to execute wide/full-required plans unless the planner is explicitly run with its wide-allowing flag
  - is a local iteration gate, not the final merge/release confidence gate
- `just verify-impact-receipt`
  - runs the same impact-aware planner with `--result-out generated/ci/verify-impact-result.json`
  - writes `dspx-verification-impact-result-v1` local evidence for passed, failed, or blocked-wide plans
  - does not replace `just verify-full`; a blocked-wide receipt is an escalation signal, not validation success
- `just verify-full`
  - runs `just verify-fast` first
  - then runs the heavier runtime/invariant branch and the typecheck/test branch in parallel
  - keeps `uv.lock` clean for the read-only validation commands it delegates through `uv run --no-sync`
  - remains the explicit full confidence gate before merge/release or when the current slice needs the whole suite

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
