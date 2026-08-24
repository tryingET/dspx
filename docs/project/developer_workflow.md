---
summary: "Canonical developer workflow contract for setup, hooks, validation, and session-safe changes."
read_when:
  - "You are changing setup, hooks, validation, or contributor workflow docs."
  - "You need the one supported local workflow path for DSPx."
---

# Developer Workflow

This document is the canonical workflow contract for local setup, hooks, validation, and session-safe changes in DSPx.

If another repo doc disagrees with this file, update the other doc to match this one and add/adjust workflow contract checks.

## Golden Path

### 1. Install dependencies

```bash
just install
just dev-install   # optional: editable installs for console scripts during dev
```

### 2. Install hooks

```bash
just hooks-install
```

Implementation detail: this uses `uvx prek install` for both `pre-commit` and `pre-push` hooks. `prek` is a fast, language-agnostic Git hook manager; DSPx keeps the interoperable `.pre-commit-config.yaml` hook definition and uses `prek` as the runner.

### Typed provider support matrix

The T3 matrix supports `DSPyTypedLMAdapter(StubProvider)` and exactly one restored
`DSPyTypedLMAdapter(OpenAICompatibleProvider)`. The latter requires an explicit model
and IP-literal loopback HTTP base URL; it has no credentials, redirects, retries,
streaming, tools, async, state, or copy surface. Other legacy auth, CLI, HTTP, RPC,
and aggregate providers remain removed rather than linked through compatibility helpers.
Canonical secret-free TOML configuration is:

```toml
[provider]
name = "openai-compatible"
model = "local-model"
base_url = "http://127.0.0.1:8000/v1"
timeout = 30
```

Dispatch additionally requires `DSPX_POLICY_ALLOW_NETWORK_MUTATE=1` and the existing
provider/capability policy checks. The policy maximum timeout caps the configured value.
Provider attempts retain only bounded model/effect metadata; prompts, bodies, URLs,
headers, and exception text are excluded. The additive
`dspx-provider-effect-evidence-v1` envelope records cumulative count, explicit
history truncation, terminal effect, and at most 64 attempts. Any indeterminate
effect permanently latches both the provider instance and typed adapter against
later dispatch, including adapter-side response-construction failures. A shared
reentrant operation lock serializes direct and adapter calls through final response
construction, so concurrent GEPA/runtime calls cannot complete past that latch.

### 3. Validate before push

Standardized owned-lane outer surface available in this repo:

```bash
just help
just check
just ci
just doctor
just run              # falls back to DSPx CLI help when called without args
```

First local product loop smoke, useful after setup or before demonstrating the base layer:

```bash
just smoke-base       # offline temp-dir signature -> module -> program -> eval -> authority-plan loop
```

This uses the stub provider, disables MLflow, writes to a temp directory by default, and does not call AK or mutate external authority. It reports materialization and behavior separately and exits non-zero if generated behavior fails even when receipts/replay succeed. See `docs/project/first-local-loop.md`.

Reproducible semantic regression gate (offline by default):

```bash
just semantic-benchmark
```

The default benchmark remains credential-free and offline. The restored loopback HTTP
provider is not exercised by that benchmark and is tested only with injected fake
clients; no live-provider pass is claimed. The machine-readable result is evidence only
and grants no activation or external
authority. See `docs/project/semantic-benchmarks.md` for corpus thresholds and
result schema.

Artifact retention is inspection-first. Generated/server output roots are never cleaned implicitly. Preview aged files below the explicit server root and retain the emitted `plan_id`; apply requires that unchanged plan plus exact-root confirmation:

```bash
just artifact-cleanup
just artifact-cleanup generated/server 7 \
  --apply --plan-id <reviewed-plan-id> --confirm-root generated/server
```

The cleanup tool rejects filesystem/home/git roots and invalid ages, never follows or deletes symlinks, never deletes directories, confines every candidate to the configured root, and refuses apply if the candidate metadata has changed since the reviewed dry run.

