---
summary: "ADR index and conventions for architecture decision records."
read_when:
  - "You are making a durable architecture or runtime decision."
  - "You need prior decision context before changing providers, policy, or contracts."
---

Architecture Decision Records (ADRs)
====================================

Purpose
-------
ADRs capture durable architecture decisions with enough context to explain *why* a path was chosen and what tradeoffs were accepted.

Naming convention
-----------------
- File name: `YYYYMMDD-short-title.md`
- Example: `20260206-pi-rpc-provider.md`

Required template fields
------------------------
Each ADR should include these sections:
- `Context`
- `Decision`
- `Consequences`
- `Status` (e.g., Proposed, Accepted, Superseded)

Index
-----

| ADR | Title | Status | Notes |
| --- | --- | --- | --- |
| [20260206-pi-rpc-provider.md](20260206-pi-rpc-provider.md) | Pi provider runtime uses persistent RPC process | Accepted | Provider-first integration; avoids shelling out one-shot per LM call. |
| TBD | Placeholder for next durable architecture decision | Proposed | Add when next cross-cutting decision is made. |
