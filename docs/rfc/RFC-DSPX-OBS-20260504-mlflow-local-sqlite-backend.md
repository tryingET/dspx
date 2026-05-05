---
summary: "Historical RFC for sqlite-only local MLflow correlation; superseded for unset tracking URI by explicit DS1621/remote tracking policy."
read_when:
  - "You are changing MLflow tracking URI handling, local explain enrichment, or MLflow-related tests."
  - "You are resolving MLflow filesystem tracking deprecation warnings."
  - "You need the historical design contract for explicit sqlite local MLflow correlation in DSPx alpha."
---

# RFC: SQLite-Only Local MLflow Backend for DSPx Alpha

## 0) Metadata

- RFC ID: `RFC-DSPX-OBS-20260504-mlflow-local-sqlite-backend`
- Status: `accepted/implemented; partially superseded`
- Owner: `DSPx maintainers`
- Reviewers: `DSPx observability reviewers`, `runtime/replay maintainers`
- Created: `2026-05-04`
- Target milestone: `MLflow deprecation cleanup / local explain hardening`
- Related docs:
  - `docs/MLFLOW_OBSERVABILITY_PLAN.md`
  - `docs/rfc/RFC-DSPX-OBS-20260207-mlflow-explain-correlation-v11.md`
  - `docs/ARCH_DRAFT_DSPX_NEXT.md`
- Related recent commits:
  - `06727cb fix: avoid deprecated mlflow file-store lookup` — superseded warning workaround
  - `754de9f docs: specify sqlite-only local mlflow backend`
  - `9c0f82d fix: require sqlite for local mlflow tracking`
  - `7cf87f7 docs: align mlflow sqlite setup surfaces`

### 0.1 Supersession note — explicit tracking URI policy

This RFC remains the historical rationale for rejecting MLflow filesystem tracking and for keeping explicit `sqlite:...` test/developer coverage. Its unset-URI fallback decision is superseded: DSPx no longer resolves missing `MLFLOW_TRACKING_URI` to `sqlite:///mlflow.db`. When MLflow is enabled but no tracking URI is configured, DSPx performs no MLflow side effects and reports missing tracking URI diagnostics for explain enrichment. The normal shared tracking target is the DS1621 MLflow service at `http://ds1621:50000`, backed by Postgres plus MinIO.

## 1) Problem statement

MLflow 3.10 emits a `FutureWarning` when code constructs the deprecated filesystem tracking backend, including local `file://.../mlruns` stores:

```text
FutureWarning: The filesystem tracking backend (e.g., './mlruns') is deprecated as of February 2026. Consider transitioning to a database backend (e.g., 'sqlite:///mlflow.db') ...
```

DSPx observed exactly three such warnings in `tests/test_run_receipts.py`. The warnings are not merely noisy test output. They reveal that important local explain-correlation tests still model filesystem tracking as a normal local MLflow path, even though DSPx's observability policy already names `sqlite:///mlflow.db` as the deterministic local default.

The immediate warning-avoidance fix in `06727cb` skipped MLflow client experiment discovery for filesystem tracking URIs. That removes one warning path but keeps a deprecated backend in the design. Because DSPx is still in alpha, preserving compatibility with deprecated filesystem tracking is the wrong default. Alpha is the moment to remove the wrong contract, not carry it forward.

The design question is therefore:

> How should DSPx make sqlite the only supported local MLflow backend and remove filesystem tracking from the supported local explain-correlation contract while preserving local-first replay truth and remote lookup guardrails?

## 2) Current state evidence

### 2.1 Existing policy already points to sqlite

`docs/MLFLOW_OBSERVABILITY_PLAN.md` states:

- when `MLFLOW_ENABLE=1` and `MLFLOW_TRACKING_URI` is unset, DSPx forces `sqlite:///mlflow.db`;
- expected local artifact root remains `./mlruns`;
- replay/explain truth remains receipt/replay-local, with MLflow as optional enrichment only.