```bash
./scripts/ci/smoke.sh
just scope-doctor                                       # diagnose dirty-tree AK task-scope binding without failing the shell
just task-scope-check task_id=<AK-ID> mode=working-tree   # before commit, for the current slice
just verify-boundary-hardening                            # focused CLI/provider/runtime/generated-program boundary hardening loop
just verify-impact-plan                                   # deterministic changed-file validation plan
just verify-impact                                        # run the bounded/expanded impact-aware plan when it is not wide
just verify-impact-wide                                   # explicitly run a wide/full-required impact-aware plan
just hooks-run files="path/one.py path/two.py"             # run repo hook stack on explicit files before staging/commit
just verify-impact-receipt                                # run impact-aware validation and write generated/ci/verify-impact-result.json
just verify-pre-push                                      # matches the pre-push hook
just verify-full                                          # explicit full gate before merge/release or when needed
just ci-quality                                           # GitHub static/contract job parity (no AK dependency)
just ci-test-shard shard=core-0                           # one exact GitHub test shard
just ci-test-shards                                       # complete offline GitHub test set
just ci-package                                           # exact Core-wheel journey/release-claim truth + Forge smoke
```

Generic `repo-loop-validation-v1` aliases for orchestration prompts:

```bash
just loop-doctor          # maps to just scope-doctor; non-failing diagnostics
just loop-verify-fast     # maps to just verify-boundary-hardening
just loop-impact-plan     # maps to just verify-impact-plan
just loop-impact-run      # maps to just verify-impact
just loop-impact-wide     # maps to just verify-impact-wide
just loop-landing-check   # maps to just check; repo-declared landing/readiness gate
```

These aliases produce repo-local validation evidence for `/visible-loop`, `/nexus-loop`, and future loop prompts. They do not replace AK task scope, repo decisions/evidence, CI/release gates, or production activation authority.

Validation contract:
- `./scripts/ci/smoke.sh`
  - protects `docs/_core/**`
  - verifies workflow contract integrity
  - validates direction-to-execution coherence against AK-native task authority
- `./scripts/ci/full.sh`
  - runs `./scripts/ci/smoke.sh`
  - runs the deterministic replay provenance check (`uv run -q python scripts/check_replay_provenance.py`)
  - runs repo ontology validation when ROCS metadata is present
- `just hooks-run files="..."`
  - runs `uvx prek run --files ...` on an explicit file set before staging/commit
  - is the normalization boundary for commit workflows: hooks may rewrite formatting/lint fixes, so inspect the diff and explicitly stage only intended paths afterward
- `just verify-fast`
  - re-checks workflow contracts
  - runs governance validation
  - runs `just task-scope-check`, which auto-selects working-tree validation when the repo is dirty and otherwise validates the full committed attested task slice from the first task-scope artifact introduction through `HEAD`, using an explicit `task_id`, an active AK claim, or changed task-scope snapshot/legacy-scope-file paths, and otherwise fails closed
  - when no explicit AK task-scope snapshot (or brownfield legacy scope file) exists for the task, the checker skips cleanly and applies repo-default scope instead of failing on missing repo-local scaffolding
  - runs `uvx prek run --all-files`
- `just verify-pre-push`
  - runs `just verify-fast`
  - is the hook-facing pre-push gate
- `just verify-runtime`
  - runs replay provenance, monorepo boundary, module synthesis quality, and `just boundary-contract-check`
  - `just boundary-contract-check` executes the repo boundary contract matrix from `docs/project/boundary-contract-matrix.md` plus docs strict validation
- `just scope-doctor`
  - prints the current working-tree task-scope diagnosis as JSON and intentionally returns success for exploration/debugging
  - does not replace `just task-scope-check` for landing readiness
- `just verify-boundary-hardening`
  - runs focused format, lint, typecheck, and adversarial boundary tests for CLI/provider/runtime/generated-program seams
  - is the fast Nexus-loop gate for boundary hardening; landing still requires a valid AK task scope and the normal merge gate
- `just verify-impact-plan`
  - runs `scripts/ci/verify_changed.py --plan-only` to produce a deterministic changed-file validation plan from `scripts/ci/verification-impact.yml`
  - does not execute checks and does not replace `just verify-full`
  - fails wide in the plan for unknown, dependency, broad shared, or cross-domain changes; CI planner/test changes stay bounded to planner tests and impact smoke for ordinary loop validation
