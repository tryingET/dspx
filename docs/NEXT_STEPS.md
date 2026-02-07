---
summary: "Legacy roadmap snapshot; canonical actionable roadmap lives at repo root."
read_when:
  - "You are investigating historical roadmap context or old phase naming."
  - "You need to compare legacy roadmap wording against root NEXT_STEPS.md."
---

Next Steps (Prioritized)
=======================

**Note:** This file is legacy; the canonical roadmap is `NEXT_STEPS.md` at the repo root.

Phase A — Mermaid → DSPy hardening
----------------------------------
- [ ] Subgraph selection: run a named phase from a full diagram.
- [ ] Edge chains: parse `A --> B --> C` and subgraphs robustly.
- [ ] Decision routing: constrain to explicit outgoing edge labels.
- [ ] React variant: real tools wiring + safety guards (timeboxed actions).
- [ ] Provenance: persist per-node JSON (inputs, outputs, pattern, runtime, errors).

Phase B — Intent capture and context
-----------------------------------
- [ ] Discord bot: live intent acceptance on reaction/phrase; produce transcript.
- [ ] Runner hook: replace transcript-file stub with bot/webhook ingestion.
- [ ] Stronger repo context: static analysis (APIs, deps, tests), code graph sketch.
- [ ] KB/Ontology: optional SPARQL endpoint support; semantic matches by intent.

Phase C — 6E pipeline and storage
---------------------------------
- [ ] SQLAlchemy + Postgres support with migrations and retries.
- [ ] Idempotency: hash source inputs; upsert/dedupe 6E rows.
- [ ] Export: write 6E JSON artifacts per node; link from MLflow.
- [ ] Validation: lint 6E (required fields; short/concise; no placeholders).

Phase D — CLARITY modules
-------------------------
- [ ] Enforce lexicographic gating (block on constraint violations).
- [ ] Add tools only at Intervene; reversible actions preference.
- [ ] Persist CLARITY provenance table; MLflow artifacts for traces.

Phase E — Tests and CI
----------------------
- [ ] Unit tests: parser (Mermaid), context tools, SixE modules, SQL store.
- [ ] Golden tests: generated programs compile and run on stubs.
- [ ] E2E: Phase 1 run uses transcript stub; asserts SQL row created.
- [ ] CI: lint, unit, and e2e matrix (skip network where needed).

Phase F — Docs and UX
---------------------
- [ ] README: “Phase 1 capture” quickstart with `DISCORD_TRANSCRIPT`.
- [ ] Docs: architecture (generator, runtime hooks, patterns).
- [ ] CLI ergonomics: `--phase`, `--variants`, `--out`, `--dry-run`.
 - [ ] Config behavior: document discovery order (DSPX_CONFIG → nearest config.toml via walk-up).
 - [ ] Observability: print resolved config path and effective MLflow URI/experiment at startup.
 - [ ] Metrics & tags: standardize MLflow params/metrics/tags (lm_model, lm_auto, lm_bypass, issues_count, durations).
 - [ ] Tech stack: keep lane docs in `tech-stack-core`; maintain repo deltas in `docs/tech-stack.local.md` (FastAPI/Granian + policy defaults).

Phase G — Provider Instrumentation
----------------------------------
- [x] Make verbose LM logging configurable per provider; document
  `DSPX_CODEX_VERBOSE` (also `DSPX_CLAUDE_VERBOSE`, `DSPX_GEMINI_VERBOSE`).
- [x] Expose LM call history in a common interface (durations, exit
  codes, snippets) via `history` lists.
- [ ] Optional: stream last-agent-message while `codex exec` runs
  (TTY-friendly UI hook).

Phase H — Consensus Reducer (Multi‑Provider)
--------------------------------------------
Goal: Choose the “best” answer when running multiple providers concurrently, with tunable strategies (heuristics or LLM‑as‑judge), and first‑pass early abort.

Design
- Reducer interface: pluggable reducer for MultiProviderLM.
  - `class Reducer: def score(self, result, context) -> float|bool|dict; def pick(self, results, context) -> {winner, scores, meta}`
  - Context includes: prompt/messages, provider name, timings, validation flags, task type hints.
