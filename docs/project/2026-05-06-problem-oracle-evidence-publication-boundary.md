---
summary: "Problem brief for the Oracle evidence publication boundary decision, separating AK authority, candidate-local Oracle scratch indexes, and shared Oracle empirical memory."
read_when:
  - "You need the trigger/problem framing for AK decision #31."
  - "You are deciding why local CoordinateIndex, shared Oracle Postgres, and society.v2.db must stay separate."
---

# Problem brief — Oracle evidence publication boundary

- Date: 2026-05-06
- Decision: `#31 Review Oracle evidence publication boundary from initial RFC`
- RFC: `docs/rfc/RFC-DSPX-ORACLE-20260506-evidence-publication-boundary.md`

## Trigger

After `program-loop` introduced a candidate-local Oracle index and the DS1621 Oracle Postgres/pgvector pilot existed as a shared target, operator discussion exposed a durable ambiguity:

```text
Should winning candidates transition their local coordinates.db into shared Postgres?
Does a dedicated Oracle Postgres DB duplicate society.v2.db / Agent Kernel authority?
```

DSPx now has three database-like surfaces:

1. `society.v2.db` / Agent Kernel for canonical authority;
2. candidate-local `coordinates.db` files for scratch Oracle interpretation;
3. DS1621 shared Oracle Postgres/pgvector pilot for future shared empirical memory.

Without an explicit boundary, implementation could incorrectly copy local cache DBs wholesale or let Oracle Postgres become a second authority database.

## Problem

DSPx needs shared Oracle memory for curated behavioral evidence, but shared Oracle must remain empirical.

The risky shortcuts are:

- treating shared Oracle Postgres as authority because it is central and durable;
- publishing only winners, which creates survivor bias;
- copying local SQLite `coordinates.db` files into Postgres, which treats a scratch cache as source truth;
- publishing sensitive generated-program evidence without explicit publisher custody, redaction status, retention class, or retraction posture;
- letting authority-shaped labels such as `activated` appear without canonical AK/governance/domain refs.

## Why this is architecture-significant

This decision constrains durable boundaries across:

- DSPx `program-loop` defaults and future publish commands;
- shared Oracle Postgres schema and idempotency semantics;
- Agent Kernel / `society.v2.db` authority boundaries;
- governance-kernel production activation semantics;
- DS1621 backup/retention and operational expectations;
- future evidence publication, redaction, and retraction behavior.

Therefore the revised RFC went through adversarial review, revision, re-review, and now ADR recording before any publication implementation proceeds.
