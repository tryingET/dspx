---
summary: "Maps this repository's validation commands to the engineering-core validation tiers."
read_when:
  - "Defining or refreshing the repository validation command surface."
---

# Validation Tier Map

Repo: `softwareco/owned/dspx`
Owner surface: `docs/engineering.local.md`

## Commands

| Tier | Command | Scope | Target runtime | Required before |
| --- | --- | --- |---|---|
| editor/save | `ruff format <changed file>` + editor type hints | file-local | instant | local editing |
| pre-commit | `just hooks-run files="<changed files>"` (prek on the staged slice) | staged slice | p95 < 10s | commit |
| task-scope | `uv run --no-sync -m pytest tests/<focused test> -q` + `just lint-core` | changed behavior | minutes | task handoff |
| pre-push | `just verify-fast` | repo full gate | acceptable local gate | push/merge |
| CI | `just ci-test-shards` + `just ci-quality` | authoritative matrix | complete enough for merge | merge/release |
| release | `just verify-full` | shipped artifact | strongest | tag/publish |

## Standard surface

- `just check`: `just verify-fast` (workflow-contract-check, direction-contract-check, governance-check)
- `just test`: `test` recipe (`uv run --no-sync -m pytest -q tests` when tests exist)
- `just build`: `n/a` — no build recipe exists; packages build through uv/publish flows, not a repo-level build target
- `just ci`: `verify-full` recipe via the `ci` alias (`just verify-full`)
- `just doctor`: `doctor` recipe (python3/uv/toolchain sanity)

## Evidence rule

Every handoff records:

- command
- scope
- result
- warning acceptance, if any
- artifact path, if any
