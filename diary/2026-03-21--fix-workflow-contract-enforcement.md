---
summary: "Diary entry: 2026-03-21 — Workflow Contract Enforcement."
read_when:
  - "You need the historical implementation context captured in this diary entry."
  - "You are reviewing or extending work related to 2026-03-21 — Workflow Contract Enforcement."
type: "diary"
---

# 2026-03-21 — Workflow Contract Enforcement

## What I Did
- Implemented the NEXUS intervention from the deep review by creating `docs/project/developer_workflow.md` as the canonical workflow contract.
- Fixed hook installation and validation drift by updating `Justfile`, adding `.pre-commit-config.yaml`, adding `.gitignore`, and wiring workflow/governance checks into `./scripts/ci/smoke.sh` and `just verify-full`.
- Updated repo workflow surfaces (`AGENTS.md`, `CONTRIBUTING.md`, `README.md`, `docs/tech-stack.local.md`, `governance/README.md`, `next_session_prompt.md`) to align with the canonical contract.
- Added executable workflow-contract validation (`scripts/check_workflow_contracts.py`) plus tests.

## What Surprised Me
- The highest-severity failures were process bugs, not product-code bugs: the documented golden path itself was broken.
- The absence of a root `.gitignore` had already produced `__pycache__` drift, so hygiene debt was active rather than theoretical.
- `just verify-full` still exposes pre-existing repo-wide `ty` failures in untouched files, so the workflow contract is now honest but the full validation baseline is not yet green.

## Patterns
- If workflow docs are spread across multiple files, at least one will fossilize unless a machine-check binds them together.
- A smoke gate that does not check the repo's claimed contracts creates false confidence faster than no smoke gate at all.

## Crystallization Candidates
- → docs/learnings/ for the pattern "convert process docs into executable contract checks before they become routing authority"
