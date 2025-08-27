Next Steps (Prioritized)
=======================

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
