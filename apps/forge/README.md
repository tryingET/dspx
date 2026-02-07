# Forge app boundary

Forge is an optional app surface on top of `dspx-core`.

Current state:
- Forge implementation lives in `apps/forge/src/dspx_forge`.
- Core package no longer owns Forge modules.
- Core CLI (`dspx`) no longer mounts `forge` commands.

Use Forge CLI directly:
- `just forge intake ...`
- `just forge plan ...`
- `just forge issues apply ...`

Dependency intent:
- apps depend on core package (`dspx-core`, module `dspx`).
- core never depends on app packages.
