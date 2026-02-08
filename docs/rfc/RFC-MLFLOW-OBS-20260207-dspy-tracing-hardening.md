---
summary: "Upstream MLflow RFC draft for DSPy tracing/callback hardening: span safety, concurrency-safe state, and autolog controls."
read_when:
  - "You are preparing MLflow upstream issues/PRs for DSPy integration observability reliability."
  - "You need release sequencing from upstream MLflow changes back into DSPx verification."
---

# RFC: Upstream MLflow DSPy/Tracing Hardening

## 0) Metadata

- RFC ID: `RFC-MLFLOW-OBS-20260207-dspy-tracing-hardening`
- Status: `draft`
- Owner: `lightningralf (DSPx upstream liaison)`
- Reviewers: `MLflow DSPy integration maintainers`, `DSPx observability reviewers`
- Created: `2026-02-07`
- Target upstream release: `mlflow >= 3.10.0` (candidate)
- Related docs:
  - `docs/ARCH_DRAFT_UPSTREAM_MLFLOW.md`
  - `docs/UPSTREAM_CONTRIBUTING_WORKFLOW.md`

## 1) Problem statement

Observed failures in DSPy+MLflow integration under real downstream use:
- span-start warning floods can reappear in expected no-op tracing states
- callback optimize/eval state model is not robust for concurrency
- autolog controls are too narrow for stable downstream run naming/tagging semantics

Priority gaps:
- noisy warnings reduce trust and make operators disable observability
- global mutable callback state risks wrong run/linkage under parallel workloads
- downstream projects repeatedly implement wrapper logic that should be upstream configurable

## 2) Scope / non-goals

### In scope
- span lifecycle no-op safety in callback/fluent tracing layers
- parallel-safe callback state model for optimize/eval paths
- additive autolog control extensions (if maintainers accept)

### Out of scope
- DSPx-specific receipt contracts
- adding backend-specific observability integrations beyond current MLflow scope

### Compatibility constraints
- no breaking default behavior for existing users
- additive config/API where possible

## 3) Current state evidence

- source locations involved:
  - `mlflow/dspy/autolog.py`
  - `mlflow/dspy/callback.py`
  - `mlflow/tracing/fluent.py`
- failing logs/traces:
  - warning pattern: `Failed to start span ... NonRecordingSpan ...`
- concurrency failure scenarios:
  - callback state linkage ambiguity under concurrent optimize/eval execution

## 4) Option analysis (A/B/C)

### Option A: Warning suppression patch only
- Design:
  - make no-op path logs quieter, keep callback state model unchanged
- Pros:
  - minimal code churn
  - quick relief for noise flood
- Cons:
  - does not solve parallel state correctness
  - leaves downstream wrapper pressure unchanged
- Risks:
  - masking deeper callback-state issues

### Option B: No-op span hardening + context-scoped state + minimal autolog controls
- Design:
  - classify expected no-op tracing states and treat as silent/debug paths
  - refactor callback state to context-scoped container (contextvars preferred)
  - introduce small optional autolog controls for naming/tag injection/correlation
- Pros:
  - resolves the highest-impact reliability gaps
  - still additive and reviewable in slices
  - reduces downstream patch burden
- Cons:
  - larger change set than Option A
  - needs concurrency/stress test investment
- Risks:
  - subtle behavioral differences in nested run trees if state migration is incomplete

### Option C: Full callback context object redesign
- Design:
  - introduce new callback context object and broad API overhaul
- Pros:
  - maximal long-term explicitness
- Cons:
  - high migration cost and maintainer risk
  - likely too large for near-term release window
- Risks:
  - API churn and prolonged review cycles

## 5) Decision

- Chosen option: `B`
- Rationale:
  - fixes correctness + noise with manageable additive changes
  - keeps PRs small enough for realistic upstream review/merge
- Deferred items:
  - any broader callback API redesign beyond minimal controls

## 6) Target architecture

### 6.1 Span safety behavior

Expected behavior taxonomy (normative):

| Class | Condition | Handling | Log level | Notes |
|---|---|---|---|---|
| N0 (expected no-op) | tracing/autolog disabled for current process or run | return no-op immediately | none | never treated as error |
| N1 (expected no-op) | tracer returns non-recording span / sampling drop | skip span mutation/end work | none (optional debug breadcrumb) | debug must be off by default |
| N2 (expected no-op) | idempotent lifecycle event (e.g., end on missing/already-ended local span) | ignore and continue | debug at most | prevents warning floods on cleanup races |
| E1 (unexpected tracing failure) | tracing API call raises unexpectedly (`start`, `set_attribute`, `end`) | degrade to no-op for that event path | warning (rate-limited) | callback must stay functional |
| E2 (unexpected state invariant failure) | callback-local stack/token invariant violation | hard-reset local callback state, continue | warning (rate-limited) | indicates correctness bug; should be rare |

