# dspx-core

Canonical DSPx product kernel.

Current state:
- Runtime code lives in `packages/dspx-core/src/dspx`.
- Package name: `dspx-core`.
- Python module name: `dspx`.
- Core CLI entrypoint lives under `dspx.cli.dspx`.

Boundary intent:
- `dspx-core` owns runtime/providers/services/tools/policy/contracts.
- Apps consume core contracts.
- Core must not import app packages (`dspx_forge.*`).
