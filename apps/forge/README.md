# Forge app boundary (scaffold)

Forge becomes an optional app surface on top of `dspx-core`.

Current state:
- Scaffold only; no code moved yet.
- Existing Forge runtime remains in `src/dspx/forge` to preserve behavior.

Boundary intent:
- App code depends on core contracts/services.
- No reverse dependency from core into app internals.
- CLI compatibility (`dspx forge ...`) is preserved via forwarding during migration.
