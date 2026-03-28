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
- Commands are standardized in `Justfile` (`just test`, `just fmt`, `just lint`, `just typecheck`).
- Optional py-lane companions when the repo actually benefits:
  - `pytest-bdd` for executable Gherkin/BDD scenarios
  - `Jinja2` for reusable text/config/html templates
- Validation tiers:
  - install hooks once: `just hooks-install`
  - current-slice validation before commit: `just task-scope-check task_id=<AK-ID> mode=working-tree`
  - pre-commit hook = fast staged checks (ruff/whitespace)
  - pre-push hook = `just verify-full`
  - `just verify-full` also runs `just task-scope-check`, which validates the full attested task slice in head mode using an explicit `task_id`, an active AK claim, changed manifest paths, or the committed `next_session_prompt.md` checkpoint, and otherwise fails closed
  - explicit batch gate: `just verify-full`
