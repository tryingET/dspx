---
summary: "DSPx repo-specific tech-stack notes (overrides on top of tech-stack-core lane docs)."
read_when:
  - "You want the preferred stack + the local deviations for this repo."
  - "You’re changing tooling (typecheck/lint/test/CI) or adding infra-ish dependencies."
---

# Tech stack (DSPx local)

Canonical lane docs live in `tech-stack-core` (do not vendor/copy here):

- list lanes: `uv tool run tech-stack-core list`
- print python lane: `uv tool run tech-stack-core show py`
- show path: `uv tool run tech-stack-core path py --prefer-repo`

Local notes for DSPx:
- Python 3.13, `uv` workflow, `ruff` lint/format, `pytest` tests.
- Typechecking uses `ty` (not mypy): `uvx ty check packages/dspx-core/src apps/forge/src`
- Canonical local workflow contract: `docs/project/developer_workflow.md`
- Commands are standardized in `Justfile` via the owned-lane contract: `just help`, `just test`, `just check`, `just build`, `just lint`, `just fmt`, `just ci`, `just doctor`, plus repo-specific helpers like `just typecheck`.
- `just run ...` is the truthful one-shot entrypoint and delegates to the DSPx CLI surface; plain `just run` falls back to CLI help and keeps the lockfile untouched.
- Read-only validation/sanity commands that use `uv run` now prefer `--no-sync` so `just doctor`, `just test`, `just replay-provenance-check`, `just monorepo-check`, `just module-synthesis-quality-check`, and `just verify-full` no longer dirty `uv.lock` just by being executed.
- No `just dev` target is exposed because DSPx has multiple long-running helper surfaces but no single canonical dev/watch entrypoint.
- Local auth-backed provider work should prefer the workspace contrib checkout via `just link-dspy-lm-auth` (defaults to `~/ai-society/softwareco/contrib/dspy-lm-auth`).
- Optional py-lane companions when the repo actually benefits:
  - `pytest-bdd` for executable Gherkin/BDD scenarios
  - `Jinja2` for reusable text/config/html templates
- Validation tiers:
  - install hooks once: `just hooks-install`
  - current-slice validation before commit: `just task-scope-check task_id=<AK-ID> mode=working-tree`
  - pre-commit hook = fast staged checks (ruff/whitespace)
  - pre-push hook = `just verify-pre-push`
  - `just verify-fast` runs workflow/governance/task-scope/pre-commit all-files checks and fails closed on unresolved task binding
  - `just verify-full` runs `verify-fast` first, then executes the heavier runtime/invariant branch and the typecheck/test branch in parallel
  - explicit batch gate before merge/release: `just verify-full`
