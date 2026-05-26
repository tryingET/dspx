---
summary: "DSPx repo-specific engineering notes (overrides on top of engineering-core lane docs)."
read_when:
  - "You want the preferred stack + the local deviations for this repo."
  - "You’re changing tooling (typecheck/lint/test/CI) or adding infra-ish dependencies."
---

# Engineering guidance (DSPx local)

Canonical lane docs live in `engineering-core` (do not vendor/copy here):

- list lanes: `uv tool run engineering-core list`
- print python lane: `uv tool run engineering-core show py`
- show path: `uv tool run engineering-core path py --prefer-repo`
- catalog: `uv tool -n run --from ~/ai-society/core/engineering-core engineering-core catalog --pretty`
- list disciplines: `uv tool -n run --from ~/ai-society/core/engineering-core engineering-core list-disciplines`
- list templates: `uv tool -n run --from ~/ai-society/core/engineering-core engineering-core list-templates`

Machine-readable recognition lives in `policy/engineering-lane.json`.

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

## Repo loop validation

DSPx adopts `repo-loop-validation-v1` for repo-agnostic orchestration prompts such as `/visible-loop`, `/nexus-loop`, and future prompt-loop surfaces. The machine-readable declaration lives in `policy/engineering-lane.json`.

- `loop-doctor`: `just loop-doctor` (maps to `just scope-doctor`; non-failing dirty-tree/task-scope diagnostics)
- `loop-verify-fast`: `just loop-verify-fast` (maps to `just verify-boundary-hardening`)
- `loop-impact-plan`: `just loop-impact-plan` (maps to `just verify-impact-plan`)
- `loop-impact-run`: `just loop-impact-run` (maps to `just verify-impact`)
- `loop-impact-wide`: `just loop-impact-wide` (maps to `just verify-impact-wide`)
- `loop-landing-check`: `just loop-landing-check` (maps to `just check`)

These commands produce DSPx-local validation evidence. They do not replace AK task scope, repo decisions/evidence, CI/release gates, or generated-program production activation authority.
