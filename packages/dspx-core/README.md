---
summary: "README for the dspx-core package."
read_when:
  - "You are working inside packages/dspx-core."
  - "You need package-level setup or usage context."
type: "guide"
---

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

Installed-wheel proof:
- `just ci-package` installs this wheel alone before Forge and runs one bounded product journey outside the checkout with `PYTHONPATH` unset.
- The journey proves stub-backed materialization, passing local behavior, receipt checking, candidate-local Oracle indexing/reporting, artifact identity/hash coherence, and the workflow's declared non-authority posture; a PATH-resolved `ak` canary separately detects ordinary AK CLI invocation.
- Its explicitly selected mock Oracle embedder proves packaging and evidence plumbing only; it does not prove live-provider behavior, production semantics, network isolation, exclusion of absolute-path/external API effects, release readiness, promotion, or activation.
