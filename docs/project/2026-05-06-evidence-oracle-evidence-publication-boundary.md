---
summary: "Evidence note for the Oracle evidence publication boundary decision, documenting current AK authority, program-loop local indexing, and shared Oracle pilot posture."
read_when:
  - "You need evidence for AK decision #30."
  - "You are checking whether shared Oracle publication should copy local coordinates.db files or re-index canonical artifacts."
---

# Evidence note — Oracle evidence publication boundary

- Date: 2026-05-06
- Decision: `#30 Adopt Oracle evidence publication boundary`
- Problem brief: `docs/project/2026-05-06-problem-oracle-evidence-publication-boundary.md`
- RFC: `docs/rfc/RFC-DSPX-ORACLE-20260506-evidence-publication-boundary.md`

## Evidence surface 1 — AK / society.v2.db is the authority substrate

Agent Kernel and `society.v2.db` are the canonical runtime authority substrate where landed. They own tasks, decisions, evidence bindings, transition references, and activation truth.

This is a different workload and authority class from Oracle embeddings, semantic coordinates, similarity search, behavior neighborhoods, and empirical interpretation.

## Evidence surface 2 — Candidate-local Oracle indexes are scratch/local

`program-loop` writes a candidate-local index by default:

```text
<candidate>/oracle/coordinates.db
```

That default is intentional. It allows one-intent dogfooding and interpretation without polluting shared memory or requiring the DS1621 pilot to be available.

The local index is derived from canonical artifacts such as:

- `manifest.json`;
- `manifest.json.meta.json`;
- `behavior_results.json` / `behavior_episode.json`;
- `oracle_evidence.json`;
- `program_oracle_report.json`;
- `program_candidate_state.json`.

Therefore the durable publication source should be those artifacts and hashes, not the local SQLite DB file.

## Evidence surface 3 — Shared Oracle Postgres exists as empirical memory target

The accepted shared coordinate backend ADR already separates Oracle Postgres from MLflow Postgres and from AK/governance authority:

- `docs/adr/20260505-shared-oracle-coordinate-backend.md`
- `docs/rfc/RFC-DSPX-ORACLE-20260505-shared-coordinate-backend.md`

The DS1621 pilot is live but not production-ready. It is useful as an explicit shared backend pilot, not as canonical authority.

## Evidence surface 4 — Winner-only publication is insufficient

Oracle learns behavior space. If only winners are published, shared Oracle memory misses:

- rejected candidates that mark known-bad regions;
- request-more-evidence candidates that mark uncertain frontiers;
- degraded or failed behavior that future candidates should avoid;
- activated and rolled-back candidates that matter for production behavior history.

The publication boundary therefore needs explicit curation labels rather than a simple winner-only migration.

## Evidence surface 5 — Activation authority remains external to Oracle

Generated program activation boundaries are already codified in:

- `docs/project/generated-program-activation-boundary.md`
- governance-kernel generated cognition-program activation passport

Oracle reports, shared records, and local candidate states may support review. They do not approve rollout. Activation still requires owning-domain/governing-body decision, canonical binding, rollout owner, and rollback plan.

## Conclusion

The evidence supports a curated publication model: future shared publication should re-index canonical DSPx artifacts into shared Oracle Postgres with provenance, curation labels, redaction status, idempotency keys, and non-authority flags. It should not copy candidate-local `coordinates.db` wholesale and should not make Oracle Postgres a second `society.v2.db`.