Failure boundary rules:
- tracing failures (`E1`, `E2`) must not crash DSPy execution paths; tracing degrades gracefully.
- user/business exceptions from DSPy callbacks are not swallowed or reclassified; they propagate unchanged after tracing cleanup.
- only `N*` classes are silent/debug; only `E*` classes are warning/error eligible.

Warning policy + rate limiting (normative):
- dedupe key: `(error_class, operation_phase, exception_type, normalized_message)`.
- `normalized_message` strips volatile identifiers (run/span IDs, UUID-like tokens, raw memory addresses) to avoid unbounded key cardinality.
- first occurrence for a key logs immediately.
- repeats for same key are suppressed for `300s` window.
- after window expiry, next log for that key includes `suppressed_count` since prior emission.
- rate limiter is process-local and thread-safe; memory bounded by LRU eviction of old keys.
- `N*` classes do not enter the warning rate limiter.

### 6.2 Parallel-safe callback state model

State container choice:
- `contextvars.ContextVar` holding callback-local stack/frame state (no module-global mutable linkage state).

Guarantees under concurrent optimize/eval:
- parent-child linkage is deterministic within a single logical context (LIFO stack discipline).
- no cross-contamination between concurrently executing optimization/eval branches.
- every push/pop/reset is balanced via `try/finally`; callback state restoration is mandatory even on exceptions.

Context propagation boundaries (explicit):
- `asyncio` tasks inherit `contextvars` snapshot at task creation.
- new OS threads do **not** implicitly share callback state; linkage starts empty unless explicitly seeded.
- thread pools therefore cannot leak linkage across workers by default.

Failure boundaries:
- if callback entry sees empty context, treat it as a new local root (never infer parent from global/process state).
- if token reset fails or stack invariants are violated, classify as `E2`, log rate-limited warning, and clear local callback state to safe baseline.
- unmatched end events are classified as `N2` (no warning flood).

### 6.3 Autolog control surface (additive)

Candidate optional args:
- `run_name_template: str | None`
- `extra_tags: dict[str, str] | None`
- `correlation_id_factory: Callable[..., str] | None`

Defaults preserve current behavior when unset.

## 7) PR slicing plan

### PR1: span no-op safety and warning policy
- files touched:
  - `mlflow/dspy/callback.py`
  - `mlflow/tracing/fluent.py`
- expected user-visible impact:
  - lower warning noise in expected no-op conditions without hiding true tracing failures
- acceptance criteria (merge gate):
  - taxonomy classes (`N0/N1/N2/E1/E2`) implemented with direct unit coverage.
  - disabled tracing + non-recording scenarios (`>=1000` span attempts each) emit `0` warnings.
  - injected `E1` failure logs once per dedupe key per `300s` window; suppression count appears after window rollover.
  - no public API signature changes; existing MLflow tracing tests remain green.

### PR2: callback concurrency safety
- files touched:
  - `mlflow/dspy/callback.py`
- expected user-visible impact:
  - stable run/linkage under parallel execution
- acceptance criteria (merge gate):
  - callback linkage state stored in `ContextVar`; no mutable module-global linkage map remains.
  - async stress test (`>=32` concurrent tasks x `>=100` nested optimize/eval operations) shows zero cross-context parent/child mismatches.
  - thread-executor integration test confirms no cross-thread leakage and correct empty-root behavior unless explicitly seeded.
  - exception-path tests confirm `try/finally` state reset (post-callback state baseline is empty/initial).
  - unmatched end lifecycle events classified as `N2` and do not generate warning floods.

### PR3: additive autolog controls
- files touched:
  - `mlflow/dspy/autolog.py`
  - docs/changelog locations
- expected user-visible impact:
  - first-class naming/tagging/correlation controls
- acceptance criteria (merge gate):
  - `autolog()` defaults remain backward compatible when new args are unset.
  - `run_name_template`, `extra_tags`, and `correlation_id_factory` each have unit coverage for happy-path and invalid-input handling.
  - integration test verifies configured name/tags/correlation id appear on produced runs.
  - docs + changelog explicitly mark controls as additive/optional.

## 8) Test strategy

Required matrix:

| Layer | Scenario | Method | Pass criteria |
|---|---|---|---|
| Unit | no-op taxonomy (`N0/N1/N2`) | deterministic fixtures for disabled tracing, non-recording span, unmatched end | `0` warnings; callback returns successfully |
| Unit | error taxonomy (`E1/E2`) | injected exceptions + invariant violations | warning emitted with correct class; execution continues |
| Unit | warning rate limiter | fake clock + repeated identical failures | max `1` warning/key/window, suppression count emitted on rollover |
| Unit | context stack invariants | nested push/pop with exception injection | stack restored to baseline in all paths |
| Integration | DSPy optimize/eval + autolog | real callback wiring, sequential + concurrent cases | deterministic parent/child linkage, no cross-context contamination |
| Integration | additive autolog controls | configure template/tags/correlation factory | produced runs include configured fields; defaults unchanged when unset |
| Stress | sustained parallel callbacks | `>=32` concurrent workers/tasks, `>=100` nested operations each, repeated loops | zero linkage mismatches; no-op cases emit `0` warnings; injected single-key failures respect `<=1` warning per `300s` window; no state growth leak |
| Regression | known warning flood pattern | replay prior `NonRecordingSpan`/disabled tracing conditions | warning flood absent (`0` warnings for expected no-op) |
| Regression | known linkage ambiguity | replay previously failing concurrent optimize/eval pattern | parent run IDs remain deterministic and isolated |

Test implementation notes:
- use deterministic seeds and injectable monotonic clock for rate-limiter assertions.
- include both `asyncio` and thread-executor coverage for context propagation boundaries.
- treat warning-count assertions as hard gates in CI for PR1/PR2.

## 9) Rollout and release

- release sequencing (ordered):
  1. file umbrella issue, align on Option B scope, and lock taxonomy/rate-limit semantics.
  2. merge PR1 first (noise/safety) with warning-count CI gates enabled.
  3. merge PR2 second (concurrency correctness) with stress job enabled in required checks.
  4. merge PR3 third (optional controls), or defer cleanly if maintainer scope trims features.
  5. verify release cut, changelog, and backport posture (if any).

- docs/changelog requirements:
  - explicit expected-no-op vs error taxonomy and warning-rate-limit behavior.
  - explicit context propagation guarantees/boundaries for callback state.
  - new optional autolog args documented as additive and backward compatible.

Release verification matrix (actionable):

| Stage | Owner | Validation | Gate |
|---|---|---|---|
| Pre-release CI | upstream maintainers | run unit + integration + stress matrix from §8 | all green; warning-count tests pass |
| RC validation | upstream + downstream liaison | install RC wheel; replay no-op/error taxonomy scenarios | no-op warning count `0`; `E*` emits max `1` warning/key/`300s` window |
| Concurrency canary | downstream (DSPx) | run parallel optimize/eval regression suite against RC (`>=32` workers/tasks) | zero linkage mismatches; no callback state leaks |
| Autolog compatibility | downstream (DSPx) | run existing autolog usage without new args | behavior unchanged vs baseline |
| Autolog controls (if PR3 merged) | downstream (DSPx) | run naming/tag/correlation configured scenarios | configured metadata present on runs |
| Post-release signoff | downstream + upstream | confirm local monkeypatch/wrapper removal not required | signoff recorded in issue + release notes |

## 10) Risks

| Risk | Trigger | Mitigation | Rollback |
|---|---|---|---|
| hidden real failures due to quieter logging | over-broad no-op classification | strict expected-vs-unexpected taxonomy tests | revert warning classification patch |
| warning limiter memory/perf pressure | high-cardinality error keys under fault storms | bounded LRU key store + stress tests for key churn | disable limiter path and restore previous warning behavior |
| concurrency regressions | incomplete state migration | staged PR with stress tests | feature-guard path + revert PR2 |
| thread-boundary surprise for users | assumption that callback state auto-propagates across new threads | explicit docs + integration tests across thread executors | document required explicit seeding and keep safe-empty default |
| API acceptance friction | maintainers push back on autolog args | keep PR3 optional and separable | drop PR3 while keeping PR1+PR2 |

## 11) Open questions for maintainers

- Q1: preferred no-op logging policy: fully silent or keep optional debug breadcrumb (default off)?
- Q2: is `contextvars` acceptable as default callback state isolation model?
- Q3: minimal accepted autolog controls set (naming only vs naming+tags+correlation)?
- Q4: is fixed `300s` warning suppression window acceptable as initial upstream default?

## 12) Execution checklist

- [ ] umbrella issue filed with Option B scope and agreed `N*/E*` taxonomy definitions.
- [ ] PR1 merged with all PR1 acceptance criteria satisfied.
- [ ] PR2 merged with stress/concurrency acceptance criteria satisfied.
- [ ] PR3 merged (or explicitly deferred) with rationale documented.
- [ ] §8 matrix wired into CI (unit/integration/stress/regression coverage).
- [ ] release notes/changelog include warning policy + context boundary semantics.
- [ ] RC wheel validated with §9 verification matrix.
- [ ] release version confirmed and linked in umbrella issue.
- [ ] DSPx follow-up compatibility validation done (including monkeypatch removal check).
