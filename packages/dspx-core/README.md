# dspx-core (scaffold)

Canonical DSPx product kernel target.

Current state:
- Scaffold only; no runtime code moved yet.
- `src/dspx/` remains canonical import/runtime location during transition.

Boundary intent:
- `dspx-core` owns runtime/providers/services/tools/policy/contracts.
- Apps consume core contracts.
- Core must not depend on app code.
