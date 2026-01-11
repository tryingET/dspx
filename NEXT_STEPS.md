# Next Steps

This document tracks actionable next steps aligned with the phased plan
in `docs/VISION.md`. Phases 1–6 are complete; below focuses on upcoming
work and refinements.

## Forge (ai-society multi-project GitLab backlog compiler) — now

Canonical spec: `docs/FORGE.md` (v0 Contract + v0 Design).

- Implement `dspx forge` MVP (issues-first)
  - `forge intake` (sanitize → multi-choice clarifier → canonical WorkOrder)
  - `forge route` (auto-route top-3 + override; multi-project allowlist)
  - `forge plan` (capabilities: implemented/configured/permitted + gap report)
  - `forge overlaps` (heuristic overlap candidates + resolutions saved)
  - `forge issues apply` (manifest-first; idempotent create/update; managed-block updates only)
  - `forge issues close-duplicates` (explicitly gated; operates only on marked duplicates)
- GitLab integration (self-hosted; multi-project routing)
  - Env-only token: `DSPX_GITLAB_TOKEN`
  - Project map: `DSPX_GITLAB_PROJECT_MAP_JSON` / `DSPX_GITLAB_PROJECT_MAP_FILE`
  - Blast-radius: `DSPX_GITLAB_ALLOWED_PROJECT_KEYS`
  - Host allowlist: `DSPX_GITLAB_ALLOWED_HOSTS` (defaults to host in base URL)
  - Issue links: use GitLab issue-links API when available; fallback to markdown refs
- Determinism + safety invariants (tests)
  - Stable `workorder_fingerprint` and IssueSpec `fingerprint`
  - Dry-run default; explicit apply requires policy gates
  - Managed-block updates preserve human edits
  - 401/404/429 behavior and token redaction tests (MockTransport)
- 4D discipline
  - Always emit `system_definition_card.md` per WorkOrder and reference it in issue managed blocks

## Publish (CLI-first toolkit) — near-term checklist

- Default provider posture: keep default `DSPX_PROVIDER=codex-exec`; document `DSPX_PROVIDER=openrouter` as opt-in; keep tests offline/deterministic by default (forced `DSPX_PROVIDER=stub`, `MLFLOW_ENABLE=0`).
- Ensure OpenRouter + 1Password DX is crisp:
  - `cp .env.example .env` (git-ignored), set `OPENROUTER_API_KEY=op://...`.
  - `just openrouter-whoami` (requires `op`; does not require `.env`).
  - `just or-codegen ...`, `just or-codegen-timed ...` (use `.env` + `op run`).
- GEPA on Codex: validate the “optimize loop” UX end-to-end with your own program:
  - `dspx optimize gepa --program prog.py --train train.csv --out optimized/ --max-metric-calls 20`
  - Prefer explicit IO/weights for reproducibility: `--input ... --output-key ... --output-weight key=1.0`.
  - Ensure the saved `optimized/manifest.json` matches what you expect for CI auditability (includes DSPx version + Python environment).
- MLflow observability: follow and execute `docs/MLFLOW_OBSERVABILITY_PLAN.md` (fix tracking URI semantics, run lifecycle, and CI-safe toggles).
  - Added smoke: `just mlflow-smoke-signature-refine` (creates `signature-refine` run in local file store and asserts tags/artifacts).
  - Optional: enable nested runs for workflows with `DSPX_MLFLOW_NESTED_RUNS=1` (current: Mermaid sig-per-node).
- Confirm `signature refine` parity: run once with `MLFLOW_ENABLE=1` and verify it produces a `signature-refine` run with standard tags and artifacts (and stays no-op when disabled).
  - Shortcut: `just mlflow-smoke-signature-refine`.
- Docs sweep: README quickstart uses the same “.env + just” flow; SERVER.md clarifies `127.0.0.1` vs `0.0.0.0` for Docker/NAS; docs mention optional `/metrics` (`DSPX_METRICS_ENABLED=1`).
  - Keep `docs/TUTORIAL_E2E.md` and `docker-compose.yml` consistent on MLflow port/URI semantics.
- Release hygiene: bump version, `just release new=x.y.z`, tag, publish.

## Phase 7 — Adapter Registry (datasets/eval/stores)

Status: DONE (MVP+)

- Implemented
  - `dspx/adapters/{datasets,stores,eval}.py` with lightweight interfaces.
  - CSV/Parquet loader, MLflow dataset reference, simple metrics (accuracy/F1).
  - Local object store for examples/tests.
  - Adapters CLI: `dspx adapters list`, `dspx adapters dataset describe`.
  - Unit tests with small fixtures, no network.

- Acceptance
  - Adapters usable by services and optimizers; tests deterministic.

