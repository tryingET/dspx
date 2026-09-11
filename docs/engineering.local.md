---
summary: "DSPx repo-specific engineering notes (overrides on top of engineering-core lane docs)."
read_when:
  - "Before engineering planning, implementation, review, advice, or validation in DSPx."
  - "You’re changing tooling (typecheck/lint/test/CI) or adding infra-ish dependencies."
type: "reference"
---

# Engineering guidance (DSPx local)

Canonical lane docs come from the immutable release declared in `policy/engineering-lane.json`; do not use the current engineering-core checkout as a substitute for that consumer pin and do not vendor/copy upstream guidance here.

Inspect only the compact policy projection defined by the workspace AGENTS rule. Use the repo-owned helper for upstream Markdown; it derives the immutable source, lane, and selected disciplines from that policy and exposes no full-document mode:

```bash
# Discover headings before selecting a small inclusive range.
python3 scripts/engineering_guidance.py lane headings
python3 scripts/engineering_guidance.py lane range 72 88

# Choose the discipline name from the compact policy projection.
python3 scripts/engineering_guidance.py discipline testing headings
python3 scripts/engineering_guidance.py discipline testing range 20 36
```

Unknown disciplines, symbolic or malformed pins, failed upstream retrieval, and invalid ranges fail closed. A range is capped at 40 lines; headings are capped at 100 lines; every successful response is capped at 16 KiB. Catalog, lane-list, discipline-list, template-list, current-checkout, and full-document output remain unsupported paths rather than default context.

Local notes for DSPx:
- Python 3.13, `uv` workflow, `ruff` lint/format, `pytest` tests.
- Typechecking uses the lockfile-pinned `ty` (not mypy): `uv run --no-sync ty check packages/dspx-core/src apps/forge/src`. Do not use unpinned `uvx ty`; it resolves the latest tool independently of `uv.lock` and can change the validation contract.
- Canonical local workflow contract: `docs/project/developer_workflow.md`
- Commands are standardized in `Justfile` via the owned-lane contract: `just help`, `just test`, `just check`, `just build`, `just lint`, `just fmt`, `just ci`, `just doctor`, plus repo-specific helpers like `just typecheck`.
- `just run ...` is the truthful one-shot entrypoint and delegates to the DSPx CLI surface; plain `just run` falls back to CLI help and keeps the lockfile untouched.
- Read-only validation/sanity commands that use `uv run` now prefer `--no-sync` so `just doctor`, `just test`, `just replay-provenance-check`, `just monorepo-check`, `just module-synthesis-quality-check`, and `just verify-full` no longer dirty `uv.lock` just by being executed.
- No `just dev` target is exposed because DSPx has multiple long-running helper surfaces but no single canonical dev/watch entrypoint.
- The T2 typed-cutover support matrix is stub-only. Auth-backed and other live providers remain unavailable until separately restored; no local provider-link helper is supported.
- Optional py-lane companions when the repo actually benefits:
  - `pytest-bdd` for executable Gherkin/BDD scenarios
  - `Jinja2` for reusable text/config/html templates
- Validation tiers:
  - install hooks once: `just hooks-install` (uses `uvx prek`; `.pre-commit-config.yaml` remains the hook definition)
  - normalize explicit files before staging/commit: `just hooks-run files="path/one.py path/two.py"`, then inspect and explicitly stage intended rewrites
  - current-slice validation before commit: `just task-scope-check task_id=<AK-ID> mode=working-tree`
  - pre-commit hook = fast staged checks (ruff/whitespace)
  - pre-push hook = `just verify-pre-push`
  - `just verify-fast` runs workflow/governance/task-scope/prek all-files checks and fails closed on unresolved task binding
  - `just verify-full` is the fail-closed host-authority/isolated-computation dispatcher; it preserves the ordered fast obligations and parallel runtime/test branches without running ambient `verify-fast`. Default execution is blocked; `just verify-full --plan` is non-executing.
  - explicit batch gate before merge/release: `just verify-full`

## Repo loop validation

DSPx adopts `repo-loop-validation-v1` for repo-agnostic orchestration prompts such as `/visible-loop`, `/nexus-loop`, and future prompt-loop surfaces. The machine-readable declaration lives in `policy/engineering-lane.json`.

- `loop-doctor`: `just loop-doctor` (maps to `just scope-doctor`; non-failing dirty-tree/task-scope diagnostics)
- `loop-verify-fast`: `just loop-verify-fast` (maps to `just verify-boundary-hardening`)
- `loop-impact-plan`: `just loop-impact-plan` (maps to `just verify-impact-plan`)
- `loop-impact-run`: `just loop-impact-run` (maps to `just verify-impact`)
- `loop-impact-wide`: `just loop-impact-wide` (maps to `just verify-impact-wide`)
- `loop-landing-check`: `just loop-landing-check` (maps to `just check`)

These commands produce DSPx-local validation evidence. They do not replace AK task scope, repo decisions/evidence, CI/release gates, or generated-program production activation authority.


## Full-gate root-cause repair (implementation awaiting independent review)

`Justfile` no longer automatically loads `.env`, for **all** recipes. Other commands
must receive deliberate caller exports; full verification discards ambient exports
and starts its fixed environment before Python site hooks, collection or hooks.
See [the approved migration table](project/2026-09-07-evidence-integrity-design.md#approved-root-cause-implementation--september-11-before-code)
and [the operational contract](project/developer_workflow.md#full-gate-isolation-and-manual-admission).

The eight artifact-fallback unit cases inject only no-claim; omitted resolver calls
still use the native function at invocation. Native nonzero errors (including old
compiler/unregistered-repo messages) now fail closed, rather than select an artifact.
The original Soomfon fd-positive node now proves explicitly synthetic OS mechanics;
its historical-runtime broad skip is retired, not counted as historical compatibility.
Native task5061 and current admitted-claim success are mandatory separate host stages.
These changes do not alter the production Soomfon adapter or historical executable pin.


Independent HOLD corrections split process custody, config-free Git and closure
validation into the three scope-v10 helpers. The default claim parser now permits
no-claim fallback only for truly absent bare `ak`; broken configured executables and
malformed rows in any repo deny. Full claimed-task leases validate literal RFC3339
offset ranges and dates. Full-custody v3 additionally binds original index bytes and staged membership;
independent node and collector-skip baselines remain mandatory; matching partial pytest collections are not coverage proof. See the
workflow contract for closed mount roles and durable lost-create-response recovery.

### September 11 implementation review disposition

Independent review dispatch1789151333325 SHIPs the bounded implementation and
technical commit readiness, superseding the awaiting-review status above only for
the reviewed bytes. See the dated addendum in
[the scoped diary](../diary/2026-09-07--evidence-rootcause-implementation.md).
This is not a full-gate pass. Owner applicability for `separately_disabled` remains
pending: a timed-out form default is not consent. No full/native profile, Docker or
real closure provisioning ran; explicit-task static scope and cached commit hooks
are commit containment only. Do not activate the full profile from this disposition.
