Contributing
============

Thanks for your interest in contributing! A few quick guidelines:

- Use Python 3.13 and uv for dependency management.
- Run quality checks locally: `just fmt`, `just lint`, `just typecheck`, `just test`.
- Keep changes focused and minimal; include docs updates when behavior changes.
- For larger proposals, open an issue first to discuss design and scope.

Development Setup
-----------------
- Clone the repo and initialize submodules:

  git submodule update --init --recursive

- Sync deps and install in editable mode:

  uv sync
  uv pip install -e .

- Enable pre-commit hooks (no pip needed):

  uvx pre-commit install
  # run on all files once
  uvx pre-commit run --all-files

Pull Requests
-------------
- Describe the problem and solution clearly.
- Add tests when feasible (unit or smoke-level).
- Ensure CI passes.

Code of Conduct
---------------
By participating, you agree to abide by the Code of Conduct (see CODE_OF_CONDUCT.md).
