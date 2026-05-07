---
summary: "Many-of-the-greats review attempt for the Oracle evidence publication boundary RFC, concluding the RFC needs revision before ADR."
read_when:
  - "You are reviewing the Oracle evidence publication boundary RFC."
  - "You need the adversarial review closure for AK decision #31."
  - "You need to know why the first RFC draft should be revised before ADR."
---

# Many-of-the-greats review — Oracle evidence publication boundary RFC

- Date: 2026-05-06
- Decision: `#31 Review Oracle evidence publication boundary from initial RFC`
- Reviewed artifact: `docs/rfc/RFC-DSPX-ORACLE-20260506-evidence-publication-boundary.md`
- Review prompt: `/home/tryinget/.pi/agent/prompts/many-of-the-greats.md`
- Review outcome: `revise_rfc`
- Legal next move: revise the RFC, then run a new review attempt against the revised RFC. Do not record an ADR yet.

## QUESTION

What is the correct architecture for moving DSPx Oracle-readable candidate evidence from local candidate work into shared Oracle Postgres without making Oracle a second authority database, copying scratch indexes as truth, or destroying the empirical value of failures and near-misses?

## MODE 1 — MANY OF THE GREATS

### School 1: Authority Monism

- Core claim: There must be one canonical authority substrate. If shared Oracle stores anything that looks like decisions, activation state, or winner labels, it will become an uncontrolled second authority DB.
- Premises:
  - Authority drift happens through convenience, not explicit coup.
  - Operators trust central durable stores more than local sidecars.
  - A queryable shared DB with labels such as `activated` or `promote_decision_recorded` can become normative even when docs say it is not.
- Strongest case:
  - `society.v2.db` / AK already exists for tasks, decisions, evidence bindings, transition refs, and activation truth. Any durable state adjacent to promotion must point back to that authority or remain clearly non-authoritative.
  - Oracle should not store activation truth; at most it should store immutable evidence hashes and opaque authority refs.
  - The RFC is directionally right, but its labels risk smuggling authority language into an empirical store.
- What it sees that others miss:
  - The biggest risk is not technical duplication. It is semantic duplication: shared Oracle records becoming the thing operators read as truth because they are faster and more legible than AK/governance records.

### School 2: Empirical Memory Realism

- Core claim: Oracle is useless as shared intelligence if it only mirrors winners or approved artifacts. A behavioral memory must retain failures, near-misses, uncertain frontiers, and rollbacks.
- Premises:
  - Behavioral learning depends on negative space.
  - Similarity search is only as good as the distribution it sees.
  - Local scratch indexes are not enough for longitudinal or cross-program intelligence.
- Strongest case:
  - Shared Oracle needs a dedicated empirical DB because vector/search workload and retention differ fundamentally from authority workflow state.
  - Publishing only winners creates survivor bias and makes future candidates overfit to known successes while forgetting known-bad regions.
  - The RFC correctly chooses curated artifact re-indexing over local DB migration.
- What it sees that others miss:
  - Over-fearing authority drift can sterilize Oracle into a useless archive. Shared Oracle must contain rejected and degraded evidence if it is to explain behavior space.

### School 3: Artifact Provenance Purism

- Core claim: Local `coordinates.db` is an implementation cache. The only legitimate publication source is canonical artifacts plus stable hashes and identities.
- Premises:
  - Caches are lossy, local, and policy-poor.
  - Durable records need reproducible lineage.
  - Publication must be reconstructable from source artifacts.
- Strongest case:
  - Re-indexing `oracle_evidence.json`, manifest, receipts, and sidecars preserves source truth and avoids coupling the shared schema to a local SQLite layout.
  - The RFC is correct to reject wholesale migration.
  - Idempotency must key on evidence identity, artifact hashes, label/event semantics, and optional authority refs.
- What it sees that others miss:
  - The shared DB should not inherit the accidental structure of whatever local index existed when the candidate was generated.

### School 4: Data Stewardship / Retention Skepticism

- Core claim: The RFC is not safe for ADR until it defines who may publish, what redaction means, and how retraction/deletion/retention work.
- Premises:
  - Generated program evidence may contain user data, task data, provider outputs, and sensitive behavioral traces.
  - Shared publication is a data-governance act, not just a vector-ingest act.
  - Operator-declared `redaction_status=checked` is too weak without at least a preflight contract.
- Strongest case:
  - The RFC requires redaction status but does not define legal values, minimum checks, publisher identity, custody, or retention class.
  - It says useful failures should be retained, but failures can be more sensitive than wins because they expose prompts, data gaps, and internal evaluation material.
  - Shared Oracle publication increases DS1621 backup/retention obligations; the RFC should say the first implementation is preflight-only and should fail closed on redaction uncertainty.
- What it sees that others miss:
  - The publication boundary is also a data boundary. Without redaction and retraction semantics, the architecture is under-specified.

### School 5: Product-Loop Pragmatism

- Core claim: `program-loop` must remain simple and useful; shared publication should become a clear opt-in path, not a maze of governance ceremony.
- Premises:
  - If the path is too hard, operators will invent ad-hoc exports.
  - Local-first loops are the product spine.
  - A good CLI can encode safety without making every user understand the whole governance stack.
- Strongest case:
  - Candidate-local index by default is correct.
  - A future `publish-preflight` and later `publish` command should make the safe path easier than copying files manually.
  - The RFC should not overfit to final authority mechanics before shipping a local preflight packet.
- What it sees that others miss:
  - Safety that is not ergonomic will be bypassed. The RFC must define the next shippable slice tightly enough to implement.

## MODE 2 — CONFRONTATION