- Next
  - DONE: dataset split helpers + CLI (`adapters dataset split`).
  - DONE: eval metrics (confusion matrix, ROUGE‑1 F1, BLEU‑1) and eval CLI
    (`adapters eval run`, `adapters eval run2`).
  - DONE: stratified splits by label and optional group‑aware splitting (CLI flags, tests).
  - DONE: macro/micro averaging for ROUGE/BLEU (CLI `--average`).
  - DONE: ROC‑AUC and per‑class precision/recall (CLI `--metric` selections, tests).
  - DONE: stratified multi‑class group‑balancing options for splits; CLI
    `--group-balance` with `instances|groups` and deterministic tests.
  - DONE: optional min‑count constraints for labels/partitions (CLI `--min-per-label`).
  - DONE: PR curve utilities (`pr_curve`) and calibration metrics (ECE via `ece`).
  - Next: additional text metrics (e.g., BERTScore), per‑class ROC/PR summaries, and
    export helpers for plotting.

## Phase 8 — Server API (optional)

Status: DONE (MVP+)

- Implemented
  - `dspx-server` (FastAPI) for `/signature`, `/module`, `/mermaid` served via Granian.
  - Request/response DTOs; ASGI tests using TestClient.
  - Bearer auth (env tokens or file; optional); standardized JSON 401 errors.
  - Rate limiting (per‑identity and global; per‑path overrides); 429 JSON errors.
  - Trusted proxies (CIDR) for X‑Forwarded‑For handling.
  - Structured request logging; lightweight counters; docs at `docs/SERVER.md`.
  - Developer DX: Just recipes for server lifecycle:
    `start` (bounded timeout, default 3s), `start-timed` (explicit
    short run), `start-forever` (no timeout), `stop` (kill listeners).
    Default bind host/port: `127.0.0.1:33213` to avoid Granian
    "invalid IP address syntax" seen with `localhost` on some systems.

- Next
  - Distributed rate limiting backend (optional) for multi‑worker deployments.
  - Integrate Prometheus properly (optional) or expose more detailed metrics (still guarded by env).
  - DTO polish and request metadata tagging for MLflow when enabled.
  - Harden logging config guidance; example JSON formatter setup.

## Phase 9 — Policy, Safety, Sandboxing

Goal: strengthen policy for tool/provider gating and isolation.

- Deliverables
  - Policy engine for tool/provider allow/deny with budgets/timeouts. (IN PROGRESS)
  - Optional isolated worktrees for code-exec; explicit destructive prompts. (PARTIAL)
  - CLI flags and config propagation. (DONE)
  - Tracing: ensure dspy spans attach to active named runs; stable run naming in CLI.

- Implemented
  - Tool & provider gating via env (allow/deny) with root CLI flags:
    `--allowed-tools`, `--disallowed-tools`, `--allowed-providers`, `--disallowed-providers`,
    `--max-timeout`, `--allow-network-mutate`, `--allowed-http-methods`, `--disallowed-http-methods`.
  - Tools wrapped with policy checks and timeout clamp; providers gated on creation.
  - OpenAPI caller respects method allow/deny and (optionally enforced) mutation guard.
  - Optional sandbox worktree for Codex Exec (`DSPX_SANDBOX_WORKTREE=1`).
  - Per‑service budgets (env or CLI `--budget-ms`) recorded in MLflow: `service.budget_ms` tag,
    metrics `service.duration_ms`, `service.budget_exceeded`.
  - Tracing improvements: `mlflow.dspy.autolog` configured not to create runs (attach to active);
    CLI starts named runs early and refines names; added duration metrics to mermaid and non‑DTO signature paths.
  - Host allowlists for web tools (fetch/scrape) with CLI integration:
    `dspx tools web fetch|scrape` now accepts `--allow-host <host>` and enforces per-call
    host allowlists. Added tests for allowed/denied hosts using httpx MockTransport.
  - Destructive‑op confirmation in CLI for mutating OpenAPI/tools (unless bypassed by policy or `--yes`).
  - Generic capability category gating for tools via registry wrapper and `_dspx_capabilities`/descriptors
    (e.g., `network.mutate`, `filesystem.write`, `code.exec`).
  - Dry‑run support with redacted previews: `tools openapi call --dry-run`, `tools run --dry-run`.
  - Redaction hardening: URL userinfo, Cookie/Set-Cookie, token/key/secret/password headers redacted
    in logs/previews where applicable.
  - Server‑side confirmation gate for mutating endpoints: if `DSPX_CONFIRM_MUTATIONS=1`, `/mermaid` requires
    `X-DSPX-Confirm: 1`.
  - Tool descriptors and typed OpenAPI ops introduced: registry now exposes `available_descriptors()`/`get_descriptor()`;
    CLIs (`tools list|search|describe`) consume descriptor metadata for consistent output.
  - MLflow: `MLFLOW_ENABLE=0` is now a hard-disable (no `mlflow` import/calls); no default HTTP tracking URI fallback; added regression test to prevent silent network retries in CI.
  - OpenRouter provider (OpenAI-style chat completions) plus Just recipes and `.env.example` to run via `op run` without secrets in CLI flags; opt-in live test gated by env.
  - GEPA optimization runner (`dspx optimize gepa`) using Codex Exec by default, with explicit IO, metrics (`exact|contains|f1`), per-output weights, optional output normalization hooks, and optional split reflection provider. Saved outputs include a manifest and copied program source for auditability; opt-in live Codex smoke test gated by `DSPX_RUN_LIVE_TESTS=1`.
  - Signature refine MLflow parity (standard tags, stable run name, params/artifacts/metrics guarded by active runs).

