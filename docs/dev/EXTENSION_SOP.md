---
summary: "Repo-local SOP for scoped DSPx changes with deterministic validation and maintenance follow-through."
read_when:
  - "You are implementing a bounded repo change and need the canonical phase order."
  - "You are verifying or maintaining a change before handoff."
---

# Extension SOP

## 1) Plan

- Confirm scope, risks, and acceptance criteria from operator intent plus repo context.
- Read the relevant local source-of-truth docs before editing.
- Prefer deterministic local commands and repo-documented workflows.

## 2) Implement

- Make the smallest complete change that closes the issue.
- Keep tests and docs in sync with behavior changes.
- Remove generated or accidental artifacts when they create repo drift.

## 3) Verify

Run the narrowest commands that prove the change, then the repo-level gates appropriate for the touched surfaces.

Minimum expectations:

```bash
uv run pytest -q <targeted-tests>
uv run ruff check <touched-files>
```

When the change touches shared workflow, server/runtime boundaries, docs contracts, or repo hygiene, also run:

```bash
just verify-full
```

## 4) Maintain

- Review the most central touched file for follow-on complexity.
- Either keep as-is because the current structure is still proportionate, or refactor now.
- If anything is deferred, record a concrete trigger in the repo's authoritative planning surface.