- `just verify-impact`
  - runs the selected impact-aware commands when the plan is bounded or expanded
  - refuses to execute wide/full-required plans unless the planner is explicitly run with its wide-allowing flag
  - is a local iteration gate, not the final merge/release confidence gate
- `just verify-impact-wide`
  - runs the same impact-aware planner with `--allow-wide`
  - is for explicit exploratory/adversarial validation of wide plans and does not by itself satisfy AK task-scope landing authority
- `just verify-impact-receipt`
  - runs the same impact-aware planner with `--result-out generated/ci/verify-impact-result.json`
  - writes `dspx-verification-impact-result-v1` local evidence for passed, failed, or blocked-wide plans
  - does not replace `just verify-full`; a blocked-wide receipt is an escalation signal, not validation success
- GitHub CI
  - runs on Python 3.13 with a frozen uv lock and uv's dependency cache
  - keeps tests bounded as four deterministic core file shards, one Forge marker shard, and one offline slow shard; live/network/model/GPU/Postgres tests are intentionally opt-in and are not represented as credential-free CI passes
  - combines branch coverage from all six disjoint shards and enforces the measured brownfield ratchet configured in `pyproject.toml`
  - builds both wheels and source distributions in a temporary directory and checks package metadata
  - installs the Core wheel alone into a clean Python 3.13 environment, runs outside the checkout with `PYTHONPATH` unset, and proves an explicit stub-provider/mock-embedding program loop through passing behavior, receipt checking, candidate-local Oracle indexing/reporting, cross-artifact hash/identity binding, and revalidation of workflow-declared non-authority fields
  - binds the installed proof to the selected Core wheel's SHA-256 and local PEP 610 direct URL, verifies every original wheel `RECORD` payload plus the complete importable package inventory in the installed tree, validates the complete installed-proof v2 contract, checks sdist `PKG-INFO` and required package content, generates and independently verifies two CycloneDX 1.6 JSON SBOMs against pinned official offline schemas, then validates a `dspx-core-release-evidence-v3` envelope over the exact wheel/sdist, installed proof, exact-wheel SBOM, resolved-environment SBOM, Git commit, and clean/dirty tree state; v1 no-SBOM and v2 exact-wheel-SBOM evidence remain accepted
  - keeps SBOM/provenance/signing/release claims separate: the first SBOM covers complete wheel payload bytes plus declared direct dependencies; the second records the root-reachable installed distribution closure, exact observed versions/edges, and Python/platform marker environment as a point-in-time resolver-dependent observation. It is not lockfile/hash-locked reproducibility, dependency-artifact custody, vulnerability/license policy, or supply-chain approval; provenance remains unattested, signatures remain unverified, technical release evidence remains incomplete, and publication/readiness/authority remain false
  - remains ephemeral by default; `bash scripts/ci/package-check.sh --retain-core-evidence <new-output.zip>` opts into a mode-0600, no-replace `dspx-core-release-bundle-v3` containing the exact wheel, sdist, installed proof, v3 envelope, both verified CycloneDX SBOMs, a local subject/source-bound provenance statement, and a complete hash/size/role manifest; the validator retains v1 and v2 compatibility
  - validates retained bundles with `uv run --no-sync python scripts/ci/core_release_bundle.py validate --bundle <output.zip>`; local retention and point-in-time environment observation are evidence custody, not CI custody, reproducible dependency resolution, retained dependency-artifact closure, attestation, signer-policy/signature verification, registry publication, release readiness, or release authority
  - validates public CI-custody inputs with `uv run --no-sync python scripts/ci/core_release_custody.py preflight-bundle --bundle <output.zip>`; the custody contract enforces the exact bundle-member allowlist, deterministic secret-shaped-content rejection, 14/90-day provider-cap checks, signed-receipt fields, and fresh artifact observation semantics
  - defines the dedicated manual `.github/workflows/core-release-evidence.yml` with immutable action revisions, `contents: read`, `actions: read`, and `id-token: write`; its job is hard-disabled unless the repository variable `DSPX_CORE_RELEASE_SIGNING_ENABLED=true`, and runtime preflight requires protected `main`, the `core-release-evidence` environment, adequate provider retention, a current policy selector, and exact validation of the deliberately unbound disabled roster; Decision 91 permits evidence-only activation without inventing release-owner bindings, while release authority remains unavailable
  - treats failed, timed-out, incomplete, duplicated, or unobservable upload/delete outcomes as `effect_indeterminate`; a provider-confirmed absence can permit an explicit retry, while receipt or evidence absence, expiry, or digest drift keeps release-use custody false
  - installs Core plus Forge into a separate clean environment and smokes the Forge CLI, so Forge cannot mask Core-only packaging/import defects during the product journey
  - labels the installed Core journey as stub-backed plumbing proof only: it is not live-provider proof, production-semantic Oracle proof, network-isolation proof, exclusion of absolute-path/external API effects, release approval, promotion, or activation authority
  - has read-only repository permission and contains no publish or secret-bearing step
