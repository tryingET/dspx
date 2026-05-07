---
summary: "Problem brief for the Oracle evidence publication boundary decision, separating AK authority, candidate-local Oracle scratch indexes, and shared Oracle empirical memory."
read_when:
  - "You need the trigger/problem framing for AK decision #30."
  - "You are deciding why local CoordinateIndex, shared Oracle Postgres, and society.v2.db must stay separate."
---

# Problem brief — Oracle evidence publication boundary

- Date: 2026-05-06
- Decision: `#30 Adopt Oracle evidence publication boundary`
- RFC: `docs/rfc/RFC-DSPX-ORACLE-20260506-evidence-publication-boundary.md`

## Trigger

After `program-loop` introduced a candidate-local Oracle index and the DS1621 Oracle Postgres pilot existed as a shared pgvector target, operator discussion exposed a new ambiguity:

```text
Should winning candidates transition their local coordinates.db into shared Postgres?
Does a dedicated Oracle Postgres DB duplicate society.v2.db / Agent Kernel authority?
```

The ambiguity matters because DSPx now has:

1. `society.v2.db` / Agent Kernel for canonical authority;
2. candidate-local `coordinates.db` files for scratch Oracle interpretation;
3. a DS1621 shared Oracle Postgres/pgvector pilot for future shared empirical memory.

Without an explicit boundary, the implementation path could incorrectly copy local cache DBs wholesale or let Oracle Postgres become a second authority database.

## Problem

DSPx needs a shared Oracle memory for curated behavioral evidence, but shared Oracle must remain empirical.

The risky shortcuts are:

- treating shared Oracle Postgres as authority because it is central and durable;
- publishing only winners, which creates survivor bias;
- copying local SQLite `coordinates.db` files into Postgres, which treats a scratch cache as source truth;
- losing provenance, redaction status, publication labels, or AK/governance references.

## Why this is architecture-significant

This decision constrains durable boundaries across:

- DSPx `program-loop` defaults and future publish commands;
- shared Oracle Postgres schema and idempotency semantics;
- Agent Kernel / `society.v2.db` authority boundaries;
- governance-kernel production activation semantics;
- DS1621 backup/retention and operational expectations.

Therefore the RFC must go through structured review, ADR recording, implementation planning, and validation/rollout/rollback notes before any publish/shared-ingest implementation proceeds.
