---
summary: "Phased, non-breaking plan to split DSPx into core package plus optional Forge app."
read_when:
  - "You are changing package boundaries or moving Forge/core code."
  - "You need migration sequencing, compatibility, or rollback guidance."
---

# Monorepo Transition Plan

## Goal

- Canonical kernel: `dspx-core`.
- Optional app boundary: Forge (`apps/forge`).
- Keep current runtime/CLI/import behavior stable during transition.

## Dependency Rule (non-negotiable)

- Allowed: `apps/* -> core`.
- Forbidden: `core -> apps/*`.
- During transition, treat `src/dspx/forge` as app code and avoid new imports into core runtime modules.

## What moves now vs later

Move now (safe scaffold):
- Create boundary folders:
  - `packages/dspx-core/`
  - `apps/forge/`
- Add boundary docs and import guardrails.
- Keep all executable code in existing `src/dspx/` layout.

Move later (after guardrails + green CI):
- Extract core modules from `src/dspx/` into `packages/dspx-core/` in small batches.
- Move Forge implementation behind app boundary (`apps/forge/`) with compatibility shims.
- Preserve `dspx forge ...` behavior via forwarding layer until deprecation window is complete.

## Phases

### Phase 1 — Scaffold (non-breaking)

Scope:
- Directory scaffolding only.
- Boundary READMEs.

Acceptance:
- New paths exist and document ownership/dependency direction.
- No runtime import paths changed.
- Existing tests/CLI remain green.

### Phase 2 — Guardrails (lightweight + practical)

Scope:
- Document import rules.
- Add automated check for forbidden reverse imports.

Acceptance:
- CI/local check fails on core importing app modules.
- Current repo passes check without code moves.

### Phase 3 — Extraction prep (still compatibility-first)

Scope:
- Introduce forwarding shims and move-safe adapters.
- Start relocating Forge entry wiring behind app boundary.
- Centralize CLI Forge imports through a compatibility facade (`dspx.apps.forge_compat`).
- Add app-boundary module wrappers under `dspx.apps.forge_app.*` to prepare later extraction without breaking legacy imports.

Acceptance:
- `dspx forge ...` behavior unchanged.
- Existing import paths continue to resolve (with shim warnings only if/when enabled).
- Tests stay green after each small move.

### Phase 4 — Incremental extraction

Scope:
- Move code in thin vertical slices (module-by-module).
- Keep each slice independently revertible.

Acceptance per slice:
- Core/app boundary rules pass.
- CLI behavior unchanged.
- Tests green.
- Diff is small and reviewable.

## Compatibility Strategy

- Keep `src/dspx` as active runtime namespace during transition.
- Prefer forwarding modules and import shims over immediate hard moves.
- Preserve existing scripts/CLI command paths (`dspx ...`, including `dspx forge ...`).
- Deprecate only after replacement path is documented and tested.

## Rollback Strategy

If a migration slice is risky or regresses behavior:
- Stop at current green commit.
- Revert only the last slice (small-commit discipline).
- Keep boundary docs/checks in place; postpone risky move to next slice.
- Prefer “prepare-only” follow-up PRs over broad rewrites.

## Operational Checklist per PR

- [ ] Boundary rule still holds (`apps -> core`, never reverse).
- [ ] No runtime behavior changes unless explicitly intended.
- [ ] `pre-commit run --all-files` passes.
- [ ] `just test` passes.
- [ ] Transition docs updated if phase scope changes.
