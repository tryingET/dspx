# Forge app boundary (scaffold)

Forge becomes an optional app surface on top of `dspx-core`.

Current state:
- Forge implementation now lives at `src/dspx/apps/forge_app/*`.
- Legacy `src/dspx/forge/*` modules remain as compatibility aliases.
- CLI uses `dspx.apps.forge_compat` as transition facade.

Boundary intent:
- App code depends on core contracts/services.
- No reverse dependency from core into app internals.
- CLI compatibility (`dspx forge ...`) is preserved via forwarding during migration.