- `just ci-quality`, `just ci-test-shard`, and `just ci-package`
  - are the local command surfaces used directly by GitHub CI; `just ci-test-shards` runs the complete credential-free test set locally
- `just verify-full`
  - runs `just verify-fast` first
  - then runs a non-pytest runtime/invariant branch alongside the package+complete-test branch; boundary and candidate-state tests run once in the complete suite instead of being duplicated in both branches
  - uses one 16-worker xdist pool for all credential-free fast and slow tests, avoiding a second pool startup and allowing workers to share the complete offline queue; standalone `test-parallel`, `test-slow-parallel`, and `verify-tests` retain their compatible split behavior
  - schedules offline tests individually across workers so oversized files cannot monopolize one worker; live/network/model/GPU/Postgres tests remain in the serial residual selection
  - isolates unbound module-synthesis evidence lookup from machine-local `generated/` state; promotion-target/default-path characterizations retain native resolution, and dedicated evidence tests bind explicit temporary receipt and Oracle roots
  - shares deterministic generated-code validation results across xdist workers only when the complete pre-validation tree, relevant environment, executable, and execution implementation match; cache hits replay path-rebased file effects into private program trees
  - builds one immutable, production-generated candidate-state graph per pytest session, gives mutation tests private copy-on-write sidecars, guards the canonical template after every test, and keeps manifest-mutating characterizations on fresh graphs
  - includes `just typecheck-tests` so test harness contracts are type-checked alongside package code
  - keeps `uv.lock` clean for the read-only validation commands it delegates through `uv run --no-sync`
  - remains the explicit full confidence gate before merge/release or when the current slice needs the whole suite
- `just loop-*`
  - maps the generic `repo-loop-validation-v1` phases to DSPx's existing scope, boundary-hardening, impact-aware, and landing checks
  - is intended for orchestration prompts and agent loops that need repo-agnostic phase names
  - produces evidence only; successful loop validation does not close AK tasks, approve merge/release, or authorize production activation by itself

## Governance + session planning

AK task ready/list/show is the live execution source of truth for DSPx task/work-item state. Use AK to choose and claim the next repo-scoped slice unless the operator gives a more specific priority.

`governance/work-items.json` is a legacy compatibility projection only. It is not the planning authority, not a scheduler, and not a landing gate for routine validation; if a future compatibility export is needed, perform it as an explicitly scoped projection-maintenance slice.

## Documentation contract

The following docs must stay aligned with this file:
- `AGENTS.md`
- `CONTRIBUTING.md`
- `README.md` (workflow snippets)
- `docs/engineering.local.md`

The retired `next_session_prompt.md` handoff file must not be reintroduced; AK task ready/list/show is the live execution source of truth. Any command referenced in the aligned files must resolve to a real script or `just` recipe.

## Local artifact boundaries

The repo root `.gitignore` must ignore Python cache artifacts at minimum:
- `__pycache__/`
- `*.py[cod]`

Additional local-only outputs may be ignored when they are reproducible or clearly machine-generated.
