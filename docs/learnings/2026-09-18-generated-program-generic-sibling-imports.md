---
summary: "AK-5756 learning: generated programs import generic process-global sibling names, so every in-process loader must evict cached namesakes BEFORE importing; saving and restoring afterwards is not enough."
read_when:
  - "Writing or reviewing any code that imports a generated program, candidate or wrapper in-process."
  - "Considering a change to the import lines emitted into generated program surfaces."
type: "learning"
task_id: 5756
---

# Generated programs import generic sibling names

Every generated program contains `from module import …` and `from signature import …`
(`program_surfaces.py`, `program_topology.py`, `program_refinement_gepa_candidate.py`).
Those names are process-global. If a `module` is already in `sys.modules`, Python serves
that cached object and never looks at the file beside the program.

## What went wrong

Two in-process loaders saved the previous `sys.modules` entries and restored them
afterwards, but did not evict them first: `optimize_service._import_program_module` and
the emitted metric-honesty wrapper's `_load_candidate`. With a stale `module` cached, the
optimizer imported a generated program that was bound to a **stranger's** module. The
test suite never showed it because tests happened to clean up, until xdist scheduling
put a leaking test and a victim on the same worker (CI, 2026-09-18).

`program_runtime_episode._generated_program_module` and the Soomfon evaluation loader
already evicted first; they were the correct pattern.

## The rule

An in-process loader of generated code must, under a lock:

1. record the current `sys.modules` entries for the program and every sibling name;
2. **evict those names**;
3. import;
4. in `finally`, evict again and restore what was recorded.

`tests/test_generated_program_import_isolation.py` pins this for the optimizer loader.
`tests/conftest.py` additionally evicts `module` and `signature` between tests, which
protects the suite but would also hide a regression in a loader — hence the dedicated spec.

## Decision: keep the emitted imports

Package-qualified or uniquely named sibling imports would remove the hazard at its
source, but the import lines are part of hash-bound generated surfaces: changing them
changes candidate identities, golden fixtures and the generated-surface policy, and
cannot be applied to historical candidates at all. The supported ways to run a generated
program do not have the problem: `dspx program-run` uses an evicting loader, and the
generated `run.py`-style script runs in its own process.

**Unsupported:** putting two generated program directories on `sys.path` and importing
them ad hoc in one process. Whichever `module` is imported first wins, silently.
Revisit the emitted imports only together with a deliberate generated-surface version
bump.
