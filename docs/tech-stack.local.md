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
- Typechecking uses `ty` (not mypy): `uvx ty check src`
- Commands are standardized in `Justfile` (`just test`, `just fmt`, `just lint`, `just typecheck`).