### Clash 1: Authority Monism vs Empirical Memory Realism

- Fundamental contradiction: Authority Monism wants any authority-adjacent labels minimized; Empirical Memory Realism wants rich labels that make behavior memory useful.
- Incompatible assumptions:
  - Authority Monism assumes labels are likely to become normative.
  - Empirical Memory Realism assumes labels can remain empirical if non-authority flags and refs are explicit.
- What Authority Monism explains better:
  - Why `activated` and `promote_decision_recorded` labels are dangerous if they appear without dereference to AK/governance truth.
- What Empirical Memory Realism explains better:
  - Why a shared Oracle that stores only neutral or winning evidence becomes weak and biased.
- Residual tension:
  - Labels are necessary, but authority-shaped labels must be mirror labels with required authority refs, not standalone Oracle truth.

### Clash 2: Artifact Provenance Purism vs Product-Loop Pragmatism

- Fundamental contradiction: Provenance Purism demands strict artifact/hash/idempotency contracts before shared writes; Product Pragmatism wants a usable path soon.
- Incompatible assumptions:
  - Provenance Purism assumes premature shared writes create durable corruption.
  - Product Pragmatism assumes too much delay creates manual workarounds.
- What Provenance Purism explains better:
  - Why local `coordinates.db` migration is a category error.
- What Product Pragmatism explains better:
  - Why the first implementation should be a preflight packet, not a complete shared publication system.
- Residual tension:
  - The bridge is a no-shared-write preflight command that is easy to run and hard to misread.

### Clash 3: Data Stewardship Skepticism vs Empirical Memory Realism

- Fundamental contradiction: Empirical Memory wants broad retained behavior evidence; Data Stewardship fears broad retention of sensitive traces.
- Incompatible assumptions:
  - Empirical Memory assumes more curated evidence improves Oracle.
  - Data Stewardship assumes every retained record has custody and leakage risk.
- What Data Stewardship explains better:
  - Why `redaction_status=checked` is not enough unless the RFC defines what checked means.
- What Empirical Memory explains better:
  - Why deleting failures by default destroys long-term intelligence.
- Residual tension:
  - Publication labels need a retention/redaction class. Negative evidence is valuable, but not all negative evidence is publishable.

### Clash 4: Authority Monism vs Product-Loop Pragmatism

- Fundamental contradiction: Authority Monism would rather slow publication than allow semantic drift; Product Pragmatism wants a smooth path that users will actually follow.
- Incompatible assumptions:
  - Authority Monism assumes accidental authority drift is the primary failure.
  - Product Pragmatism assumes bypass/ad-hoc sharing is the primary failure if the official path is too heavy.
- What Authority Monism explains better:
  - Why `program-loop --publish-to-shared retained` must not land before a standalone publish/preflight path is proven.
- What Product Pragmatism explains better:
  - Why the final UX should eventually integrate publication into the loop with visible opt-in.
- Residual tension:
  - The product path should be staged: preflight first, publish second, loop convenience last.

## MODE 3 — INTEGRATION OR DECISION

- Chosen path: Contextual Dominance.

- Result:
  - For authority truth, Authority Monism dominates: AK/governance must remain canonical and Oracle must store only empirical records plus opaque refs.
  - For behavior memory, Empirical Memory Realism dominates: shared Oracle must retain useful failures, near-misses, and rollbacks, not only winners.
  - For publication mechanics, Artifact Provenance Purism dominates: re-index canonical artifacts; never migrate local `coordinates.db` wholesale.
  - For first implementation, Product-Loop Pragmatism dominates only after Data Stewardship constraints are explicit: ship preflight first, no shared writes.
  - For safety, Data Stewardship dominates before ADR: the RFC must define redaction status, publisher responsibility, label classes, and retraction/retention posture more concretely.

- Why this path is justified:
  - No single school can dominate all contexts without breaking the system. Authority Monism alone would make Oracle too sterile. Empirical Memory alone risks data and authority drift. Pragmatism alone ships too early. Data Stewardship alone can freeze the product. The correct architecture is contextual: authority, memory, mechanics, data custody, and UX each have different controlling constraints.

- What remains unresolved:
  - Whether publication events are separate records or append-only events.
  - Which labels require an authority ref.
  - What exact redaction statuses are legal.
  - Who is allowed to publish to shared Oracle.
  - What deletion/retraction means for shared Oracle records and backups.

## PRACTICAL CONSEQUENCE

The RFC should not proceed to ADR yet. It has the right central direction, but it needs revision before acceptance.

Required RFC revisions:

1. Define legal `redaction_status` values and make `unknown` / missing fail closed for shared publication.
2. Define publisher identity / responsibility fields for shared publication preflight.
3. Split labels into classes:
   - empirical labels: `local_observed`, `retained`, `request_more_evidence`, `rejected`;
   - authority-mirror labels: `accepted_for_review`, `promote_decision_recorded`, `activated`, `rolled_back`.
4. Require an external authority ref for authority-mirror labels while stating Oracle only mirrors that ref.
5. Define minimal retention/retraction semantics, including the fact that backup deletion may be infra-governed and not instantaneous.
6. State Phase 1 as the only legal implementation slice: publication preflight packet, no shared writes.
7. Keep `program-loop` local by default and defer any `--publish-to-shared` convenience flag until standalone preflight and publish are proven.

## Review conclusion

Outcome: `revise_rfc`.

The RFC's core choice is strong: curated artifact re-indexing into shared Oracle empirical memory is better than local DB migration or authority duplication. But ADR acceptance should wait until the RFC closes the redaction, publisher responsibility, authority-mirror label, and retraction/retention gaps.
