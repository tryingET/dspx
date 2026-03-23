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
| [20260322-provider-runtime-v4.md](20260322-provider-runtime-v4.md) | Provider runtime v4 is the local mixed-provider unblock path | Accepted | Keeps template-adapter optional while shipping explicit `vllm-local` + `dspy-lm-auth` provider workflows. |
| [20260322-synthesis-architecture-v7-v9.md](20260322-synthesis-architecture-v7-v9.md) | Synthesis architecture targets V7 operational delivery on a V9-compatible core | Accepted | Defines the repo's dated references for V7/V8/V9 and the implementation posture to architect for V9 while shipping V7 first. |
| [20260323-synthesis-evidence-retrieval-v1.md](20260323-synthesis-evidence-retrieval-v1.md) | Synthesis evidence retrieval contract v1 | Accepted | Freezes the first SG2 evidence bundle: exact-match module-gen receipts, replay health, then Oracle neighbors. |
