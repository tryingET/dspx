---
summary: "Use sibling upstream clones (DSPy/MLflow/vibe-dspy/attachments) instead of adding more submodules."
read_when:
  - "You need to debug/patch DSPy or MLflow behavior while working in dspx."
  - "You need to wire vibe-dspy/attachments from local upstream clones."
  - "You are considering adding new upstream repos as git submodules in this repo."
---

# Upstream Contribution Workflow (no new submodules)

## Decision

For upstream dependencies (especially `dspy`, `mlflow`, `vibe-dspy`, `attachments`),
prefer **sibling upstream clones** over adding new git submodules in this repo.

Current repo posture: no git submodules tracked.

Why:
- avoids submodule lifecycle friction (`--recurse-submodules`, detached HEADs, CI complexity)
- keeps `dspx` focused on integration boundaries
- makes upstream PR flow explicit and fast

## Recommended local layout

```bash
mkdir -p ~/programming/upstream
cd ~/programming/upstream

git clone https://github.com/stanfordnlp/dspy.git
git clone https://github.com/mlflow/mlflow.git
git clone https://github.com/Archelunch/vibe-dspy.git
git clone https://github.com/MaximeRivest/attachments.git
```

## Use local upstream code in dspx

From `dspx/`:

```bash
# swap currently installed wheel with editable upstream checkout
uv pip install -e ~/programming/upstream/dspy
uv pip install -e ~/programming/upstream/mlflow
```

For vibe-dspy-backed signature generation, DSPx will auto-discover:

1. `DSPX_VIBE_DSPY_SRC` (explicit `.../vibe-dspy/src`)
2. `DSPX_UPSTREAM_DIR/vibe-dspy/src` (if set)
3. `~/programming/upstream/vibe-dspy/src` (default)

Optional explicit pin:

```bash
export DSPX_VIBE_DSPY_SRC=~/programming/upstream/vibe-dspy/src
```

For attachments helpers, use `PYTHONPATH` when needed:

```bash
uv run env PYTHONPATH=~/programming/upstream/attachments/src python -c "import attachments; print('attachments ok')"
```

Then run focused checks in `dspx`:

```bash
just test-core
just test-forge
just monorepo-check
```

## Upstream-first fix loop

1. Reproduce in `dspx`.
2. Patch in upstream clone (`~/programming/upstream/dspy` or `.../mlflow`).
3. Re-run failing `dspx` checks.
4. Open upstream PR.
5. After upstream release, bump `dspx` dependency constraints to released version.

## Reset back to released dependencies

```bash
# restore environment from lock/workspace metadata
uv sync
```

## Notes

- Keep local editable overrides out of committed lock/pinning decisions unless explicitly planned.
- If a temporary upstream git pin is needed for unblock, track it in `NEXT_STEPS.md` and remove after release.