Before this RFC was implemented, that plan still listed `file:...` and local path tracking modes. This RFC superseded that portion for DSPx alpha: file/local-path MLflow tracking is not a supported DSPx local mode.

### 2.2 Former implementation drift treated file-store as local

Before the sqlite-only implementation, `run_explain_service.py` treated sqlite and filesystem tracking as local scan modes. That was the source of the design drift. SQLite tracking is now the local backend of record. Filesystem tracking is rejected or degraded before MLflow can construct the deprecated backend.

The local artifact scan remains valid for sqlite because MLflow sqlite stores metadata in the database while artifacts normally live on the filesystem. The problem was not scanning artifacts; the problem was treating the artifact directory as the MLflow tracking backend.

### 2.3 Former warning-producing tests encoded the wrong contract

The three warning-producing tests created fake `mlruns` directory layouts and set `MLFLOW_TRACKING_URI` to `file://.../mlruns`:

- same-artifact filtering by expected tags;
- partial tag matching;
- nested artifact paths.

Those behaviors are valuable, but the fixture backend was wrong. The canonical tests now use real sqlite-backed MLflow runs for those behaviors.

### 2.4 Implementation outcome

The sqlite-only contract is implemented:

- unset `MLFLOW_TRACKING_URI` resolves to `sqlite:///mlflow.db`;
- explicit `sqlite:...` local tracking is supported;
- `file:...` and bare local path tracking URIs are unsupported;
- read-only explain degrades MLflow enrichment with `mlflow_filesystem_backend_unsupported` rather than instantiating MLflow's filesystem backend;
- canonical local explain-correlation tests use sqlite-backed MLflow runs for tag filtering, partial tag matching, and nested artifact paths;
- setup/onboarding surfaces now tell local users to leave `MLFLOW_TRACKING_URI` unset or set `sqlite:///mlflow.db`.

## 3) Goals and non-goals

### Goals

- Make sqlite the only supported local MLflow tracking backend in DSPx alpha.
- Resolve filesystem tracking deprecation warnings by removing supported filesystem tracking paths, not by hiding warnings.
- Rewrite canonical local explain-correlation tests to create real sqlite-backed MLflow runs.
- Preserve local-first replay/explain authority: receipts and replay checks remain authoritative; MLflow is optional enrichment.
- Preserve remote tracking as user-managed and default-off for lookup unless `--mlflow-remote-lookup` is explicit.
- Fail closed or degrade MLflow enrichment when a filesystem tracking URI is supplied, without failing baseline replay/explain.
- Ensure targeted tests fail on future MLflow `FutureWarning`s.

### Non-goals

- Preserving compatibility with explicit `file:` or local-path MLflow tracking URIs.
- Maintaining fake filesystem `mlruns` fixtures as canonical MLflow behavior tests.
- Making MLflow required for replay/explain correctness.
- Starting MLflow runs from read-only `dspx run explain`.
- Enabling remote MLflow lookup by default.
- Changing upstream MLflow behavior.
- Rewriting DSPy autolog or the broader observability stack in this slice.

## 4) Design tensions and resolution

### 4.1 Correct backend vs compatibility pressure

A compatibility-oriented design would keep file-store reads as a best-effort path. That is attractive in mature software with known file-store users. DSPx is still alpha, and the existing local policy already says sqlite. Carrying a deprecated backend forward would increase surface area, test burden, and operator confusion.

Resolution: no local filesystem tracking compatibility. SQLite is the only supported local backend.

### 4.2 MLflow metadata API vs artifact filesystem scan

SQLite does not mean all data lives in sqlite. MLflow stores run/experiment metadata in sqlite and typically stores artifacts under a local artifact root. DSPx should use MLflow APIs for sqlite metadata and local filesystem scanning for artifact correlation after artifact roots are resolved.