- Next
  - Stronger sandbox isolation options for code‑exec providers (env allowlist, RO mounts).
  - Capability gating hooks in providers for `code.exec` capability categories.
  - Optional parent/child nested runs (workflow → service) for hierarchical trace views (started; expand beyond Mermaid sig-per-node).
  - Unify descriptor usage across any remaining tool paths and further reduce ad‑hoc function introspection.
  - Expand server tooling endpoints (optional) using descriptors + confirmation helper.
  - Module artifacts for optimization: DONE — `module-gen` emits `build_student()` + `io_spec()` + `output_weights()`/`normalize_output()` stubs by default; see `docs/GEPA_FROM_MODULE_GEN.md`.

- Acceptance
  - Policies enforced across tools/providers; deny/allow and mutation tests pass;
    budgets visible in MLflow runs under configured experiment.

## Phase 10 — Plugins & Extension Points

Goal: enable third-party providers/tools/generators via entry points.

- Deliverables
  - Plugin registry + discovery; example plugin + docs.

- Acceptance
  - Plugins loadable and testable; documentation covers lifecycle.

## Refinements (Near-term 80/20)

- OpenAPI: now includes `ops --tags` and `ops --json`, `describe --json` with response schema summaries;
  added validation for enums/arrays/nested objects plus local `$ref` + shallow `allOf` merge, and basic bounds (`minLength`, `pattern`, `minimum/maximum`). Also supports `additionalProperties`, `nullable`, `multipleOf`, and `const`. Next: widen coverage for more schema constraints and response schemas.
- OpenRouter: keep the “.env + just” path first-class; `dspx providers smoke` exists to quickly validate provider wiring and print metadata.
- MLflow: standardized tags (`service`, `template_version`, `provider`) and artifacts/manifests attached;
  run naming (`signature-*`, `module-*`, `codegen-*`, `mermaid-*`), grouping via `DSPX_RUN_GROUP` (now exported by the `bench-mlflow` recipe);
  per‑service budgets (`--budget-ms`) with `service.duration_ms` and `service.budget_exceeded`;
  dspy autolog attached to active named runs. Mermaid SIG now uses `ensure_run_with_standard_tags(...)` so `run_group` is applied consistently. Next: optional parent run per bench/workflow and aggregate per‑workflow budgets and summary artifacts.
- Templates: expand module/codegen templates (multi‑output, additional languages).
- Caching: `--no-cache`, `--cache-info` shipped; meta includes cache key/file. Added
  `dspx cache` subcommands (info/list/show/clear). Next: size summaries by kind and
  selective pruning by age/size.
- Docs: added end‑to‑end tutorial (`docs/TUTORIAL_E2E.md`) showing Mermaid + OpenAPI + CSV adapters.
  Next: extend with runnable OpenAPI node example and adapters split/eval examples.
  Added: server docs (`docs/SERVER.md`) and quickstart in README.
  Added: `example.toml`; `config.toml` is git‑ignored and discovered automatically.
  Mermaid example updated to a pedagogical workflow (Unterrichtsstörungen, DE).
- Tools UX: `tools list --json` (capabilities/description/OpenAPI), `tools describe --json --examples`,
  `tools search --tags --json`, `tools run --dry-run`, and `tools openapi call --dry-run`.
  Next: unify renderers across all CLIs and expand docs with examples.
- Adapters: `adapters list` shows descriptions; `adapters dataset split` supports `--dry-run` preview.

## DX Notes (Updated)

- Justfile now runs all CLIs from source using `uv run -m dspx.cli.<module>`, removing the requirement to install console scripts via `uvx`/`uv tool install`. If you prefer global‑ish commands, you can still run `just tool-install` and call `uvx dspx-*` manually.
- Server helpers in Justfile:
  - `just start` → bounded timeout (default 3s) for quick smoke runs.
  - `just start N [host] [port]` → run for N seconds at host:port.
  - `just start-forever` → long‑running server, no timeout.
  - `just stop [port]` → best‑effort kill of port listeners.
  Default: `127.0.0.1:33213`.
- `bench-mlflow` sets and exports `DSPX_RUN_GROUP` and ensures `MLFLOW_ENABLE=1` by default, so MLflow runs are grouped and visible when a tracking server is reachable (use `just mlflow-up`).
- Some provider-backed demos (e.g., Claude/Gemini) require their respective CLIs and credentials; failures will surface as non‑zero rc in bench output.

## Day-to-Day Checklist

 - Run `just test` before and after changes; target ~<12s locally.
- Keep docs in sync (VISION/ARCHITECTURE/NEXT_STEPS) with major changes.
- Prefer small, scoped PRs per phase/sub-phase; include acceptance notes.

## Test Warnings

The previous MLflow/protobuf DeprecationWarning for `label()` is now suppressed at test time
via `pyproject.toml` under `[tool.pytest.ini_options].filterwarnings`. Test runs are warning-free.
