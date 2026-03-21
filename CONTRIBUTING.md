Contributing
============

Thanks for your interest in contributing! A few quick guidelines:

- Use Python 3.13 and uv for dependency management.
- Canonical local workflow: `docs/project/developer_workflow.md`.
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
  # run the full validation gate once
  just verify-full

Pull Requests
-------------
- Describe the problem and solution clearly.
- Add tests when feasible (unit or smoke-level).
- Ensure CI passes.

Code of Conduct
---------------
By participating, you agree to abide by the Code of Conduct (see CODE_OF_CONDUCT.md).