Resolution: reject filesystem tracking as a backend, but keep filesystem artifact scanning as part of sqlite local correlation.

### 4.3 Real integration fixtures vs fake filesystem fixtures

Fake `mlruns` layouts are fast but encode MLflow internals and can canonize deprecated behavior. Real sqlite-backed MLflow runs provide stronger evidence and align with the supported backend.

Resolution: canonical local tests must create real sqlite-backed MLflow runs and log artifacts/tags through MLflow APIs.

### 4.4 Warning silence vs contract correctness

A passing warning-as-error test is necessary but not sufficient. The product contract must stop accepting deprecated filesystem tracking as local MLflow.

Resolution: tests must prove both no `FutureWarning` and sqlite-backed coverage for the scenarios that previously used filesystem fixtures.

## 5) Decision

DSPx should adopt a sqlite-only local MLflow tracking contract for alpha:

1. `sqlite:///mlflow.db` is the canonical and only supported local MLflow tracking backend.
2. Unset `MLFLOW_TRACKING_URI` resolves to sqlite local tracking.
3. Explicit `sqlite:///...` URIs are supported local tracking.
4. Explicit `file://...` URIs and local path tracking URIs are unsupported.
5. If an unsupported filesystem tracking URI is supplied to read-only explain, baseline replay/explain still runs, but `mlflow_context` degrades with a deterministic reason code and no MLflow filesystem backend construction.
6. If an unsupported filesystem tracking URI is supplied to MLflow logging/bootstrap paths, DSPx should fail closed to MLflow-disabled behavior rather than call `mlflow.set_tracking_uri(...)` with a deprecated filesystem backend.
7. The `06727cb` workaround should be replaced or narrowed: the goal is not direct-scan compatibility for file-store, but explicit unsupported-mode handling.

## 6) Target architecture

### 6.1 Tracking mode classification

`run explain --with-mlflow` should classify tracking input as follows:

| Input | Mode | Supported? | Metadata lookup | Artifact lookup |
|---|---|---:|---|---|
| unset `MLFLOW_TRACKING_URI` | `local-sqlite-default` | yes | MLflow/sqlite | local artifact roots, default `./mlruns` |
| `sqlite:///.../mlflow.db` | `local-sqlite` | yes | MLflow/sqlite | MLflow experiment artifact roots + local scan |
| `file://.../mlruns` | `unsupported-filesystem-tracking` | no | none | none |
| local path | `unsupported-filesystem-tracking` | no | none | none |
| `http(s)://...` | `remote-uri` | yes, user-managed | opt-in remote MLflow API | remote candidate search only when explicit |

The supported local modes are exactly `local-sqlite-default` and `local-sqlite`.

### 6.2 Unsupported filesystem tracking behavior

For `dspx run explain --with-mlflow` with `file:` or local-path tracking URI:

- do not instantiate `MlflowClient`;
- do not search experiments;
- do not parse `meta.yaml` or tags from a fake `mlruns` layout;
- do not scan artifacts under the filesystem tracking root;
- keep baseline replay/explain result intact;
- emit degraded MLflow enrichment diagnostics.

Recommended additive diagnostics:

```json
{
  "mlflow_context": {
    "requested": true,
    "mode": "unsupported-filesystem-tracking",
    "lookup_mode": "disabled",
    "linked_runs": [],
    "candidate_count": 0,
    "matched_count": 0,
    "degrade_reason_codes": ["mlflow_filesystem_backend_unsupported"],
    "warnings": [
      "MLflow filesystem tracking backends are unsupported in DSPx alpha; use sqlite:///mlflow.db."
    ]
  }
}
```

`mlflow_filesystem_backend_unsupported` should be appended to the reason-code taxonomy rather than reusing remote or disabled reason codes.

### 6.3 SQLite local correlation flow

For sqlite local tracking:

1. Run baseline replay/explain first.
2. Resolve tracking URI as sqlite.
3. Use MLflow APIs to discover experiments, runs, tags, and artifact locations.
4. Include the default local artifact root (`./mlruns`) as a fallback only for sqlite artifact lookup when experiment metadata is unavailable or incomplete.
5. Scan local artifact roots for required/optional receipt artifacts.
6. Use MLflow sqlite metadata/tags for candidate verification when local artifact-side metadata is absent.
7. Emit deterministic `mlflow_context` with stable reason codes.

The sqlite path may scan artifact files, but it must not treat the filesystem directory as the MLflow tracking backend.

### 6.4 MLflow bootstrap/logging guard

Any DSPx helper that configures MLflow from environment should reject unsupported filesystem tracking URIs before calling MLflow tracking setup APIs.

For example, `enable_mlflow_from_env()` should:

- accept unset URI and resolve to `sqlite:///mlflow.db`;
- accept explicit `sqlite:`;
- accept explicit `http(s):` as user-managed remote;
- reject `file:` and local path tracking by returning `False` or otherwise degrading to no MLflow side effects;
- avoid importing or configuring MLflow solely to discover that a filesystem backend is unsupported.

This preserves the `MLFLOW_ENABLE=0` no-side-effect rule and prevents filesystem backend warnings in logging paths as well as explain paths.

### 6.5 Read-only explain invariant

`dspx run explain --with-mlflow` must not:

- create MLflow experiments;
- start or end MLflow runs;
- log artifacts, metrics, params, or tags;
- mutate receipts, replay artifacts, AK, governance, or external authority;
- perform remote lookup unless explicitly requested with `--mlflow-remote-lookup`.

## 7) Test plan

### 7.1 Migrate canonical local tests to sqlite

Rewrite the three warning-producing tests to create real sqlite-backed MLflow runs:

- `test_run_explain_local_mlflow_filters_same_artifacts_by_expected_tags`
- `test_run_explain_local_mlflow_accepts_partial_matching_tags`
- `test_run_explain_local_mlflow_accepts_nested_artifact_paths`

Fixture requirements:

- use `MLFLOW_TRACKING_URI=sqlite:///<tmp>/mlflow.db`;
- create an experiment with a temp artifact root;
- create runs through MLflow fluent APIs or `MlflowClient` under sqlite;
- set the same `dspx.*` tags used by receipt hints;
- log artifacts through MLflow APIs, including nested artifact paths for nested coverage;
- end active runs in cleanup;
- assert matching behavior and no mutation as before.

### 7.2 Unsupported filesystem tracking tests

Add narrow tests for unsupported filesystem tracking behavior:

- explicit `file://.../mlruns` with `run explain --with-mlflow` degrades MLflow enrichment with `mlflow_filesystem_backend_unsupported`;
- local path tracking URI does the same;
- neither path emits MLflow's filesystem tracking `FutureWarning`;
- neither path links runs from fake `mlruns` fixtures;
- baseline replay/explain still succeeds or fails according to receipt truth, independent of MLflow enrichment.

These tests should not preserve direct-scan matching behavior for filesystem tracking.

### 7.3 Warning regression gate

The targeted MLflow receipt suite should pass with FutureWarnings as errors:

```bash
uv run pytest tests/test_run_receipts.py -q -W error::FutureWarning
```

At least one sqlite local explain-correlation test and one unsupported filesystem-tracking test should explicitly catch warnings around `runner.invoke(...)` and assert no message contains:

```text
filesystem tracking backend
```

### 7.4 Broader validation

Minimum validation for implementation:

```bash
uv run pytest tests/test_run_receipts.py -q -W error::FutureWarning
uvx ruff check packages/dspx-core/src/dspx/tracing.py packages/dspx-core/src/dspx/services/run_explain_service.py tests/test_run_receipts.py
uvx ty check packages/dspx-core/src
just boundary-contract-check
node ~/ai-society/core/agent-scripts/scripts/docs-list.mjs --docs . --strict
git diff --check
```

