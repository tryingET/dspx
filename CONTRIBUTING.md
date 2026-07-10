---
summary: "Contributor guide for DSPx development."
read_when:
  - "You are contributing changes to DSPx."
  - "You need local development or contribution expectations."
type: "guide"
---

Contributing
============

Thanks for your interest in contributing! A few quick guidelines:

- Use Python 3.13 and uv for dependency management.
- Canonical local workflow: `docs/project/developer_workflow.md`.
- Standardized outer Justfile surface: `just help`, `just check`, `just ci`, `just doctor`, `just run` (plain `just run` falls back to DSPx CLI help).
- Run quality checks locally: `just fmt`, `just lint`, `just typecheck`, `just test`.
- Keep changes focused and minimal; include docs updates when behavior changes.
- For larger proposals, open an issue first to discuss design and scope.

Development Setup
-----------------
- Clone the repo and initialize submodules:

  git submodule update --init --recursive

- Install workspace dependencies:

  just install

- Optionally install editable packages for console-script development:

  just dev-install

- Enable hooks:

  just hooks-install
  # optional standardized sanity checks
  just help
  just doctor
  # validate the current slice explicitly before commit, then run the hook-facing fast gate
  just task-scope-check task_id=<AK-ID> mode=working-tree
  just verify-pre-push
  # run the full parallelized gate before merge/release or when the slice needs whole-repo confidence
  just verify-full
  # exact credential-free GitHub CI surfaces when changing CI or packaging
  just ci-quality
  just ci-test-shards
  just ci-package

Pull Requests
-------------
- Describe the problem and solution clearly.
- Add tests when feasible (unit or smoke-level).
- Ensure CI passes. CI uses Python 3.13, `uv sync --frozen`, bounded offline test shards, the measured coverage ratchet, and isolated package checks; it never publishes artifacts.

Code of Conduct
---------------
By participating, you agree to abide by the Code of Conduct (see CODE_OF_CONDUCT.md).