- Strategies:
  - HeuristicReducer: length, keyword coverage, regex match, JSON parse success, schema keys, toxicity filters.
  - ValidatorReducer: wraps existing validators; pass/fail + tie‑break (e.g., shortest valid, fastest valid).
  - JudgeReducer (LLM‑as‑judge): ask a judge model to rate candidates; configurable judge LM (can be one of providers, a separate API, or local).
  - Self‑consistency: prompt variants to each provider and vote across samples; optional due to cost.
  - Weighted voting: per‑provider weights by historical quality/cost/latency.
- Termination rules:
  - Early stop when a candidate exceeds threshold (2c), abort others.
  - Or time‑budget: wait `T` ms then pick highest score.
  - Or min‑k: wait for k candidates or timeout, then pick.
- Isolation interplay:
  - Shared workspace: prefer read‑only or idempotent tasks.
  - Git worktrees: safe for code‑editing; reducer should store chosen patch only.
  - Database capture: persist all candidates even when not chosen; reducer records provenance and rationale.

API sketch
```
class ReduceResult:
    winner_index: int
    scores: dict[str, float]
    rationale: str | None
    threshold_passed: bool

class Reducer(Protocol):
    def prepare(self, context: dict) -> None: ...  # e.g., warm judge LM
    def score(self, text: str, meta: dict, context: dict) -> float: ...
    def pick(self, candidates: list[dict], context: dict) -> ReduceResult: ...

# Integrate into MultiProviderLM
MultiProviderLM(..., reducer: Reducer | None = None, reduce_timeout_ms: int | None = None)
```

MLflow
- Log reducer details: `reducer.strategy`, `reducer.threshold`, `winner`, `scores.{provider}`.
- Artifacts: `candidates/<provider>.txt`, `reducer/rationale.txt`, `reducer/config.json`.
- Tags: `providers`, `strategy`, `isolation_mode`, `winner`, `validated=1/0`.

Implementation plan
1) [x] Interface: add optional `reducer` and `reduce_timeout_ms` to
   `MultiProviderLM`.
2) [x] HeuristicReducer: implements keyword/regex/json heuristics +
   simple tie‑breakers.
3) [ ] JudgeReducer: configurable judge LM (Claude/Codex/OpenAI);
   prompt templates for scoring and pairwise comparisons.
4) [ ] Wiring: in `parallel_first`, route finished candidates to the
   reducer; add threshold/time‑budget/min‑k policies.
5) [x] CLI: extend `dspx-multi-demo` with `--reducer
   {none,heuristic,judge}` and options.
6) [~] MLflow: log reducer scores/artifacts; `winner` tag present;
   add `scores` and candidate artifacts next.
7) [ ] Docs: examples + guidance (safety, side‑effects, cost,
   reproducibility).

Open questions
- Judge neutrality: avoid using a candidate provider as its own judge by default; allow explicit judge selection.
- Score calibration: normalize across tasks; allow per‑task schema/metric hooks.
- Cost control: limit candidates (k‑best by validator) before invoking judge.

Phase I — CI & Release
----------------------
- [ ] GitHub Actions: lint (ruff), typecheck (ty on src), build (uv).
- [ ] Publish on tag: build & upload to PyPI (uv publish) with token.
- [ ] Cache uv and Python for fast CI.

Phase J — Typing and Lint
-------------------------
- [ ] Resolve remaining ty issues in project code (Optional/Union,
  container types in multi‑provider and mermaid helpers).
- [ ] Decide which ty warnings to fix vs ignore; enforce `uvx ty check src --error-on-warning` in CI and `just typecheck`.
- [ ] Replace “mypy happy” comments / stale `type: ignore` with ty-friendly typing (reduce noise).
- [ ] Add type stubs for third‑party libs as needed (e.g., pandas‑stubs,
  types‑beautifulsoup4).
- [ ] Gradually enable stricter ty rules once baseline is clean.