If time allows, run `just verify-full`; if it exceeds harness time, run `just verify-runtime` and the impacted test subsets separately and report timeout truthfully.

## 8) Implementation wave

Implemented wave:

```text
Remove local MLflow filesystem tracking and migrate explain correlation to sqlite
```

Implemented scope:

- `packages/dspx-core/src/dspx/tracing.py`
- `packages/dspx-core/src/dspx/services/run_explain_service.py`
- `tests/test_run_receipts.py`
- `docs/MLFLOW_OBSERVABILITY_PLAN.md`
- `governance/work-items.json`
- `governance/task-scopes/AK-<ID>.snapshot.json`

Completed steps:

1. Added sqlite MLflow fixture helpers that create a temp sqlite DB, experiment, artifact root, run tags, and logged artifacts.
2. Rewrote the three warning-producing tests to use sqlite-backed real runs.
3. Replaced file-store direct-scan behavior with unsupported filesystem tracking degradation.
4. Added `mlflow_filesystem_backend_unsupported` to diagnostics/reason-code handling.
5. Guarded MLflow bootstrap/logging helpers against `file:` and local path tracking URIs.
6. Updated `docs/MLFLOW_OBSERVABILITY_PLAN.md` and setup/onboarding surfaces to remove file/local-path tracking from supported modes.
7. Ran targeted warning-as-error validation and sqlite smoke validation.

## 9) Compatibility and rollout

DSPx is in alpha. No filesystem-tracking compatibility window is required.

Rollout status:

1. SQLite-backed test migration and unsupported filesystem tracking diagnostics landed in one focused implementation wave.
2. Fake file-store matching fixtures were removed from canonical explain-correlation tests.
3. Output schema changes stayed additive where practical, but deprecated backend behavior was not preserved for schema compatibility alone.
4. The migration path for local users is documented as: set `MLFLOW_TRACKING_URI=sqlite:///mlflow.db` or leave it unset.

## 10) Acceptance evidence

Implemented acceptance evidence:

- the three former warning-producing tests no longer use `file://.../mlruns` as their backend;
- sqlite-backed real MLflow runs cover tag filtering, partial tag matching, and nested artifact paths;
- explicit `file:` and local path tracking URIs are unsupported and do not link runs;
- unsupported filesystem tracking emits deterministic diagnostics, including `mlflow_filesystem_backend_unsupported`;
- DSPx rejects filesystem tracking before configuring MLflow's deprecated filesystem backend;
- `uv run pytest tests/test_mlflow_tracking_uri_modes.py tests/test_mlflow_enabled_local_store.py tests/test_run_receipts.py -q -W error::FutureWarning` passed after implementation/setup alignment;
- docs say sqlite is the only supported local MLflow backend;
- read-only explain still has no MLflow run creation/logging side effects;
- remote lookup remains opt-in.

## 11) Resolved questions

1. Unsupported filesystem tracking sets `mlflow_context.mode` to `unsupported-filesystem-tracking` rather than preserving `local-file-store` naming.
2. `enable_mlflow_from_env()` returns `False` for filesystem tracking URIs before importing/configuring MLflow; structured diagnostics are emitted on caller surfaces that already expose `mlflow_context`, such as `run explain`.
3. Bare local paths are not sqlite shorthand. Users must leave `MLFLOW_TRACKING_URI` unset or use explicit `sqlite:///...`.

## 12) Reviewer checklist

- Does this RFC correctly treat MLflow's warning as a contract migration signal?
- Does it use alpha status to remove the deprecated local backend rather than preserve it?
- Does it preserve DSPx local-first replay/explain authority?
- Does it prevent read-only explain from mutating MLflow state?
- Does it require real sqlite-backed MLflow fixtures for canonical local behavior?
- Does it remove fake filesystem tracking from canonical tests?
- Does it keep remote lookup default-off?
