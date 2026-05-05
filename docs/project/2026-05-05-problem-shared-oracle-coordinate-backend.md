---
summary: "Problem brief for promoting session-captured shared Oracle backend architecture into the DSPx decision workflow."
read_when:
  - "You need the trigger/problem framing for AK decision #29."
  - "You are deciding why shared Oracle coordinate storage is architecture-significant."
---

# Problem brief — Shared Oracle coordinate backend

- Date: 2026-05-05
- Decision: `#29 Adopt shared Oracle coordinate backend target architecture`
- RFC: `docs/rfc/RFC-DSPX-ORACLE-20260505-shared-coordinate-backend.md`

## Trigger

A session discussion established a production-grade Oracle shape for generated DSPy/cognition programs, but the result stayed in Pi session JSONL instead of the normal RFC/ADR workflow. Later discussion blurred three different states:

1. DS1621 MLflow Postgres + MinIO exists for MLflow tracking and artifacts.
2. DSPx Oracle currently persists explicit local indexes in SQLite `CoordinateIndex` files.
3. A production Oracle target should be a shared, governed behavioral coordinate backend.

The confusion showed that the architecture needed a durable RFC/ADR chain before implementation work continued.

## Problem

DSPx needs production Oracle to become useful as shared behavioral evidence without becoming accidental authority.

The current local Oracle path is correct but incomplete:

- local SQLite indexes are replayable and good for development;
- they are not a team-visible durable behavior memory;
- they do not provide a production substrate for cross-program similarity, drift/territory/frontier analysis, or generated-program activation evidence references.

At the same time, simply pointing Oracle at the existing MLflow Postgres would collapse ownership boundaries:

- MLflow owns run tracking and artifacts;
- Oracle owns behavioral coordinates and empirical interpretation;
- governance/owning domain owns production activation decisions.

## Why this is Tier 1 / architecture-significant

This changes or constrains durable contracts across multiple owner surfaces:

- DSPx storage abstraction and Oracle ingestion semantics;
- DS1621 infra deployment/backup/runbook boundaries if selected as pilot host;
- MLflow/Oracle separation;
- AK/governance non-authority boundary for generated cognition-program activation;
- future CLI/API/UI labels and report semantics.

Therefore the normal decision lifecycle is required: RFC, review memo, ADR, implementation plan, validation/rollout/rollback notes, then scoped execution.
