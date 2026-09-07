---
summary: "AK-5511 residual runtime-graph HOLD repair, complete readback inventory, exact authorized auth repin and bounded proof."
read_when:
  - "Reviewing the corrected capsule after the second implementation HOLD."
---

# Runtime graph corrections — independent corrected SHIP pending

Exact task continuation: AK-5511, runtime-graph HOLD dispatch-1788781092681.
The controller explicitly authorized current-execution repin to AK-5512 review
source a893382e3a7abc06de0814f29709b9143b930826 (dispatch-1788781092679).
No task state, original evidence, target/fork source, live effects or push changed.

## Repro and correction

Before editing the verifier, both Espresso runtime() calls accepted zeroed trace
behavior-source hashes after trace locator, episode, receipt, replay and cache-key
rehashing. The new regression failed twice with DID NOT RAISE. After correction,
both direct checks and isolated full-capsule calls reject at runtime_trace_source,
with original subject and seven expected roots unchanged.

Audited the complete runtime readback validator and its identity/provider/trace/
Oracle helpers, the original GEPA result/materialization validators, and comparison
validators/loaders/reducers. The single protocol doc now carries a 25-row check
inventory with implementation, proof and explicit boundary differences. Additional
findings repaired: quality/status/summary joins, complete trace reconstruction,
Oracle source artifacts/input refs/identity/behavior/facets/text projections,
provider/receipt dependencies, GEPA base guards and exact metric-wrapper rendering,
generated-behavior redundant declarations, and comparison authority guards.

Four existing current pure modules are included in the fixed installation rather
than approximated: trace, source-record coverage, quality evaluation, metric wrapper
rendering. The Oracle pure builder copies have full function-AST differential tests.
The fixed capsule is now 16 modules, not 11; wire schemas/hash domains are unchanged.
The protocol's refreshed manifest/profile must be reviewed before consumer trust.
No generated script, optimizer pickle, historical module or model was executed by
the verifier. Historical effect flags remain assertions, not sandbox/authenticity.

## Repin

All eight module hashes and extra-file pins were collected from an owned clean
local detached clone of a893382e. Tree a4c4b050e2bace57586119d2e8ae9865511484d8;
version 0.1.6; lock d24ee392e2846b3baac33e16a67ff3e9094b3b021c67e32e50a1f1d11b077648.
The integration test repeats exact-clone source verification, consuming the local
object store rather than requiring mutable maintained HEAD to match. The two old
owner-tree assertions were updated, not suppressed. Historical 6c3473ca/80cc409/
777388a profile bytes are unchanged. Unknown non-strict observed jury models remain
None; requested model labels do not fill the observation gap.

## Proof and limits

- Focused closure/comparison suite: 248 passed; default frozen fixtures, no opt-in.
- Imported-vLLM optional audit: 13 passed.
- Final expanded slice: 908 passed in 197 seconds. Includes foundry, closure,
  comparison, Oracle backend, runtime episode/trace, GEPA candidate and quality tests.
- First expanded attempt timed out at 230 seconds and had the two stale tree
  assertions; it is not passing proof. Final selected suite reran completely.
- Final offline ci-quality and verify-fast passed, including full test typechecking,
  task-scope binding and hooks. Module hashes independently matched the protocol.
- Full offline heavy-job wrapper denied by retained-run process-reference preflight:
  eight protected same-UID processes; no bypass or unrelated scratch deletion.
- Reanchored local annotation-positive fixtures pass direct runtime validation but
  fail unchanged historical outer roots. Provider/receipt/base-GEPA tests are direct
  contract proofs, not substituted end-to-end claims.

Delta over 9e78cca2: net source +831 LOC, tests +556 LOC. Cumulative source growth
since the original repair baseline is +3872 LOC. Existing pure dependency inclusion
also expands the reviewed installation footprint without duplicating their code;
this is not a claim that the pending budget reconciliation is approved.

Current profile: e17c2ef0390b1c3783b477654c858672b4bd8c850b7014874ca9bf407ab7b7ea.
Entrypoint remains reviewed-python -I -S -B installed/program_foundry_closure_check.py.
Acceptance, historical authority and provider-output authentication remain unknown;
review_eligible remains false. Full-gate proof and independent corrected SHIP are
not established by these local results. No untrusted report enabling or lifecycle
completion was performed.
