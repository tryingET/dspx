---
summary: "Decision 105 learning closure: attest only directly mediated effects, preserve ambiguity, and close post-ADR work through durable owner evidence."
read_when:
  - "Designing execution-attempt custody or evidence claims in DSPx."
  - "Closing an architecture decision after implementation and an exact-byte acceptance gate."
type: "learning"
decision_id: 105
closure_task_id: 4621
---

# Bounded semantic-evaluation execution custody

## Context

Decision 105 introduced a DSPx-local execution-attempt lifecycle for synthetic, no-network semantic-evaluation evidence. The work had to preserve owner boundaries while proving crash recovery, atomic closure, replay lineage, projection eligibility, canonical bytes, and store safety. It deliberately did not activate runtime or CLI paths or claim ROCS, publication, governance, or production authority.

## Discovery

Three lessons survived implementation and strict review.

1. **Attestation must stop at the mediation boundary.** DSPx can attest durable start, local writes, and return or failure observed at its callable boundary. It cannot infer provider-side cardinality, process cleanup, network isolation, executed model identity, semantic correctness, or governance from hashes or receipts.
2. **Ambiguity is evidence, not a retry instruction.** Unknown outcomes after durable start must become terminal `indeterminate`. Recovery cannot rerun the same attempt or manufacture a success receipt; replay needs a fresh attempt with explicit source lineage.
3. **Implementation acceptance is not lifecycle closure.** Green tests, canonical Git integration, and even an accepted projection-byte task do not close the decision. Historical acceptance evidence must be dated, repository-durable, attributed to the actual reviewers and accepting controller, attached through the AK owner surface, and followed by explicit KES-style learning closure.

## Evidence

- AK Decision `105`: accepted ADR and owner lifecycle record.
- ADR: `docs/adr/20260803-bounded-semantic-evaluation-execution-custody-v1.md`.
- Implementation commit/tree: `cc6c80678482e0ff46cd4252f4bd5cebfe78bab1` / `ab35a0844aa3892eff76100038ebb693da44e832`.
- Implementation task `4607`: `accepted_and_integrated` after four unanimous review lanes.
- Exact projection-byte gate task `4614`: `accepted_and_canonical`.
- Dated gate record: `docs/project/2026-08-03-semantic-evaluation-execution-custody-v1-projection-byte-acceptance.md`.
- Durable accepted manifest: `docs/project/2026-08-03-semantic-evaluation-execution-custody-v1-verification-manifest.json`.
- Accepted projection SHA-256: `43cb523b3787726956f331ea0917fd55757cf317a13815cd6f0f97c8b9eb7206` over exactly 1810 bytes.
- Rejected implementation commits `dd83cce93d4254581b7a25efb4fbcf6affaf9660` and `698c6211f47681d003f1604773f2cdb5c11ee4c0` remain negative evidence.

## Application

Use this pattern for future owner-local execution evidence:

- define the observable effect inventory before APIs;
- persist start before any potentially external call;
- use terminal ambiguity instead of same-attempt retry;
- atomically bind outcome, evidence, receipt, trace, and terminal state;
- expose cross-owner bytes only from explicitly eligible sealed terminals;
- review code identity and exact projection identity separately;
- keep event records dated and durable;
- verify the AK decision passport and attach `kes_learning` before saying the lifecycle is complete.

This learning does not authorize Decision 106, Decision 107, runtime wiring, provider or network use, publication, adoption, promotion, or production activation.

## TIP Candidate

Yes, after one additional owner-local custody implementation confirms the same pattern. The likely reusable TIP is: **separate mediated-effect implementation acceptance, immutable cross-owner byte acceptance, and owner-recorded lifecycle learning closure; none implies the next.**
