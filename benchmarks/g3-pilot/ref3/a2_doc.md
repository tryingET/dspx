---
summary: "Repository-local engineering-core selections, commands, and deviations."
read_when:
  - "Before changing repository engineering conventions or validation commands."
type: "policy"
---

# Repository engineering contract

## Selected lanes and addenda

- `py`

## Selected disciplines

- `validation`
- `testing`
- `security-privacy`
- `documentation`
- `dependency-governance`

## Canonical local commands

- Catalog: `engineering-core catalog --pretty`
- List disciplines: `engineering-core list-disciplines`
- List templates: `engineering-core list-templates`
- Diagnose adoption: `engineering-core doctor --repo .`

## Validation evidence before handoff

Run the repository-local test and lint commands (`uv run python -m pytest tests/`,
`uv run ruff check .`) selected by the py lane and the validation discipline, then
report the commands and outcomes.

## Deliberate deviations

- `keep-local-uv-mirror` — CI mirrors PyPI through a local uv cache; upstream freshness gates do not apply
